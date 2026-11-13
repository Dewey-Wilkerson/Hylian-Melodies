#!/usr/bin/env python3
"""Write a Ninja file that compiles the generated C (and the runtime) and run Ninja.

  python3 tools/build_game.py --gen DIR --out DIR [--target linkcheck|game] [--march v3|v2|native] [-j N]

linkcheck: every generated object + tests/c/linkcheck_stub.c linked as a shared object with --no-undefined
(M3 acceptance: zero unresolved symbols). game: the runtime + generated code into the game executable (M4+).
The -march level defaults to x86-64-v3 when the CPU has AVX2/FMA/BMI2, else x86-64-v2.
"""

import argparse
import shlex
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nj(p):
    """A path in a Ninja build/dependency list."""
    return p.replace('$', '$$').replace(' ', '$ ').replace(':', '$:')


def cpu_level():
    try:
        flags = open('/proc/cpuinfo').read().split('flags', 1)[1].split('\n', 1)[0].split()
    except (OSError, IndexError):
        return 'x86-64-v2'
    return 'x86-64-v3' if {'avx2', 'fma', 'bmi2', 'movbe'} <= set(flags) else 'x86-64-v2'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gen', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target', choices=('linkcheck', 'game'), default='linkcheck')
    ap.add_argument('--march', default=None)
    ap.add_argument('--cc', default=os.environ.get('HM_CC', 'clang'))
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    for t in (a.cc, 'ninja', 'ld.lld'):
        if not shutil.which(t):
            sys.exit(f'build_game: {t} not found')
    march = {'v3': 'x86-64-v3', 'v2': 'x86-64-v2', None: cpu_level()}.get(a.march, a.march)
    gen, out = os.path.abspath(a.gen), os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    rt = os.path.join(ROOT, 'runtime')
    genflags = (f'-O1 -march={march} -fno-strict-aliasing -fPIC -fvisibility=hidden -Wno-return-type '
                f'-Wno-unused-label -Wno-unused-variable -I{shlex.quote(rt)}')
    srcs = sorted(glob.glob(os.path.join(gen, 'main', '*.c')) + glob.glob(os.path.join(gen, 'sdk', '*.c')))
    if not srcs:
        sys.exit(f'build_game: no generated C under {gen}')
    lines = [
        f'cc = {a.cc}',
        f'genflags = {genflags}',
        'rule cc',
        '  command = $cc $genflags $extra -MD -MF $out.d -c $in -o $out',
        '  depfile = $out.d',
        '  deps = gcc',
        '  description = CC $in',
        'rule link',
        '  command = $cc -fuse-ld=lld $ldflags $in -o $out $libs',
        '  description = LINK $out',
    ]
    objs = []
    for s in srcs:
        rel = os.path.relpath(s, gen)
        o = os.path.join(out, 'obj', rel[:-2] + '.o')
        objs.append(o)
        lines.append(f'build {nj(o)}: cc {nj(s)}')
    if a.target == 'linkcheck':
        stub = os.path.join(ROOT, 'tests', 'c', 'linkcheck_stub.c')
        so = os.path.join(out, 'obj', 'linkcheck_stub.o')
        lines.append(f'build {nj(so)}: cc {nj(stub)}')
        lines.append(f'build {nj(out)}/linkcheck.so: link {" ".join(map(nj, objs))} {nj(so)}')
        lines.append('  ldflags = -shared -Wl,--no-undefined')
        lines.append(f'default {nj(out)}/linkcheck.so')
    else:
        sys.exit('build_game: the game target arrives with the runtime (M4)')
    with open(os.path.join(out, 'build.ninja'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    r = subprocess.run(['ninja', '-C', out, f'-j{a.j}'])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
