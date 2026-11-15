// The in-game overlay menu (Dear ImGui on the Vulkan backend; input fed from SDL events). Its shape follows LAS
// Recomp's runtime/ui/menu.mm (MIT, THIRD_PARTY_NOTICES.md): the event queue between threads, the overlay command
// buffer hand-off, the style. Its pages are this game's.
//
// Threads: SDL events arrive on the window thread (device.c ui_run -> menu_handle_event) and are queued; the menu is
// laid out and drawn on the render thread inside the present (device.c -> menu_render), after the game image.
//
// Open / close: F1, or Minus + Plus held together on a gamepad (or its Home button); Esc or B also close it. While it
// is open the game sees no input (runtime/ui/input.c publish: menu_input_captured).
#include <SDL3/SDL.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <atomic>
#include <vector>

#include "imgui.h"
#include "imgui_impl_vulkan.h"

extern "C" {
#include "../rt.h"
#include "../settings.h"
#include "menu.h"
bool vk_imgui_backend_init(void);  // runtime/ui/imgui_glue.cpp
// runtime/nvn/vulkan/device.c: the command buffer ImGui records into (a secondary one the recorder thread executes in
// the window image's commands, or that buffer itself after the recorder caught up), then handed back
void *vk_overlay_begin(void *window_cmd);
void vk_overlay_end(void *window_cmd, void *cmd);
const char *hm_version(void);  // runtime/main.c
// runtime/ui/input.c
void input_reset(void);
int input_button_count(void);
const char *input_button_id(int b);
void input_binding_text(int b, bool pad, char *out, size_t cap);
void input_bind_set(int b, bool pad, int code);
void input_bindings_reset(void);
int input_bind_code(const SDL_Event *e, bool pad);
#include "game_font.h"
}

// ------------------------------------------------------------------ state shared with the window thread
static std::atomic<bool> g_open{false};
static std::atomic<int> g_capture{-1};  // Controls tab waiting for a press: button * 2 + (1: gamepad), else -1
static std::atomic<bool> g_want_fullscreen{false};
static std::atomic<int> g_tab_request{-1};
static std::atomic<int> g_open_count{0};  // (each opening: the menu window takes the focus again)

struct QEvent {
    enum { KEY, ANALOG, MOUSE_POS, MOUSE_BUTTON, WHEEL } kind;
    ImGuiKey key;
    bool down;
    float value, x, y;
    int button;
};
static pthread_mutex_t q_lock = PTHREAD_MUTEX_INITIALIZER;
static std::vector<QEvent> q_events;
static std::atomic<float> g_pixel_density{1.0f};

static void push(const QEvent &e) {
    pthread_mutex_lock(&q_lock);
    q_events.push_back(e);
    pthread_mutex_unlock(&q_lock);
}
static void push_key(ImGuiKey k, bool down) {
    QEvent q = {};
    q.kind = QEvent::KEY, q.key = k, q.down = down;
    push(q);
}

bool menu_input_captured(void) { return g_open.load(); }

static void set_open(bool open) {
    if (open == g_open.load()) return;
    g_open.store(open);
    if (open) g_open_count++;
    g_capture = -1;
    input_reset();  // nothing held while the menu had focus leaks into the game, nor the press that opened it
    LOG("[menu] %s\n", open ? "opened" : "closed");
    if (!open && !settings_save()) LOG("[menu] saving hylian-melodies.ini failed\n");
}

// HM_MENU_AT=<frame> (device.c) opens it for screenshot tests; HM_MENU_TAB=<n> picks the page (0 Video .. 3 About)
void menu_test_open(void) {
    if (const char *t = getenv("HM_MENU_TAB")) g_tab_request = atoi(t);
    set_open(true);
}

