// Window requests from the game's own Options menu (runtime/hle/game_menu.c), applied on the window thread
// (runtime/nvn/vulkan/device.c ui_run). The settings themselves are rows of the game's menu (docs/IN-GAME-MENU.md).
#include "menu.h"

#include "../settings.h"

extern volatile int g_game_menu_fullscreen_req;  // (set when the Fullscreen row flips)

void menu_apply_window_requests(SDL_Window *w) {
    if (!g_game_menu_fullscreen_req) return;
    g_game_menu_fullscreen_req = 0;
    SDL_SetWindowFullscreen(w, g_settings.fullscreen);
}
