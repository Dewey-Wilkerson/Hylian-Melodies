// runtime/hle/bntx.c: header fields, the name dictionary's bit, and every pixel stored once and read back.
#include <stdio.h>
#include <string.h>

#include "hle/bntx.h"

static unsigned u32(const uint8_t *p) { unsigned v; memcpy(&v, p, 4); return v; }

int main(void) {
    static uint8_t rgba[4096], out[BNTX_RGBA32_SIZE], seen[4096];
    for (int i = 0; i < 4096; i++) rgba[i] = (uint8_t)(i * 7 + (i >> 8));
    if (bntx_rgba32("this_name_is_too_long", rgba, out)) { puts("long name accepted"); return 1; }
    if (bntx_rgba32("HM_ExitButton", rgba, out) != BNTX_RGBA32_SIZE) { puts("no file"); return 1; }
    if (memcmp(out, "BNTX", 4) || u32(out + 0x1c) != BNTX_RGBA32_SIZE || memcmp(out + 0x1f0, "BRTI", 4) ||
        memcmp(out + 0xff0, "BRTD", 4) || memcmp(out + 0x2000, "_RLT", 4)) { puts("bad blocks"); return 1; }
    if (u32(out + 0x214) != 32 || u32(out + 0x218) != 32 || u32(out + 0x20c) != 0x0b01) { puts("bad info"); return 1; }
    if (memcmp(out + 0x1ba, "HM_ExitButton", 14)) { puts("bad name"); return 1; }
    if (u32(out + 0x1e0) != 1) { puts("bad dictionary bit"); return 1; }  // ('n' = 0x6e: bit 1 is its first set bit)
    // block linear, 128-byte rows, 4-GOB blocks: each texel's 4 bytes once, in GOB order
    for (int y = 0; y < 32; y++)
        for (int x = 0; x < 32; x++) {
            int bx = x * 4, gob = ((y / 8 / 4 * 2 + bx / 64) * 4 + y / 8 % 4) * 512;
            int in = (bx % 64) / 32 * 256 + (y % 8) / 2 * 64 + (bx % 32) / 16 * 32 + (y % 2) * 16 + bx % 16;
            if (memcmp(out + 0x1000 + gob + in, rgba + (y * 32 + x) * 4, 4)) { printf("texel %d,%d\n", x, y); return 1; }
            for (int k = 0; k < 4; k++) if (seen[gob + in + k]++) { puts("texel stored twice"); return 1; }
        }
    puts("ok");
    return 0;
}
