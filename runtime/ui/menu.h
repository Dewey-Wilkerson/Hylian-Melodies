// Window requests from the game's own Options menu (runtime/hle/game_menu.c runs on the game thread; the window
// belongs to the window thread, which applies them here once per pass of its event loop).
#pragma once
#include <SDL3/SDL.h>

void menu_apply_window_requests(SDL_Window *w);
