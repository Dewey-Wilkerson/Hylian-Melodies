// The port's own update check (update_check.h). The request is made by the system's curl, run as a child process:
// no TLS or HTTP library linked into the game, and nothing about the player is sent (GitHub sees an ordinary
// unauthenticated request with the user agent "Hylian-Melodies/<version>"). Any failure (no curl, no network, an
// answer we can't read) just means no notice.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE  // (strcasestr; the game's build defines it already)
#endif
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rt.h"
#include "settings.h"
#include "update_check.h"

#define REPO_URL "https://github.com/Dewey-Wilkerson/Hylian-Melodies"
#define RELEASES_URL "https://api.github.com/repos/Dewey-Wilkerson/Hylian-Melodies/releases/latest"
// what the terminal runs (sh -c): the README's install line, then a pause so the window doesn't vanish on an error
#define INSTALL_CMD                                                                                                    \
    "curl -fsSL " REPO_URL "/releases/latest/download/install.sh | sh; s=$?; echo; "                               \
    "[ $s -eq 0 ] || echo \"The installer stopped (exit status $s).\"; "                                            \
    "printf 'Press Enter to close this window. '; read -r _"

const char *hm_version(void);  // runtime/main.c

bool update_version_parse(const char *s, int v[3]) {
    if (!s) return false;
    if (*s == 'v' || *s == 'V') s++;
    int n = 0;
    v[0] = v[1] = v[2] = 0;
    while (n < 3) {
        if (*s < '0' || *s > '9') return false;
        long x = strtol(s, (char **)&s, 10);
        if (x > 99999) return false;
        v[n++] = (int)x;
        if (*s != '.') break;
        s++;
    }
    return *s == 0 || *s == '-' || *s == '+';  // (a pre-release or build suffix is ignored)
}

bool update_version_newer(const char *a, const char *b) {
    int x[3], y[3];
    if (!update_version_parse(a, x) || !update_version_parse(b, y)) return false;
    for (int i = 0; i < 3; i++)
        if (x[i] != y[i]) return x[i] > y[i];
    return false;
}

bool update_tag_from_json(const char *json, char *out, size_t cap) {
    const char *p = json ? strstr(json, "\"tag_name\"") : NULL;
    if (!p) return false;
    p += 10;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p++ != ':') return false;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p++ != '"') return false;
    size_t n = 0;
    while (p[n] && p[n] != '"' && p[n] != '\\') n++;
    if (p[n] != '"' || n == 0 || n >= cap) return false;
    memcpy(out, p, n);
    out[n] = 0;
    return true;
}

static char g_newer[32];
static atomic_int g_found;    // 1: g_newer holds a newer version
static atomic_int g_started;

const char *update_check_newer(void) { return atomic_load(&g_found) ? g_newer : NULL; }

#if defined(__linux__) || defined(__APPLE__)
#include <fcntl.h>
#include <sys/stat.h>
#include <pthread.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

// -> the response body (malloc'd, NUL-terminated) or NULL
static char *fetch(const char *url) {
    char agent[64];
    snprintf(agent, sizeof agent, "Hylian-Melodies/%s", hm_version());
    char *argv[] = {"curl", "-fsSL", "--proto", "=https,file", "--connect-timeout", "5", "--max-time", "10",
                    "-H", "Accept: application/vnd.github+json", "-A", agent, (char *)url, NULL};
    int fd[2];
    if (pipe(fd)) return NULL;
    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_adddup2(&fa, fd[1], 1);
    posix_spawn_file_actions_addclose(&fa, fd[0]);
    posix_spawn_file_actions_addclose(&fa, fd[1]);
    posix_spawn_file_actions_addopen(&fa, 2, "/dev/null", O_WRONLY, 0);
    pid_t pid;
    int rc = posix_spawnp(&pid, "curl", &fa, NULL, argv, environ);
    posix_spawn_file_actions_destroy(&fa);
    close(fd[1]);
    if (rc) {
        close(fd[0]);
        LOG("[update] curl not found: no update check\n");
        return NULL;
    }
    size_t cap = 1 << 16, n = 0;  // (a release's JSON is a few KiB; more than this is not one)
    char *buf = malloc(cap + 1);
    ssize_t r;
    while (buf && n < cap && (r = read(fd[0], buf + n, cap - n)) > 0) n += (size_t)r;
    close(fd[0]);
    int st = 0;
    waitpid(pid, &st, 0);
    if (!buf || !WIFEXITED(st) || WEXITSTATUS(st)) {
        LOG("[update] check failed (curl exit %d)\n", WIFEXITED(st) ? WEXITSTATUS(st) : -1);
        free(buf);
        return NULL;
    }
    buf[n] = 0;
    return buf;
}

