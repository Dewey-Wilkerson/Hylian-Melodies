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

// ------------------------------------------------------------------ saving
// The file is the player's: comments, unknown keys and lines the menu doesn't manage are kept. A changed key replaces
// its line in place (the first uncommented "key = ...", else the commented example "# key = ..." of the default file,
// keeping that line's trailing comment); a key with no line at all goes at the end. Written to a .tmp file, then
// renamed over the old one (a crash leaves the old file or the new one, never half of one).
static unsigned g_changed;
static char *g_binding_lines;  // (NULL: the file's key./pad. lines stay as they are)

void settings_changed(unsigned which) { g_changed |= which; }

void settings_set_binding_lines(const char *lines) {
    free(g_binding_lines);
    g_binding_lines = strdup(lines ? lines : "");
}

static const struct { unsigned bit; const char *key; } managed[] = {
    {SET_FULLSCREEN, "fullscreen"}, {SET_UPSCALE_FILTER, "upscale_filter"}, {SET_SHOW_FPS, "show_fps"},
    {SET_FRAME_PACING, "frame_pacing"}, {SET_VOLUME, "volume"},
};
#define NMANAGED (sizeof managed / sizeof managed[0])

static void value_text(unsigned bit, char *out, size_t cap) {
    switch (bit) {
    case SET_FULLSCREEN: snprintf(out, cap, "%d", g_settings.fullscreen); break;
    case SET_UPSCALE_FILTER: snprintf(out, cap, "%d", g_settings.upscale_filter); break;
    case SET_SHOW_FPS: snprintf(out, cap, "%d", g_settings.show_fps); break;
    case SET_FRAME_PACING: snprintf(out, cap, "%d", g_settings.frame_pacing); break;
    case SET_VOLUME: snprintf(out, cap, "%.2f", g_settings.volume); break;
    }
}

// Which line is key's: 2 = "key = ...", 1 = "# key = ...", 0 = neither. *after: just past the '='.
static int line_is(const char *l, const char *key, const char **after) {
    const char *p = l;
    while (*p == ' ' || *p == '\t') p++;
    int kind = 2;
    if (*p == '#') {
        kind = 1;
        p++;
        while (*p == ' ' || *p == '\t') p++;
    }
    size_t n = strlen(key);
    if (strncmp(p, key, n)) return 0;
    p += n;
    while (*p == ' ' || *p == '\t') p++;
    if (*p != '=') return 0;
    *after = p + 1;
    return kind;
}

static bool is_binding_line(const char *l) {
    while (*l == ' ' || *l == '\t') l++;
    return !strncmp(l, "key.", 4) || !strncmp(l, "pad.", 4);
}

bool settings_save_to(const char *path) {
    // the old file's lines
    char **lines = NULL;
    size_t n = 0, cap = 0;
    FILE *f = fopen(path, "r");
    if (f) {
        char buf[1024];
        while (fgets(buf, sizeof buf, f)) {
            buf[strcspn(buf, "\r\n")] = 0;
            if (n == cap) lines = realloc(lines, (cap = cap ? cap * 2 : 64) * sizeof *lines);
            lines[n++] = strdup(buf);
        }
        fclose(f);
    }
    // where each changed key goes
    long at[NMANAGED];
    for (size_t k = 0; k < NMANAGED; k++) {
        at[k] = -1;
        if (!(g_changed & managed[k].bit)) continue;
        int best = 0;
        for (size_t i = 0; i < n; i++) {
            const char *after;
            int kind = line_is(lines[i], managed[k].key, &after);
            if (kind > best) best = kind, at[k] = (long)i;
            if (kind == 2) break;
        }
    }
    char tmp[1100];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *o = fopen(tmp, "w");
    if (!o) goto fail;
    bool bindings_done = !g_binding_lines;
    for (size_t i = 0; i < n; i++) {
        if (g_binding_lines && is_binding_line(lines[i])) {
            if (!bindings_done) fputs(g_binding_lines, o), bindings_done = true;  // (in place of the first old one)
            continue;
        }
        size_t k = 0;
        while (k < NMANAGED && at[k] != (long)i) k++;
        if (k == NMANAGED) { fprintf(o, "%s\n", lines[i]); continue; }
        const char *after;
        line_is(lines[i], managed[k].key, &after);
        // the old value, then what follows it (spacing and a trailing comment) is kept
        const char *p = after;
        while (*p == ' ' || *p == '\t') p++;
        while (*p && *p != ' ' && *p != '\t' && *p != '#') p++;
        char v[32];
        value_text(managed[k].bit, v, sizeof v);
        fprintf(o, "%s = %s%s\n", managed[k].key, v, p);
    }
    bool header = false;
    for (size_t k = 0; k < NMANAGED; k++) {
        if (!(g_changed & managed[k].bit) || at[k] >= 0) continue;
        char v[32];
        value_text(managed[k].bit, v, sizeof v);
        if (!header) fprintf(o, "\n# --- set in the menu\n"), header = true;
        fprintf(o, "%s = %s\n", managed[k].key, v);
    }
    if (!bindings_done && g_binding_lines[0]) fprintf(o, "\n# --- controls (set in the menu; docs/controls.md)\n%s", g_binding_lines);
    bool ok = !ferror(o);
    ok = (fclose(o) == 0) && ok;
    if (!ok || rename(tmp, path)) { remove(tmp); goto fail; }
    for (size_t i = 0; i < n; i++) free(lines[i]);
    free(lines);
    g_changed = 0;
    free(g_binding_lines);
    g_binding_lines = NULL;
    return true;
fail:
    for (size_t i = 0; i < n; i++) free(lines[i]);
    free(lines);
    return false;
}

bool settings_save(void) {
    if (!g_changed && !g_binding_lines) return true;
    return settings_save_to("hylian-melodies.ini");
}
