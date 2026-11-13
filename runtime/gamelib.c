#include "gamelib.h"

extern const uint64_t main_fn_addrs[], sdk_fn_addrs[], main_fn_count, sdk_fn_count;
extern const GuestFn main_fn_ptrs[], sdk_fn_ptrs[];

const GameLibTables *gamelib_tables(void) {
    static const GameLibTables t = {main_fn_addrs, sdk_fn_addrs, main_fn_ptrs, sdk_fn_ptrs, &main_fn_count,
                                    &sdk_fn_count};
    return &t;
}