static void *check_thread(void *arg) {
    (void)arg;
    const char *url = getenv("HM_UPDATE_URL");  // (tests: a file:// URL of a release JSON)
    char *body = fetch(url && *url ? url : RELEASES_URL);
    char tag[32];
    if (body && update_tag_from_json(body, tag, sizeof tag)) {
        bool newer = update_version_newer(tag, hm_version());
        LOG("[update] latest release %s, this build %s%s\n", tag, hm_version(), newer ? ": update available" : "");
        if (newer) {
            snprintf(g_newer, sizeof g_newer, "%s", tag[0] == 'v' || tag[0] == 'V' ? tag + 1 : tag);
            atomic_store(&g_found, 1);
        }
    } else if (body) {
        LOG("[update] no version in the answer\n");
    }
    free(body);
    return NULL;
}

// ---- the installer in a terminal
// The player's terminal, desktop-agnostic (owner): xdg-terminal-exec (the freedesktop default-terminal launcher, which
// honours the player's choice), then $TERMINAL (with -e), then x-terminal-emulator (Debian's default), then the first
// of these common ones found. Each with how it takes a command (the arguments before "sh -c <command>").
static const struct { const char *exe, *args[3]; } terminals[] = {
    {"xdg-terminal-exec", {NULL}},
    {"x-terminal-emulator", {"-e", NULL}},
    {"konsole", {"-e", NULL}},
    {"ptyxis", {"--", NULL}},
    {"kgx", {"--", NULL}},
    {"gnome-terminal", {"--", NULL}},
    {"xfce4-terminal", {"-x", NULL}},
    {"mate-terminal", {"-x", NULL}},
    {"kitty", {NULL}},
    {"alacritty", {"-e", NULL}},
    {"foot", {NULL}},
    {"wezterm", {"start", "--", NULL}},
    {"xterm", {"-e", NULL}},
};

static bool on_path(const char *exe, char *out, size_t cap) {
    if (strchr(exe, '/')) {
        snprintf(out, cap, "%s", exe);
        return access(out, X_OK) == 0;
    }
    const char *path = getenv("PATH");
    for (const char *p = path ? path : "/usr/local/bin:/usr/bin:/bin"; *p;) {
        const char *e = strchr(p, ':');
        size_t n = e ? (size_t)(e - p) : strlen(p);
        if (n && n + strlen(exe) + 2 <= cap) {
            snprintf(out, cap, "%.*s/%s", (int)n, p, exe);
            if (access(out, X_OK) == 0) return true;
        }
        p += n + (e != NULL);
    }
    return false;
}

// The child's environment: ours, minus what the AppImage set for the game alone (its library folders, the folders
// pointing into the mounted image), so a terminal of the system's starts with the system's libraries.
static char **child_env(void) {
    const char *gd = getenv("HM_GAME_DIR");
    const char *m = gd ? strstr(gd, "/opt/hylian-melodies") : NULL;
    bool appimage = gd && strstr(gd, "/.mount_") && m;
    size_t n = 0;
    while (environ[n]) n++;
    char **env = calloc(n + 1, sizeof *env);
    if (!env) return environ;
    size_t w = 0;
    for (size_t i = 0; i < n; i++) {
        const char *v = environ[i];
        if (appimage && (!strncmp(v, "HM_GAME_DIR=", 12) || !strncmp(v, "HM_SUPPORT_DIR=", 15))) continue;
        if (appimage && !strncmp(v, "LD_LIBRARY_PATH=", 16)) {  // (only the entries inside the image go)
            size_t root = (size_t)(m - gd);
            char *keep = malloc(strlen(v) + 1);
            if (!keep) continue;
            strcpy(keep, "LD_LIBRARY_PATH=");
            for (const char *p = v + 16; *p;) {
                const char *e = strchr(p, ':');
                size_t len = e ? (size_t)(e - p) : strlen(p);
                if (len && !(len >= root && !strncmp(p, gd, root)))
                    snprintf(keep + strlen(keep), len + 2, "%s%.*s", keep[16] ? ":" : "", (int)len, p);
                p += len + (e != NULL);
            }
            if (keep[16]) env[w++] = keep;
            else free(keep);
            continue;
        }
        env[w++] = (char *)v;
    }
    return env;
}

