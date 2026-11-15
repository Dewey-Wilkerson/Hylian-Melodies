// Reader for the game's BFFNT fonts (Nintendo's bitmap font format, version 4 as on the Switch). Our own code, from
// the format's structure as found in the player's files (docs/DECISIONS.md, 2026-11-14):
//   "FFNT" header (0x14 bytes), then sections, each "MAGIC" + u32 size:
//   FINF  font info: type, height, width, ascent, line feed, default widths, encoding, then u32 offsets (each just past
//         a section's 8-byte header) of TGLP, CWDH and CMAP
//   TGLP  glyph sheets: cell width/height (u8), sheet count (u8), max width (u8), sheet size (u32), baseline (u16),
//         format (u16), columns, rows, sheet width, height (u16), u32 offset of the sheet data: a BNTX holding one
//         texture with a layer per sheet (BC4, Tegra block-linear, stored bottom row first). Cell (c, r) of a sheet is
//         at x = c * (cell width + 1) + 1, y = r * (cell height + 1) + 1.
//   CWDH  widths per glyph index (chained): first, last index (u16), next (u32), then {s8 left, u8 width, u8 advance}
//   CMAP  code maps (chained): first, last code (u32), method (u16), pad, next (u32), then per method:
//         0 direct (u16 first index), 1 table (u16 index per code, 0xffff none), 2 scan (u32 count, {u32 code, u32 index})
#include "game_font.h"

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>


#define MAX_CODE 0x2fff  // (the menu's text: Latin, Greek, Cyrillic, symbols; the CJK sheets aren't decoded)

struct GameFont {
    char path[1024];
    uint8_t *d;
    size_t n;
    int line, cell_w, cell_h, sheets, cols, rows, sheet_w, sheet_h;
    size_t tex_off, layer_size;  // first sheet's pixel data in d, bytes per sheet
    int block_h_log2;
    GameGlyph *g;
    int ng;
    uint8_t **decoded;  // per sheet: sheet_w * sheet_h coverage, top row first (decoded when first needed)
};

static uint16_t u16(const GameFont *f, size_t o) { return o + 2 <= f->n ? (uint16_t)(f->d[o] | f->d[o + 1] << 8) : 0; }
static uint32_t u32(const GameFont *f, size_t o) { return o + 4 <= f->n ? (uint32_t)u16(f, o) | (uint32_t)u16(f, o + 2) << 16 : 0; }
static uint64_t u64(const GameFont *f, size_t o) { return (uint64_t)u32(f, o) | (uint64_t)u32(f, o + 4) << 32; }

static int by_code(const void *a, const void *b) { return (int)((const GameGlyph *)a)->code - (int)((const GameGlyph *)b)->code; }

static void add(GameFont *f, int *cap, uint32_t code, uint32_t index) {
    if (code < 0x20 || code > MAX_CODE || index >= (uint32_t)(f->sheets * f->cols * f->rows)) return;
    if (f->ng == *cap) f->g = realloc(f->g, (size_t)(*cap = *cap ? *cap * 2 : 512) * sizeof *f->g);
    f->g[f->ng++] = (GameGlyph){.code = (uint16_t)code, .index = (uint16_t)index};
}

