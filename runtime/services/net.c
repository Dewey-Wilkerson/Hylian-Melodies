// Network services, always offline (docs/DECISIONS.md): nifm reports no connection, bsd (sockets) reports the
// network down. Command IDs follow Switchbrew's nifm and bsd pages.
#include <string.h>

#include "../hle.h"
#include "../ipc.h"

#define NIFM_NO_CONNECTION MAKE_RESULT(110, 300)  // (any failure: the game only needs "not connected")
#define BSD_ENETDOWN 100

static uint32_t new_event(void) {
    uint32_t w, r;
    kernel_create_event_pair(&w, &r);
    return r;
}

static void nifm_request(Service *s, IpcReq *req, IpcResp *resp) {
    (void)s;
    switch (req->cmd) {
    case 0: OUT(uint32_t, 0) = 1; resp_size(resp, 4); break;   // GetRequestState: free (not accepted)
    case 1: resp->result = NIFM_NO_CONNECTION; break;           // GetResult
    case 2:                                                     // GetSystemEventReadableHandles
        resp->copy_handles[resp->ncopy++] = new_event();
        resp->copy_handles[resp->ncopy++] = new_event();
        break;
    default: break;  // Cancel, Submit, SetRequirement*, SetConnectionConfirmationOption, ...: accepted, no effect
    }
}

static void nifm_general(Service *s, IpcReq *req, IpcResp *resp) {
    (void)s;
    switch (req->cmd) {
    case 1: memset(resp->data, 0, 16); resp_size(resp, 16); break;  // GetClientId
    case 4: ipc_return_object(resp, service_new("nifm:IRequest", nifm_request, NULL)); break;  // CreateRequest
    case 12: case 15: case 18: resp->result = NIFM_NO_CONNECTION; break;  // GetCurrentIpAddress, GetCurrentIpConfigInfo, GetInternetConnectionStatus
    case 17: case 20: case 21: OUT(uint8_t, 0) = 0; resp_size(resp, 1); break;  // IsWireless/IsEthernet enabled, IsAnyInternetRequestAccepted
    default: LOG("[nifm] IGeneralService cmd %u (ok)\n", req->cmd);
    }
}

SERVICE("nifm:u", nifm_u) {
    (void)s;
    switch (req->cmd) {
    case 4: case 5: ipc_return_object(resp, service_new("nifm:IGeneralService", nifm_general, NULL)); break;
    default: LOG("[nifm] cmd %u (ok)\n", req->cmd);
    }
}

// bsd: every call answers (ret, errno). RegisterClient and StartMonitoring succeed; sockets fail with ENETDOWN.
static void bsd(Service *s, IpcReq *req, IpcResp *resp) {
    (void)s;
    switch (req->cmd) {
    case 0: OUT(uint64_t, 0) = 0; resp_size(resp, 8); break;  // RegisterClient -> pid
    case 1: break;                                            // StartMonitoring
    default:
        OUT(int32_t, 0) = -1;
        OUT(uint32_t, 4) = BSD_ENETDOWN;
        resp_size(resp, 8);
        static int n;
        if (n++ < 8) LOG("[bsd] cmd %u -> network down\n", req->cmd);
    }
}
SERVICE("bsd:u", bsd_u) { bsd(s, req, resp); }
SERVICE("bsd:s", bsd_s) { bsd(s, req, resp); }
