# Controls

Player 1 is a Switch "full key" controller, fed by any SDL3 gamepad and by the keyboard at the same time
(`runtime/ui/input.c`). Presses reach the game at its next poll: no queue, no extra frame.

## Gamepad (by position, as on the Switch)

| Switch | Gamepad |
|---|---|
| A / B / X / Y | right / bottom / top / left face button |
| L / R, ZL / ZR | shoulders, triggers |
| + / - | Start / Back (View) |
| D-pad, sticks, stick clicks | the same |

Xbox and PlayStation pads therefore have A and B swapped by name (the Switch's A is the right button). Swap them in
the ini if you prefer the labels: `pad.a = south` and `pad.b = east`.

## Keyboard

| Switch | Keys |
|---|---|
| D-pad | arrow keys, or W A S D |
| A | X or Enter |
| B | Z or Backspace |
| X / Y | C / V |
| L / R | Q / E |
| ZL / ZR | 1 / 3 |
| + / - | Esc / Tab |
| stick clicks | F / G |

## Window

F11 or Alt+Enter switches between a window and fullscreen (borderless, the desktop's resolution).
`hylian-melodies --fullscreen` starts in fullscreen.

## Settings menu

**F1**, or **Minus + Plus** held together on a gamepad (or its Home button), opens and closes the settings menu over
the game; Esc, B, Z or Backspace also close it. While it is open the game gets no input. Arrows / W A S D or the d-pad
move, Enter / X or the right face button choose, L / R or Q / E change page; the mouse works too. (Esc alone doesn't
open it: Esc is the game's +.)

Pages: Video (fullscreen, scaling filter, FPS in the title, frame pacing), Audio (volume), Controls (rebinding: choose
a binding, then press the new key or gamepad button; Esc or Home cancels; "Reset all to defaults"), About (version,
the settings and saves folder). Changes apply at once, except the scaling filter (next start), and are written to
`hylian-melodies.ini` when the menu closes: only the changed lines, the rest of the file stays as it is.

The menu uses the game's own fonts, read from your copy's files at start (`runtime/ui/game_font.c`); the system's
sans-serif font if they can't be read, or with `HM_MENU_FONT=system`. `HM_MENU_AT=<frame>` opens it at a frame and
`HM_MENU_TAB=<0-3>` picks the page (screenshot tests).

## Rebinding (`hylian-melodies.ini`)

```
key.<button> = <key>[, <key>...]          e.g.  key.a = J, Return
pad.<button> = <gamepad button>[, ...]    e.g.  pad.a = south
```

`<button>`: `a b x y l r zl zr plus minus up down left right lstick rstick`. Key names are SDL's (`Left`, `Return`,
`Space`, `A`...); gamepad buttons are `south`, `east`, `west`, `north` (face buttons by position) or SDL's names
(`leftshoulder`, `rightshoulder`, `lefttrigger`, `righttrigger`, `start`, `back`, `dpup`...). A line replaces that button's defaults. Controllers SDL
doesn't know can be added with a `gamecontrollerdb.txt` (SDL_GameControllerDB format) next to the settings file.

Rumble from the game goes to the gamepad (SDL rumble).

## Test runs

`HM_LOG_INPUT=1` logs every change of the held buttons (and whether a gamepad is the source).

`HM_INPUT_SCRIPT=<frame>:<button>[+<button>...][/<frames>],...` presses buttons at presented frames (held for 6
frames unless `/<frames>` says otherwise), e.g. `700:a,900:a+up/30`.
