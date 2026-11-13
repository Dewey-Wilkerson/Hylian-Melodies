#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "settings.h"

Settings g_settings = {.volume = 1.0, .reverb = true, .audio_latency_ms = 0};

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
