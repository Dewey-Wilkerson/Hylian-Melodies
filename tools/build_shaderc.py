#!/usr/bin/env python3
"""Build shaderc (google/shaderc, Apache-2.0) from a pinned release as one static library, for distro releases
whose shaderc package cannot be used (Debian 12: its library lacks the GLSL compiler it calls).

  python3 tools/build_shaderc.py [--src DIR] [--out DIR] [--cc CC]

Fetches only the pinned commits of shaderc and of the three projects it builds on (glslang, SPIRV-Tools,
SPIRV-Headers: the revisions that shaderc release names in its DEPS file) into --src (default
toolchain/src/shaderc), builds with CMake + Ninja and puts libshaderc_combined.a, the headers and the licenses
into --out (default toolchain/shaderc): tools/build_game.py --shaderc <out> then links the game against it
statically, so the installed game needs no shaderc package. Nothing of these is vendored here. Takes a few minutes.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# (folder under --src, repository, commit); the first is shaderc v2026.4, the rest are from its DEPS file
PARTS = (
    ('', 'https://github.com/google/shaderc.git', 'b64fd42c4a2a9d501c47aca5d3571f7673a5e9cc'),
    ('third_party/glslang', 'https://github.com/KhronosGroup/glslang.git', 'e1b562a8bed273a02f30b59b66a5d499793cede5'),
    ('third_party/spirv-tools', 'https://github.com/KhronosGroup/SPIRV-Tools.git',
     'ef96ed763b43b59b33b31b362f09a02b729fa1c9'),
    ('third_party/spirv-headers', 'https://github.com/KhronosGroup/SPIRV-Headers.git',
     '04fd3caa1e8267e4d95c806cad901181728e1006'),
)
STAMP = ' '.join(c for _, _, c in PARTS)
LICENSES = (('LICENSE', 'LICENSE.shaderc'), ('third_party/glslang/LICENSE.txt', 'LICENSE.glslang'),
            ('third_party/spirv-tools/LICENSE', 'LICENSE.spirv-tools'),
            ('third_party/spirv-headers/LICENSE', 'LICENSE.spirv-headers'))


def git(src, *args):
    subprocess.run(['git', '-C', str(src), *args], check=True)


def fetch(src, url, commit, clean):
    if not (src / '.git').is_dir():
        src.mkdir(parents=True, exist_ok=True)
        git(src, 'init', '-q')
        git(src, 'remote', 'add', 'origin', url)
    head = subprocess.run(['git', '-C', str(src), 'rev-parse', '-q', '--verify', 'HEAD'], capture_output=True,
                          text=True).stdout.strip()
    if head != commit:
        git(src, 'fetch', '-q', '--depth', '1', 'origin', commit)
    git(src, 'checkout', '-q', '-f', commit)
    if clean:  # (not for shaderc itself: its third_party folder holds the other checkouts)
        git(src, 'clean', '-q', '-fdx')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', type=Path, default=ROOT / 'toolchain' / 'src' / 'shaderc')
    ap.add_argument('--out', type=Path, default=ROOT / 'toolchain' / 'shaderc')
    ap.add_argument('--cc', default=os.environ.get('HM_CC', 'clang'))
    a = ap.parse_args()
    for tool in ('git', 'cmake', 'ninja', a.cc.split()[0], a.cc.split()[0] + '++'):
        if not shutil.which(tool):
            sys.exit(f'build_shaderc: {tool} not found')
    src, out = a.src.resolve(), a.out.resolve()
    lib, stamp = out / 'lib' / 'libshaderc_combined.a', out / 'COMMIT'
    if lib.is_file() and stamp.is_file() and stamp.read_text().strip() == STAMP:
        print(f'build_shaderc: {out} already at {PARTS[0][2][:7]}')
        return
    for sub, url, commit in PARTS:
        fetch(src / sub, url, commit, clean=bool(sub))
    build = src / 'build-hm'
    shutil.rmtree(build, ignore_errors=True)
    env = {k: v for k, v in os.environ.items() if k not in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS')}
    log = src / 'build.log'
    steps = (
        ['cmake', '-S', str(src), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         f'-DCMAKE_C_COMPILER={a.cc}', f'-DCMAKE_CXX_COMPILER={a.cc}++', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
         '-DBUILD_SHARED_LIBS=OFF', '-DSHADERC_SKIP_TESTS=ON', '-DSHADERC_SKIP_EXAMPLES=ON',
         '-DSHADERC_SKIP_COPYRIGHT_CHECK=ON', '-DSPIRV_SKIP_EXECUTABLES=ON',
         '-DENABLE_GLSLANG_BINARIES=OFF', '-DGLSLANG_TESTS=OFF'],
        # (install rules stay on: shaderc's SHADERC_SKIP_INSTALL leaves glslang's on and breaks the configure;
        # nothing is installed anyway, the one archive is copied out below)
        ['cmake', '--build', str(build), '--target', 'shaderc_combined'],
    )
    with open(log, 'w') as f:
        for cmd in steps:
            if subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode:
                sys.exit(f'build_shaderc: {cmd[0]} {cmd[1]} failed; log: {log}')
    built = build / 'libshaderc' / 'libshaderc_combined.a'
    if not built.is_file():
        sys.exit(f'build_shaderc: {built} was not built; log: {log}')
    shutil.rmtree(out, ignore_errors=True)
    (out / 'lib').mkdir(parents=True)
    shutil.copy2(built, lib)
    shutil.copytree(src / 'libshaderc' / 'include', out / 'include')
    for name, to in LICENSES:
        shutil.copy2(src / name, out / to)
    stamp.write_text(STAMP + '\n')
    print(f'build_shaderc: {out} built at {PARTS[0][2][:7]} (shaderc v2026.4)')


if __name__ == '__main__':
    main()
