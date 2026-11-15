// The in-game overlay menu (M10). Until then: nothing is drawn and no event is taken (runtime/ui/menu_stub.c).
#pragma once
#include <stdbool.h>
#include <SDL3/SDL.h>

void menu_render(void *cmd, unsigned width, unsigned height);
bool menu_handle_event(const SDL_Event *e);
void menu_apply_window_requests(SDL_Window *w);
void menu_test_open(void);
bool menu_input_captured(void);
