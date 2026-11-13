// Controllers at the nn::hid function level (as LAS Recomp's runtime/hle/input.c does, MIT; rewritten, smaller):
// player 1 (npad id 0) is a connected full-key controller. M4: no buttons are held; M7 feeds SDL3 gamepad and
// keyboard state into input_buttons / input_sticks before the game polls at the start of each frame.
#include <string.h>

#include "../hle.h"
#include "../kernel.h"

volatile uint64_t g_input_buttons;  // nn::hid NpadButton bits (M7)
volatile int32_t g_input_sticks[4];  // lx, ly, rx, ry in -32767..32767 (M7)
static int64_t sampling;

static void fill_state(Cpu *c) {
    uint8_t *s = (uint8_t *)(uintptr_t)c->x[0];
    uint32_t id = *(uint32_t *)(uintptr_t)c->x[1];
    memset(s, 0, 0x28);
    *(int64_t *)s = ++sampling;
    if (id != 0) return;  // only player 1; other ids report disconnected
    uint64_t b = g_input_buttons;
    int32_t lx = g_input_sticks[0], ly = g_input_sticks[1], rx = g_input_sticks[2], ry = g_input_sticks[3];
    if (lx < -16000) b |= 1ull << 16;  // stick directions as buttons, as the SDK reports them
    if (ly > 16000) b |= 1ull << 17;
    if (lx > 16000) b |= 1ull << 18;
    if (ly < -16000) b |= 1ull << 19;
    if (rx < -16000) b |= 1ull << 20;
    if (ry > 16000) b |= 1ull << 21;
    if (rx > 16000) b |= 1ull << 22;
    if (ry < -16000) b |= 1ull << 23;
    *(uint64_t *)(s + 8) = b;
    *(int32_t *)(s + 16) = lx;
    *(int32_t *)(s + 20) = ly;
    *(int32_t *)(s + 24) = rx;
    *(int32_t *)(s + 28) = ry;
    *(uint32_t *)(s + 32) = 1;  // attributes: IsConnected
}

HLE_FUNC("_ZN2nn3hid12GetNpadStateEPNS0_16NpadFullKeyStateERKj", hid_state_fullkey) { fill_state(c); }
HLE_FUNC("_ZN2nn3hid12GetNpadStateEPNS0_16NpadJoyDualStateERKj", hid_state_dual) { fill_state(c); }
HLE_FUNC("_ZN2nn3hid12GetNpadStateEPNS0_16NpadJoyLeftStateERKj", hid_state_left) { fill_state(c); }
HLE_FUNC("_ZN2nn3hid12GetNpadStateEPNS0_17NpadHandheldStateERKj", hid_state_handheld) { fill_state(c); }
HLE_FUNC("_ZN2nn3hid12GetNpadStateEPNS0_17NpadJoyRightStateERKj", hid_state_right) { fill_state(c); }

HLE_FUNC("_ZN2nn3hid15GetNpadStyleSetERKj", hid_style_set) {
    uint32_t id = *(uint32_t *)(uintptr_t)c->x[0];
    c->x[0] = id == 0 ? 1 : 0;  // FullKey for player 1, nothing else
}

// Vibration (rumble arrives in M7 through runtime/rumble.h): devices exist, values are accepted.
HLE_FUNC("_ZN2nn3hid25InitializeVibrationDeviceERKNS0_21VibrationDeviceHandleE", hid_init_vibration) { (void)c; }
HLE_FUNC("_ZN2nn3hid25GetVibrationDeviceHandlesEPNS0_21VibrationDeviceHandleEiRKjNS_4util10BitFlagSetILi32ENS0_12NpadStyleTagEEE",
         hid_vibration_handles) {
    uint32_t *out = (uint32_t *)(uintptr_t)c->x[0];
    int n = (int)c->x[1] < 2 ? (int)c->x[1] : 2;
    uint32_t id = *(uint32_t *)(uintptr_t)c->x[2];
    for (int i = 0; i < n; i++) out[i] = 3u | ((id & 0xFF) << 8) | ((uint32_t)i << 16);
    c->x[0] = (uint64_t)(n > 0 ? n : 0);
}
HLE_FUNC("_ZN2nn3hid22GetVibrationDeviceInfoEPNS0_19VibrationDeviceInfoERKNS0_21VibrationDeviceHandleE", hid_vibration_info) {
    uint32_t *out = (uint32_t *)(uintptr_t)c->x[0];
    uint32_t h = *(uint32_t *)(uintptr_t)c->x[1];
    out[0] = 1;            // device type: linear resonant actuator
    out[1] = (h >> 16) & 1 ? 2 : 1;  // position: right / left
}
HLE_FUNC("_ZN2nn3hid18SendVibrationValueERKNS0_21VibrationDeviceHandleERKNS0_14VibrationValueE", hid_send_vibration) {
    (void)c;
}
HLE_FUNC("_ZN2nn3hid20IsVibrationPermittedEv", hid_vibration_permitted) { c->x[0] = 1; }
HLE_FUNC("_ZN2nn3hid16GetKeyboardStateEPNS0_13KeyboardStateE", hid_keyboard_state) {
    memset((void *)(uintptr_t)c->x[0], 0, 0x38);  // the game's own keyboard path stays idle: keys map to the pad (M7)
}
HLE_FUNC("_ZN2nn3hid13GetMouseStateEPNS0_10MouseStateE", hid_mouse_state) {
    memset((void *)(uintptr_t)c->x[0], 0, 0x28);
}
HLE_FUNC("_ZN2nn3hid14GetMouseStatesEPNS0_10MouseStateEi", hid_mouse_states) {
    memset((void *)(uintptr_t)c->x[0], 0, 0x28 * (c->x[1] > 0 ? c->x[1] : 0));
    c->x[0] = 0;
}
