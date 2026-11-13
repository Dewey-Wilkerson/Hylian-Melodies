// Window-side entry points while there is no renderer (M4): the boot runs headless. M5 replaces this file with the
// SDL3 window and the NVN-on-Vulkan renderer.
#include <stdbool.h>
#include <stdint.h>
#include <unistd.h>

bool ui_window_focused(void) { return true; }
uint64_t renderer_present_count(void) { return 0; }
int ui_run(void) {
    for (;;) pause();
}
