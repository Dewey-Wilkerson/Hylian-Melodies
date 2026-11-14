// Controllers and keyboard (SDL3) -> the game's player-1 controller (runtime/hle/input.c reads g_input_buttons and
// g_input_sticks whenever the game polls, so a press is seen at the game's next poll: no queue, no frame of delay).
// Events arrive on the window thread (runtime/nvn/vulkan/device.c ui_run); the state is kept in atomics.
//
// Bindings (docs/controls.md): defaults below; hylian-melodies.ini can change them with lines
//   key.<button> = <SDL key name>[, <SDL key name>...]     e.g. key.a = X, Return
//   pad.<button> = <SDL gamepad button>[, ...]             e.g. pad.a = south
// <button>: a b x y l r zl zr plus minus up down left right lstick rstick.
// HM_INPUT_SCRIPT=<frame>:<button>[+<button>...][/<frames>],... presses buttons at presented frames (test runs).
#include <SDL3/SDL.h>
#include <ctype.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../rt.h"
#include "../rumble.h"
#include "../settings.h"
#include "menu.h"

extern volatile uint64_t g_input_buttons;  // runtime/hle/input.c
extern volatile int32_t g_input_sticks[4];

enum { B_A, B_B, B_X, B_Y, B_LSTICK, B_RSTICK, B_L, B_R, B_ZL, B_ZR, B_PLUS, B_MINUS, B_LEFT, B_UP, B_RIGHT, B_DOWN, NB };
static const char *const bnames[NB] = {"a", "b", "x", "y", "lstick", "rstick", "l", "r", "zl", "zr", "plus", "minus",
                                       "left", "up", "right", "down"};

#define MAXB 4
static SDL_Scancode keymap[NB][MAXB];
static int padmap[NB][MAXB];  // SDL_GamepadButton, or 100 + axis for the triggers
// (the maps are read on the window thread and changed by the menu's Controls tab on the render thread)
static pthread_mutex_t map_lock = PTHREAD_MUTEX_INITIALIZER;

static void defaults(void) {
    for (int b = 0; b < NB; b++)
        for (int i = 0; i < MAXB; i++) keymap[b][i] = SDL_SCANCODE_UNKNOWN, padmap[b][i] = -1;
    // keyboard: arrows move (the d-pad), the rest grouped under the left hand and the right hand
    static const struct { int b; SDL_Scancode k[2]; } kd[] = {
        {B_UP, {SDL_SCANCODE_UP, SDL_SCANCODE_W}},          {B_DOWN, {SDL_SCANCODE_DOWN, SDL_SCANCODE_S}},
        {B_LEFT, {SDL_SCANCODE_LEFT, SDL_SCANCODE_A}},      {B_RIGHT, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_D}},
        {B_A, {SDL_SCANCODE_X, SDL_SCANCODE_RETURN}},       {B_B, {SDL_SCANCODE_Z, SDL_SCANCODE_BACKSPACE}},
        {B_X, {SDL_SCANCODE_C, 0}},                         {B_Y, {SDL_SCANCODE_V, 0}},
        {B_L, {SDL_SCANCODE_Q, 0}},                         {B_R, {SDL_SCANCODE_E, 0}},
        {B_ZL, {SDL_SCANCODE_1, 0}},                        {B_ZR, {SDL_SCANCODE_3, 0}},
        {B_PLUS, {SDL_SCANCODE_ESCAPE, 0}},                 {B_MINUS, {SDL_SCANCODE_TAB, 0}},
        {B_LSTICK, {SDL_SCANCODE_F, 0}},                    {B_RSTICK, {SDL_SCANCODE_G, 0}},
    };
    for (unsigned i = 0; i < sizeof kd / sizeof kd[0]; i++)
        for (int j = 0; j < 2; j++) keymap[kd[i].b][j] = kd[i].k[j];
    // gamepad: by position, as on the Switch (A on the right, B at the bottom, X at the top, Y on the left)
    static const struct { int b, p; } pd[] = {
        {B_A, SDL_GAMEPAD_BUTTON_EAST},           {B_B, SDL_GAMEPAD_BUTTON_SOUTH},
        {B_X, SDL_GAMEPAD_BUTTON_NORTH},          {B_Y, SDL_GAMEPAD_BUTTON_WEST},
        {B_L, SDL_GAMEPAD_BUTTON_LEFT_SHOULDER},  {B_R, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER},
        {B_ZL, 100 + SDL_GAMEPAD_AXIS_LEFT_TRIGGER}, {B_ZR, 100 + SDL_GAMEPAD_AXIS_RIGHT_TRIGGER},
        {B_PLUS, SDL_GAMEPAD_BUTTON_START},       {B_MINUS, SDL_GAMEPAD_BUTTON_BACK},
        {B_LSTICK, SDL_GAMEPAD_BUTTON_LEFT_STICK}, {B_RSTICK, SDL_GAMEPAD_BUTTON_RIGHT_STICK},
        {B_UP, SDL_GAMEPAD_BUTTON_DPAD_UP},       {B_DOWN, SDL_GAMEPAD_BUTTON_DPAD_DOWN},
        {B_LEFT, SDL_GAMEPAD_BUTTON_DPAD_LEFT},   {B_RIGHT, SDL_GAMEPAD_BUTTON_DPAD_RIGHT},
    };
    for (unsigned i = 0; i < sizeof pd / sizeof pd[0]; i++) padmap[pd[i].b][0] = pd[i].p;
}

