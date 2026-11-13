// Small services: parental control, add-on content, and other mostly-stubbed interfaces.
#include <string.h>

#include "../hle.h"
#include "../ipc.h"

static void ok_logger(Service *s, IpcReq *req, IpcResp *resp) {
    LOG("[svc] %s cmd %u (ok)\n", s->name, req->cmd);
    resp_size(resp, 0x10);
}

static uint32_t new_event_handle(void) {
    uint32_t w, r;
    kernel_create_event_pair(&w, &r);
    return r;
}

// ------------------------------------------------------------------ pctl
static void pctl_service(Service *s, IpcReq *req, IpcResp *resp) {
    (void)s;
    switch (req->cmd) {
    case 1031: case 1035: case 1018: OUT(uint8_t, 0) = 0; resp_size(resp, 1); break;  // restrictions off
    case 1032: OUT(uint32_t, 0) = 0; resp_size(resp, 4); break;
    default: LOG("[pctl] IParentalControlService cmd %u (ok)\n", req->cmd); resp_size(resp, 0x10);
    }
}

static void pctl_root(Service *s, IpcReq *req, IpcResp *resp) {
    (void)s;
    if (req->cmd == 0 || req->cmd == 1)
        ipc_return_object(resp, service_new("IParentalControlService", pctl_service, NULL));
}
SERVICE("pctl", pctl) { pctl_root(s, req, resp); }
SERVICE("pctl:s", pctl_s) { pctl_root(s, req, resp); }
SERVICE("pctl:a", pctl_a) { pctl_root(s, req, resp); }
SERVICE("pctl:r", pctl_r) { pctl_root(s, req, resp); }

// ------------------------------------------------------------------ aoc:u (add-on content: the DLC in aoc/)
// DLC n is title <application id> + 0x1000 + n; the installer extracts each pack to aoc/<title id>/ (lower-case hex),
// which services/fs.c serves for OpenDataStorageByDataId. Command IDs as on Switchbrew (aoc:u).
#include <dirent.h>
#include <stdlib.h>
#define AOC_BASE 0x01000B900D8B1000ull  // (installer/known.py APP_TITLE + 0x1000)
extern const char *g_aoc_dir;  // main.c

static int aoc_indices(uint32_t *out, int max) {
    static int n = -1;
    static uint32_t idx[64];
    if (n < 0) {
        n = 0;
        DIR *d = g_aoc_dir ? opendir(g_aoc_dir) : NULL;
        struct dirent *e;
        while (d && (e = readdir(d)) && n < 64) {
            char *end;
            unsigned long long id = strtoull(e->d_name, &end, 16);
            if (*end || id <= AOC_BASE || id > AOC_BASE + 0x7ff) continue;
            idx[n++] = (uint32_t)(id - AOC_BASE);
        }
        if (d) closedir(d);
        for (int i = 1; i < n; i++)  // (sorted, small)
            for (int j = i; j > 0 && idx[j - 1] > idx[j]; j--) { uint32_t t = idx[j]; idx[j] = idx[j - 1]; idx[j - 1] = t; }
        LOG("[aoc] %d add-on content pack(s) installed\n", n);
    }
    for (int i = 0; out && i < n && i < max; i++) out[i] = idx[i];
    return n;
}

SERVICE("aoc:u", aoc_u) {
    (void)s;
    switch (req->cmd) {
    case 0: case 2: OUT(uint32_t, 0) = (uint32_t)aoc_indices(NULL, 0); resp_size(resp, 4); break;  // CountAddOnContent
    case 1: case 3: {  // ListAddOnContent(offset, count) -> B buffer of u32 indices; returns how many were written
        int32_t off = IN(int32_t, 0), cnt = IN(int32_t, 4);
        IpcBuf *b = out_buf(req, 0);
        uint32_t all[64];
        int n = aoc_indices(all, 64), w = 0;
        int max = b ? (int)(b->size / 4) : 0;
        for (int i = off; i < n && w < cnt && w < max; i++) ((uint32_t *)(uintptr_t)b->addr)[w++] = all[i];
        OUT(uint32_t, 0) = (uint32_t)w;
        resp_size(resp, 4);
        break;
    }
    case 4: case 5: OUT(uint64_t, 0) = AOC_BASE; resp_size(resp, 8); break;  // GetAddOnContentBaseId
    case 6: case 7: break;                                                    // PrepareAddOnContent
    case 8: resp->copy_handles[resp->ncopy++] = new_event_handle(); break;    // GetAddOnContentListChangedEvent
    default: ok_logger(s, req, resp);
    }
}
