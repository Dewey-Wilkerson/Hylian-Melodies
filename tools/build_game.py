#!/usr/bin/env python3
"""Write a Ninja file that compiles the generated C (and the runtime) and run Ninja.

  python3 tools/build_game.py --gen DIR --out DIR [--target linkcheck|game] [--march v2|v3|native]
                              [--vma DIR] [--sdl3 DIR] [--shaderc DIR] [-j N]

linkcheck: every generated object + tests/c/linkcheck_stub.c linked as a shared object with --no-undefined
(M3 acceptance: zero unresolved symbols). game: the runtime with the Vulkan backend and the SDL3 window + generated
code -> hylian-melodies. headless: the null backend, no window -> hylian-melodies-headless (M4 boot tests).
The game target takes the Vulkan Memory Allocator header from --vma DIR, default toolchain/src/vma, fetched there by
tools/fetch_vma.py when missing (offline once its stamp matches).
--sdl3 DIR links SDL3 statically from that folder (built by tools/build_sdl3.py) instead of the system's SDL3:
for distro releases without an SDL3 package. --shaderc DIR does the same for shaderc (tools/build_shaderc.py):
for releases whose shaderc package cannot be used.
The -march level defaults to x86-64-v2 (generic: any x86-64 CPU from about 2009 on), so the result runs on other
machines too. --march v3 (AVX2/FMA/BMI2, 2013+) or native is the opt-in "optimize for this computer's CPU"; v3 is
refused when this CPU lacks it, since the game could not start here.
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


MARCH = {'v2': 'x86-64-v2', 'v3': 'x86-64-v3', 'native': 'native'}
DEFAULT_MARCH = 'v2'


def cpu_has_v3():
    try:
        flags = open('/proc/cpuinfo').read().split('flags', 1)[1].split('\n', 1)[0].split()
    except (OSError, IndexError):
        return False
    return {'avx2', 'fma', 'bmi2', 'movbe'} <= set(flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gen', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--target', choices=('linkcheck', 'game', 'headless'), default='game')
    ap.add_argument('--march', choices=sorted(MARCH), default=DEFAULT_MARCH,
                    help='v2 (default, runs on any x86-64 CPU since ~2009), v3 or native (this computer only)')
    ap.add_argument('--cc', default=os.environ.get('HM_CC', 'clang'))
    ap.add_argument('--vma', default=os.path.join(ROOT, 'toolchain', 'src', 'vma'))
    ap.add_argument('--shaderc', help='folder of a static shaderc built by tools/build_shaderc.py (default: the system shaderc)')
    ap.add_argument('--sdl3', help='folder of a static SDL3 built by tools/build_sdl3.py (default: the system SDL3)')
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    for t in (a.cc, 'ninja', 'ld.lld'):
        if not shutil.which(t):
            sys.exit(f'build_game: {t} not found')
    if a.march == 'v3' and not cpu_has_v3():
        sys.exit('build_game: --march v3 needs AVX2/FMA/BMI2/MOVBE, which this CPU lacks; use v2')
    march = MARCH[a.march]
    gen, out = os.path.abspath(a.gen), os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    rt = os.path.join(ROOT, 'runtime')
    # (-ffile-prefix-map: no build path in the executable: __FILE__ and debug data name repo-relative files)
    pmap = (f'-ffile-prefix-map={shlex.quote(ROOT + os.sep)}= '
            f'-ffile-prefix-map={shlex.quote(os.path.abspath(a.gen) + os.sep)}=generated/')
    genflags = (f'-O1 -march={march} -fno-strict-aliasing -fPIC -fvisibility=hidden -Wno-return-type '
                f'-Wno-unused-label -Wno-unused-variable -I{shlex.quote(rt)} {pmap}')
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
        # game: Vulkan backend + SDL3 window (hylian-melodies); headless: the NVN front end with the null backend,
        # no window (hylian-melodies-headless, the M4 boot tests). Both share the generated objects.
        headless = a.target == 'headless'
        pkgs = ['libavformat', 'libavcodec', 'libavutil', 'libswscale'] + ([] if headless else ['vulkan', 'shaderc'])
        if not shutil.which('pkg-config'):
            sys.exit('build_game: pkg-config not found')

        def pc(*args, env=None):
            return subprocess.run(['pkg-config', *args], capture_output=True, text=True, env=env)
        if a.sdl3:  # our own static SDL3: the archive itself plus the system libraries its .pc file lists
            sdl = os.path.abspath(a.sdl3)
            sdl_pc = os.path.join(sdl, 'lib', 'pkgconfig', 'sdl3.pc')
            if not os.path.isfile(sdl_pc):
                sys.exit(f'build_game: no SDL3 in {a.sdl3} (run tools/build_sdl3.py --out there)')
            # (read here, not through pkg-config: its output does not quote a folder name with a space in it)
            private = [ln.split(':', 1)[1] for ln in open(sdl_pc) if ln.startswith('Libs.private:')]
            sdl_cflags = f'-I{shlex.quote(os.path.join(sdl, "include"))}'
            sdl_libs = ' '.join([shlex.quote(os.path.join(sdl, 'lib', 'libSDL3.a'))] +
                                [x for x in ' '.join(private).split() if x.startswith('-l') or x == '-pthread'])
        else:
            pkgs.insert(0, 'sdl3')
            sdl_cflags = sdl_libs = ''
        if a.shaderc and not headless:  # our own static shaderc: one archive with glslang and SPIRV-Tools inside
            sc = os.path.abspath(a.shaderc)
            sc_lib = os.path.join(sc, 'lib', 'libshaderc_combined.a')
            if not os.path.isfile(sc_lib):
                sys.exit(f'build_game: no shaderc in {a.shaderc} (run tools/build_shaderc.py --out there)')
            pkgs.remove('shaderc')
            sdl_cflags += f' -I{shlex.quote(os.path.join(sc, "include"))}'
            sdl_libs += f' {shlex.quote(sc_lib)}'
        missing = [p for p in pkgs if pc('--exists', p).returncode]
        if missing:
            sys.exit('build_game: development files not found (pkg-config): ' + ' '.join(missing))
        cflags = (sdl_cflags + ' ' + pc('--cflags', *pkgs).stdout.strip()).strip()
        libs = (sdl_libs + ' ' + pc('--libs', *pkgs).stdout.strip()).strip()
        inc = ' '.join(f'-I{shlex.quote(os.path.join(rt, d))}' for d in ('', 'nvn', 'nvn/vulkan', 'nvn/maxwell'))
        version = open(os.path.join(ROOT, 'VERSION')).read().strip()
        common = (f'-O2 -g {pmap} -DHM_VERSION=\\"{version}\\" -D_GNU_SOURCE -fno-strict-aliasing -Wall -Wno-unused-function -Wno-format '
                  f'-Wno-unused-variable -Wno-unused-but-set-variable -march={march} {inc} {cflags}')
        lines.insert(2, f'rtflags = -std=gnu11 {common}')
        lines.insert(3, f'rtcxxflags = -std=gnu++17 {common}')
        lines += ['rule rtcc', '  command = $cc $rtflags -MD -MF $out.d -c $in -o $out', '  depfile = $out.d',
                  '  deps = gcc', '  description = CC $in',
                  'rule rtcxx', f'  command = {a.cc}++ $rtcxxflags -MD -MF $out.d -c $in -o $out', '  depfile = $out.d',
                  '  deps = gcc', '  description = CXX $in']
        rsrcs = (glob.glob(os.path.join(rt, '*.c')) + glob.glob(os.path.join(rt, 'hle', '*.c')) +
                 glob.glob(os.path.join(rt, 'services', '*.c')) + glob.glob(os.path.join(rt, 'nvn', '*.c')) +
                 [os.path.join(rt, 'platform', 'linux.c')])
        if headless:  # (the renderer's helpers that need the Vulkan backend stay out)
            vk_only = ('pace.c', 'output_scale.c', 'shader_prep.c', 'shader_seen.c', 'slowframe.c')
            rsrcs = [x for x in rsrcs if os.path.basename(x) not in vk_only]
        else:
            rsrcs = [x for x in rsrcs if os.path.basename(x) not in ('null_backend.c', 'ui_headless.c')]
            rsrcs += (glob.glob(os.path.join(rt, 'nvn', 'vulkan', '*.c')) + glob.glob(os.path.join(rt, 'nvn', 'vulkan', '*.cpp'))
                      + glob.glob(os.path.join(rt, 'nvn', 'maxwell', '*.c')) + glob.glob(os.path.join(rt, 'ui', '*.c'))
                      + glob.glob(os.path.join(rt, 'ui', '*.cpp')))
        rtdir = 'rt-headless' if headless else 'rt'
        for src in sorted(rsrcs):
            rel = os.path.relpath(src, rt)
            o = os.path.join(out, rtdir, rel.rsplit('.', 1)[0] + '.o')
            objs.append(o)
            lines.append(f'build {nj(o)}: {"rtcxx" if src.endswith(".cpp") else "rtcc"} {nj(src)}')
        if not headless:  # the Vulkan Memory Allocator header (runtime/nvn/vulkan/vk.h, vma.cpp), pinned
            vma = os.path.abspath(a.vma)
            if subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'fetch_vma.py'), '--src', vma]).returncode:
                sys.exit('build_game: fetching the Vulkan Memory Allocator header failed')
            vinc = f' -I{shlex.quote(os.path.join(vma, "include"))} -ffile-prefix-map={shlex.quote(vma + os.sep)}=vma/'
            lines[2] += vinc
            lines[3] += vinc
        exe = 'hylian-melodies-headless' if headless else 'hylian-melodies'
        lines.append(f'build {nj(out)}/{exe}: link {" ".join(map(nj, objs))}')
        lines.append('  ldflags = -rdynamic' + ('' if headless else ' -DHM_GAME'))
        lines.append(f'  libs = {libs} -lstdc++ -lpthread -ldl -lm')
        lines.append(f'default {nj(out)}/{exe}')
    with open(os.path.join(out, 'build.ninja'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    r = subprocess.run(['ninja', '-C', out, f'-j{a.j}'])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
