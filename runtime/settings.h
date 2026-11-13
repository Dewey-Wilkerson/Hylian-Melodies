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
    int screen_filter;     // 0 = off (LAS Recomp's colour filters; unused here)
    bool mirror_mode;      // (unused here)
    bool show_fps;
    // audio
    double volume;         // master volume 0..1
    bool reverb;           // (audio renderer only; unused by this game)
    bool movie_audio;
    int audio_latency_ms;  // extra output latency compensation (rhythm calibration, M6)
    // game
    char language[8];      // the game's language code, e.g. en-US ("language" in the ini; default: system)
} Settings;

extern Settings g_settings;
extern int g_default_upscaler, g_default_res_mode;
extern bool g_gpu_integrated;
void settings_load(void);
void settings_resolve_defaults(bool integrated);
const char *settings_language(void);
