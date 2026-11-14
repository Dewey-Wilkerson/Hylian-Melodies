"""What the build needs from the system, whether it is there, and the command that gets it.

  python3 -m installer.deps [--json] [--os-release FILE]

Every need is checked by capability (a command on PATH, a pkg-config module, a Python import, a one-line compile),
never by asking the package manager for a package name: a renamed package cannot produce a false "missing". The
package names are used only to print one command for the player to run; nothing is installed from here. The table
was tried on bare images of each distro (docs/installer.md, section 9).
"""

import argparse
import json
import shutil
import subprocess
import sys

FAMILIES = ('arch', 'debian', 'fedora', 'suse')

# family -> the command a player runs (the package names are appended)
INSTALL = {
    'arch': 'sudo pacman -S --needed',
    'debian': 'sudo apt install',
    'fedora': 'sudo dnf install',
    'suse': 'sudo zypper install',
}

# the distro's own packaging tool, for the system-package output
PACKER = {'arch': 'makepkg', 'debian': 'dpkg-deb', 'fedora': 'rpmbuild', 'suse': 'rpmbuild'}

# Releases whose repositories have no SDL3: (os-release ID, first VERSION_ID that has it, its name)
SDL3_SINCE = {'debian': ((13,), 'Debian 13'), 'ubuntu': ((26, 4), 'Ubuntu 26.04')}

FFMPEG = ('libavformat', 'libavcodec', 'libavutil', 'libswscale')


def _need(key, what, check, arch, debian, fedora, suse, group='build'):
    return {'key': key, 'what': what, 'check': check, 'group': group,
            'packages': {'arch': arch.split(), 'debian': debian.split(), 'fedora': fedora.split(),
                         'suse': suse.split()}}


# check: ('cmd', names...) | ('pc', modules...) | ('pcver', module, minimum) | ('py', module) | ('cxx',)
NEEDS = [
    _need('git', 'git (fetches hactool, Dear ImGui and the VMA header at pinned commits)', ('cmd', 'git'),
          'git', 'git ca-certificates', 'git', 'git'),
    _need('curses', "Python's curses module (this installer's screens)", ('py', 'curses'),
          'python', 'python3', 'python3', 'python3-curses', group='ui'),
    _need('clang', 'clang and clang++ (compile the game)', ('cmd', 'clang', 'clang++'),
          'clang', 'clang', 'clang', 'clang'),
    _need('lld', 'the lld linker', ('cmd', 'ld.lld'), 'lld', 'lld', 'lld', 'lld'),
    _need('ninja', 'ninja', ('cmd', 'ninja'), 'ninja', 'ninja-build', 'ninja-build', 'ninja'),
    _need('make', 'make and a C compiler (build hactool)', ('cmd', 'make', 'cc'),
          'make gcc', 'make gcc', 'make gcc', 'make gcc'),
    _need('cxx', 'the C++ standard library headers', ('cxx',), 'gcc', 'g++', 'gcc-c++', 'gcc-c++'),
    _need('pkg-config', 'pkg-config', ('cmd', 'pkg-config'),
          'pkgconf', 'pkgconf', 'pkgconf-pkg-config', 'pkgconf-pkg-config'),
    _need('strip', 'strip (binutils)', ('cmd', 'strip'), 'binutils', 'binutils', 'binutils', 'binutils'),
    _need('sdl3', 'SDL3 development files', ('pc', 'sdl3'), 'sdl3', 'libsdl3-dev', 'SDL3-devel', 'SDL3-devel'),
    _need('ffmpeg', 'FFmpeg development files (the game\'s movies)', ('pc',) + FFMPEG,
          'ffmpeg', ' '.join(m + '-dev' for m in FFMPEG), ' '.join(m + '-free-devel' for m in FFMPEG),
          ' '.join(f'pkgconfig({m})' for m in FFMPEG)),
    _need('vulkan', 'Vulkan headers (1.3 or newer) and loader', ('pcver', 'vulkan', '1.3'),
          'vulkan-headers vulkan-icd-loader', 'libvulkan-dev', 'vulkan-headers vulkan-loader-devel', 'vulkan-devel'),
    _need('shaderc', 'shaderc development files', ('pc', 'shaderc'),
          'shaderc', 'libshaderc-dev', 'libshaderc-devel', 'shaderc-devel'),
    _need('magick', 'ImageMagick (the menu icon)', ('cmd', 'magick'),
          'imagemagick', 'imagemagick', 'ImageMagick', 'ImageMagick', group='package'),
    _need('packer', "the distro's packaging tool", ('packer',),
          'base-devel', 'dpkg', 'rpm-build', 'rpm-build', group='package'),
]


