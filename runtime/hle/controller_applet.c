// The controller-support applet ("connect a controller"): the game shows it when it finds no controller. On the PC the
// player's pad or keyboard is always player 1, so the applet returns at once: one player, player 1 selected.
#include <string.h>

#include "../hle.h"

// Result nn::hid::ShowControllerSupport(ControllerSupportResultInfo *out, const ControllerSupportArg &arg)
// ControllerSupportResultInfo: int8 player count, 3 bytes padding, uint32 selected npad id.
HLE_FUNC("_ZN2nn3hid21ShowControllerSupportEPNS0_27ControllerSupportResultInfoERKNS0_20ControllerSupportArgE",
         hid_show_controller_support) {
    uint8_t *out = (uint8_t *)(uintptr_t)c->x[0];
    if (out) {
        memset(out, 0, 8);
        out[0] = 1;  // players
        uint32_t id = 0;  // npad id No1
        memcpy(out + 4, &id, 4);
    }
    LOG("[hid] controller applet: player 1 connected\n");
    c->x[0] = RES_OK;
}
