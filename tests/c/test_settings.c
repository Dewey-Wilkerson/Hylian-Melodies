// Harness for runtime/settings.c's saving (tests/test_settings_save.py): loads <path>, applies changes from the
// command line, saves into <path>.
//   test_settings <path> [fullscreen=1] [upscale_filter=2] [frame_pacing=0]
//                        [bindings=<text with \n>]
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "settings.h"

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    const char *path = argv[1];
    for (int i = 2; i < argc; i++) {
        char *eq = strchr(argv[i], '=');
        if (!eq) return 2;
        *eq = 0;
        const char *k = argv[i], *v = eq + 1;
        if (!strcmp(k, "fullscreen")) g_settings.fullscreen = atoi(v), settings_changed(SET_FULLSCREEN);
        else if (!strcmp(k, "upscale_filter")) g_settings.upscale_filter = atoi(v), settings_changed(SET_UPSCALE_FILTER);
        else if (!strcmp(k, "frame_pacing")) g_settings.frame_pacing = atoi(v), settings_changed(SET_FRAME_PACING);
        else if (!strcmp(k, "bindings")) {
            char t[4096], *o = t;
            for (const char *p = v; *p && o < t + sizeof t - 1; p++) {
                if (p[0] == '\\' && p[1] == 'n') *o++ = '\n', p++;
                else *o++ = *p;
            }
            *o = 0;
            settings_set_binding_lines(t);
        } else return 2;
    }
    return settings_save_to(path) ? 0 : 1;
}
