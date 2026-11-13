// Rumble placeholder until M7: accepted and ignored.
#include "../rumble.h"
static bool permitted = true;
void input_rumble_send(uint32_t handle, const RumbleValue *value) { (void)handle; (void)value; }
RumbleValue input_rumble_get(uint32_t handle) { (void)handle; return (RumbleValue){0}; }
void input_rumble_permit(bool p) { permitted = p; }
bool input_rumble_permitted(void) { return permitted; }
void input_rumble_poll(void) {}