static ImGuiKey key_from_scancode(SDL_Scancode sc) {
    switch (sc) {
    case SDL_SCANCODE_UP: case SDL_SCANCODE_W: return ImGuiKey_UpArrow;
    case SDL_SCANCODE_DOWN: case SDL_SCANCODE_S: return ImGuiKey_DownArrow;
    case SDL_SCANCODE_LEFT: case SDL_SCANCODE_A: return ImGuiKey_LeftArrow;
    case SDL_SCANCODE_RIGHT: case SDL_SCANCODE_D: return ImGuiKey_RightArrow;
    case SDL_SCANCODE_RETURN: case SDL_SCANCODE_X: return ImGuiKey_Enter;
    case SDL_SCANCODE_KP_ENTER: return ImGuiKey_KeypadEnter;
    case SDL_SCANCODE_SPACE: return ImGuiKey_Space;
    case SDL_SCANCODE_TAB: return ImGuiKey_Tab;
    case SDL_SCANCODE_LSHIFT: return ImGuiKey_LeftShift;
    case SDL_SCANCODE_RSHIFT: return ImGuiKey_RightShift;
    case SDL_SCANCODE_LCTRL: return ImGuiKey_LeftCtrl;
    case SDL_SCANCODE_RCTRL: return ImGuiKey_RightCtrl;
    case SDL_SCANCODE_Q: return ImGuiKey_Q;  // previous page (as the game's L)
    case SDL_SCANCODE_E: return ImGuiKey_E;  // next page (R)
    case SDL_SCANCODE_Z: case SDL_SCANCODE_BACKSPACE: return ImGuiKey_Backspace;  // back (as the game's B)
    default: return ImGuiKey_None;
    }
}

// Gamepad buttons by position, as in the game: the right face button confirms (ImGui's FaceDown "activate"), the
// bottom one goes back (FaceRight "cancel"), the shoulders change page.
static ImGuiKey key_from_pad(Uint8 b) {
    switch (b) {
    case SDL_GAMEPAD_BUTTON_EAST: return ImGuiKey_GamepadFaceDown;
    case SDL_GAMEPAD_BUTTON_SOUTH: return ImGuiKey_GamepadFaceRight;
    case SDL_GAMEPAD_BUTTON_NORTH: return ImGuiKey_GamepadFaceUp;
    case SDL_GAMEPAD_BUTTON_WEST: return ImGuiKey_GamepadFaceLeft;
    case SDL_GAMEPAD_BUTTON_DPAD_UP: return ImGuiKey_GamepadDpadUp;
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN: return ImGuiKey_GamepadDpadDown;
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT: return ImGuiKey_GamepadDpadLeft;
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT: return ImGuiKey_GamepadDpadRight;
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return ImGuiKey_GamepadL1;
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return ImGuiKey_GamepadR1;
    default: return ImGuiKey_None;
    }
}

// The Controls tab waiting for a press: it takes the next key (keyboard column) or gamepad button / trigger (gamepad
// column). Esc or the gamepad's Home cancels; the menu's own keys can't be bound.
static bool capture_event(const SDL_Event *e) {
    int c = g_capture.load();
    if (c < 0) return false;
    bool pad = c & 1;
    if ((e->type == SDL_EVENT_KEY_DOWN && (e->key.scancode == SDL_SCANCODE_ESCAPE || e->key.scancode == SDL_SCANCODE_F1)) ||
        (e->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN && e->gbutton.button == SDL_GAMEPAD_BUTTON_GUIDE)) {
        g_capture = -1;
        return true;
    }
    int code = input_bind_code(e, pad);
    if (code == SDL_SCANCODE_F11 && !pad) code = -1;
    if (code >= 0) {
        input_bind_set(c >> 1, pad, code);
        g_capture = -1;
        return true;
    }
    // (everything else of the kind being bound is swallowed, so the press doesn't also move the menu's cursor)
    switch (e->type) {
    case SDL_EVENT_KEY_DOWN: case SDL_EVENT_KEY_UP: return !pad;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN: case SDL_EVENT_GAMEPAD_BUTTON_UP: case SDL_EVENT_GAMEPAD_AXIS_MOTION: return pad;
    default: return false;
    }
}

