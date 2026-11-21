// Window requests from the game's own Options menu (runtime/hle/game_menu.c), applied on the window thread
// (runtime/nvn/vulkan/device.c ui_run). The settings themselves are rows of the game's menu (docs/IN-GAME-MENU.md).
#include "menu.h"

#include "../settings.h"

#include <time.h>

#include "../hle.h"

extern volatile int g_game_menu_fullscreen_req;  // (set when the Fullscreen row flips)
extern volatile uint64_t g_game_menu_quit_req, g_game_menu_quit_commits;  // (the pause menu's Save and Quit)
extern volatile uint64_t g_save_commits, g_save_activity_ns;              // (runtime/services/fs.c)
extern volatile int g_game_menu_quit_now;                                  // (the title screen's Exit)

// Save and Quit: the game saves and goes to its title screen; the window closes (as with its close button) once a
// save was committed after the request and nothing was written for a moment, or after 20 s whatever happened.
static void quit_when_saved(void) {
    if (g_game_menu_quit_now == 1) {  // the title screen's Exit: nothing to save; a moment for its sound
        static uint64_t at;
        uint64_t t = SDL_GetTicksNS();
        if (!at) at = t;
        if (t < at + 400000000ull) return;
        g_game_menu_quit_now = 2;
        LOG("[game-menu] exit from the title screen, closing\n");
        SDL_Event e = {.type = SDL_EVENT_QUIT};
        SDL_PushEvent(&e);
        return;
    }
    uint64_t req = g_game_menu_quit_req;
    if (!req) return;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);  // (the clock of g_save_activity_ns and the request)
    uint64_t now = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
    bool saved = g_save_commits > g_game_menu_quit_commits && now > g_save_activity_ns + 1500000000ull;
    if (!saved && now < req + 20000000000ull) return;
    g_game_menu_quit_req = 0;
    LOG("[game-menu] save and quit: %s, closing\n", saved ? "saved" : "no save seen in 20 s");
    SDL_Event e = {.type = SDL_EVENT_QUIT};
    SDL_PushEvent(&e);
}

void menu_apply_window_requests(SDL_Window *w) {
    quit_when_saved();
    if (!g_game_menu_fullscreen_req) return;
    g_game_menu_fullscreen_req = 0;
    SDL_SetWindowFullscreen(w, g_settings.fullscreen);
}
