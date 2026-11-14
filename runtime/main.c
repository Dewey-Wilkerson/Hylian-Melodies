// Hylian Melodies entry: load the modules, set up the kernel, run nn::init::Start on the main thread.
// Boot sequence after LAS Recomp's runtime/main.c (MIT, see THIRD_PARTY_NOTICES.md), without its start screen,
// in-place reboot and randomizer.
//
// Data is found next to the real executable (/proc/self/exe): romfs/, aoc/, exefs/main.npdm, profile/ (saves).
// HM_GAME_DIR overrides that folder (development). HM_HEADLESS=1 runs without a window (M4 boot traces).
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "hle.h"
#include "kernel.h"

const char *g_romfs_dir, *g_aoc_dir, *g_game_dir;

static void run_array(Cpu *c, uint64_t arr, uint64_t size) {
    for (uint64_t i = 0; i < size / 8; i++) {
        uint64_t fn = ((uint64_t *)arr)[i];
        if (fn) guest_call(c, fn);
    }
}

// nn::init::Start calls x2 right after nnosInitialize and x3 after nninitStartup, just before nnMain. rtld runs a
// module's DT_INIT (registers it with the SDK's libc, then runs its init_array); fall back to the array.
static void module_init(Cpu *c, Module *m) {
    LOG("init %s (DT_INIT %llx, %llu init_array entries)\n", m->name, (unsigned long long)m->init,
        (unsigned long long)(m->init_array_sz / 8));
    if (m->init) guest_call(c, m->init);
    else run_array(c, m->init_array, m->init_array_sz);
}
static void rtld_init_sdk(Cpu *c) { module_init(c, &g_modules[1]); }
static void rtld_init_main(Cpu *c) { module_init(c, &g_modules[0]); }

// Claim the guest address range before anything else maps there; on a collision, start again for a fresh layout.
__attribute__((constructor(101))) static void reserve_guest_space(void) {
    if (plat_reserve_guest(GUEST_LO, GUEST_HI)) return;
    const char *tries = getenv("HM_REEXEC");
    int n = tries ? atoi(tries) : 0;
    if (n >= 20) {
        fprintf(stderr, "FATAL: guest address range %llx-%llx is not free\n", GUEST_LO, GUEST_HI);
        exit(1);
    }
    char buf[16];
    snprintf(buf, sizeof buf, "%d", n + 1);
    setenv("HM_REEXEC", buf, 1);
    plat_exec(NULL);
    perror("re-exec");
    exit(1);
}

static const char *game_dir(void) {
    static char dir[PATH_MAX];
    const char *env = getenv("HM_GAME_DIR");
    if (env && *env) return realpath(env, dir) ? dir : env;
    ssize_t n = readlink("/proc/self/exe", dir, sizeof dir - 1);
    if (n <= 0) return ".";
    dir[n] = 0;
    char *slash = strrchr(dir, '/');
    if (slash) *slash = 0;
    return dir;
}

static char *join(const char *a, const char *b) {
    size_t n = strlen(a) + strlen(b) + 2;
    char *p = malloc(n);
    snprintf(p, n, "%s/%s", a, b);
    return p;
}

int g_headless;

// HM_DUMP_AT=<seconds>[,<seconds>...]: log every guest thread and what it waits on at those times (diagnostics).
static void *dump_timer(void *arg) {
    (void)arg;
    extern void kernel_dump_threads(const char *prefix);
    double prev = 0;
    for (const char *p = getenv("HM_DUMP_AT"); p && *p;) {
        double at = strtod(p, (char **)&p);
        if (at > prev) usleep((useconds_t)((at - prev) * 1e6));
        prev = at;
        LOG("[dump] at %.1f s\n", at);
        kernel_dump_threads("[dump]");
        if (*p == ',') p++; else break;
    }
    return NULL;
}

// HM_RUN_SECONDS=N: end a run (windowed or headless) after N seconds (test runs; the runtime takes SIGTERM).
static void *run_timer(void *arg) {
    sleep((unsigned)(uintptr_t)arg);
    extern void kernel_dump_threads(const char *prefix);
    kernel_dump_threads("[exit]");
    extern volatile uint64_t g_vsync_count;
    extern uint64_t renderer_present_count(void);
    LOG("[boot] run ended after %u s (HM_RUN_SECONDS): %llu frames presented, %llu vsyncs signalled\n",
        (unsigned)(uintptr_t)arg, (unsigned long long)renderer_present_count(), (unsigned long long)g_vsync_count);
    fflush(stderr);
    _exit(0);
    return NULL;
}

