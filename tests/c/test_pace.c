// Harness for runtime/nvn/pace.c (tests/test_pace.py): runs the frame pacer on a simulated clock, with stubs for the
// runtime it reads. Each simulated frame: the game works <work> ms (CPU time), presents (pace_frame), then the display
// cadence waits for the next 60 Hz slot as objects.c does - counted as blocked, or not (<uncounted>: the old bug).
//   test_pace <frames> <work ms> [uncounted] [switch] [interval2]
// interval2: the game asks for present interval 2 (its own 30 fps mode) - frames 33 ms apart, on time.
// ownwait: the game waits out a second vsync itself each frame (this game's own 30 fps mode: blocked, not late).
// gpubound: each frame waits ~31 ms in the present for the GPU (blocked, but late: a GPU-bound machine).
// switch: one frame in the middle is presented from another thread (a movie's frames).
// Prints "slow=<0|1> held=<frames held>" and the pacer's log lines on stderr.
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "nvn/pace.h"

static uint64_t clock_ns = 1000000000ull;
static __thread uint64_t cpu_ns;  // (per thread, as CLOCK_THREAD_CPUTIME_ID)
uint64_t plat_now_ns(void) { return clock_ns; }
uint64_t plat_thread_cpu_ns(void) { return cpu_ns; }
void plat_sleep_until_ns(uint64_t t) { if (t > clock_ns) clock_ns = t; }

__thread uint64_t g_blocked_ns, g_rq_wait_ns, g_rq_lock_ns, g_submit_ns, g_gpu_wait_ns, g_present_ns, g_hooks_ns;
volatile uint64_t g_vsync_count, g_vsync_ns;
uint64_t rq_render_cpu_ns(void) { return 0; }
int64_t pace_gpu_ns(void) { return -1; }
void slow_frame_present(uint64_t now_ns, uint64_t thread_cpu_ns) { (void)now_ns, (void)thread_cpu_ns; }
int game_in_play(void) { return 1; }
bool world_on_screen(void) { return true; }
const char *game_level_name(void) { return "Stage"; }
uint64_t game_camera_zone(void) { return 1; }

static int uncounted;
int g_present_interval = 1;  // (objects.c's)
static void display_cadence(void) {  // (objects.c's)
    static uint64_t next;
    uint64_t period = 16666667ull * (uint64_t)g_present_interval, now = plat_now_ns();
    if (!next || now > next + period) { next = now; return; }
    next += period;
    if (next > now) {
        plat_sleep_until_ns(next);
        if (!uncounted) g_blocked_ns += plat_now_ns() - now;
    }
}

static uint64_t work_ns;
static int ownwait, gpubound;
static void frame(void) {
    clock_ns += work_ns, cpu_ns += work_ns;
    if (ownwait) {  // (a kernel wait to ~33 ms a frame: kernel.c counts it)
        uint64_t w = 33233333ull - work_ns;
        clock_ns += w, g_blocked_ns += w;
    }
    if (gpubound) clock_ns += 31000000ull, g_blocked_ns += 31000000ull, g_present_ns += 31000000ull;
    pace_frame();
    display_cadence();
}
static void *other_thread(void *a) { (void)a; cpu_ns = 5; frame(); return NULL; }

int main(int argc, char **argv) {
    if (argc < 3) return 2;
    long n = atol(argv[1]);
    work_ns = (uint64_t)(atof(argv[2]) * 1e6);
    int sw = 0;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "uncounted")) uncounted = 1;
        else if (!strcmp(argv[i], "switch")) sw = 1;
        else if (!strcmp(argv[i], "interval2")) g_present_interval = 2;
        else if (!strcmp(argv[i], "ownwait")) ownwait = 1;
        else if (!strcmp(argv[i], "gpubound")) gpubound = 1;
        else return 2;
    }
    cpu_ns = 7000000000ull;  // (the game thread has run a while: another thread's clock is far behind)
    long held = 0;
    for (long i = 0; i < n; i++) {
        if (sw && i == n / 2) {
            pthread_t t;
            pthread_create(&t, NULL, other_thread, NULL);
            pthread_join(t, NULL);
        } else frame();
        held += pace_is_slow();
    }
    printf("slow=%d held=%ld\n", pace_is_slow(), held);
    return 0;
}