// Gamepad button names in the ini: SDL's ("a" = the bottom face button, "start", "dpup", "lefttrigger"...) and the
// face buttons by position (south east west north), which this SDL doesn't take. Returns a padmap code or -1.
static const char *const face_names[4] = {"south", "east", "west", "north"};  // (SDL_GAMEPAD_BUTTON_SOUTH..NORTH)
static int pad_code_of(const char *t) {
    for (int i = 0; i < 4; i++) if (!SDL_strcasecmp(t, face_names[i])) return SDL_GAMEPAD_BUTTON_SOUTH + i;
    int p = SDL_GetGamepadButtonFromString(t);
    if (p != SDL_GAMEPAD_BUTTON_INVALID) return p;
    SDL_GamepadAxis ax = SDL_GetGamepadAxisFromString(t);
    if (ax == SDL_GAMEPAD_AXIS_LEFT_TRIGGER || ax == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) return 100 + ax;
    return -1;
}
static const char *pad_code_name(int p) {  // (the ini's name; pad_code_of reads it back)
    if (p >= SDL_GAMEPAD_BUTTON_SOUTH && p <= SDL_GAMEPAD_BUTTON_NORTH) return face_names[p - SDL_GAMEPAD_BUTTON_SOUTH];
    if (p >= 100) return SDL_GetGamepadStringForAxis((SDL_GamepadAxis)(p - 100));
    const char *n = SDL_GetGamepadStringForButton((SDL_GamepadButton)p);
    return n ? n : "?";
}

static int button_of(const char *n) {
    for (int b = 0; b < NB; b++) if (!strcmp(n, bnames[b])) return b;
    return -1;
}

static char *trim(char *s) {
    while (isspace((unsigned char)*s)) s++;
    char *e = s + strlen(s);
    while (e > s && isspace((unsigned char)e[-1])) *--e = 0;
    return s;
}

// key.<button> / pad.<button> lines of hylian-melodies.ini (in the working directory: the player's folder)
static void load_bindings(void) {
    FILE *f = fopen("hylian-melodies.ini", "r");
    if (!f) return;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char *l = trim(line);
        if (*l == '#' || (strncmp(l, "key.", 4) && strncmp(l, "pad.", 4))) continue;
        bool key = l[0] == 'k';
        char *eq = strchr(l, '=');
        if (!eq) continue;
        *eq = 0;
        int b = button_of(trim(l + 4));
        if (b < 0) { LOG("[input] unknown button in \"%s\"\n", l); continue; }
        int n = 0;
        for (char *tok = strtok(eq + 1, ","); tok && n < MAXB; tok = strtok(NULL, ",")) {
            char *t = trim(tok);
            if (key) {
                SDL_Scancode sc = SDL_GetScancodeFromName(t);
                if (sc == SDL_SCANCODE_UNKNOWN) { LOG("[input] unknown key \"%s\"\n", t); continue; }
                if (!n) for (int i = 0; i < MAXB; i++) keymap[b][i] = SDL_SCANCODE_UNKNOWN;
                keymap[b][n++] = sc;
            } else {
                int p = pad_code_of(t);
                if (p < 0) { LOG("[input] unknown gamepad button \"%s\"\n", t); continue; }
                if (!n) for (int i = 0; i < MAXB; i++) padmap[b][i] = -1;
                padmap[b][n++] = p;
            }
        }
    }
    fclose(f);
}

