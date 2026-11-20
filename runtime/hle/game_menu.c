// The port's settings as rows of the game's own Options menu (branch in-game-gui; docs/IN-GAME-MENU.md).
//
// Function hooks (recomp/hooks.txt) on the supported game version:
//  - the Options screen builder: after it ran, Yes/No rows of the game's own toggle class are added to the Graphics
//    page (found by its first row's label), their values and change callbacks ours;
//  - the toggle's per-frame update: keeps our Fullscreen row in step when F11 / Alt+Enter switch;
//  - the text lookup (text id -> style and UTF-32 text): ids from HM_TEXT_BASE up are ours (labels and descriptions,
//    in the game's languages), every other id goes to the game.
// Everything below is how this game version lays out its objects, found by reading the lifted code (facts only:
// addresses, offsets, sizes). Guest memory is host memory, so the game's objects are read and written in place.
#include <string.h>

#include "../hle.h"
#include "../settings.h"

// game functions and data (1.4.0)
#define G_NEW            0x70007c80a0ull  // operator new(size) -> x0
#define G_DELETE         0x70007c80b0ull  // operator delete(p)
#define G_TOGGLE_CTOR    0x70000662b0ull  // (row, label id, desc id, const std::string *key, std::function<void(bool)> *, default, 0, 0)
#define G_VEC_PUSH_SLOW  0x7000012b90ull  // vector<unique_ptr<Row>>::push_back slow path (vec, unique_ptr *)
#define G_BIND_VT_GOT    0x7000a34fa0ull  // GOT slot: vtable of the bound member function the toggles take
#define ROW_SIZE         0x90
#define ROW_LABEL        0x08             // u32 text id
#define ROW_VALUE        0x88             // u8 current value of a toggle
#define ROW_VT_REFRESH   0x30             // vtable slots the toggle constructor calls after setting the value:
#define ROW_VT_REFRESH2  0x28             //   refresh(row), then (row, 0)
#define SCREEN_PAGES     0x68             // vector<vector<unique_ptr<Row>>> in the Options screen object
#define LABEL_DISCO      70               // first row of the Graphics page

// ---- our text: even ids are labels, odd ids their descriptions (the lookup hook borrows a game label or description
// of the same kind for the style field)
enum { HM_TEXT_BASE = 0x484d0000, T_FULLSCREEN = HM_TEXT_BASE, T_FULLSCREEN_DESC, T_PACING, T_PACING_DESC, T_COUNT };

// The game's language codes (localization.xml), in this order in every row below. Translations other than English
// were drafted by the agent; a native check is wanted.
static const char *const langs[] = {"en", "ja", "de", "fr", "cafr", "es", "uses", "it", "kr", "sc", "tc"};
enum { NLANG = sizeof langs / sizeof *langs };

static const char *const texts[T_COUNT - HM_TEXT_BASE][NLANG] = {
    {"FULLSCREEN", "フルスクリーン", "VOLLBILD", "PLEIN ÉCRAN", "PLEIN ÉCRAN", "PANTALLA COMPLETA", "PANTALLA COMPLETA",
     "SCHERMO INTERO", "전체 화면", "全屏", "全螢幕"},
    {"Fill the screen (borderless, at the desktop's resolution). F11 or Alt+Enter also switch.",
     "画面全体に表示します（枠なし、デスクトップの解像度）。F11 または Alt+Enter でも切り替えられます。",
     "Füllt den Bildschirm (randlos, in der Auflösung des Desktops). F11 oder Alt+Eingabe schalten ebenfalls um.",
     "Occupe tout l'écran (sans bordure, à la résolution du bureau). F11 ou Alt+Entrée basculent aussi.",
     "Occupe tout l'écran (sans bordure, à la résolution du bureau). F11 ou Alt+Entrée basculent aussi.",
     "Ocupa toda la pantalla (sin bordes, a la resolución del escritorio). F11 o Alt+Intro también cambian el modo.",
     "Ocupa toda la pantalla (sin bordes, con la resolución del escritorio). F11 o Alt+Enter también cambian el modo.",
     "Riempie lo schermo (senza bordi, alla risoluzione del desktop). Anche F11 o Alt+Invio cambiano modalità.",
     "화면 전체에 표시합니다(테두리 없음, 바탕 화면 해상도). F11 또는 Alt+Enter로도 전환할 수 있습니다.",
     "填满整个屏幕（无边框，使用桌面分辨率）。也可按 F11 或 Alt+Enter 切换。",
     "填滿整個螢幕（無邊框，使用桌面解析度）。也可按 F11 或 Alt+Enter 切換。"},
    {"FRAME PACING", "フレームペーシング", "BILDTAKT", "CADENCE D'IMAGES", "CADENCE D'IMAGES", "RITMO DE FOTOGRAMAS",
     "RITMO DE CUADROS", "CADENZA FOTOGRAMMI", "프레임 페이싱", "帧同步", "影格同步"},
    {"A steady 60 Hz, like the Switch's display. Turn it off only if the picture stutters evenly.",
     "Switch の画面と同じ安定した 60 Hz で表示します。映像が規則的にカクつく場合のみオフにしてください。",
     "Gleichmäßige 60 Hz wie auf dem Bildschirm der Switch. Nur ausschalten, wenn das Bild gleichmäßig ruckelt.",
     "Un 60 Hz régulier, comme l'écran de la Switch. Désactivez-le seulement si l'image saccade de façon régulière.",
     "Un 60 Hz régulier, comme l'écran de la Switch. Désactivez-le seulement si l'image saccade de façon régulière.",
     "60 Hz constantes, como la pantalla de Switch. Desactívalo solo si la imagen da tirones regulares.",
     "60 Hz constantes, como la pantalla de Switch. Desactívalo solo si la imagen se traba de forma regular.",
     "60 Hz costanti, come lo schermo di Switch. Disattivalo solo se l'immagine scatta in modo regolare.",
     "Switch 화면처럼 안정적인 60Hz로 표시합니다. 화면이 일정하게 끊길 때만 끄세요.",
     "像 Switch 屏幕一样稳定的 60 Hz。仅在画面规律性卡顿时关闭。",
     "像 Switch 螢幕一樣穩定的 60 Hz。僅在畫面規律性卡頓時關閉。"},
};

