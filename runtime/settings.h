// Player settings (hylian-melodies.ini in the player's folder). The video fields follow LAS Recomp's settings.h
// (MIT), which its renderer reads; the rest is this game's.
#pragma once
#include <stdbool.h>

enum { RES_MATCH = 0, /* 1..8 = 1x..8x */ RES_DYNAMIC = 9, RES_Q75 = 10, RES_Q25 = 11, RES_Q50 = 12 };
enum { UPSCALE_BILINEAR = 0, UPSCALE_METALFX = 1, UPSCALE_FSR1 = 2 };
#define UPSCALE_SHARP UPSCALE_FSR1

typedef struct {
    // video
    bool fullscreen;
    int res_mode;          // RES_*: internal resolution
    int upscaler;          // UPSCALE_*
    int upscale_filter;    // game image -> window: 0 sharp bilinear (default), 1 linear, 2 nearest
    int screen_filter;     // always 0 (off): the present shader's colour filter parameter, not a setting here
    bool frame_pacing;     // the Switch display's 60 Hz cadence at each present (default on; nvn/objects.c)
    // audio
    int audio_period;      // device period asked of the audio server, frames at 48 kHz (default 256 = 5.3 ms)
    double audio_queue_ms; // what the output stream may hold before the next game buffer is taken (0 = one period)
    // game
    char language[8];      // the game's language code, e.g. en-US ("language" in the ini; default: system)
    int gpu;               // Vulkan device index, -1 = auto (discrete first); "gpu" in the ini, HM_GPU wins
    // troubleshooting (written by the installer, installer/options.py; each HM_* variable, when set, wins)
    bool shader_cache;     // the saved SPIR-V cache (default on; HM_VK_NO_SPIRV_CACHE)
    bool vk_validation;    // Khronos validation layer (HM_VK_VALIDATION)
    bool log_input;        // buttons and keys to the log (HM_LOG_INPUT)
    double audio_stats;    // seconds between audio timing lines, 0 = off (HM_AUDIO_STATS)
} Settings;

extern Settings g_settings;
extern int g_default_upscaler, g_default_res_mode;
extern bool g_gpu_integrated;
void settings_load(void);                             // (once; later calls do nothing)
void settings_resolve_defaults(bool integrated);
const char *settings_language(void);

// Saving (the overlay menu): only what was changed is written; every other line of the file stays as it was.
// (show_fps and volume were removed 2026-11-19: old lines in the file are left alone and ignored)
enum { SET_FULLSCREEN = 1 << 0, SET_UPSCALE_FILTER = 1 << 1, SET_FRAME_PACING = 1 << 3 };
void settings_changed(unsigned which);                // SET_* bits: written at the next save
void settings_set_binding_lines(const char *lines);   // key./pad. lines to replace all of the file's ("" = none: defaults)
bool settings_save(void);                             // hylian-melodies.ini in the working directory (the player's folder)
bool settings_save_to(const char *path);              // (tests) the same into path; true when written
