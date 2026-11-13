// Stand-ins for the overlay menu (M10) and the input layer's window side (M7), so LAS Recomp's window loop
// (runtime/nvn/vulkan/device.c ui_run) runs unchanged.
#include <stdbool.h>
#include <stdint.h>
#include <SDL3/SDL.h>

#include "menu.h"

void menu_render(void *cmd, unsigned width, unsigned height) { (void)cmd; (void)width; (void)height; }
bool menu_handle_event(const SDL_Event *e) { (void)e; return false; }
void menu_apply_window_requests(SDL_Window *w) { (void)w; }
void menu_test_open(void) {}
bool menu_is_open(void) { return false; }
bool menu_input_captured(void) { return false; }

// input (M7: SDL3 gamepad and keyboard into runtime/hle/input.c)
void input_frame(uint64_t frame) { (void)frame; }
void input_apply_background(void) {}
void input_load_user_mappings(void) {}
bool input_user_blocked(const SDL_Event *e) { (void)e; return false; }
void input_cursor_event(const SDL_Event *e) { (void)e; }
void input_handle_event(const SDL_Event *e) { (void)e; }
void input_rumble_stop(void) {}
void input_led_poll(void) {}
void input_led_stop(void) {}
