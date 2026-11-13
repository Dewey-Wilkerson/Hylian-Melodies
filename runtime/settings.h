// Player settings (hylian-melodies.ini next to the executable). Grows in M6/M7/M10.
#pragma once
#include <stdbool.h>

typedef struct {
    double volume;          // master volume 0..1
    bool reverb;            // (audio renderer only; unused by this game)
    int audio_latency_ms;   // extra output latency compensation (rhythm calibration, M6)
    char language[8];       // the game's language code, e.g. en-US ("language" in the ini; default: system)
} Settings;

extern Settings g_settings;
void settings_load(void);
const char *settings_language(void);