static bool spawn_detached(char *const argv[]) {
    posix_spawn_file_actions_t fa;
    posix_spawnattr_t at;
    posix_spawn_file_actions_init(&fa);
    for (int fd = 0; fd < 3; fd++) posix_spawn_file_actions_addopen(&fa, fd, "/dev/null", fd ? O_WRONLY : O_RDONLY, 0);
    posix_spawnattr_init(&at);
#ifdef POSIX_SPAWN_SETSID
    posix_spawnattr_setflags(&at, POSIX_SPAWN_SETSID);  // (its own session: closing the game doesn't take it along)
#endif
    pid_t pid;
    char **env = child_env();
    int rc = posix_spawn(&pid, argv[0], &fa, &at, argv, env);
    posix_spawn_file_actions_destroy(&fa);
    posix_spawnattr_destroy(&at);
    return rc == 0;
}

// -> the number of arguments before "sh -c <command>" (in pre), or -1 when no terminal is found
static int find_terminal(char *exe, size_t cap, const char *pre[3], char *name, size_t ncap) {
    const char *term = getenv("TERMINAL");
    enum { N = sizeof terminals / sizeof *terminals };
    int order[N + 1], k = 0;
    order[k++] = 0;                      // xdg-terminal-exec
    if (term && *term) order[k++] = -1;  // $TERMINAL
    for (int i = 1; i < N; i++) order[k++] = i;
    for (int j = 0; j < k; j++) {
        int i = order[j];
        const char *n = i < 0 ? term : terminals[i].exe;
        if (!on_path(n, exe, cap)) continue;
        snprintf(name, ncap, "%s", n);
        int a = 0;
        if (i < 0) pre[a++] = "-e";  // (the common convention)
        else
            for (int x = 0; terminals[i].args[x]; x++) pre[a++] = terminals[i].args[x];
        return a;
    }
    return -1;
}

bool update_installer_available(void) {
    char exe[4096], name[256];
    const char *pre[3];
    return find_terminal(exe, sizeof exe, pre, name, sizeof name) >= 0 || on_path("xdg-open", exe, sizeof exe);
}

int update_run_installer(void) {
    const char *cmd = getenv("HM_UPDATE_INSTALLER");  // (tests: what the terminal runs)
    if (!cmd || !*cmd) cmd = INSTALL_CMD;
    char exe[4096], name[256];
    const char *pre[3];
    int n = find_terminal(exe, sizeof exe, pre, name, sizeof name);
    if (n >= 0) {
        char *argv[8];
        int a = 0;
        argv[a++] = exe;
        for (int i = 0; i < n; i++) argv[a++] = (char *)pre[i];
        argv[a++] = "sh";
        argv[a++] = "-c";
        argv[a++] = (char *)cmd;
        argv[a] = NULL;
        if (spawn_detached(argv)) {
            LOG("[update] installer started in %s\n", name);
            return UPDATE_RAN_TERMINAL;
        }
    }
    char *open[] = {exe, REPO_URL "/releases/latest", NULL};
    if (on_path("xdg-open", exe, sizeof exe) && spawn_detached(open)) {
        LOG("[update] no terminal found: the releases page opened in the browser\n");
        return UPDATE_RAN_BROWSER;
    }
    LOG("[update] no terminal and no xdg-open: the installer could not be started\n");
    return UPDATE_RAN_NOTHING;
}

// ---- Gaming Mode
bool update_gaming_mode(void) {
    const char *d = getenv("XDG_CURRENT_DESKTOP");
    if (d && strcasestr(d, "gamescope")) return true;  // (gamescope-session sets it)
    if (!getenv("GAMESCOPE_WAYLAND_DISPLAY")) return false;
    FILE *f = fopen("/etc/os-release", "r");  // (gamescope nested in a desktop session is not Gaming Mode: SteamOS only)
    char line[256];
    bool steamos = false;
    while (f && !steamos && fgets(line, sizeof line, f)) steamos = !strncmp(line, "ID=steamos", 10);
    if (f) fclose(f);
    return steamos;
}

bool update_desktop_switch_available(void) {
    char exe[4096];
    return on_path("steamos-session-select", exe, sizeof exe);
}