bool menu_handle_event(const SDL_Event *e) {
    static bool minus_down, plus_down;
    if (g_open.load() && capture_event(e)) return true;
    switch (e->type) {
    case SDL_EVENT_KEY_DOWN:
        if (!e->key.repeat && e->key.scancode == SDL_SCANCODE_F1) { set_open(!g_open.load()); return true; }
        if (g_open.load() && !e->key.repeat && e->key.scancode == SDL_SCANCODE_ESCAPE) { set_open(false); return true; }
        if (e->key.scancode == SDL_SCANCODE_F11 || (e->key.scancode == SDL_SCANCODE_RETURN && (e->key.mod & SDL_KMOD_ALT)))
            return false;  // (fullscreen toggle: input.c, menu open or not)
        /* fallthrough */
    case SDL_EVENT_KEY_UP: {
        if (!g_open.load()) return false;
        ImGuiKey k = key_from_scancode(e->key.scancode);
        if (k != ImGuiKey_None) push_key(k, e->type == SDL_EVENT_KEY_DOWN);
        return true;
    }
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN: case SDL_EVENT_GAMEPAD_BUTTON_UP: {
        bool down = e->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN;
        if (e->gbutton.button == SDL_GAMEPAD_BUTTON_BACK) minus_down = down;
        if (e->gbutton.button == SDL_GAMEPAD_BUTTON_START) plus_down = down;
        if (down && ((minus_down && plus_down) || e->gbutton.button == SDL_GAMEPAD_BUTTON_GUIDE)) {
            set_open(!g_open.load());
            return true;
        }
        if (!g_open.load()) return false;
        ImGuiKey k = key_from_pad(e->gbutton.button);
        if (k != ImGuiKey_None) push_key(k, down);
        return true;
    }
    case SDL_EVENT_GAMEPAD_AXIS_MOTION: {
        if (!g_open.load()) return false;
        float v = e->gaxis.value / 32767.0f;
        QEvent q = {};
        q.kind = QEvent::ANALOG;
        if (e->gaxis.axis == SDL_GAMEPAD_AXIS_LEFTX) {
            q.key = ImGuiKey_GamepadLStickLeft, q.value = v < -0.3f ? -v : 0, push(q);
            q.key = ImGuiKey_GamepadLStickRight, q.value = v > 0.3f ? v : 0, push(q);
        } else if (e->gaxis.axis == SDL_GAMEPAD_AXIS_LEFTY) {
            q.key = ImGuiKey_GamepadLStickUp, q.value = v < -0.3f ? -v : 0, push(q);
            q.key = ImGuiKey_GamepadLStickDown, q.value = v > 0.3f ? v : 0, push(q);
        }
        return true;
    }
    case SDL_EVENT_MOUSE_MOTION:
        if (!g_open.load()) return false;
        {
            QEvent q = {};
            q.kind = QEvent::MOUSE_POS, q.x = e->motion.x * g_pixel_density, q.y = e->motion.y * g_pixel_density;
            push(q);
        }
        return true;
    case SDL_EVENT_MOUSE_BUTTON_DOWN: case SDL_EVENT_MOUSE_BUTTON_UP:
        if (!g_open.load()) return false;
        {
            QEvent q = {};
            q.kind = QEvent::MOUSE_BUTTON;
            q.button = e->button.button == SDL_BUTTON_LEFT ? 0 : e->button.button == SDL_BUTTON_RIGHT ? 1 : 2;
            q.down = e->type == SDL_EVENT_MOUSE_BUTTON_DOWN;
            push(q);
        }
        return true;
    case SDL_EVENT_MOUSE_WHEEL:
        if (!g_open.load()) return false;
        {
            QEvent q = {};
            q.kind = QEvent::WHEEL, q.x = e->wheel.x, q.y = e->wheel.y;
            push(q);
        }
        return true;
    default:
        return false;
    }
}

