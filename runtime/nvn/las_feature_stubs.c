// LAS Recomp's renderer calls into features of its own game (recolouring, texture patches, widescreen camera fixes,
// randomizer pots and pets, warps, the save editor, in-place reboot, SMAA). This port has none of them: each answers
// "off / nothing to do", so the renderer takes its plain path. Remove the calls as the renderer is trimmed.
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "nvn.h"
#include "recolour.h"

volatile int g_debug_frame_request;

void escape_bottle_tint(int kind, const float *ui, uint32_t ui_size, float tint[8]) { (void)kind; (void)ui; (void)ui_size; (void)tint; }
uint64_t game_camera_zone(void) { return 0; }
int game_in_play(void) { return 1; }
const char *game_level_name(void) { return ""; }
bool hint_sheet_icon_draw(const float *ui, uint32_t ui_size) { (void)ui; (void)ui_size; return false; }
bool mirror_draw(bool composite) { (void)composite; return false; }
bool mirror_scene_size(uint32_t sw, uint32_t sh, uint32_t w, uint32_t h) { (void)sw; (void)sh; (void)w; (void)h; return false; }
bool pets_hide_item_cursor(void) { return false; }
bool pot_glow_active(void) { return false; }
void pot_gold_tint(float tint[8]) { (void)tint; }
bool pot_instance_gold(const float *m) { (void)m; return false; }
bool pot_level_active(void) { return false; }
bool pot_tint(const float *m, float tint[8], uint64_t mesh) { (void)m; (void)tint; (void)mesh; return false; }
void reboot_test_frame(uint64_t frame) { (void)frame; }
void recolour_add(int cls[2], int c) { (void)cls; (void)c; }
int recolour_class_of(int id) { (void)id; return 0; }
void recolour_tint_draw(const int cls[2], float tint[RECOLOUR_TINT_FLOATS]) { (void)cls; (void)tint; }
int rt_reboot_requested(void) { return 0; }
void save_editor_frame(uint64_t frame) { (void)frame; }
void scene_size_log(bool composite, uint32_t sw, uint32_t sh, uint32_t w, uint32_t h) { (void)composite; (void)sw; (void)sh; (void)w; (void)h; }
void texpatch_apply(int id, uint32_t lv, uint8_t *blocks, uint32_t w, uint32_t h, uint32_t row) { (void)id; (void)lv; (void)blocks; (void)w; (void)h; (void)row; }
int texpatch_bottle_kind(int id) { (void)id; return -1; }
uint32_t texpatch_generation(void) { return 0; }
int texpatch_heart_kind(int id) { (void)id; return -1; }
void texpatch_heart_tint(int kind, float tint[8]) { (void)kind; (void)tint; }
NvnTexture *texpatch_hint_icon(void) { return NULL; }
int texpatch_identify(const NvnTexture *t) { (void)t; return -1; }
bool texpatch_is_item_cursor(int id) { (void)id; return false; }
void warp_frame(uint64_t frame) { (void)frame; }
bool widescreen_allowed(void) { return false; }
void widescreen_backdrop_seen(uint64_t hash) { (void)hash; }
float widescreen_effect_stretch(uint64_t fs_hash) { (void)fs_hash; return 1.0f; }
void widescreen_frame_end(uint64_t frame) { (void)frame; }
// The present's crop of the game image: all of it (uv origin 0,0, size 1x1); the viewport is left as given.
void widescreen_present_crop(uint64_t frame, double shape, float *crop, double *vx, double *vy, double *vw, double *vh) {
    (void)frame; (void)shape; (void)vx; (void)vy; (void)vw; (void)vh;
    crop[0] = 0.0f, crop[1] = 0.0f, crop[2] = 1.0f, crop[3] = 1.0f;
}
void widescreen_scene_ubo(const float *u, uint64_t size) { (void)u; (void)size; }
void widescreen_set_factor(float f) { (void)f; }
bool widescreen_ui_pane_partial(const float *u, uint64_t size) { (void)u; (void)size; return false; }
bool world_on_screen(void) { return true; }

// SMAA (anti-aliasing) is not built: no shader source, zero lookup tables. Settings keep it off.
const char smaa_hlsl_src[] = "";
static const unsigned char zero_area[160 * 560 * 2], zero_search[64 * 16];
const unsigned char *smaa_area_tex(void) { return zero_area; }
const unsigned char *smaa_search_tex(void) { return zero_search; }
