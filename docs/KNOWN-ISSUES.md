# Known issues

- Input is not connected yet (M7): the game runs but can't be controlled; the controller check is answered as
  "player 1 connected".
- Pixel-art scaling: LAS Recomp's resolution logic renders at a fraction of the window (dynamic resolution) and
  scales with bilinear filtering, so the image is slightly soft. Wanted for this game: render at 1280x720 and scale
  by whole numbers with nearest filtering (M10).
- Loading and the splash videos run at 30 fps (the game's own choice while loading; to confirm on hardware).
- No overlay menu (M10); the software keyboard returns the initial text unchanged.
- Restored LAS Recomp renderer code still contains comments and dormant paths about Link's Awakening; the hooks are
  answered "off" (`runtime/nvn/las_feature_stubs.c`). To trim over time.
- SMAA anti-aliasing is not built (not useful for pixel art anyway).
- Audio is measured (docs/audio.md) but not yet checked by ear against the beat; end-to-end latency to the speakers
  is not measured (use the game's calibration).