const char *game_menu_text(uint32_t id, const char *lang) {  // (tests: tests/c via the same table)
    if (id < HM_TEXT_BASE || id >= T_COUNT) return NULL;
    int l = 0;
    for (int i = 0; i < NLANG; i++)
        if (lang && !strcmp(lang, langs[i])) l = i;
    return texts[id - HM_TEXT_BASE][l];
}

// ---- guest helpers
static uint64_t call1(Cpu *c, uint64_t fn, uint64_t a0) {
    c->x[0] = a0;
    guest_call(c, fn);
    return c->x[0];
}

static void row_refresh(Cpu *c, uint64_t row) {  // after a value change: the toggle constructor's own calls
    call1(c, LD64(LD64(row) + ROW_VT_REFRESH), row);
    c->x[1] = 0;
    call1(c, LD64(LD64(row) + ROW_VT_REFRESH2), row);
}

// ---- the rows
volatile int g_game_menu_fullscreen_req;  // (consumed on the window thread: runtime/ui/menu.cpp)
static uint64_t fullscreen_row;           // the current Options screen's (checked by label before use)

static void save(void) {
    if (!settings_save()) LOG("[game-menu] saving hylian-melodies.ini failed\n");
}

static void on_fullscreen(Cpu *c) {  // bound member function: x0 = object (unused), w1 = new value
    bool v = c->x[1] & 1;
    g_settings.fullscreen = v;
    settings_changed(SET_FULLSCREEN);
    save();
    g_game_menu_fullscreen_req = 1;
    LOG("[game-menu] fullscreen %s\n", v ? "on" : "off");
}

static void on_pacing(Cpu *c) {
    bool v = c->x[1] & 1;
    g_settings.frame_pacing = v;  // (read at every present: runtime/nvn/objects.c)
    settings_changed(SET_FRAME_PACING);
    save();
    LOG("[game-menu] frame pacing %s\n", v ? "on" : "off");
}

static uint64_t add_toggle(Cpu *c, uint64_t page, uint32_t label, bool value, const char *cb_name, HostFn cb) {
    uint64_t cb_addr = hle_register(cb_name, cb);  // (the same address for the same name)
    uint64_t sp0 = c->sp;
    c->sp -= 0x80;
    uint64_t key = c->sp, fn = c->sp + 0x20, slot = c->sp + 0x50;
    memset((void *)key, 0, 0x60);  // key: empty std::string (no config entry: the toggle then only calls back)
    ST64(fn + 0x00, LD64(G_BIND_VT_GOT) + 0x10);
    ST64(fn + 0x08, cb_addr);      // member function pointer: our host function
    ST64(fn + 0x10, 0);            // this-adjust 0, not virtual
    ST64(fn + 0x18, 0);            // bound object
    ST64(fn + 0x20, fn);           // std::function's callable: in its own buffer

    uint64_t row = call1(c, G_NEW, ROW_SIZE);
    c->x[0] = row; c->x[1] = label; c->x[2] = label + 1; c->x[3] = key; c->x[4] = fn;
    c->x[5] = value; c->x[6] = 0; c->x[7] = 0;
    guest_call(c, G_TOGGLE_CTOR);
    call1(c, LD64(LD64(fn) + 0x20), fn);  // the local std::function's destroy() (the row holds a copy)

    ST8(row + ROW_VALUE, value);  // (with an empty key the constructor starts it at "no")
    row_refresh(c, row);

    uint64_t end = LD64(page + 8), cap = LD64(page + 16);
    if (end < cap) {
        ST64(end, row);
        ST64(page + 8, end + 8);
    } else {
        ST64(slot, row);
        c->x[1] = slot;
        call1(c, G_VEC_PUSH_SLOW, page);
    }
    c->sp = sp0;
    return row;
}

