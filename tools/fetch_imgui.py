#!/usr/bin/env python3
"""Fetch Dear ImGui (ocornut/imgui, MIT) at a pinned commit for the overlay menu.

  python3 tools/fetch_imgui.py [--src DIR]

Fetches only the pinned commit into --src (default toolchain/src/imgui), discards local changes there and applies
tools/imgui/*.patch. Nothing of ImGui is vendored in this repo (imgui.cpp alone is over the content guard's size
limit); tools/build_game.py compiles the few files it needs straight from --src. Prints the source directory.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = 'https://github.com/ocornut/imgui.git'
COMMIT = '97428e8ac99e339ce05eee531cf55b77b29ea709'  # tag v1.91.9
PATCH_DIR = ROOT / 'tools' / 'imgui'
FILES = ('imgui.cpp', 'imgui_draw.cpp', 'imgui_tables.cpp', 'imgui_widgets.cpp',
         'backends/imgui_impl_vulkan.cpp', 'backends/imgui_impl_sdl3.cpp')


def git(src, *args):
    subprocess.run(['git', '-C', str(src), *args], check=True)


def stamp_text():
    patches = sorted(PATCH_DIR.glob('*.patch')) if PATCH_DIR.is_dir() else []
    return COMMIT + ''.join(' ' + p.name + ':' + str(p.stat().st_size) for p in patches), patches


def fetch(src):
    want, patches = stamp_text()
    stamp = src / '.hm-stamp'
    if stamp.is_file() and stamp.read_text().strip() == want and all((src / f).is_file() for f in FILES):
        return
    if not shutil.which('git'):
        sys.exit('fetch_imgui: git not found')
    if not (src / '.git').is_dir():
        src.mkdir(parents=True, exist_ok=True)
        git(src, 'init', '-q')
        git(src, 'remote', 'add', 'origin', URL)
    head = subprocess.run(['git', '-C', str(src), 'rev-parse', '-q', '--verify', 'HEAD'], capture_output=True,
                          text=True).stdout.strip()
    if head != COMMIT:
        git(src, 'fetch', '-q', '--depth', '1', 'origin', COMMIT)
    git(src, 'checkout', '-q', '-f', COMMIT)
    git(src, 'clean', '-q', '-fdx')
    for p in patches:
        git(src, 'apply', '--whitespace=nowarn', str(p))
    stamp.write_text(want + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', type=Path, default=ROOT / 'toolchain' / 'src' / 'imgui')
    a = ap.parse_args()
    src = a.src.resolve()
    fetch(src)
    print(src)


if __name__ == '__main__':
    main()
