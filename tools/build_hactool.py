#!/usr/bin/env python3
"""Build hactool from a pinned upstream commit (SciresM/hactool, ISC license) on this machine.

  python3 tools/build_hactool.py [--src DIR] [--out DIR] [--cc CC]

Fetches only the pinned commit into --src (default toolchain/src/hactool), discards any local changes there,
applies tools/hactool/*.patch if present, builds with the system cc and make (mbedtls comes with hactool's tree), and
copies hactool and its LICENSE to --out (default toolchain/hactool). Nothing of hactool is vendored in this repo.
Modelled on totk-pc-recomp's tool of the same name (own implementation).
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = 'https://github.com/SciresM/hactool.git'
COMMIT = '1d64a83450e025622f3468c28fc4164dad2c5ef6'
PATCH_DIR = ROOT / 'tools' / 'hactool'


def git(src, *args, capture=False):
    return subprocess.run(['git', '-C', str(src), *args], check=True, capture_output=capture, text=True)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', type=Path, default=ROOT / 'toolchain' / 'src' / 'hactool')
    ap.add_argument('--out', type=Path, default=ROOT / 'toolchain' / 'hactool')
    ap.add_argument('--cc', default=os.environ.get('HM_HACTOOL_CC', 'cc'))
    a = ap.parse_args()
    for tool in ('git', 'make', a.cc.split()[0]):
        if not shutil.which(tool):
            sys.exit(f'build_hactool: {tool} not found (install base-devel and git)')
    src, out = a.src.resolve(), a.out.resolve()
    exe = out / 'hactool'
    stamp = out / 'COMMIT'
    patches = sorted(PATCH_DIR.glob('*.patch')) if PATCH_DIR.is_dir() else []
    want = COMMIT + ''.join(' ' + p.name for p in patches)
    if exe.is_file() and stamp.is_file() and stamp.read_text().strip() == want:
        print(f'build_hactool: {exe} already at {COMMIT[:7]}')
        return
    fetch(src)
    for p in patches:
        git(src, 'apply', '--whitespace=nowarn', str(p))
    (src / 'config.mk').write_text(
        f'CC = {a.cc}\nEXEEXT =\nCFLAGS = -O2 -Wall -Wextra -std=gnu11\n'
        'LDFLAGS = -lmbedtls -lmbedx509 -lmbedcrypto\n')
    env = {k: v for k, v in os.environ.items() if k not in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS')}
    r = subprocess.run(['make', f'-j{os.cpu_count() or 4}', f'CC={a.cc}'], cwd=src, env=env, capture_output=True,
                       text=True)
    (src / 'build.log').write_text(r.stdout + r.stderr)
    if r.returncode:
        sys.exit(f'build_hactool: make failed ({r.returncode}); log: {src / "build.log"}')
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / 'hactool', exe)
    shutil.copy2(src / 'LICENSE', out / 'LICENSE')
    # Banner check with an empty HOME: hactool would otherwise read the builder's ~/.switch keys.
    with tempfile.TemporaryDirectory() as home:
        r = subprocess.run([str(exe)], capture_output=True, text=True, env=dict(env, HOME=home))
    if 'hactool (c) SciresM' not in r.stdout + r.stderr:
        sys.exit(f'build_hactool: {exe} does not start')
    stamp.write_text(want + '\n')
    print(f'build_hactool: {exe} built at {COMMIT[:7]}')


if __name__ == '__main__':
    main()