void menu_apply_window_requests(SDL_Window *w) {
    g_pixel_density = SDL_GetWindowPixelDensity(w);
    if (g_want_fullscreen.exchange(false)) SDL_SetWindowFullscreen(w, g_settings.fullscreen);
    static bool fps_was;
    if (fps_was && !g_settings.show_fps) SDL_SetWindowTitle(w, "Hylian Melodies");  // (the FPS left in the title)
    fps_was = g_settings.show_fps;
    if (g_open.load()) SDL_ShowCursor();
}

// ------------------------------------------------------------------ render thread
static bool g_inited, g_init_failed;
static ImGuiContext *g_ctx;
static ImFont *g_font, *g_font_big;
static bool g_game_font;  // the game's own display face, not a system font
static float g_head_scale = 1;  // the heading: g_font_big, this much larger (the game's face: one font, drawn larger)

static void style_init(void) {
    ImGuiStyle &s = ImGui::GetStyle();
    ImGui::StyleColorsDark();
    s.WindowRounding = 14, s.FrameRounding = 8, s.GrabRounding = 8, s.TabRounding = 8, s.ChildRounding = 10;
    s.WindowPadding = ImVec2(28, 24), s.FramePadding = ImVec2(14, 8), s.ItemSpacing = ImVec2(14, 12);
    s.WindowBorderSize = 0, s.ScrollbarSize = 18;
    ImVec4 *c = s.Colors;
    ImVec4 gold(0.93f, 0.76f, 0.33f, 1), gold_dim(0.62f, 0.49f, 0.20f, 1), green(0.15f, 0.36f, 0.25f, 1);
    c[ImGuiCol_WindowBg] = ImVec4(0.06f, 0.09f, 0.08f, 0.94f);
    c[ImGuiCol_ChildBg] = ImVec4(0.09f, 0.13f, 0.11f, 0.85f);
    c[ImGuiCol_PopupBg] = ImVec4(0.07f, 0.10f, 0.09f, 0.98f);
    c[ImGuiCol_Text] = ImVec4(0.96f, 0.94f, 0.88f, 1);
    c[ImGuiCol_TextDisabled] = ImVec4(0.62f, 0.64f, 0.58f, 1);
    c[ImGuiCol_FrameBg] = ImVec4(0.13f, 0.19f, 0.16f, 1);
    c[ImGuiCol_FrameBgHovered] = green;
    c[ImGuiCol_FrameBgActive] = ImVec4(0.19f, 0.45f, 0.31f, 1);
    c[ImGuiCol_Button] = ImVec4(0.14f, 0.22f, 0.18f, 1);
    c[ImGuiCol_ButtonHovered] = green;
    c[ImGuiCol_ButtonActive] = ImVec4(0.21f, 0.50f, 0.34f, 1);
    c[ImGuiCol_Header] = green;
    c[ImGuiCol_HeaderHovered] = ImVec4(0.19f, 0.45f, 0.31f, 1);
    c[ImGuiCol_HeaderActive] = ImVec4(0.21f, 0.50f, 0.34f, 1);
    c[ImGuiCol_Tab] = ImVec4(0.12f, 0.18f, 0.15f, 1);
    c[ImGuiCol_TabHovered] = green;
    c[ImGuiCol_TabSelected] = ImVec4(0.21f, 0.44f, 0.31f, 1);
    c[ImGuiCol_TabSelectedOverline] = gold;
    c[ImGuiCol_CheckMark] = gold;
    c[ImGuiCol_SliderGrab] = gold_dim;
    c[ImGuiCol_SliderGrabActive] = gold;
    c[ImGuiCol_NavCursor] = gold;
    c[ImGuiCol_Separator] = ImVec4(0.30f, 0.36f, 0.30f, 1);
    c[ImGuiCol_TableBorderLight] = ImVec4(0.20f, 0.26f, 0.22f, 1);
    c[ImGuiCol_TableRowBgAlt] = ImVec4(1, 1, 1, 0.03f);
}

