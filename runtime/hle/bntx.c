// A texture file in the Switch's BNTX format, for the port's own art (runtime/hle/game_menu.c): one 32x32 RGBA8
// texture, no mipmaps. The game loads a loose texture from "data:/textures_bin/<name>.bntx" when its name isn't in
// its texture pack, so the port's art reaches the game's own sprites through a RomFS file (runtime/romfs_build.c).
//
// Layout (offsets in the file; pointers are file offsets, relocated by the loader through the _RLT table at the end):
//   0x000 BNTX file header        0x020 NX header (texture count, pointers to the info array, data block, dictionary)
//   0x198 info pointer array      0x1a0 _STRP string pool (an empty string, then the texture's name)
//   0x1c8 _DIC name dictionary    0x1f0 BRTI texture info (+0xa0 bytes for the loader's own objects, zeros)
//   0x490 mip offset array        0xff0 BRTD data block, pixels from 0x1000 (Tegra block-linear, 4-GOB blocks)
//   0x2000 _RLT relocation table  0x2068 end
#include "bntx.h"

#include <string.h>

static void w16(uint8_t *p, uint16_t v) { memcpy(p, &v, 2); }
static void w32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static void w64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }

// Byte offset of (x bytes, y rows) in a block-linear surface 128 bytes wide (2 GOBs), block height 4 GOBs (32 rows).
static size_t block_linear(size_t x, size_t y) {
    size_t gob_x = x / 64, gob_y = y / 8, block = gob_y / 4, in_block = gob_y % 4;
    size_t gob = ((block * 2 + gob_x) * 4 + in_block) * 512;
    size_t in_gob = ((x % 64) / 32) * 256 + ((y % 8) / 2) * 64 + ((x % 32) / 16) * 32 + (y % 2) * 16 + (x % 16);
    return gob + in_gob;
}

// The dictionary's bit for a single name: the first set bit, counting from bit 0 of the name's last character.
static uint32_t dic_bit(const char *name, size_t n) {
    for (uint32_t bit = 0; bit < 8 * n; bit++)
        if (((unsigned char)name[n - 1 - (bit >> 3)] >> (bit & 7)) & 1) return bit;
    return 0;
}