static bool parse(GameFont *f) {
    if (f->n < 0x40 || memcmp(f->d, "FFNT", 4) || u16(f, 4) != 0xfeff) return false;
    size_t finf = u16(f, 6);
    if (memcmp(f->d + finf, "FINF", 4)) return false;
    f->line = u16(f, finf + 12);
    size_t tglp = u32(f, finf + 0x14), cwdh = u32(f, finf + 0x18), cmap = u32(f, finf + 0x1c);
    if (tglp < 8 || tglp + 0x20 > f->n || memcmp(f->d + tglp - 8, "TGLP", 4)) return false;
    f->cell_w = f->d[tglp], f->cell_h = f->d[tglp + 1], f->sheets = f->d[tglp + 2];
    if (u16(f, tglp + 10) != 0xc) return false;  // (BC4: the only sheet format seen)
    f->cols = u16(f, tglp + 12), f->rows = u16(f, tglp + 14), f->sheet_w = u16(f, tglp + 16), f->sheet_h = u16(f, tglp + 18);
    size_t bntx = u32(f, tglp + 20);
    if (!f->cell_w || !f->cell_h || !f->sheets || !f->cols || !f->rows || f->sheet_w % 4 || f->sheet_h % 4 ||
        bntx + 0x40 > f->n || memcmp(f->d + bntx, "BNTX", 4))
        return false;
    // the BNTX's one texture: BC4 (0x1d01), block-linear, a layer per sheet
    uint8_t *brti = memmem(f->d + bntx, f->n - bntx, "BRTI", 4);
    if (!brti) return false;
    size_t ti = (size_t)(brti - f->d);
    if (u32(f, ti + 0x1c) != 0x1d01 || (int)u32(f, ti + 0x24) != f->sheet_w || (int)u32(f, ti + 0x28) != f->sheet_h ||
        (int)u32(f, ti + 0x30) < f->sheets)
        return false;
    f->block_h_log2 = (int)(u32(f, ti + 0x34) & 7);
    f->layer_size = u32(f, ti + 0x50) / u32(f, ti + 0x30);
    f->tex_off = bntx + u64(f, bntx + u64(f, ti + 0x70));
    if (f->layer_size < (size_t)f->sheet_w * f->sheet_h / 2 || f->tex_off + f->layer_size * f->sheets > f->n) return false;
    // code -> glyph index
    int cap = 0;
    for (int guard = 0; cmap >= 8 && cmap + 12 <= f->n && guard < 256; guard++) {
        uint32_t first = u32(f, cmap), last = u32(f, cmap + 4);
        uint16_t method = u16(f, cmap + 8);
        if (method == 0) {
            uint16_t idx = u16(f, cmap + 16);
            for (uint32_t c = first; c <= last && c <= MAX_CODE; c++) add(f, &cap, c, idx + (c - first));
        } else if (method == 1) {
            for (uint32_t c = first; c <= last && c <= MAX_CODE; c++) {
                uint16_t idx = u16(f, cmap + 16 + 2 * (c - first));
                if (idx != 0xffff) add(f, &cap, c, idx);
            }
        } else if (method == 2) {
            uint32_t cnt = u32(f, cmap + 16);
            for (uint32_t k = 0; k < cnt && cmap + 28 + 8 * k <= f->n; k++) add(f, &cap, u32(f, cmap + 20 + 8 * k), u32(f, cmap + 24 + 8 * k));
        }
        cmap = u32(f, cmap + 12);
    }
    if (!f->ng) return false;
    qsort(f->g, (size_t)f->ng, sizeof *f->g, by_code);
    int k = 0;  // (one entry per code: the first map that has it)
    for (int i = 0; i < f->ng; i++)
        if (!k || f->g[k - 1].code != f->g[i].code) f->g[k++] = f->g[i];
    f->ng = k;
    // widths
    for (int i = 0; i < f->ng; i++) f->g[i].width = (uint8_t)f->cell_w, f->g[i].advance = (uint8_t)f->cell_w;
    for (int guard = 0; cwdh >= 8 && cwdh + 8 <= f->n && guard < 256; guard++) {
        uint16_t a = u16(f, cwdh), b = u16(f, cwdh + 2);
        for (int i = 0; i < f->ng; i++) {
            uint16_t idx = f->g[i].index;
            size_t o = cwdh + 8 + 3 * (size_t)(idx - a);
            if (idx < a || idx > b || o + 3 > f->n) continue;
            f->g[i].left = (int8_t)f->d[o];
            f->g[i].width = f->d[o + 1] > f->cell_w ? (uint8_t)f->cell_w : f->d[o + 1];
            f->g[i].advance = f->d[o + 2];
        }
        cwdh = u32(f, cwdh + 4);
    }
    f->decoded = calloc((size_t)f->sheets, sizeof *f->decoded);
    return true;
}

static GameFont *open_font(const char *path) {
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    GameFont *f = calloc(1, sizeof *f);
    snprintf(f->path, sizeof f->path, "%s", path);
    fseek(fp, 0, SEEK_END);
    long n = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    if (n > 0 && n < (64 << 20)) {
        f->d = malloc((size_t)n);
        f->n = fread(f->d, 1, (size_t)n, fp);
    }
    fclose(fp);
    if (!f->d || !parse(f)) { game_font_free(f); return NULL; }
    return f;
}

void game_font_free(GameFont *f) {
    if (!f) return;
    for (int i = 0; f->decoded && i < f->sheets; i++) free(f->decoded[i]);
    free(f->decoded);
    free(f->g);
    free(f->d);
    free(f);
}

static bool covers_ascii(const GameFont *f) {
    int have = 0;
    for (int i = 0; i < f->ng; i++) have += f->g[i].code >= 0x20 && f->g[i].code <= 0x7e;
    return have == 0x7f - 0x20;
}