// A sans-serif font of the system's (fontconfig's choice, else the usual places), else ImGui's built-in one.
static bool font_file(char *out, size_t cap) {
    if (FILE *p = popen("fc-match -f '%{file}' 'sans-serif:style=Regular' 2>/dev/null", "r")) {
        size_t n = fread(out, 1, cap - 1, p);
        out[n] = 0;
        pclose(p);
        if (n && access(out, R_OK) == 0) return true;
    }
    static const char *const paths[] = {"/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/noto/NotoSans-Regular.ttf",
                                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"};
    for (const char *f : paths)
        if (access(f, R_OK) == 0) { snprintf(out, cap, "%s", f); return true; }
    return false;
}

// The game's own display face from the player's RomFS (runtime/ui/game_font.c): its largest serif font (42-pixel
// line, small capitals for lowercase), smooth-edged, for all the menu's text: scaled to the window with filtering, the
// heading drawn larger. Each glyph goes into ImGui's atlas as a custom rectangle on a font of that line height (ImGui's
// built-in font underneath, reduced to the space character). HM_MENU_FONT=system keeps the system font.
struct GlyphRect { int rect; GameFont *f; int index, width; };
static std::vector<GlyphRect> g_rects;

static ImFont *add_game_font(ImGuiIO &io, GameFont *f) {
    static const ImWchar only_space[] = {0x20, 0x20, 0};
    ImFontConfig cfg;
    cfg.SizePixels = (float)game_font_line(f);
    cfg.GlyphRanges = only_space;
    cfg.PixelSnapH = true;
    snprintf(cfg.Name, sizeof cfg.Name, "game %dpx", game_font_line(f));
    ImFont *font = io.Fonts->AddFontDefault(&cfg);
    const GameGlyph *g;
    int n = game_font_glyphs(f, &g), h = game_font_cell_height(f);
    for (int i = 0; i < n; i++) {
        int w = g[i].width ? g[i].width : 1;
        int r = io.Fonts->AddCustomRectFontGlyph(font, (ImWchar)g[i].code, w, h, (float)g[i].advance, ImVec2((float)g[i].left, 0));
        g_rects.push_back({r, f, g[i].index, g[i].width});
    }
    return font;
}

static bool game_fonts(ImGuiIO &io) {
    const char *want = getenv("HM_MENU_FONT");
    if (want && !strcmp(want, "system")) return false;
    GameFont *face = game_font_pick(g_romfs_dir ? g_romfs_dir : "romfs", 42, NULL);
    if (!face) return false;
    g_font = g_font_big = add_game_font(io, face);
    if (!io.Fonts->Build()) {
        LOG("[menu] the game's font didn't fit ImGui's atlas\n");
        g_rects.clear();
        game_font_free(face);
        return false;
    }
    unsigned char *px;
    int tw, th;
    io.Fonts->GetTexDataAsAlpha8(&px, &tw, &th);
    for (const GlyphRect &gr : g_rects) {
        const ImFontAtlasCustomRect *r = io.Fonts->GetCustomRectByIndex(gr.rect);
        int pitch;
        const uint8_t *cell = game_font_cell(gr.f, gr.index, &pitch);
        if (!cell || !r->IsPacked()) continue;
        for (int y = 0; y < r->Height; y++)
            for (int x = 0; x < gr.width && x < r->Width; x++) px[(size_t)(r->Y + y) * tw + r->X + x] = cell[(size_t)y * pitch + x];
    }
    LOG("[menu] the game's font: %dpx line; atlas %dx%d\n", game_font_line(face), tw, th);
    g_rects.clear();
    game_font_free(face);
    g_head_scale = 1.5f;
    g_game_font = true;
    return true;
}

static bool init(void) {
    IMGUI_CHECKVERSION();
    g_ctx = ImGui::CreateContext();
    ImGui::SetCurrentContext(g_ctx);
    ImGuiIO &io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
    io.IniFilename = NULL;
    io.LogFilename = NULL;
    style_init();
    char path[PATH_MAX];
    ImFontConfig cfg;
    cfg.OversampleH = 2;
    if (game_fonts(io)) {
    } else if (io.Fonts->Clear(), g_font = g_font_big = NULL, font_file(path, sizeof path)) {
        g_font = io.Fonts->AddFontFromFileTTF(path, 34, &cfg);
        g_font_big = io.Fonts->AddFontFromFileTTF(path, 56, &cfg);
        LOG("[menu] font %s\n", path);
    }
    if (!g_font || !g_font_big) {
        ImFontConfig d;
        d.SizePixels = 26;
        g_font = g_font_big = io.Fonts->AddFontDefault(&d);
        LOG("[menu] no system font found: ImGui's own\n");
    }
    return vk_imgui_backend_init();
}

static void drain_events(ImGuiIO &io) {
    pthread_mutex_lock(&q_lock);
    std::vector<QEvent> ev;
    ev.swap(q_events);
    pthread_mutex_unlock(&q_lock);
    for (const QEvent &q : ev) {
        switch (q.kind) {
        case QEvent::KEY: io.AddKeyEvent(q.key, q.down); break;
        case QEvent::ANALOG: io.AddKeyAnalogEvent(q.key, q.value > 0.1f, q.value); break;
        case QEvent::MOUSE_POS: io.AddMousePosEvent(q.x, q.y); break;
        case QEvent::MOUSE_BUTTON: io.AddMouseButtonEvent(q.button, q.down); break;
        case QEvent::WHEEL: io.AddMouseWheelEvent(q.x, q.y); break;
        }
    }
}

// ---- pages
static void note(const char *text) {
    ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyle().Colors[ImGuiCol_TextDisabled]);
    ImGui::TextWrapped("%s", text);
    ImGui::PopStyleColor();
}

