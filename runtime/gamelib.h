// The lifted game code is linked into the executable; these are its function tables (recomp/gen.py <name>_table.c).
#pragma once
#include <stdint.h>
#include "cpu.h"

typedef struct {
    const uint64_t *main_addrs, *sdk_addrs;  // sorted guest addresses
    const GuestFn *main_fns, *sdk_fns;       // the functions at them
    const uint64_t *main_count, *sdk_count;
} GameLibTables;

const GameLibTables *gamelib_tables(void);
