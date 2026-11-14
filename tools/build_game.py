#!/usr/bin/env python3
"""Write a Ninja file that compiles the generated C (and the runtime) and run Ninja.

  python3 tools/build_game.py --gen DIR --out DIR [--target linkcheck|game] [--march v3|v2|native] [--imgui DIR] [-j N]

linkcheck: every generated object + tests/c/linkcheck_stub.c linked as a shared object with --no-undefined
(M3 acceptance: zero unresolved symbols). game: the runtime with the Vulkan backend and the SDL3 window + generated
code -> hylian-melodies. headless: the null backend, no window -> hylian-melodies-headless (M4 boot tests).
The game target also compiles Dear ImGui (the overlay menu) from --imgui DIR, default toolchain/src/imgui, fetched
there by tools/fetch_imgui.py when missing (offline once its stamp matches).
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
    ap.add_argument('--target', choices=('linkcheck', 'game', 'headless'), default='game')
    ap.add_argument('--march', default=None)
    ap.add_argument('--cc', default=os.environ.get('HM_CC', 'clang'))
    ap.add_argument('--imgui', default=os.path.join(ROOT, 'toolchain', 'src', 'imgui'))
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    for t in (a.cc, 'ninja', 'ld.lld'):
        if not shutil.which(t):
            sys.exit(f'build_game: {t} not found')
    march = {'v3': 'x86-64-v3', 'v2': 'x86-64-v2', None: cpu_level()}.get(a.march, a.march)
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
        pkgs = ['sdl3', 'libavformat', 'libavcodec', 'libavutil', 'libswscale'] + ([] if headless else ['vulkan', 'shaderc'])
        cflags = subprocess.run(['pkg-config', '--cflags', *pkgs], capture_output=True, text=True).stdout.strip()
        libs = subprocess.run(['pkg-config', '--libs', *pkgs], capture_output=True, text=True).stdout.strip()
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
            vk_only = ('pace.c', 'output_scale.c', 'shader_prep.c', 'shader_seen.c', 'slowframe.c', 'las_feature_stubs.c')
            rsrcs = [x for x in rsrcs if os.path.basename(x) not in vk_only]
        else:
            rsrcs = [x for x in rsrcs if os.path.basename(x) not in ('null_backend.c', 'ui_headless.c')]
            rsrcs += (glob.glob(os.path.join(rt, 'nvn', 'vulkan', '*.c')) + glob.glob(os.path.join(rt, 'nvn', 'vulkan', '*.cpp'))
                      + glob.glob(os.path.join(rt, 'nvn', 'maxwell', '*.c')) + glob.glob(os.path.join(rt, 'ui', '*.c'))
                      + glob.glob(os.path.join(rt, 'ui', '*.cpp')))
            rsrcs = [x for x in rsrcs if os.path.basename(x) != 'menu_stub.c']
        rtdir = 'rt-headless' if headless else 'rt'
        for src in sorted(rsrcs):
            rel = os.path.relpath(src, rt)
            o = os.path.join(out, rtdir, rel.rsplit('.', 1)[0] + '.o')
            objs.append(o)
            lines.append(f'build {nj(o)}: {"rtcxx" if src.endswith(".cpp") else "rtcc"} {nj(src)}')
        if not headless:  # Dear ImGui: the overlay menu (runtime/ui/menu.cpp, imgui_glue.cpp)
            imgui = os.path.abspath(a.imgui)
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'fetch_imgui.py'), '--src', imgui])
            if r.returncode:
                sys.exit('build_game: fetching Dear ImGui failed')
            iinc = f'-I{shlex.quote(imgui)} -I{shlex.quote(os.path.join(imgui, "backends"))}'
            # (rtcxxflags: menu.cpp and the glue include imgui.h; no build path from ImGui's assertions either)
            lines[3] += f' {iinc} -ffile-prefix-map={shlex.quote(imgui + os.sep)}=imgui/'
            lines += ['rule imgui', f'  command = {a.cc}++ $rtcxxflags -w -MD -MF $out.d -c $in -o $out',
                      '  depfile = $out.d', '  deps = gcc', '  description = CXX $in']
            for f in ('imgui.cpp', 'imgui_draw.cpp', 'imgui_tables.cpp', 'imgui_widgets.cpp',
                      'backends/imgui_impl_vulkan.cpp'):
                o = os.path.join(out, 'imgui', os.path.basename(f)[:-4] + '.o')
                objs.append(o)
                lines.append(f'build {nj(o)}: imgui {nj(os.path.join(imgui, f))}')
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
