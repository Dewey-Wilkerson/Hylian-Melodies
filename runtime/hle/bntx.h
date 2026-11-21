// A 32x32 RGBA8 texture file in the Switch's BNTX format (runtime/hle/bntx.c).
#pragma once
#include <stddef.h>
#include <stdint.h>

#define BNTX_RGBA32_SIZE 0x2068

// name: the texture's name, 1..13 characters; rgba: 32x32 pixels, rows top to bottom, 4 bytes each.
// Returns BNTX_RGBA32_SIZE, or 0 when the name doesn't fit.
size_t bntx_rgba32(const char *name, const uint8_t *rgba, uint8_t out[BNTX_RGBA32_SIZE]);