// ------------------------------------------------------------------ state
static _Atomic uint64_t key_bits, pad_bits, script_bits;
static _Atomic int32_t pad_axes[4];
static SDL_Gamepad *pad;
static SDL_JoystickID pad_id;

static void publish(void) {
    uint64_t b = atomic_load(&key_bits) | atomic_load(&pad_bits) | atomic_load(&script_bits);
    bool captured = menu_input_captured();  // (the overlay menu is open: the game sees nothing held)
    if (captured) b = 0;
    static int log = -1;
    if (log < 0) log = getenv("HM_LOG_INPUT") != NULL;
    if (log && b != g_input_buttons) {
        char names[160] = "";
        for (int i = 0; i < NB; i++)
            if (b & (1ull << i)) { strcat(names, " "); strcat(names, bnames[i]); }
        LOG("[input] held:%s%s\n", names[0] ? names : " (none)", atomic_load(&pad_bits) ? " (gamepad)" : "");
    }
    g_input_buttons = b;
    for (int i = 0; i < 4; i++) g_input_sticks[i] = captured ? 0 : atomic_load(&pad_axes[i]);
}

static void recompute_keys(void) {
    const bool *ks = SDL_GetKeyboardState(NULL);
    uint64_t b = 0;
    pthread_mutex_lock(&map_lock);
    for (int i = 0; i < NB; i++)
        for (int j = 0; j < MAXB; j++)
            if (keymap[i][j] && ks[keymap[i][j]]) b |= 1ull << i;
    pthread_mutex_unlock(&map_lock);
    atomic_store(&key_bits, b);
}

static int32_t stick(int16_t v, bool invert) {
    int32_t x = v < -32767 ? -32767 : v;
    return invert ? -x : x;
}

static void recompute_pad(void) {
    uint64_t b = 0;
    if (pad) {
        pthread_mutex_lock(&map_lock);
        for (int i = 0; i < NB; i++)
            for (int j = 0; j < MAXB; j++) {
                int p = padmap[i][j];
                if (p < 0) continue;
                bool on = p >= 100 ? SDL_GetGamepadAxis(pad, (SDL_GamepadAxis)(p - 100)) > 16000
                                   : SDL_GetGamepadButton(pad, (SDL_GamepadButton)p);
                if (on) b |= 1ull << i;
            }
        pthread_mutex_unlock(&map_lock);
        atomic_store(&pad_axes[0], stick(SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTX), false));
        atomic_store(&pad_axes[1], stick(SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTY), true));  // (Switch: up is +)
        atomic_store(&pad_axes[2], stick(SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_RIGHTX), false));
        atomic_store(&pad_axes[3], stick(SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_RIGHTY), true));
    } else {
        for (int i = 0; i < 4; i++) atomic_store(&pad_axes[i], 0);
    }
    atomic_store(&pad_bits, b);
}

static void open_first_pad(void) {
    if (pad) return;
    int n = 0;
    SDL_JoystickID *ids = SDL_GetGamepads(&n);
    for (int i = 0; ids && i < n && !pad; i++) {
        pad = SDL_OpenGamepad(ids[i]);
        if (pad) {
            pad_id = ids[i];
            LOG("[input] gamepad: %s\n", SDL_GetGamepadName(pad) ? SDL_GetGamepadName(pad) : "?");
        }
    }
    SDL_free(ids);
}

static void ensure_init(void) {
    static bool init;
    if (init) return;
    init = true;
    defaults();
    load_bindings();
}

