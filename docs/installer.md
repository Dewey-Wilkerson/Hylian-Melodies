# Installer

`python3 -m installer` turns the user's own dump and keys into an install folder. Stdlib-only Python; one JSON event
per line on stdout; full log in `<temp>/run-<time>/logs/install.log`; exit status 0 only when the result is `ok`.

```
python3 -m installer --base cadence-base.xci [--update cadence-update.nsp] --keys prod.keys --dest DIR
                     [--temp DIR] [--root DIR] [--hactool EXE] [--firmware DIR] [--until STEP]
```

## Steps

| Step | State | What it does |
|---|---|---|
| check | done | inputs exist; keys file sane (count only, never values; needs master key revision 0x0A); Python >= 3.11; free space; containers open with the keys |
| extract | done | unpack the XCI secure partition (or NSP) into `<temp>/work/nca`; parse every CNMT; verify each needed NCA against its CNMT SHA-256 and the known-good table (`installer/known.py`); title keys from the cart's tickets into a private temp HOME; merge base + 1.4.0 update into `exefs/` + `romfs/`; verify ExeFS hashes and the RomFS manifest; extract the four DLC RomFS into `aoc/<title id>/` |
| lift | M3 | ARM64 -> C into `<temp>/generated` |
| compile | M3/M4 | clang + lld + ninja into the game executable |
| shaders | M5 | needs a graphical session |
| cleanup | | remove work files |

## Install folder

```
<dest>/
  exefs/  romfs/  aoc/<title id>/     extracted, verified game files
  hm-install.json                     finished steps, version, extract sub-steps (resume)
```

## Resume

Each step records completion in `hm-install.json`; a rerun skips finished steps (event `resume`). Inside extract,
sub-steps (`unpack`, `hashes`, `game`, `aoc`) are recorded too, and partial output lives in `.partial*` folders that
are renamed into place only after verification, so a run killed at any point resumes cleanly.

## Events

`start {steps}`, `step {step,msg}`, `progress {step,pct}` (integer, only on change), `info|warning|error
{msg,args,text}` with `msg` an ID from `installer/messages.py`, `end {result: ok|error, ...}`.

## Keys

The keys file is read by hactool only (via `-k`); the installer reads it just to count entries and check which key
names exist. hactool runs through `installer/hactool.py` with a private HOME under `<temp>/work/hactool-home` (0700,
wiped at start and end), so it never sees `~/.switch` and the title-key file never outlives a run. Its output is
filtered before logging.
