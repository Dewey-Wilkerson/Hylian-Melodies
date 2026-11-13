// Headless renderer backend (M4): the NVN front end records the game's commands, nothing is drawn. Fences complete
// at once. M5 replaces it with the Vulkan backend (LAS Recomp's runtime/nvn/vulkan/), built instead of this file.
#include <stdbool.h>
#include <stdint.h>
#include "nvn.h"

static uint64_t seq;
static uint64_t executed, presented;

void backend_init(void) {}
void backend_execute(uint64_t handle) { (void)handle; executed++; seq++; }
void backend_present(NvnTexture *tex) { (void)tex; presented++; }
void backend_present_now(NvnTexture *t, uint64_t frame) { (void)t; (void)frame; presented++; }
void backend_upload_now(NvnTexture *t, int kind, void *data, uint32_t w, uint32_t h, uint32_t stride, uint32_t uv) {
    (void)t; (void)kind; (void)w; (void)h; (void)stride; (void)uv;
    extern void free(void *);
    free(data);
}
void backend_texture_destroyed(NvnTexture *tex) { (void)tex; }
void backend_texture_view_format(NvnTexture *tex, uint32_t format) { (void)tex; (void)format; }
void backend_pool_written(uint64_t addr, uint64_t size) { (void)addr; (void)size; }
void *backend_pool_push(void) { return 0; }
void backend_pool_pop(void *p) { (void)p; }
uint64_t renderer_fence_seq(void) { return seq; }
void renderer_wait_seq(uint64_t s) { (void)s; }
uint64_t renderer_submit_seq(void) { return seq; }
uint64_t renderer_issued_seq(void) { return seq; }
void renderer_flush(void) {}
void renderer_sync(void) {}
uint64_t null_backend_presented(void) { return presented; }
uint64_t null_backend_executed(void) { return executed; }
void renderer_upload_rgba(NvnTexture *t, const void *rgba, uint32_t w, uint32_t h, uint32_t stride) {
    (void)t; (void)rgba; (void)w; (void)h; (void)stride;
}
bool renderer_upload_nv12(NvnTexture *t, const void *nv12, uint32_t w, uint32_t h, uint32_t stride, uint32_t uv_off) {
    (void)t; (void)nv12; (void)w; (void)h; (void)stride; (void)uv_off;
    return true;  // (taken: nothing to draw headless)
}
void shader_prep_boot(const char *romfs) { (void)romfs; }  // (the Vulkan build prepares shaders: nvn/shader_prep.c)
