#!/usr/bin/env python3
"""Build SDL3 (libsdl-org/SDL, zlib license) from a pinned release as a static library, for distro releases that
have no SDL3 package (Debian 12, Ubuntu 24.04).

  python3 tools/build_sdl3.py [--src DIR] [--out DIR] [--cc CC]

Fetches only the pinned commit into --src (default toolchain/src/sdl3), configures with CMake + Ninja and installs
into --out (default toolchain/sdl3): tools/build_game.py --sdl3 <out> then links the game against it statically, so
the installed game needs no SDL3 package. SDL loads the desktop's libraries (Wayland, X11, PipeWire, PulseAudio,
ALSA, udev, D-Bus) at run time; their development files must be present now, or that support is left out. The
build stops unless at least one window system and one audio system made it in. Nothing of SDL is vendored here.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = 'https://github.com/libsdl-org/SDL.git'
COMMIT = 'f00dc919ca35b9756316e86c4777392de442f9b2'  # tag release-3.4.20
VIDEO = ('WAYLAND', 'X11')
AUDIO = ('PIPEWIRE', 'PULSEAUDIO', 'ALSA')


def git(src, *args):
    subprocess.run(['git', '-C', str(src), *args], check=True)


def fetch(src):
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


def built_in(config_h):
    """The window and audio systems this build of SDL supports, from its generated SDL_build_config.h."""
    text = config_h.read_text()
    have = lambda kind, name: re.search(rf'^#define SDL_{kind}_DRIVER_{name} 1', text, re.M) is not None
    return [n for n in VIDEO if have('VIDEO', n)], [n for n in AUDIO if have('AUDIO', n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', type=Path, default=ROOT / 'toolchain' / 'src' / 'sdl3')
    ap.add_argument('--out', type=Path, default=ROOT / 'toolchain' / 'sdl3')
    ap.add_argument('--cc', default=os.environ.get('HM_CC', 'clang'))
    a = ap.parse_args()
    for tool in ('git', 'cmake', 'ninja', a.cc.split()[0]):
        if not shutil.which(tool):
            sys.exit(f'build_sdl3: {tool} not found')
    src, out = a.src.resolve(), a.out.resolve()
    stamp = out / 'COMMIT'
    if (out / 'lib' / 'libSDL3.a').is_file() and stamp.is_file() and stamp.read_text().strip() == COMMIT:
        print(f'build_sdl3: {out} already at {COMMIT[:7]}')
        return
    fetch(src)
    build = src / 'build-hm'
    env = {k: v for k, v in os.environ.items() if k not in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS')}
    log = src / 'build.log'
    steps = (
        ['cmake', '-S', str(src), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         f'-DCMAKE_C_COMPILER={a.cc}', f'-DCMAKE_INSTALL_PREFIX={out}', '-DCMAKE_INSTALL_LIBDIR=lib',
         '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DSDL_SHARED=OFF', '-DSDL_STATIC=ON', '-DSDL_TEST_LIBRARY=OFF',
         '-DSDL_TESTS=OFF', '-DSDL_EXAMPLES=OFF', '-DSDL_INSTALL_DOCS=OFF',
         # what the game never uses, so their development files are not asked for (it draws with Vulkan)
         '-DSDL_OPENGL=OFF', '-DSDL_OPENGLES=OFF', '-DSDL_KMSDRM=OFF', '-DSDL_CAMERA=OFF', '-DSDL_JACK=OFF',
         '-DSDL_SNDIO=OFF', '-DSDL_OSS=OFF'],
        ['cmake', '--build', str(build)],
    )
    with open(log, 'w') as f:
        for cmd in steps:
            if subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode:
                sys.exit(f'build_sdl3: {cmd[0]} {cmd[1]} failed; log: {log}')
    video, audio = built_in(build / 'include-config-release' / 'build_config' / 'SDL_build_config.h')
    if not video or not audio:
        sys.exit('build_sdl3: this build would have no ' + ('window' if not video else 'audio') + ' support: the '
                 'development files of Wayland or X11, and of PipeWire, PulseAudio or ALSA, are needed')
    shutil.rmtree(out, ignore_errors=True)
    with open(log, 'a') as f:
        if subprocess.run(['cmake', '--install', str(build)], env=env, stdout=f, stderr=subprocess.STDOUT).returncode:
            sys.exit(f'build_sdl3: install failed; log: {log}')
    shutil.copy2(src / 'LICENSE.txt', out / 'LICENSE.txt')
    stamp.write_text(COMMIT + '\n')
    print(f'build_sdl3: {out} built at {COMMIT[:7]} (window: {" ".join(video).lower()}; audio: {" ".join(audio).lower()})')


if __name__ == '__main__':
    main()
