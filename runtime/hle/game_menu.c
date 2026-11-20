// The port's settings as rows of the game's own Options menu (prototype, branch in-game-gui).
//
// Two function hooks (recomp/hooks.txt) on the supported game version:
//  - the Options screen builder: after it ran, a Yes/No row of the game's own toggle class is added to the Graphics
//    page (found by its first row's label), its value and change callback ours;
//  - the text lookup (text id -> style and UTF-32 text): ids from HM_TEXT_BASE up are ours (labels and descriptions), every
//    other id goes to the game.
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
#define SCREEN_PAGES     0x68             // vector<vector<unique_ptr<Row>>> in the Options screen object
#define LABEL_DISCO      70               // first row of the Graphics page

enum { HM_TEXT_BASE = 0x484d0000, T_FULLSCREEN = HM_TEXT_BASE, T_FULLSCREEN_DESC };

static const char *hm_text(uint32_t id) {
    switch (id) {
    case T_FULLSCREEN: return "FULLSCREEN";
    case T_FULLSCREEN_DESC: return "Fill the screen (borderless, at the desktop's resolution). F11 or Alt+Enter also switch.";
    }
    return NULL;
}

volatile int g_game_menu_fullscreen_req;  // (consumed on the window thread: runtime/ui/menu.cpp)

static void on_fullscreen(Cpu *c) {  // bound member function: x0 = object (unused), w1 = new value
    bool v = c->x[1] & 1;
    g_settings.fullscreen = v;
    settings_changed(SET_FULLSCREEN);
    if (!settings_save()) LOG("[game-menu] saving hylian-melodies.ini failed\n");
    g_game_menu_fullscreen_req = 1;
    LOG("[game-menu] fullscreen %s\n", v ? "on" : "off");
}

static uint64_t call1(Cpu *c, uint64_t fn, uint64_t a0) {
    c->x[0] = a0;
    guest_call(c, fn);
    return c->x[0];
}

static void add_toggle(Cpu *c, uint64_t page, uint32_t label, uint32_t desc, bool value, HostFn cb) {
    static uint64_t cb_addr;
    if (!cb_addr) cb_addr = hle_register("hm_game_menu_fullscreen", cb);
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
    c->x[0] = row; c->x[1] = label; c->x[2] = desc; c->x[3] = key; c->x[4] = fn;
    c->x[5] = value; c->x[6] = 0; c->x[7] = 0;
    guest_call(c, G_TOGGLE_CTOR);
    call1(c, LD64(LD64(fn) + 0x20), fn);  // the local std::function's destroy() (the row holds a copy)

    ST8(row + ROW_VALUE, value);           // (with an empty key the constructor starts it at "no")
    call1(c, LD64(LD64(row) + 0x30), row);  // the constructor's own refresh calls
    c->x[1] = 0;
    call1(c, LD64(LD64(row) + 0x28), row);

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
}

void hm_hook_options_build(Cpu *c, GuestFn orig) {
    uint64_t self = c->x[0];
    orig(c);
    if (getenv("HM_GAME_MENU") && !strcmp(getenv("HM_GAME_MENU"), "0")) return;
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);  // x19..x30 and the return value stay the caller's
    uint64_t r0 = c->x[0];
    uint64_t b = LD64(self + SCREEN_PAGES), e = LD64(self + SCREEN_PAGES + 8);
    int added = 0;
    for (uint64_t page = b; page < e; page += 24) {
        uint64_t rb = LD64(page), re = LD64(page + 8);
        if (rb == re || LD32(LD64(rb) + ROW_LABEL) != LABEL_DISCO) continue;
        add_toggle(c, page, T_FULLSCREEN, T_FULLSCREEN_DESC, g_settings.fullscreen, on_fullscreen);
        added = 1;
        break;
    }
    LOG("[game-menu] options screen %llx: %s\n", (unsigned long long)self,
        added ? "Fullscreen row added to Graphics" : "Graphics page not found");
    memcpy(&c->x[19], saved, sizeof saved);
    c->x[0] = r0;
}

// The text lookup's result: {i32 style (-1: no such text); std::u32string text at +8}. libc++ u32string: short form
// (first byte = length << 1, up to 4 characters at +4) or long form (capacity | 1, length, buffer from the game's
// allocator, which the game's destructor frees).
static void put_u32string(Cpu *c, uint64_t s, const char *t) {
    if (LD8(s) & 1) call1(c, G_DELETE, LD64(s + 16));
    size_t n = strlen(t);  // (ASCII only)
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
    for (size_t i = 0; i <= n; i++) ST32(d + 4 * i, (uint8_t)t[i]);
}

void hm_hook_text_lookup(Cpu *c, GuestFn orig) {  // w0 = id, x1 = language (std::string *), x8 = result
    uint32_t id = (uint32_t)c->x[0];
    const char *t = id >= HM_TEXT_BASE ? hm_text(id) : NULL;
    if (!t) { orig(c); return; }
    uint64_t res = c->x[8];
    c->x[0] = (id - HM_TEXT_BASE) & 1 ? LABEL_DISCO + 1 : LABEL_DISCO;  // a label or a description of the game's,
    orig(c);                                                           // for the style field; the text is replaced
    uint64_t saved[13];
    memcpy(saved, &c->x[19], sizeof saved);
    put_u32string(c, res + 8, t);
    memcpy(&c->x[19], saved, sizeof saved);
}
