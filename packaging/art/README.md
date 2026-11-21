# Art for the port's own buttons

- `exit-button-template.png`: the canvas for the title screen's Exit button icon (beside the gear): 32x32 RGBA,
  transparent. The game draws its framed box around the icon; the icon is drawn at the game's own pixel scale (one
  texel = one game pixel, 2x in a 1280x720 window).
- `exit-button-guide.png`: the same canvas with guides only (not for use as art): the cyan box is the area the gear's
  own icon fills (x 6..26, y 5..27, 21x23), the yellow dot the centre. The game's icons are white with a one-pixel
  dark shadow on their lower edges.

Art here is the project's own (never taken from the game).

- `exit-button.png`: the Exit button's icon (the owner's, 2026-11-21). The runtime embeds it as
  `runtime/hle/exit_icon.h`; after changing the PNG run
  `python3 tools/icon_to_c.py packaging/art/exit-button.png runtime/hle/exit_icon.h hm_exit_icon` (needs Pillow).
