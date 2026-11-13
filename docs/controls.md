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

## Rebinding (`hylian-melodies.ini`)

```
key.<button> = <key>[, <key>...]          e.g.  key.a = J, Return
pad.<button> = <gamepad button>[, ...]    e.g.  pad.a = south
```

`<button>`: `a b x y l r zl zr plus minus up down left right lstick rstick`. Key names are SDL's (`Left`, `Return`,
`Space`, `A`...); gamepad names are SDL's (`south`, `east`, `west`, `north`, `leftshoulder`, `rightshoulder`,
`lefttrigger`, `righttrigger`, `start`, `back`, `dpup`...). A line replaces that button's defaults. Controllers SDL
doesn't know can be added with a `gamecontrollerdb.txt` (SDL_GameControllerDB format) next to the settings file.

Rumble from the game goes to the gamepad (SDL rumble).

## Test runs

`HM_INPUT_SCRIPT=<frame>:<button>[+<button>...][/<frames>],...` presses buttons at presented frames (held for 6
frames unless `/<frames>` says otherwise), e.g. `700:a,900:a+up/30`.
