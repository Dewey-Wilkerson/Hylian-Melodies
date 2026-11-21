// Host OS layer: everything the runtime needs that differs between systems. Linux is implemented
// (runtime/platform/linux.c); the macOS and Windows branches here and elsewhere in runtime/ are kept from LAS Recomp
// as the starting point for those ports (not built or tested yet).
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#include "platform/win_compat.h"
#elif defined(__linux__)
#include "platform/linux_compat.h"
#endif

#ifdef __cplusplus
extern "C" {
#endif

// ---- guest address space
// Claim [lo, hi) for the guest at exactly that address, readable/writable (pages may be backed lazily).
bool plat_reserve_guest(uint64_t lo, uint64_t hi);
// Make sure [addr, addr+size) inside the guest window is backed (before the OS itself writes there, e.g.
// file reads); a no-op where the whole window is backed from the start.
void plat_commit(uint64_t addr, uint64_t size);
// Every page of [lo, hi) back to zero (and unbacked), the window still claimed.
bool plat_reset_guest(uint64_t lo, uint64_t hi);
// Pages of [addr, addr+size) in the guest window the CPU wrote since the last call over them (write tracking: Windows
// MEM_WRITE_WATCH, Linux 6.7+ userfaultfd + PAGEMAP_SCAN), their addresses into pages[] (at most max), and the tracking
// reset for the range. Returns the count (max: maybe more), or -1 where there is no tracking (macOS, older Linux).
// Page size: *page.
int plat_written_pages(uint64_t addr, uint64_t size, uint64_t *pages, int max, uint64_t *page);
#ifdef __linux__
void plat_write_tracking_off(const char *why);  // tracking off from now on (unless HM_WRITE_TRACKING=1)
// Tracking of [lo, hi) by mprotect + SIGSEGV instead (memory the kernel's can't watch: the heap as driver memory);
// HM_SOFT_WRITE_TRACKING=0: off
void plat_soft_write_tracking(uint64_t lo, uint64_t hi);
// The OS is about to write [addr, addr+size) (a file read into guest memory): pages soft tracking protected are opened
// and count as written first (a write by the OS on a protected page would fail instead of faulting)
void plat_os_write(uint64_t addr, uint64_t size);
#else
static inline void plat_os_write(uint64_t addr, uint64_t size) { (void)addr, (void)size; }
#endif
#define PLAT_PAGE 0x4000ull  // largest page size we deal with (macOS 16K; multiple of Windows' 4K)

// ---- time
uint64_t plat_now_ns(void);                // monotonic
void plat_sleep_until_ns(uint64_t t);      // precise wait for plat_now_ns() >= t
void plat_thread_realtime(uint64_t period_ns);  // periodic timing thread (vsync): don't coalesce its timers
int plat_thread_realtime_check(uint64_t period_ns);  // (the calling thread, after a late wait) 0 the policy holds, 1 it was
                                                     // gone and is set again, -1 can't tell; only macOS looks
int plat_cpu_count(void);  // logical cores this process may run on (its affinity mask); 0 if unknown
void plat_thread_guest(int prio);  // a guest thread's host scheduling class from its Switch priority (lower = more urgent)
uint64_t plat_thread_cpu_ns(void);  // the calling thread's CPU time so far (user + system; diagnostics)
// The calling thread is one of the frame's critical threads: on Windows, no power throttling (EcoQoS) for it and, on a
// hybrid CPU, a preference for the performance cores (selected CPU sets; HM_PCORE=0: off). Elsewhere a no-op.
enum { PLAT_PERF_GAME, PLAT_PERF_RENDER, PLAT_PERF_VSYNC };
#ifdef _WIN32
void plat_thread_perf_core(int role);
#else
static inline void plat_thread_perf_core(int role) { (void)role; }
#endif

// ---- process
void plat_init(void);                                // first thing in main()
extern int plat_console_fd;                          // stderr as it was before the log took it (-1: none)
bool plat_exe_path(char *buf, size_t size);
void plat_exec(char *const argv[]);  // replace the process (NULL = same command line); returns only on failure
#if defined(_WIN32) || defined(__linux__)
void plat_terminate(void);  // end the process now, skipping DLL teardown (exit status 0)
#endif

// ---- diagnostics
// Name of the host function containing pc (guest functions are f_<addr>), NULL if unknown.
const char *plat_symbol(uint64_t pc, uint64_t *offset);
bool plat_module_name(uint64_t pc, char *out, size_t n);  // the file of the module (exe / library / driver) holding pc
void plat_print_backtrace(void);
void plat_fatal_notice(void);  // a fatal error is about to end the process: tell the user (Windows release: message box)
// Something the player should know that doesn't stop the game (a save that failed): the same dialog as
// plat_fatal_notice, as a warning, from its own thread so the game keeps running. Like it, only shown when started as
// the app (a terminal / test run has the log).
void plat_notice(const char *text);
void plat_crash_handler_install(void);  // per thread where the OS needs it (alternate signal stack)
void rt_fault_report(const char *what, uint64_t fault_addr, uint64_t host_pc, uint64_t host_lr) __attribute__((noreturn));

#ifdef __cplusplus
}
#endif
