#!/usr/bin/env python3
"""Refuse game-derived content, keys and blobs in the repository.

  python3 tools/check_content.py --staged      what `git commit` would record (the pre-commit hook)
  python3 tools/check_content.py --tracked     every tracked file
  python3 tools/check_content.py PATH...       files on disk

Fails (exit 1) on: forbidden extensions (game containers, executables, keys), files over SIZE_LIMIT, binary files
outside the small allowlist, high-entropy text (embedded blobs), key-looking hex strings, files under game-data
paths, and files carrying the generator's marker. Prints one line per problem; never prints file contents.
"""

import argparse
import math
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every file the lifter emits starts with this marker (recomp/ writes it); no tracked file may contain it.
GENERATED_MARKER = 'HYLIAN-MELODIES-GENERATED: do not commit'
SIZE_LIMIT = 512 * 1024

FORBIDDEN_EXT = {
    '.xci', '.xcz', '.nsp', '.nsz', '.nca', '.ncz', '.nso', '.nro', '.npdm', '.nacp', '.tik', '.cert', '.keys',
    '.bntx', '.bnsh', '.bffnt', '.bfttf', '.bank', '.fsb', '.bfsar', '.bars', '.szs', '.sarc', '.zs',
    '.elf', '.so', '.a', '.o', '.dll', '.exe', '.bin', '.dat', '.mp4', '.webm', '.spv', '.pkg', '.zst',
}
FORBIDDEN_NAMES = {'prod.keys', 'title.keys', 'dev.keys', 'keys.txt', 'main', 'sdk', 'rtld', 'subsdk0',
                   'subsdk1', 'subsdk2', 'control.nacp'}
GAME_DIRS = {'extracted', 'generated', 'build', 'stage', 'firmware', 'romfs', 'exefs', 'toolchain', 'install-temp',
             'refs'}
# Binary files that are allowed (our own art), by extension; still size-limited.
BINARY_OK_EXT = {'.png', '.ico'}
# Files allowed to contain 32/64-hex-digit strings (hashes of official files are facts, not keys).
HEX_OK_FILES = {'installer/known.py', 'tests/test_check_content.py', 'tools/check_content.py'}
HEX_CONTEXT = re.compile(r'sha-?256|sha256sums|hash|digest|commit|build[ _-]?id|checksum', re.I)
HEX_TOKEN = re.compile(r'(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{64})(?![0-9A-Fa-f])')
KEYFILE_LINE = re.compile(r'^\s*[a-z][a-z0-9_]*\s*=\s*[0-9A-Fa-f]{32,}\s*$', re.M)


def entropy(s):
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def check(path, data):
    """Problems with one file (path: repo-relative POSIX path, data: bytes)."""
    p = PurePosixPath(path)
    probs = []
    name = p.name.lower()
    if p.suffix.lower() in FORBIDDEN_EXT or name in FORBIDDEN_NAMES or name.endswith('.keys'):
        probs.append('forbidden file type or name')
    if any(part in GAME_DIRS for part in p.parts[:-1]):
        probs.append('under a game-data directory')
    if len(data) > SIZE_LIMIT:
        probs.append(f'larger than {SIZE_LIMIT // 1024} KiB ({len(data)} bytes)')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        if p.suffix.lower() not in BINARY_OK_EXT:
            probs.append('binary file')
        return probs
    if '\0' in text and p.suffix.lower() not in BINARY_OK_EXT:
        probs.append('binary file')
        return probs
    if GENERATED_MARKER in text and path != 'tools/check_content.py' and not path.startswith('tests/') \
            and not path.startswith('recomp/'):
        probs.append('carries the generated-code marker')
    if KEYFILE_LINE.search(text):
        probs.append('looks like a keys file (name = hex)')
    if path not in HEX_OK_FILES:
        for i, line in enumerate(text.splitlines(), 1):
            if HEX_TOKEN.search(line) and not HEX_CONTEXT.search(line):
                probs.append(f'line {i}: key-looking hex string (32 or 64 hex digits without a hash/commit context)')
                break
    for i, line in enumerate(text.splitlines(), 1):
        s = max(line.split(), key=len, default='')
        if len(s) >= 200 and entropy(s) > 4.5:
            probs.append(f'line {i}: high-entropy run of {len(s)} characters (embedded blob?)')
            break
    return probs


def git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, check=True).stdout


def staged():
    out = git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z').decode()
    for path in filter(None, out.split('\0')):
        yield path, git('show', f':{path}')


def tracked():
    out = git('ls-files', '-z').decode()
    for path in filter(None, out.split('\0')):
        full = os.path.join(ROOT, path)
        if os.path.isfile(full):
            with open(full, 'rb') as f:
                yield path, f.read()


def on_disk(paths):
    for p in paths:
        rel = os.path.relpath(os.path.abspath(p), ROOT).replace(os.sep, '/')
        with open(p, 'rb') as f:
            yield rel, f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--staged', action='store_true')
    g.add_argument('--tracked', action='store_true')
    ap.add_argument('paths', nargs='*')
    a = ap.parse_args(argv)
    files = staged() if a.staged else tracked() if a.tracked or not a.paths else on_disk(a.paths)
    bad = 0
    for path, data in files:
        for prob in check(path, data):
            print(f'check_content: {path}: {prob}', file=sys.stderr)
            bad += 1
    if bad:
        print(f'check_content: {bad} problem(s); see CONTRIBUTING.md "Content rules"', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