def parse_os_release(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        out[k.strip()] = v
    return out


def family(osr):
    """arch | debian | fedora | suse | None from os-release's ID, then ID_LIKE."""
    ids = [osr.get('ID', '').lower()] + osr.get('ID_LIKE', '').lower().split()
    for i in ids:
        if i in ('arch', 'archlinux'):
            return 'arch'
        if i in ('debian', 'ubuntu'):
            return 'debian'
        if i in ('fedora', 'rhel', 'centos'):
            return 'fedora'
        if i in ('suse', 'opensuse') or i.startswith('opensuse'):
            return 'suse'
    return None


def _version(s):
    out = []
    for part in s.split('.'):
        if not part.isdigit():
            break
        out.append(int(part))
    return tuple(out)


def sdl3_since(osr):
    """The first release of this distro with an SDL3 package when this one is older, else None."""
    since = SDL3_SINCE.get(osr.get('ID', '').lower())
    have = _version(osr.get('VERSION_ID', ''))
    if since and have and have < since[0]:
        return since[1]
    return None


class Probe:
    """The real checks; tests pass their own object with the same four methods."""

    def cmd(self, name):
        return shutil.which(name) is not None

    def pc(self, module, minimum=None):
        if not shutil.which('pkg-config'):
            return False
        arg = [f'--atleast-version={minimum}'] if minimum else ['--exists']
        return subprocess.run(['pkg-config', *arg, module], capture_output=True).returncode == 0

    def py(self, module):
        return subprocess.run([sys.executable, '-c', f'import {module}'], capture_output=True).returncode == 0

    def cxx(self):
        if not shutil.which('clang++'):
            return False
        return subprocess.run(['clang++', '-x', 'c++', '-fsyntax-only', '-'], input=b'#include <vector>\n',
                              capture_output=True).returncode == 0


def _ok(need, fam, probe):
    kind, *args = need['check']
    if kind == 'cmd':
        return all(probe.cmd(a) for a in args)
    if kind == 'pc':
        return all(probe.pc(a) for a in args)
    if kind == 'pcver':
        return probe.pc(args[0], args[1])
    if kind == 'py':
        return probe.py(args[0])
    if kind == 'cxx':
        return probe.cxx()
    if kind == 'packer':
        return fam is None or probe.cmd(PACKER[fam])
    raise ValueError(kind)


def check(osr, probe=None, groups=('build', 'ui', 'package')):
    """-> {'family', 'needs': [{key, what, group, ok, packages}], 'missing': [keys], 'command', 'notes': [text]}"""
    probe = probe or Probe()
    fam = family(osr)
    needs, pkgs, notes = [], [], []
    for n in NEEDS:
        if n['group'] not in groups:
            continue
        ok = _ok(n, fam, probe)
        mine = n['packages'][fam] if fam else []
        needs.append({'key': n['key'], 'what': n['what'], 'group': n['group'], 'ok': ok, 'packages': mine})
        if not ok:
            pkgs += [p for p in mine if p not in pkgs]
    missing = [n['key'] for n in needs if not n['ok']]
    since = sdl3_since(osr)
    if 'sdl3' in missing and since:
        notes.append(f'This release has no SDL3 package (it starts with {since}): the system package cannot be '
                     'built here.')
        pkgs = [p for p in pkgs if p not in NEEDS_BY_KEY['sdl3']['packages'][fam]]
    if missing and not fam:
        notes.append('Unknown distribution: install the items marked missing with your package manager.')
    command = ''
    if fam and pkgs:
        command = INSTALL[fam] + ' ' + ' '.join(f"'{p}'" if '(' in p else p for p in pkgs)
    return {'family': fam, 'needs': needs, 'missing': missing, 'command': command, 'notes': notes}


NEEDS_BY_KEY = {n['key']: n for n in NEEDS}


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m installer.deps', description=__doc__.splitlines()[0])
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--os-release', default='/etc/os-release')
    a = ap.parse_args(argv)
    try:
        with open(a.os_release) as f:
            osr = parse_os_release(f.read())
    except OSError:
        osr = {}
    r = check(osr)
    if a.json:
        print(json.dumps(r))
    else:
        print(f"{osr.get('PRETTY_NAME', 'unknown distribution')} ({r['family'] or 'no package table'})")
        for n in r['needs']:
            print(f"  {'ok     ' if n['ok'] else 'MISSING'}  {n['what']}")
        for t in r['notes']:
            print(t)
        if r['command']:
            print('Run this, then check again:\n  ' + r['command'])
    return 1 if r['missing'] else 0


if __name__ == '__main__':
    sys.exit(main())
