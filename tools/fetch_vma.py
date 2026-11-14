#!/usr/bin/env python3
"""Fetch the Vulkan Memory Allocator header (GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator, MIT) at a pinned commit.

  python3 tools/fetch_vma.py [--src DIR]

Fetches only the pinned commit into --src (default toolchain/src/vma) and discards local changes there. Nothing of
VMA is vendored in this repo and no distro package is needed (Arch has it in the AUR only, and the packaged
versions differ); tools/build_game.py adds <src>/include to the include path. Prints the source directory.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = 'https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator.git'
COMMIT = '0f1a757da579831283413295cc7f3b47eb521c77'  # tag v3.5.0
HEADER = 'include/vk_mem_alloc.h'


def git(src, *args):
    subprocess.run(['git', '-C', str(src), *args], check=True)


def fetch(src):
    stamp = src / '.hm-stamp'
    if stamp.is_file() and stamp.read_text().strip() == COMMIT and (src / HEADER).is_file():
        return
    if not shutil.which('git'):
        sys.exit('fetch_vma: git not found')
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
    if not (src / HEADER).is_file():
        sys.exit(f'fetch_vma: {HEADER} is missing at {COMMIT[:7]}')
    stamp.write_text(COMMIT + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', type=Path, default=ROOT / 'toolchain' / 'src' / 'vma')
    a = ap.parse_args()
    src = a.src.resolve()
    fetch(src)
    print(src)


if __name__ == '__main__':
    main()