static void page_video(void) {
    bool fs = g_settings.fullscreen;
    if (ImGui::Checkbox("Fullscreen", &fs)) {
        g_settings.fullscreen = fs;
        settings_changed(SET_FULLSCREEN);
        g_want_fullscreen = true;
    }
    note("Borderless, at the desktop's resolution. F11 or Alt+Enter also switch.");
    ImGui::Spacing();

    static const char *const filters[] = {"Sharp pixels (recommended)", "Smooth", "Nearest"};
    static int shown_filter = -1;  // (what this run draws with: the filter is built into the present shader)
    if (shown_filter < 0) shown_filter = g_settings.upscale_filter;
    int f = g_settings.upscale_filter;
    if (f < 0 || f > 2) f = 0;
    ImGui::SetNextItemWidth(ImGui::CalcTextSize(filters[0]).x + ImGui::GetFrameHeight() + ImGui::GetStyle().FramePadding.x * 2);
    if (ImGui::Combo("Scaling filter", &f, filters, 3)) {
        g_settings.upscale_filter = f;
        settings_changed(SET_UPSCALE_FILTER);
    }
    note(g_settings.upscale_filter != shown_filter ? "Takes effect at the next start."
                                                   : "How the game's 1280x720 image is scaled to the window.");
    ImGui::Spacing();

    bool fps = g_settings.show_fps;
    if (ImGui::Checkbox("Show frames per second in the window title", &fps)) {
        g_settings.show_fps = fps;
        settings_changed(SET_SHOW_FPS);
    }
    bool pace = g_settings.frame_pacing;
    if (ImGui::Checkbox("Frame pacing", &pace)) {
        g_settings.frame_pacing = pace;
        settings_changed(SET_FRAME_PACING);
    }
    note("A steady 60 Hz, like the Switch's display (recommended). Off: the game's own limiter, about 61 fps.");
}