void input_handle_event(const SDL_Event *e) {
    ensure_init();
    if (getenv("HM_LOG_INPUT")) {  // (diagnostics: what the window receives)
        if (e->type == SDL_EVENT_KEY_DOWN && !e->key.repeat)
            LOG("[input] key down: %s\n", SDL_GetScancodeName(e->key.scancode));
        else if (e->type == SDL_EVENT_WINDOW_FOCUS_GAINED || e->type == SDL_EVENT_WINDOW_FOCUS_LOST)
            LOG("[input] window %s keyboard focus\n", e->type == SDL_EVENT_WINDOW_FOCUS_GAINED ? "got" : "lost");
    }
    static int debug_keys = -1;
    if (debug_keys < 0) debug_keys = getenv("HM_DEBUG_KEYS") && atoi(getenv("HM_DEBUG_KEYS")) != 0;
    if (e->type == SDL_EVENT_KEY_DOWN && !e->key.repeat &&
        (e->key.scancode == SDL_SCANCODE_F9 || (debug_keys && e->key.scancode == SDL_SCANCODE_P))) {
        // F9 (or P with HM_DEBUG_KEYS=1: desktops often take F9): dump the next frame's render passes and draw list
        // (build/pass_*.png and the log; diagnostics)
        extern volatile int g_debug_frame_request;
        g_debug_frame_request = 1;
        LOG("[input] F9: debug frame requested\n");
        return;
    }
    if (e->type == SDL_EVENT_KEY_DOWN && !e->key.repeat &&
        (e->key.scancode == SDL_SCANCODE_F11 ||
         (e->key.scancode == SDL_SCANCODE_RETURN && (e->key.mod & SDL_KMOD_ALT)))) {
        // F11 / Alt+Enter: fullscreen (borderless, the desktop's resolution) <-> window (for this run; the menu's
        // Video tab keeps it for the next start)
        extern SDL_Window *ui_window(void);
        SDL_Window *w = ui_window();
        if (w) {
            bool fs = (SDL_GetWindowFlags(w) & SDL_WINDOW_FULLSCREEN) != 0;
            SDL_SetWindowFullscreen(w, !fs);
            g_settings.fullscreen = !fs;
            LOG("[input] %s\n", fs ? "windowed" : "fullscreen");
        }
        return;
    }
    switch (e->type) {
    case SDL_EVENT_KEY_DOWN: case SDL_EVENT_KEY_UP: recompute_keys(); break;
    case SDL_EVENT_WINDOW_FOCUS_LOST: atomic_store(&key_bits, 0); break;  // (keys released while away)
    case SDL_EVENT_GAMEPAD_ADDED: open_first_pad(); recompute_pad(); break;
    case SDL_EVENT_GAMEPAD_REMOVED:
        if (pad && e->gdevice.which == pad_id) {
            LOG("[input] gamepad removed\n");
            SDL_CloseGamepad(pad);
            pad = NULL;
            open_first_pad();
        }
        recompute_pad();
        break;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN: case SDL_EVENT_GAMEPAD_BUTTON_UP: case SDL_EVENT_GAMEPAD_AXIS_MOTION:
        recompute_pad();
        break;
    default: return;
    }
    publish();
}

// ------------------------------------------------------------------ the menu's Controls tab (runtime/ui/menu.cpp)
int input_button_count(void) { return NB; }
const char *input_button_id(int b) { return b >= 0 && b < NB ? bnames[b] : "?"; }

// Nothing held any more (the menu opened or closed: a press it took doesn't reach the game, nor stays held there).
// Keys and buttons still down count again from their next event.
void input_reset(void) {
    atomic_store(&key_bits, 0);
    atomic_store(&pad_bits, 0);
    for (int i = 0; i < 4; i++) atomic_store(&pad_axes[i], 0);
    publish();
}

static void key_label(SDL_Scancode sc, char *out, size_t cap) {
    const char *n = SDL_GetScancodeName(sc);
    snprintf(out, cap, "%s", n && *n ? n : "?");
}
static void pad_label(int p, char *out, size_t cap) {  // (what the player sees: positions, not maker's letters)
    static const char *const face[4] = {"Bottom face", "Right face", "Left face", "Top face"};
    static const struct { int p; const char *n; } other[] = {
        {SDL_GAMEPAD_BUTTON_BACK, "Back / View"}, {SDL_GAMEPAD_BUTTON_START, "Start / Menu"},
        {SDL_GAMEPAD_BUTTON_GUIDE, "Home"}, {SDL_GAMEPAD_BUTTON_LEFT_STICK, "Left stick click"},
        {SDL_GAMEPAD_BUTTON_RIGHT_STICK, "Right stick click"}, {SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, "Left shoulder"},
        {SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, "Right shoulder"}, {SDL_GAMEPAD_BUTTON_DPAD_UP, "D-pad up"},
        {SDL_GAMEPAD_BUTTON_DPAD_DOWN, "D-pad down"}, {SDL_GAMEPAD_BUTTON_DPAD_LEFT, "D-pad left"},
        {SDL_GAMEPAD_BUTTON_DPAD_RIGHT, "D-pad right"}, {100 + SDL_GAMEPAD_AXIS_LEFT_TRIGGER, "Left trigger"},
        {100 + SDL_GAMEPAD_AXIS_RIGHT_TRIGGER, "Right trigger"},
    };
    if (p >= SDL_GAMEPAD_BUTTON_SOUTH && p <= SDL_GAMEPAD_BUTTON_NORTH) { snprintf(out, cap, "%s", face[p]); return; }
    for (unsigned i = 0; i < sizeof other / sizeof other[0]; i++)
        if (other[i].p == p) { snprintf(out, cap, "%s", other[i].n); return; }
    snprintf(out, cap, "%s", pad_code_name(p));
}