static void scan(const char *dir, int depth, int want, const GameFont *skip, GameFont **best) {
    DIR *d = depth < 8 ? opendir(dir) : NULL;
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        char p[1024];
        snprintf(p, sizeof p, "%s/%s", dir, e->d_name);
        struct stat st;
        if (stat(p, &st)) continue;
        if (S_ISDIR(st.st_mode)) { scan(p, depth + 1, want, skip, best); continue; }
        size_t l = strlen(e->d_name);
        if (l < 6 || strcasecmp(e->d_name + l - 6, ".bffnt")) continue;
        if (skip && !strcmp(skip->path, p)) continue;
        GameFont *f = open_font(p);
        if (!f || !covers_ascii(f)) { game_font_free(f); continue; }
        int dist = abs(f->line - want), bd = *best ? abs((*best)->line - want) : 1 << 30;
        if (dist < bd || (dist == bd && f->ng > (*best)->ng)) { game_font_free(*best); *best = f; }
        else game_font_free(f);
    }
    closedir(d);
}

GameFont *game_font_pick(const char *romfs_dir, int want_line, const GameFont *skip) {
    GameFont *best = NULL;
    scan(romfs_dir, 0, want_line, skip, &best);
    return best;
}

int game_font_line(const GameFont *f) { return f->line; }
int game_font_cell_height(const GameFont *f) { return f->cell_h; }
int game_font_glyphs(const GameFont *f, const GameGlyph **out) { *out = f->g; return f->ng; }

// ---- sheets: Tegra block-linear (GOBs of 64 bytes x 8 rows, block_h GOBs high) over BC4 blocks (8 bytes each)
static size_t gob_offset(size_t x, size_t y) {
    return (x % 64) / 32 * 256 + (y % 8) / 2 * 64 + (x % 32) / 16 * 32 + (y % 2) * 16 + (x % 16);
}

static uint8_t *decode_sheet(const GameFont *f, int sheet) {
    size_t wb = (size_t)f->sheet_w / 4, hb = (size_t)f->sheet_h / 4, row_bytes = wb * 8;
    size_t gobs_w = (row_bytes + 63) / 64, bh = (size_t)1 << f->block_h_log2;
    const uint8_t *src = f->d + f->tex_off + f->layer_size * (size_t)sheet;
    uint8_t *out = malloc((size_t)f->sheet_w * f->sheet_h);
    if (!out) return NULL;
    for (size_t by = 0; by < hb; by++)
        for (size_t bx = 0; bx < wb; bx++) {
            uint8_t blk[8];
            for (int k = 0; k < 8; k++) {
                size_t x = bx * 8 + (size_t)k, gy = by / 8;
                size_t a = ((gy / bh) * gobs_w * bh + (x / 64) * bh + gy % bh) * 512 + gob_offset(x, by);
                blk[k] = a < f->layer_size ? src[a] : 0;
            }
            uint8_t pal[8] = {blk[0], blk[1]};
            if (blk[0] > blk[1])
                for (int i = 0; i < 6; i++) pal[2 + i] = (uint8_t)(((6 - i) * blk[0] + (i + 1) * blk[1]) / 7);
            else {
                for (int i = 0; i < 4; i++) pal[2 + i] = (uint8_t)(((4 - i) * blk[0] + (i + 1) * blk[1]) / 5);
                pal[6] = 0, pal[7] = 255;
            }
            uint64_t bits = 0;
            for (int k = 0; k < 6; k++) bits |= (uint64_t)blk[2 + k] << (8 * k);
            for (int p = 0; p < 16; p++) {
                size_t x = bx * 4 + (size_t)(p % 4), y = by * 4 + (size_t)(p / 4);
                out[((size_t)f->sheet_h - 1 - y) * (size_t)f->sheet_w + x] = pal[(bits >> (3 * p)) & 7];  // (bottom row first)
            }
        }
    return out;
}

const uint8_t *game_font_cell(GameFont *f, int index, int *pitch) {
    int per = f->cols * f->rows, sheet = index / per, cell = index % per;
    if (index < 0 || sheet >= f->sheets) return NULL;
    if (!f->decoded[sheet] && !(f->decoded[sheet] = decode_sheet(f, sheet))) return NULL;
    int x = (cell % f->cols) * (f->cell_w + 1) + 1, y = (cell / f->cols) * (f->cell_h + 1) + 1;
    if (x + f->cell_w > f->sheet_w || y + f->cell_h > f->sheet_h) return NULL;
    *pitch = f->sheet_w;
    return f->decoded[sheet] + (size_t)y * f->sheet_w + x;
}