static void page_audio(void) {
    float v = (float)(g_settings.volume * 100.0);
    ImGui::SetNextItemWidth(ImGui::GetFontSize() * 14);
    if (ImGui::SliderFloat("Volume", &v, 0.0f, 100.0f, "%.0f%%", ImGuiSliderFlags_AlwaysClamp)) {
        g_settings.volume = roundf(v) / 100.0;
        settings_changed(SET_VOLUME);
    }
    note("The game's own options also have music and sound levels and the rhythm calibration.");
}

static void page_controls(void) {
    static const char *const names[] = {"A", "B", "X", "Y", "Left stick click", "Right stick click", "L", "R", "ZL", "ZR",
                                        "+ (Plus)", "- (Minus)", "D-pad left", "D-pad up", "D-pad right", "D-pad down"};
    int n = input_button_count();
    int cap = g_capture.load();
    note(cap >= 0 ? (cap & 1 ? "Press a gamepad button or trigger for it (Home cancels)."
                             : "Press a key for it (Esc cancels).")
                  : "Choose a binding to change it. Gamepad buttons are named by position.");
    if (ImGui::BeginTable("##binds", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH | ImGuiTableFlags_ScrollY,
                          ImVec2(0, ImGui::GetContentRegionAvail().y - ImGui::GetFrameHeightWithSpacing() * 1.3f))) {
        ImGui::TableSetupScrollFreeze(0, 1);
        ImGui::TableSetupColumn("Switch", ImGuiTableColumnFlags_WidthStretch, 0.8f);
        ImGui::TableSetupColumn("Keyboard", ImGuiTableColumnFlags_WidthStretch, 1.1f);
        ImGui::TableSetupColumn("Gamepad", ImGuiTableColumnFlags_WidthStretch, 1.1f);
        ImGui::TableHeadersRow();
        for (int b = 0; b < n; b++) {
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::AlignTextToFramePadding();
            ImGui::TextUnformatted(b < (int)(sizeof names / sizeof names[0]) ? names[b] : input_button_id(b));
            for (int side = 0; side < 2; side++) {
                ImGui::TableNextColumn();
                char text[160], label[200];
                if (cap == b * 2 + side) snprintf(text, sizeof text, "...");
                else input_binding_text(b, side, text, sizeof text);
                snprintf(label, sizeof label, "%s##%d_%d", text, b, side);
                if (ImGui::Button(label, ImVec2(-FLT_MIN, 0))) g_capture = b * 2 + side;
            }
        }
        ImGui::EndTable();
    }
    if (ImGui::Button("Reset all to defaults")) {
        g_capture = -1;
        input_bindings_reset();
    }
}

static void page_about(void) {
    ImGui::Text("Hylian Melodies %s", hm_version());
    note("A native Linux build of your own copy of Cadence of Hyrule, made by static recompilation. Personal use only.");
    ImGui::Spacing();
    char cwd[PATH_MAX];
    if (getcwd(cwd, sizeof cwd)) {
        ImGui::TextUnformatted("Settings and saves");
        note(cwd);
    }
    ImGui::Spacing();
    ImGui::TextUnformatted("Menu");
    note("F1, or Minus + Plus together on a gamepad, opens and closes this menu. Esc or B closes it; L / R or Q / E "
         "change page. Changes are saved when it closes.");
}

// ---- the window
static int g_tab;

