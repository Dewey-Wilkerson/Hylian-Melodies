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

## Settings

The port's settings are rows of the game's own Options menu (title screen: the gear, then Options; docs/IN-GAME-MENU.md):

- **Graphics**: *Fullscreen*, *Frame pacing* (a steady 60 Hz, like the Switch's display) and *Scaling filter* (Sharp,
  Smooth or Nearest; used from the next start), after the game's own rows.
- **Controls** (after Language): one row per Switch button with its keys and gamepad buttons. Press A (or left /
  right) on a row, then the key or gamepad button to use: a key replaces the keyboard binding, a gamepad button or
  trigger the gamepad one. Esc or Home cancels. *Reset to defaults* is the last row.

Every change is written to `hylian-melodies.ini` at once: only the changed lines, the rest of the file stays as it
is. Sound and music volume are the game's own (Options > Audio). There is no overlay menu any more: F1 and Minus +
Plus reach the game like any other key.

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