static bool disabled(void) {
    const char *e = getenv("HM_GAME_MENU");
    return e && !strcmp(e, "0");
}

void hm_hook_options_build(Cpu *c, GuestFn orig) {
    uint64_t self = c->x[0];
    orig(c);
    if (disabled()) return;
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);  // x19..x30 and the return value stay the caller's
    uint64_t r0 = c->x[0];
    uint64_t b = LD64(self + SCREEN_PAGES), e = LD64(self + SCREEN_PAGES + 8);
    int added = 0;
    for (uint64_t page = b; page < e; page += 24) {
        uint64_t rb = LD64(page), re = LD64(page + 8);
        if (rb == re || LD32(LD64(rb) + ROW_LABEL) != LABEL_DISCO) continue;
        fullscreen_row = add_toggle(c, page, T_FULLSCREEN, g_settings.fullscreen, "hm_game_menu_fullscreen", on_fullscreen);
        add_toggle(c, page, T_PACING, g_settings.frame_pacing, "hm_game_menu_pacing", on_pacing);
        added = 1;
        break;
    }
    LOG("[game-menu] options screen %llx: %s\n", (unsigned long long)self,
        added ? "rows added to Graphics" : "Graphics page not found");
    memcpy(&c->x[19], saved, sizeof saved);
    c->x[0] = r0;
}

void hm_hook_toggle_update(Cpu *c, GuestFn orig) {  // x0 = row, every frame for each toggle on the open page
    uint64_t row = c->x[0];
    if (row == fullscreen_row && LD32(row + ROW_LABEL) == T_FULLSCREEN &&
        (LD8(row + ROW_VALUE) & 1) != g_settings.fullscreen) {  // F11 / Alt+Enter switched meanwhile
        uint64_t saved[13], regs[8];
        memcpy(saved, &c->x[19], sizeof saved);
        memcpy(regs, &c->x[0], sizeof regs);
        ST8(row + ROW_VALUE, g_settings.fullscreen);
        row_refresh(c, row);
        memcpy(&c->x[19], saved, sizeof saved);
        memcpy(&c->x[0], regs, sizeof regs);  // (the update's own arguments)
    }
    orig(c);
}

// ---- layout
// The Options screen's per-frame layout of the open page (640x360 units): visible rows (byte +0x2c) 30 apart, the block
// centred on y = 183, the panel 17 above the first row and 18 taller than the rows. The game's pages have at most 8
// rows; more run into the title and the description box (about y 35..303 is free), so longer pages get a tighter
// pitch, centred in that space. Pages of 8 or fewer keep the game's own layout.
#define SCREEN_PAGE_INDEX 0xc4  // i32: the open page
#define SCREEN_WIDE       0xc8  // u8: panel 408 wide, else 328
#define SCREEN_PANEL      0x28  // the panel element (set by G_PANEL_SET)
#define ROW_VISIBLE       0x2c  // u8
#define ROW_VT_SET_Y      0x20  // (row, y)
#define G_LAYOUT_PRE1     0x700024c890ull  // (the layout's first calls, on the elements at screen +0x10 and +0x18)
#define G_LAYOUT_PRE2     0x700024c580ull
#define G_PANEL_SET       0x700024ad90ull  // (panel, x, y, w, h, 0, 0, 1)
#define FREE_TOP          35
#define FREE_BOTTOM       303

