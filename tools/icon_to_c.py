#!/usr/bin/env python3
"""The port's own button art (packaging/art/*.png, 32x32) as a C array of RGBA8 pixels for the runtime.

    python3 tools/icon_to_c.py packaging/art/exit-button.png runtime/hle/exit_icon.h hm_exit_icon

Needs Pillow (a development step only: the header is committed, builds don't run this).
"""
import sys

from PIL import Image


def main(src, dst, name):
    im = Image.open(src).convert('RGBA')
    if im.size != (32, 32):
        sys.exit(f'{src}: {im.size[0]}x{im.size[1]}, expected 32x32')
    data = im.tobytes()
    rows = [', '.join(f'0x{b:02x}' for b in data[i:i + 16]) for i in range(0, len(data), 16)]
    with open(dst, 'w') as f:
        f.write(f'// Generated from {src} by tools/icon_to_c.py: 32x32 RGBA8, rows top to bottom. Do not edit.\n')
        f.write('#pragma once\n#include <stdint.h>\n\n')
        f.write(f'static const uint8_t {name}[32 * 32 * 4] = {{\n')
        f.write(''.join(f'    {r},\n' for r in rows))
        f.write('};\n')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
