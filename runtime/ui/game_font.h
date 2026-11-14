// The game's own bitmap fonts (BFFNT files in the player's RomFS), read at run time for the overlay menu
// (runtime/ui/menu.cpp). Nothing of the fonts is in this repository: they come from the player's dump.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t code;            // Unicode (BMP)
    uint16_t index;           // glyph index in the font (sheet cell)
    int8_t left;              // space before the glyph image
    uint8_t width, advance;   // glyph image width, advance to the next character
} GameGlyph;

typedef struct GameFont GameFont;

// The font in romfs_dir (searched recursively) whose line height is closest to want_line among those that cover
// printable ASCII; ties go to the one with more characters. skip: a font to leave out. NULL when there is none.
GameFont *game_font_pick(const char *romfs_dir, int want_line, const GameFont *skip);
void game_font_free(GameFont *f);

int game_font_line(const GameFont *f);        // line height in pixels
int game_font_cell_height(const GameFont *f);
int game_font_glyphs(const GameFont *f, const GameGlyph **out);  // characters up to U+2FFF (no CJK), sorted by code
// The glyph's cell as 8-bit coverage (white text: alpha), top-left first; *pitch: bytes per row. NULL on failure.
const uint8_t *game_font_cell(GameFont *f, int index, int *pitch);
const char *game_font_path(const GameFont *f);
