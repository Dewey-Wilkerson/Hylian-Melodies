#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "settings.h"

Settings g_settings = {.aspect = ASPECT_ORIGINAL, .res_mode = 1, .res_auto = false, .upscaler = UPSCALE_BILINEAR,
                       .upscaler_auto = true, .antialias = AA_OFF, .frame_pacing = true, .volume = 1.0, .reverb = true, .movie_audio = true,
                       .audio_period = 256, .audio_queue_ms = 0};
int g_default_upscaler = UPSCALE_BILINEAR, g_default_res_mode = 1;  // (1: native, 1280x720 pixel art at 1:1)
bool g_gpu_integrated;

// Defaults that depend on the GPU (LAS Recomp chose lower ones for integrated GPUs; this 2D game needs no change).
void settings_resolve_defaults(bool integrated) { g_gpu_integrated = integrated; }

void settings_load(void) {
    FILE *f = fopen("hylian-melodies.ini", "r");
    if (!f) return;
    char line[256], key[64];
    double v;
    while (fgets(line, sizeof line, f)) {
        char str[16];
        if (sscanf(line, " language = %15s", str) == 1) { snprintf(g_settings.language, sizeof g_settings.language, "%s", str); continue; }
        if (sscanf(line, " %63[a-z_] = %lf", key, &v) != 2) continue;
        if (!strcmp(key, "volume")) g_settings.volume = v;
        else if (!strcmp(key, "audio_latency_ms")) g_settings.audio_latency_ms = (int)v;
        else if (!strcmp(key, "fullscreen")) g_settings.fullscreen = v != 0;
        else if (!strcmp(key, "aspect_unlocked")) g_settings.aspect = v != 0 ? ASPECT_UNLOCKED : ASPECT_ORIGINAL;
        else if (!strcmp(key, "resolution")) g_settings.res_mode = (int)v, g_settings.res_auto = false;
        else if (!strcmp(key, "upscaler")) g_settings.upscaler = (int)v, g_settings.upscaler_auto = false;
        else if (!strcmp(key, "show_fps")) g_settings.show_fps = v != 0;
        else if (!strcmp(key, "frame_pacing")) g_settings.frame_pacing = v != 0;
        else if (!strcmp(key, "upscale_filter")) g_settings.upscale_filter = (int)v;
        else if (!strcmp(key, "audio_period")) g_settings.audio_period = (int)v;
        else if (!strcmp(key, "audio_queue_ms")) g_settings.audio_queue_ms = v;
        else if (!strcmp(key, "movie_audio")) g_settings.movie_audio = v != 0;
    }
    fclose(f);
}

// The Switch language codes the game accepts; picked from the ini, else from the system locale, else en-US.
const char *settings_language(void) {
    if (g_settings.language[0]) return g_settings.language;
    const char *l = getenv("LC_ALL");
    if (!l || !*l) l = getenv("LC_MESSAGES");
    if (!l || !*l) l = getenv("LANG");
    static const struct { const char *pre, *code; } map[] = {
        {"ja", "ja"}, {"fr_CA", "fr-CA"}, {"fr", "fr"}, {"de", "de"}, {"it", "it"}, {"es_MX", "es-419"},
        {"es_AR", "es-419"}, {"es", "es"}, {"en_GB", "en-GB"}, {"en", "en-US"}, {"nl", "nl"}, {"pt", "pt"},
        {"ru", "ru"}, {"ko", "ko"}, {"zh_TW", "zh-Hant"}, {"zh_HK", "zh-Hant"}, {"zh", "zh-Hans"},
    };
    if (l)
        for (unsigned i = 0; i < sizeof map / sizeof map[0]; i++)
            if (!strncmp(l, map[i].pre, strlen(map[i].pre))) return map[i].code;
    return "en-US";
}
