// Player settings (hylian-melodies.ini next to the executable). The video fields follow LAS Recomp's settings.h
// (MIT) so its renderer works unchanged; the rest is this game's.
#pragma once
#include <stdbool.h>

enum { ASPECT_UNLOCKED = 0, ASPECT_ORIGINAL = 1 };
enum { RES_MATCH = 0, /* 1..8 = 1x..8x */ RES_DYNAMIC = 9, RES_Q75 = 10, RES_Q25 = 11, RES_Q50 = 12 };
enum { UPSCALE_BILINEAR = 0, UPSCALE_METALFX = 1, UPSCALE_FSR1 = 2 };
#define UPSCALE_SHARP UPSCALE_FSR1
enum { AA_OFF = 0, AA_SMAA = 1 };

typedef struct {
    // video
    int aspect;            // ASPECT_*: original = 16:9 with bars (default; the game is laid out for 16:9)
    bool fullscreen;
    int res_mode;          // RES_*: internal resolution
    bool res_auto;
    int upscaler;          // UPSCALE_*
    bool upscaler_auto;
    int antialias;         // AA_* (SMAA is not built yet: off)
    int upscale_filter;    // game image -> window: 0 sharp bilinear (default), 1 linear, 2 nearest
    int screen_filter;     // 0 = off (LAS Recomp's colour filters; unused here)
    bool mirror_mode;      // (unused here)
    bool show_fps;
    bool frame_pacing;     // the Switch display's 60 Hz cadence at each present (default on; nvn/objects.c)
    // audio
    double volume;         // master volume 0..1
    bool reverb;           // (audio renderer only; unused by this game)
    bool movie_audio;
    int audio_latency_ms;  // (reserved: the game has its own calibration, see docs/audio.md)
    int audio_period;      // device period asked of the audio server, frames at 48 kHz (default 256 = 5.3 ms)
    double audio_queue_ms; // what the output stream may hold before the next game buffer is taken (0 = one period)
    // game
    char language[8];      // the game's language code, e.g. en-US ("language" in the ini; default: system)
} Settings;

extern Settings g_settings;
extern int g_default_upscaler, g_default_res_mode;
extern bool g_gpu_integrated;
void settings_load(void);
void settings_resolve_defaults(bool integrated);
const char *settings_language(void);

// Saving (the overlay menu): only what was changed is written; every other line of the file stays as it was.
enum { SET_FULLSCREEN = 1 << 0, SET_UPSCALE_FILTER = 1 << 1, SET_SHOW_FPS = 1 << 2, SET_FRAME_PACING = 1 << 3,
       SET_VOLUME = 1 << 4 };
void settings_changed(unsigned which);                // SET_* bits: written at the next save
void settings_set_binding_lines(const char *lines);   // key./pad. lines to replace all of the file's ("" = none: defaults)
bool settings_save(void);                             // hylian-melodies.ini in the working directory (the player's folder)
bool settings_save_to(const char *path);              // (tests) the same into path; true when written