size_t bntx_rgba32(const char *name, const uint8_t *rgba, uint8_t out[BNTX_RGBA32_SIZE]) {
    size_t n = strlen(name);
    if (n == 0 || n > 13) return 0;  // (the string pool has room for 13 characters)
    memset(out, 0, BNTX_RGBA32_SIZE);
    // file header
    memcpy(out + 0x00, "BNTX", 4);
    w32(out + 0x08, 0x00040000);       // version 4.0
    w16(out + 0x0c, 0xfeff);           // byte order mark (little endian)
    out[0x0e] = 0x0c;                  // alignment 2^12
    out[0x0f] = 0x40;                  // 64-bit pointers
    w32(out + 0x10, 0x1ba);            // file name: the texture's name in the string pool
    w16(out + 0x16, 0x1a0);            // first block (_STRP)
    w32(out + 0x18, 0x2000);           // relocation table
    w32(out + 0x1c, BNTX_RGBA32_SIZE); // file size
    // NX header
    memcpy(out + 0x20, "NX  ", 4);
    w32(out + 0x24, 1);                // textures
    w64(out + 0x28, 0x198);            // info pointer array
    w64(out + 0x30, 0xff0);            // data block
    w64(out + 0x38, 0x1c8);            // dictionary
    w32(out + 0x40, 0x58);             // memory pool info size
    w64(out + 0x198, 0x1f0);           // -> the BRTI
    // string pool: an empty string (0x1b4), then the name (0x1b8: length, characters, NUL)
    memcpy(out + 0x1a0, "_STRP", 5);
    w32(out + 0x1a4, 0x50);            // next block (relative)
    w32(out + 0x1a8, 0x50);            // block size
    w32(out + 0x1b0, 1);               // strings
    w16(out + 0x1b8, (uint16_t)n);
    memcpy(out + 0x1ba, name, n);
    // dictionary: root node (bit -1, left -> node 1), node 1 (the name: left -> root, right -> itself)
    memcpy(out + 0x1c8, "_DIC", 4);
    w32(out + 0x1cc, 1);
    w32(out + 0x1d0, 0xffffffffu);
    w16(out + 0x1d4, 1);
    w64(out + 0x1d8, 0x1b4);
    w32(out + 0x1e0, dic_bit(name, n));
    w16(out + 0x1e6, 1);
    w64(out + 0x1e8, 0x1b8);
    // texture info
    memcpy(out + 0x1f0, "BRTI", 4);
    w32(out + 0x1f4, 0xe00);           // next block (relative)
    w64(out + 0x1f8, 0xe00);           // block size
    out[0x200] = 1;                    // flags
    out[0x201] = 2;                    // 2D
    w16(out + 0x206, 1);               // mip levels
    w32(out + 0x208, 1);               // samples
    w32(out + 0x20c, 0x0b01);          // R8G8B8A8 unorm
    w32(out + 0x210, 0x20);            // GPU access: texture
    w32(out + 0x214, 32);              // width
    w32(out + 0x218, 32);              // height
    w32(out + 0x21c, 1);               // depth
    w32(out + 0x220, 1);               // array layers
    w32(out + 0x224, 2);               // block height log2 (4 GOBs)
    w32(out + 0x228, 0x10007);
    w32(out + 0x240, 0x1000);          // image size
    w32(out + 0x244, 0x200);           // alignment
    out[0x248] = 2, out[0x249] = 3, out[0x24a] = 4, out[0x24b] = 5;  // channels R, G, B, A
    w32(out + 0x24c, 1);               // texture dimension: 2D
    w64(out + 0x250, 0x1b8);           // name
    w64(out + 0x258, 0x20);            // parent: the NX header
    w64(out + 0x260, 0x490);           // mip offsets
    w64(out + 0x270, 0x290);           // the loader's texture object
    w64(out + 0x278, 0x390);           // the loader's texture view object
    w64(out + 0x490, 0x1000);          // mip 0 data
    // data block
    memcpy(out + 0xff0, "BRTD", 4);
    w64(out + 0xff8, 0x1010);          // block size (header included)
    for (size_t y = 0; y < 32; y++)
        for (size_t x = 0; x < 32; x++) memcpy(out + 0x1000 + block_linear(x * 4, y), rgba + (y * 32 + x) * 4, 4);
    // relocation table: two sections (headers and info; the data block), five entries
    memcpy(out + 0x2000, "_RLT", 4);
    w32(out + 0x2004, 0x2000);         // its own offset
    w32(out + 0x2008, 2);              // sections
    w32(out + 0x201c, 0x498);          // section 0: offset 0, size, entries 0..3
    w32(out + 0x2024, 4);
    w32(out + 0x2030, 0xff0);          // section 1: the data block, entry 4
    w32(out + 0x2034, 0x1010);
    w32(out + 0x2038, 4);
    w32(out + 0x203c, 1);
    static const struct { uint32_t off; uint16_t structs; uint8_t ptrs, skip; } rel[5] = {
        {0x028, 2, 1, 0x2d},  // NX header: info array, then the dictionary (0x38)... as pairs with a stride
        {0x038, 2, 2, 0x45},
        {0x1d8, 2, 1, 0x01},  // dictionary nodes' name pointers
        {0x250, 1, 3, 0x00},  // BRTI: name, parent, mip offsets
        {0x030, 2, 1, 0x8b},  // data block pointer and mip 0 data
    };
    for (int i = 0; i < 5; i++) {
        uint8_t *e = out + 0x2040 + 8 * i;
        w32(e, rel[i].off);
        w16(e + 4, rel[i].structs);
        e[6] = rel[i].ptrs, e[7] = rel[i].skip;
    }
    return BNTX_RGBA32_SIZE;
}