// The bindings of button b, for display: "X, Return" / "Right face" ("-" when none).
void input_binding_text(int b, bool padside, char *out, size_t cap) {
    ensure_init();
    out[0] = 0;
    if (b < 0 || b >= NB || !cap) return;
    size_t n = 0;
    pthread_mutex_lock(&map_lock);
    for (int j = 0; j < MAXB; j++) {
        char one[48];
        if (padside ? padmap[b][j] < 0 : !keymap[b][j]) continue;
        if (padside) pad_label(padmap[b][j], one, sizeof one);
        else key_label(keymap[b][j], one, sizeof one);
        n += (size_t)snprintf(out + n, n < cap ? cap - n : 0, "%s%s", n ? ", " : "", one);
        if (n >= cap) break;
    }
    pthread_mutex_unlock(&map_lock);
    if (!out[0]) snprintf(out, cap, "-");
}

// key.<button> / pad.<button> lines for every button, for the ini (settings_save puts them in place of the old ones)
static void bindings_to_settings(void) {
    static char text[NB * 2 * 96];
    size_t n = 0;
    pthread_mutex_lock(&map_lock);
    for (int side = 0; side < 2; side++)
        for (int b = 0; b < NB; b++) {
            n += (size_t)snprintf(text + n, sizeof text - n, "%s.%s =", side ? "pad" : "key", bnames[b]);
            int k = 0;
            for (int j = 0; j < MAXB; j++) {
                if (side ? padmap[b][j] < 0 : !keymap[b][j]) continue;
                n += (size_t)snprintf(text + n, sizeof text - n, "%s %s", k++ ? "," : "",
                                      side ? pad_code_name(padmap[b][j]) : SDL_GetScancodeName(keymap[b][j]));
            }
            n += (size_t)snprintf(text + n, sizeof text - n, "\n");
        }
    pthread_mutex_unlock(&map_lock);
    settings_set_binding_lines(text);
}

static void bindings_changed(void) {
    recompute_keys();
    recompute_pad();
    publish();
}

// One binding for button b, replacing its others; a key or pad button bound to another button leaves that one.
void input_bind_set(int b, bool padside, int code) {
    ensure_init();
    if (b < 0 || b >= NB) return;
    pthread_mutex_lock(&map_lock);
    for (int o = 0; o < NB; o++)
        for (int j = 0; j < MAXB; j++) {
            if (padside && padmap[o][j] == code) padmap[o][j] = -1;
            if (!padside && keymap[o][j] == (SDL_Scancode)code) keymap[o][j] = SDL_SCANCODE_UNKNOWN;
        }
    for (int j = 0; j < MAXB; j++) {
        if (padside) padmap[b][j] = j ? -1 : code;
        else keymap[b][j] = j ? SDL_SCANCODE_UNKNOWN : (SDL_Scancode)code;
    }
    pthread_mutex_unlock(&map_lock);
    LOG("[input] %s.%s bound to %s\n", padside ? "pad" : "key", bnames[b],
        padside ? pad_code_name(code) : SDL_GetScancodeName((SDL_Scancode)code));
    bindings_to_settings();
    bindings_changed();
}

// Every binding back to the defaults above (the ini's key./pad. lines go at the next save).
void input_bindings_reset(void) {
    ensure_init();
    pthread_mutex_lock(&map_lock);
    defaults();
    pthread_mutex_unlock(&map_lock);
    LOG("[input] bindings reset to the defaults\n");
    settings_set_binding_lines("");
    bindings_changed();
}

// A press to bind (the Controls tab waiting for one): a key, or a gamepad button / trigger. Returns the code or -1.
int input_bind_code(const SDL_Event *e, bool padside) {
    if (!padside && e->type == SDL_EVENT_KEY_DOWN && !e->key.repeat) return (int)e->key.scancode;
    if (padside && e->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) return e->gbutton.button;
    if (padside && e->type == SDL_EVENT_GAMEPAD_AXIS_MOTION && e->gaxis.value > 24000 &&
        (e->gaxis.axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER || e->gaxis.axis == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER))
        return 100 + e->gaxis.axis;
    return -1;
}