// A desktop entry's Exec argument, quoted (the Desktop Entry spec: in double quotes, \ before " ` $ \; then the
// string escaping of the file doubles every backslash)
static void exec_quote(char *out, size_t cap, const char *s) {
    size_t n = 0;
    if (cap < 3) return;
    out[n++] = '"';
    for (; *s && n + 6 < cap; s++) {
        if (strchr("\"`$\\", *s)) out[n++] = '\\', out[n++] = '\\';
        out[n++] = *s;
    }
    out[n++] = '"';
    out[n] = 0;
}

static bool g_switch;
static void switch_at_exit(void) {
    char exe[4096];
    char *argv[] = {exe, "plasma", NULL};
    fflush(stderr);
    if (on_path("steamos-session-select", exe, sizeof exe) && spawn_detached(argv))
        LOG("[update] switching to Desktop Mode\n");
    else
        LOG("[update] steamos-session-select could not be started\n");
    fflush(stderr);
}

bool update_switch_to_desktop_at_exit(void) {
    // what the desktop runs: this program again with --run-installer (the AppImage file itself for an AppImage, whose
    // copied executable needs the image's libraries)
    char self[4096] = "";
    const char *ai = getenv("APPIMAGE");
    if (ai && *ai == '/') snprintf(self, sizeof self, "%s", ai);
    else {
        ssize_t n = readlink("/proc/self/exe", self, sizeof self - 1);
        if (n <= 0) return false;
        self[n] = 0;
    }
    char dir[4096], path[4200];
    const char *x = getenv("XDG_CONFIG_HOME"), *home = getenv("HOME");
    if (x && *x == '/') snprintf(dir, sizeof dir, "%s/autostart", x);
    else if (home && *home == '/') snprintf(dir, sizeof dir, "%s/.config/autostart", home);
    else return false;
    char parent[4096];
    snprintf(parent, sizeof parent, "%s", dir);
    char *slash = strrchr(parent, '/');
    if (slash) *slash = 0, mkdir(parent, 0755);
    mkdir(dir, 0755);
    snprintf(path, sizeof path, "%s/hylian-melodies-update.desktop", dir);
    char qself[9000], qpath[9000];
    exec_quote(qself, sizeof qself, self);
    exec_quote(qpath, sizeof qpath, path);
    FILE *f = fopen(path, "w");
    if (!f) return false;
    fprintf(f, "[Desktop Entry]\n"
               "Type=Application\n"
               "Name=Hylian Melodies update\n"
               "Comment=Starts the Hylian Melodies installer once, after the switch from Gaming Mode; removes itself\n"
               "Exec=sh -c \"rm -f \\\\\"\\\\$1\\\\\"; exec \\\\\"\\\\$2\\\\\" --run-installer\" sh %s %s\n"
               "NoDisplay=true\n"
               "X-KDE-autostart-phase=2\n", qpath, qself);
    bool ok = !ferror(f);
    ok = !fclose(f) && ok;
    if (!ok) return false;
    LOG("[update] Desktop Mode will start the installer once (%s)\n", path);
    if (!g_switch) g_switch = true, atexit(switch_at_exit);
    return true;
}

static void installer_at_exit(void) {
    fflush(stderr);
    update_run_installer();
    fflush(stderr);
}

void update_run_installer_at_exit(void) {
    static atomic_int once;
    if (!atomic_exchange(&once, 1)) atexit(installer_at_exit);
}

void update_check_start(void) {
    int v[3];
    if (!g_settings.check_updates || atomic_exchange(&g_started, 1)) return;
    if (!update_version_parse(hm_version(), v)) {  // ("dev" builds have nothing to compare)
        LOG("[update] this build has no version (%s): no update check\n", hm_version());
        return;
    }
    pthread_t t;
    if (!pthread_create(&t, NULL, check_thread, NULL)) pthread_detach(t);
}
#else
// Windows: not written yet (the port is Linux first; the same check through curl.exe would do).
void update_check_start(void) { (void)g_started; }
int update_run_installer(void) { return UPDATE_RAN_NOTHING; }
bool update_installer_available(void) { return false; }
void update_run_installer_at_exit(void) {}
bool update_gaming_mode(void) { return false; }
bool update_desktop_switch_available(void) { return false; }
bool update_switch_to_desktop_at_exit(void) { return false; }
#endif