#ifndef HM_VERSION
#define HM_VERSION "dev"
#endif
const char *hm_version(void) { return HM_VERSION; }  // (VERSION, passed by tools/build_game.py)

int g_cli_fullscreen = -1;  // --fullscreen / --windowed (overrides the ini; runtime/nvn/vulkan/device.c)

static void usage(void) {
    fprintf(stderr, "usage: hylian-melodies [--fullscreen | --windowed]\n"
                    "  --fullscreen  borderless fullscreen at the desktop's resolution\n"
                    "  --windowed    a window (the default; or fullscreen = 1 in hylian-melodies.ini)\n");
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--fullscreen") || !strcmp(argv[i], "-f")) g_cli_fullscreen = 1;
        else if (!strcmp(argv[i], "--windowed") || !strcmp(argv[i], "-w")) g_cli_fullscreen = 0;
        else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) { usage(); return 0; }
        else { fprintf(stderr, "hylian-melodies: unknown option %s\n", argv[i]); usage(); return 2; }
    }
    plat_init();
    setvbuf(stderr, NULL, _IOLBF, 0);
    g_headless = getenv("HM_HEADLESS") && strcmp(getenv("HM_HEADLESS"), "0");
    if (getenv("HM_DUMP_AT")) {
        pthread_t t;
        if (!pthread_create(&t, NULL, dump_timer, NULL)) pthread_detach(t);
    }
    if (getenv("HM_RUN_SECONDS") && atoi(getenv("HM_RUN_SECONDS")) > 0) {
        pthread_t t;
        if (!pthread_create(&t, NULL, run_timer, (void *)(uintptr_t)atoi(getenv("HM_RUN_SECONDS")))) pthread_detach(t);
    }
    g_game_dir = game_dir();
    g_romfs_dir = join(g_game_dir, "romfs");
    g_aoc_dir = join(g_game_dir, "aoc");
    if (chdir(g_game_dir)) { perror(g_game_dir); return 1; }
    LOG("[boot] Hylian Melodies, game folder %s%s\n", g_game_dir, g_headless ? " (headless)" : "");

    if (!g_headless) {  // the window and graphics device first, so the guest heap can be the driver's memory before any
        // game thread runs (LAS Recomp: runtime/nvn/vulkan/exec.c backend_guest_heap_prepare)
        extern void ui_window_init(void) __attribute__((weak));
        extern void backend_guest_heap_prepare(void) __attribute__((weak));
        if (!ui_window_init) FATAL("this build has no window: run hylian-melodies-headless with HM_HEADLESS=1\n");
        ui_window_init();
        backend_guest_heap_prepare();
    }
    loader_load("exefs");
    kernel_init();
    dispatch_init();

    uint32_t stack_size = 0x100000;
    int prio = 44;
    FILE *f = fopen("exefs/main.npdm", "rb");
    if (f) {
        uint8_t meta[0x80];
        if (fread(meta, 1, sizeof meta, f) == sizeof meta && !memcmp(meta, "META", 4)) {
            prio = meta[0xE];
            stack_size = *(uint32_t *)(meta + 0x1C);
        }
        fclose(f);
    }
    LOG("main thread: prio %d, stack 0x%x\n", prio, stack_size);
    uint64_t start = loader_find_symbol("_ZN2nn4init5StartEmmPFvvES2_");
    if (!start) FATAL("nn::init::Start not found\n");
    uint64_t init_fn = hle_register("<rtld_init_sdk>", rtld_init_sdk);
    uint64_t fini_fn = hle_register("<rtld_init_main>", rtld_init_main);
    KThread *t = kernel_create_main_thread(start, stack_size, prio);
    kernel_run_main(t, t->handle, 0, init_fn, fini_fn);
    if (g_headless) {  // HM_HEADLESS_SECONDS=N: stop after N seconds (test runs; SIGTERM is taken by the runtime)
        const char *secs = getenv("HM_HEADLESS_SECONDS");
        if (secs && atoi(secs) > 0) {
            sleep((unsigned)atoi(secs));
            extern void kernel_dump_threads(const char *prefix);
            kernel_dump_threads("[exit]");
            extern uint64_t null_backend_presented(void) __attribute__((weak));
            extern uint64_t null_backend_executed(void) __attribute__((weak));
            LOG("[boot] headless run ended after %s s: %llu frames presented, %llu command lists run\n", secs,
                (unsigned long long)(null_backend_presented ? null_backend_presented() : 0),
                (unsigned long long)(null_backend_executed ? null_backend_executed() : 0));
            fflush(stderr);
            _exit(0);
        }
        for (;;) pause();
    }
    return ui_run();
}