// ------------------------------------------------------------------ scripted input (test runs)
static void script_frame(uint64_t frame) {
    static const char *script;
    static int init;
    static struct { uint64_t at, until; uint64_t bits; } steps[256];
    static int nsteps;
    if (!init) {
        init = 1;
        script = getenv("HM_INPUT_SCRIPT");
        for (const char *p = script; p && *p && nsteps < 256;) {
            uint64_t at = strtoull(p, (char **)&p, 10), len = 6, bits = 0;
            if (*p++ != ':') break;
            char name[16];
            for (;;) {
                int n = 0;
                while (*p && *p != '+' && *p != '/' && *p != ',' && n < 15) name[n++] = (char)tolower((unsigned char)*p++);
                name[n] = 0;
                int b = button_of(name);
                if (b >= 0) bits |= 1ull << b;
                if (*p != '+') break;
                p++;
            }
            if (*p == '/') len = strtoull(p + 1, (char **)&p, 10);
            steps[nsteps].at = at, steps[nsteps].until = at + len, steps[nsteps].bits = bits;
            nsteps++;
            if (*p == ',') p++; else break;
        }
        if (nsteps) LOG("[input] script: %d steps\n", nsteps);
    }
    if (!nsteps) return;
    uint64_t b = 0;
    for (int i = 0; i < nsteps; i++)
        if (frame >= steps[i].at && frame < steps[i].until) {
            b |= steps[i].bits;
            if (frame == steps[i].at) LOG("[input] script frame %llu: press %#llx\n", (unsigned long long)frame,
                                          (unsigned long long)steps[i].bits);
        }
    atomic_store(&script_bits, b);
    publish();
}

void input_frame(uint64_t frame) { script_frame(frame); }

// The real keyboard and pads stay live in scripted runs too (nothing to block).
bool input_user_blocked(const SDL_Event *e) { (void)e; return false; }
void input_cursor_event(const SDL_Event *e) {
    if (e->type == SDL_EVENT_KEY_DOWN || e->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) SDL_HideCursor();
    else if (e->type == SDL_EVENT_MOUSE_MOTION) SDL_ShowCursor();
}
void input_apply_background(void) { SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "0"); }
void input_load_user_mappings(void) {
    // the player's own controller mappings (SDL_GameControllerDB format), next to the settings
    ensure_init();
    if (SDL_AddGamepadMappingsFromFile("gamecontrollerdb.txt") > 0) LOG("[input] loaded gamecontrollerdb.txt\n");
    open_first_pad();
    recompute_pad();
    publish();
}

// ------------------------------------------------------------------ rumble (runtime/rumble.h)
static _Atomic bool permitted = true;
static RumbleValue current[2];
static _Atomic int rumble_dirty;
static SDL_Mutex *rlock;

void input_rumble_send(uint32_t handle, const RumbleValue *v) {
    int side = rumble_side(handle);
    if (side < 0) return;
    if (!rlock) rlock = SDL_CreateMutex();
    SDL_LockMutex(rlock);
    current[side] = *v;
    SDL_UnlockMutex(rlock);
    atomic_store(&rumble_dirty, 1);
}
RumbleValue input_rumble_get(uint32_t handle) {
    int side = rumble_side(handle);
    return side < 0 ? (RumbleValue){0} : current[side];
}
void input_rumble_permit(bool p) { atomic_store(&permitted, p); }
bool input_rumble_permitted(void) { return atomic_load(&permitted); }
void input_rumble_poll(void) {  // window thread
    if (!atomic_exchange(&rumble_dirty, 0) || !pad || !rlock) return;
    uint16_t lo, hi;
    SDL_LockMutex(rlock);
    rumble_mix(current, &lo, &hi);
    SDL_UnlockMutex(rlock);
    if (!atomic_load(&permitted)) lo = hi = 0;
    SDL_RumbleGamepad(pad, lo, hi, 250);  // (renewed by the game's next value; ends by itself if none comes)
}
void input_rumble_stop(void) { if (pad) SDL_RumbleGamepad(pad, 0, 0, 0); }
void input_led_poll(void) {}
void input_led_stop(void) {}