static void draw_menu(ImGuiIO &io, float scale) {
    ImGui::GetBackgroundDrawList()->AddRectFilled(ImVec2(0, 0), io.DisplaySize, IM_COL32(0, 0, 0, 120));
    float w = fminf(io.DisplaySize.x * 0.9f, 1400 * scale), h = io.DisplaySize.y - 2 * 24 * scale;
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(w, h), ImGuiCond_Always);
    ImGui::Begin("##menu", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings);
    static int focused_for = -1;
    if (focused_for != g_open_count.load()) ImGui::SetWindowFocus(), focused_for = g_open_count.load();

    ImGui::PushFont(g_font_big);
    ImGui::SetWindowFontScale(g_head_scale);
    ImGui::TextColored(ImVec4(0.93f, 0.76f, 0.33f, 1), "Settings");
    ImGui::SetWindowFontScale(1);
    ImGui::PopFont();

    static const char *const tabs[] = {"Video", "Audio", "Controls", "About"};
    const int ntabs = 4;
    int req = g_tab_request.exchange(-1);
    bool capturing = g_capture.load() >= 0;
    if (!capturing && (ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) || ImGui::IsKeyPressed(ImGuiKey_Q, false)))
        req = (g_tab + ntabs - 1) % ntabs;
    if (!capturing && (ImGui::IsKeyPressed(ImGuiKey_GamepadR1, false) || ImGui::IsKeyPressed(ImGuiKey_E, false)))
        req = (g_tab + 1) % ntabs;
    if (ImGui::BeginTabBar("##tabs", ImGuiTabBarFlags_NoTabListScrollingButtons)) {
        for (int i = 0; i < ntabs; i++) {
            ImGuiTabItemFlags fl = req == i ? ImGuiTabItemFlags_SetSelected : 0;
            if (ImGui::BeginTabItem(tabs[i], NULL, fl)) {
                g_tab = i;
                ImGui::Spacing();
                ImGui::BeginChild("##page", ImVec2(0, 0), ImGuiChildFlags_NavFlattened);
                switch (i) {
                case 0: page_video(); break;
                case 1: page_audio(); break;
                case 2: page_controls(); break;
                case 3: page_about(); break;
                }
                ImGui::EndChild();
                ImGui::EndTabItem();
            }
        }
        ImGui::EndTabBar();
    }
    // B (gamepad), Z / Backspace close it (Esc: menu_handle_event)
    if (!capturing && (ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false) || ImGui::IsKeyPressed(ImGuiKey_Backspace, false)))
        set_open(false);
    ImGui::End();
}

void menu_render(void *cmd, unsigned target_w, unsigned target_h) {
    if (!g_open.load() || g_init_failed) {
        if (g_inited) {
            pthread_mutex_lock(&q_lock);
            q_events.clear();
            pthread_mutex_unlock(&q_lock);
        }
        return;
    }
    if (!g_inited) {
        g_inited = true;
        if (!init()) {
            g_init_failed = true;
            set_open(false);
            return;
        }
    }
    ImGui::SetCurrentContext(g_ctx);
    ImGuiIO &io = ImGui::GetIO();
    io.DisplaySize = ImVec2((float)target_w, (float)target_h);
    io.DisplayFramebufferScale = ImVec2(1, 1);
    static double last;
    double now = SDL_GetTicks() / 1000.0;
    io.DeltaTime = last > 0 && now > last ? (float)(now - last) : 1.0f / 60;
    last = now;
    drain_events(io);
    // fonts are built for a ~1080 px tall output; sizes and spacing follow the window
    float scale = fmaxf((float)target_h / 1080.0f, 0.45f);
    // (the game's face has a 42-pixel line: about the system font's 34 pixels at 1080p)
    io.FontGlobalScale = g_game_font ? scale * 34.0f / 42.0f : scale;
    static ImGuiStyle base;
    static float style_scale = -1;
    if (style_scale < 0) base = ImGui::GetStyle();
    if (fabsf(style_scale - scale) > 0.01f) {
        ImGui::GetStyle() = base;
        ImGui::GetStyle().ScaleAllSizes(scale);
        style_scale = scale;
    }
    ImGui_ImplVulkan_NewFrame();
    ImGui::NewFrame();
    ImGui::PushFont(g_font);
    draw_menu(io, scale);
    ImGui::PopFont();
    ImGui::Render();
    // ImGui records its commands itself: into a secondary command buffer of device.c's that the recorder thread executes
    // in the window image's commands (or into cmd directly once the recorder caught up; device.c vk_overlay_begin)
    void *oc = vk_overlay_begin(cmd);
    ImGui_ImplVulkan_RenderDrawData(ImGui::GetDrawData(), (VkCommandBuffer)oc);
    vk_overlay_end(cmd, oc);
}
