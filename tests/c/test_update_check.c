// Harness for runtime/update_check.c (tests/test_update_check.py).
//   test_update_check parse <text>          -> "a.b.c" or "no"
//   test_update_check newer <a> <b>         -> "yes" / "no"
//   test_update_check tag <file>            -> the release's tag_name or "no"
//   test_update_check check <version>       -> runs the check as the game does (HM_UPDATE_URL), prints the newer
//                                              version or "none" (waits up to 5 s)
//   test_update_check run                   -> starts the installer as the update button does: "terminal",
//                                              "browser" or "nothing"
//   test_update_check desktop               -> Gaming Mode's switch: "gaming"/"desktop", then "written" or "no";
//                                              at exit the switch runs (steamos-session-select on PATH)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "settings.h"
#include "update_check.h"

static const char *g_ver = "0.3.0";
const char *hm_version(void) { return g_ver; }

int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1], "parse")) {
        int v[3];
        if (update_version_parse(argv[2], v)) printf("%d.%d.%d\n", v[0], v[1], v[2]);
        else puts("no");
    } else if (argc == 4 && !strcmp(argv[1], "newer")) {
        puts(update_version_newer(argv[2], argv[3]) ? "yes" : "no");
    } else if (argc == 3 && !strcmp(argv[1], "tag")) {
        static char buf[1 << 16];
        FILE *f = fopen(argv[2], "rb");
        if (!f) return 2;
        buf[fread(buf, 1, sizeof buf - 1, f)] = 0;
        fclose(f);
        char tag[32];
        puts(update_tag_from_json(buf, tag, sizeof tag) ? tag : "no");
    } else if (argc == 3 && !strcmp(argv[1], "check")) {
        g_ver = argv[2];
        g_settings.check_updates = true;  // (off by default)
        update_check_start();
        for (int i = 0; i < 50 && !update_check_newer(); i++) usleep(100000);
        puts(update_check_newer() ? update_check_newer() : "none");
    } else if (argc == 2 && !strcmp(argv[1], "run")) {
        static const char *const what[] = {"nothing", "terminal", "browser"};
        puts(what[update_run_installer()]);
    } else if (argc == 2 && !strcmp(argv[1], "desktop")) {
        puts(update_gaming_mode() ? "gaming" : "desktop");
        puts(update_switch_to_desktop_at_exit() ? "written" : "no");
    } else {
        return 2;
    }
    return 0;
}