void hm_hook_options_layout(Cpu *c, GuestFn orig) {  // x0 = the Options screen
    uint64_t self = c->x[0];
    uint64_t page = LD64(self + SCREEN_PAGES) + (int64_t)(int32_t)LD32(self + SCREEN_PAGE_INDEX) * 24;
    uint64_t rb = LD64(page), re = LD64(page + 8);
    int n = 0;
    for (uint64_t r = rb; r < re; r += 8) n += LD8(LD64(r) + ROW_VISIBLE);
    if (n <= 8) { orig(c); return; }
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);
    int pitch = (FREE_BOTTOM - FREE_TOP - 18) / n;
    if (pitch > 30) pitch = 30;
    int h = n * pitch;
    int top = (FREE_TOP + FREE_BOTTOM) / 2 + 17 - (h + 18) / 2;  // (panel centred in the free space)
    call1(c, G_LAYOUT_PRE1, LD64(self + 0x10));
    call1(c, G_LAYOUT_PRE2, LD64(self + 0x18));
    int i = 0;
    for (uint64_t r = rb; r < re; r += 8) {
        uint64_t row = LD64(r);
        if (!LD8(row + ROW_VISIBLE)) continue;
        c->x[1] = (uint32_t)(top - 5 + i++ * pitch);
        call1(c, LD64(LD64(row) + ROW_VT_SET_Y), row);
    }
    int w = LD8(self + SCREEN_WIDE) ? 408 : 328;
    c->x[0] = self + SCREEN_PANEL;
    c->x[1] = (uint32_t)((640 - w) / 2); c->x[2] = (uint32_t)(top - 17); c->x[3] = (uint32_t)w;
    c->x[4] = (uint32_t)(h + 18); c->x[5] = 0; c->x[6] = 0; c->x[7] = 1;
    guest_call(c, G_PANEL_SET);
    memcpy(&c->x[19], saved, sizeof saved);
}

// ---- text
// The text lookup's result: {i32 style (-1: no such text); std::u32string text at +8}. libc++ u32string: short form
// (first byte = length << 1, up to 4 characters at +4) or long form (capacity | 1, length, buffer from the game's
// allocator, which the game's destructor frees).
static size_t utf8_decode(const char *s, uint32_t *out) {  // out may be NULL (count only)
    size_t n = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p;) {
        uint32_t cp = *p++;
        int more = cp >= 0xF0 ? 3 : cp >= 0xE0 ? 2 : cp >= 0xC0 ? 1 : 0;
        if (more) cp &= 0x3F >> more;
        while (more-- && (*p & 0xC0) == 0x80) cp = cp << 6 | (*p++ & 0x3F);
        if (out) out[n] = cp;
        n++;
    }
    return n;
}

static void put_u32string(Cpu *c, uint64_t s, const char *t) {
    if (LD8(s) & 1) call1(c, G_DELETE, LD64(s + 16));
    size_t n = utf8_decode(t, NULL);
    memset((void *)s, 0, 24);
    uint64_t d = s + 4;
    if (n > 4) {
        uint64_t cap = (n + 4) & ~3ull;  // elements, room for the terminator
        d = call1(c, G_NEW, cap * 4);
        ST64(s, cap | 1);
        ST64(s + 8, n);
        ST64(s + 16, d);
    } else {
        ST8(s, n << 1);
    }
    utf8_decode(t, (uint32_t *)d);
    ST32(d + 4 * n, 0);
}

static void read_string(uint64_t s, char *out, size_t cap) {  // libc++ std::string -> C string (truncated)
    size_t n = LD8(s) & 1 ? LD64(s + 8) : LD8(s) >> 1;
    const char *p = (const char *)(LD8(s) & 1 ? LD64(s + 16) : s + 1);
    if (n >= cap) n = cap - 1;
    memcpy(out, p, n);
    out[n] = 0;
}

void hm_hook_text_lookup(Cpu *c, GuestFn orig) {  // w0 = id, x1 = language (std::string *, in/out), x8 = result
    uint32_t id = (uint32_t)c->x[0];
    if (id < HM_TEXT_BASE || id >= T_COUNT) { orig(c); return; }
    uint64_t res = c->x[8], lang_s = c->x[1];
    c->x[0] = (id - HM_TEXT_BASE) & 1 ? LABEL_DISCO + 1 : LABEL_DISCO;  // a label or a description of the game's,
    orig(c);                                                           // for the style field; the text is replaced
    char lang[16];
    read_string(lang_s, lang, sizeof lang);  // (the lookup fills in the game's current language when it was empty)
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);
    put_u32string(c, res + 8, game_menu_text(id, lang));
    memcpy(&c->x[19], saved, sizeof saved);
    static char logged[16];
    if (strcmp(logged, lang)) {
        LOG("[game-menu] text language \"%s\"\n", lang);
        memcpy(logged, lang, sizeof logged);
    }
}
