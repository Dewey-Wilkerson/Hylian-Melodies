// The game's RomFS image, laid out from a folder of game files (runtime/romfs_build.c). The game reads its data through
// one raw RomFS image; runtime/services/fs.c serves that image from this layout - the header and tables in memory, each
// file's data straight from its file in the player's romfs/ folder - so no second copy of the game data is kept.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ROMFS_DATA_START 0x200u
typedef struct {
    uint64_t start, size;  // start: offset in the image
    char *path;            // the file's data: a host file, or (path NULL) `data` in memory
    const uint8_t *data;
} RomfsLayoutFile;
// A file the port adds to the image (its own art, runtime/hle/game_menu.c): path inside the image ("a/b/c.ext"),
// data in memory for as long as the image is used. One of the folder's own files at that path is replaced.
typedef struct { const char *path; const uint8_t *data; uint64_t size; } RomfsExtraFile;
typedef struct {
    uint8_t header[ROMFS_DATA_START];  // the image's first bytes (the 0x50-byte header, then zeros)
    uint64_t tables_off, tables_size;  // dir hash, dir entries, file hash and file entries, one blob
    uint8_t *tables;
    RomfsLayoutFile *files;  // sorted by start; the bytes between files read as zeros
    int nfiles;
    uint64_t size;  // the whole image
} RomfsLayout;

// Lays out the RomFS image of the folder `dir`. false = failed (why: a short message).
bool romfs_layout(const char *dir, RomfsLayout *out, char *why, size_t why_size);
// The same, with files added from memory (extra may be NULL when nextra is 0).
bool romfs_layout_ex(const char *dir, const RomfsExtraFile *extra, int nextra, RomfsLayout *out, char *why,
                     size_t why_size);

#ifdef __cplusplus
}
#endif
