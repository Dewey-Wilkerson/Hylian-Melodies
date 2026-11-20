"""What the build needs from the system, whether it is there, and the command that gets it.

  python3 -m installer.deps [--json] [--os-release FILE]

Every need is checked by capability (a command on PATH, a pkg-config module, a Python import, a one-line compile),
never by asking the package manager for a package name: a renamed package cannot produce a false "missing". The
package names are used only to print one command for the player to run; nothing is installed from here. The table
was tried on bare images of each distro (docs/installer.md, section 9).
"""

import argparse
import json
import os
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

# Releases whose repositories have no SDL3: (os-release ID, first VERSION_ID that has it, its name). On these
# SDL3 is built from source and linked into the game (tools/build_sdl3.py), which needs the 'sdl3-own' group below.
SDL3_SINCE = {'debian': ((13,), 'Debian 13'), 'ubuntu': ((26, 4), 'Ubuntu 26.04')}

# Releases whose shaderc package cannot be used (Debian 12: the library lacks the GLSL compiler it calls, so nothing
# links against it): shaderc is built from source and linked in (tools/build_shaderc.py). Same shape as SDL3_SINCE.
SHADERC_SINCE = {'debian': ((13,), 'Debian 13')}

# Releases where a need has another package name: os-release ID -> (first VERSION_ID with the usual name, {key: names})
# (Debian 12's `clang` is 14; 19 is in its repositories under a versioned name, in /usr/lib/llvm-19/bin)
OLD_PACKAGES = {'debian': ((13,), {'clang': ['clang-19'], 'lld': ['lld-19']})}

CLANG_MIN = 17  # (runtime/simd_fp.h uses __builtin_elementwise_fma)

# what SDL's own build looks for (pkg-config modules), so the built SDL3 has Wayland, X11, audio and gamepads
SDL3_OWN_PC = ('wayland-client', 'wayland-cursor', 'wayland-egl', 'egl', 'xkbcommon', 'libdecor-0', 'x11', 'xext',
               'xrandr', 'xcursor', 'xi', 'xfixes', 'xscrnsaver', 'xtst', 'libpipewire-0.3', 'libpulse', 'alsa',
               'libudev', 'dbus-1')

FFMPEG = ('libavformat', 'libavcodec', 'libavutil', 'libswscale')


def _need(key, what, check, arch, debian, fedora, suse, group='build'):
    return {'key': key, 'what': what, 'check': check, 'group': group,
            'packages': {'arch': arch.split(), 'debian': debian.split(), 'fedora': fedora.split(),
                         'suse': suse.split()}}


# check: ('cmd', names...) | ('anycmd', names...) | ('pc', modules...) | ('pcver', module, minimum) | ('py', module)
#        | ('cxx',) | ('clang', minimum major version) | ('packer',)
NEEDS = [
    _need('git', 'git (fetches hactool and the VMA header at pinned commits)', ('cmd', 'git'),
          'git', 'git ca-certificates', 'git', 'git'),
    _need('curses', "Python's curses module (this installer's screens)", ('py', 'curses'),
          'python', 'python3', 'python3', 'python3-curses', group='ui'),
    _need('clang', f'clang and clang++, version {CLANG_MIN} or newer (compile the game)', ('clang', CLANG_MIN),
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
    _need('cmake', 'cmake (builds the libraries this release lacks)', ('cmd', 'cmake'),
          'cmake', 'cmake', 'cmake', 'cmake', group='own'),
    _need('sdl3-headers', 'desktop development files SDL3 is built against (Wayland, X11, audio, udev, D-Bus)',
          ('pc',) + SDL3_OWN_PC, '',
          'libwayland-dev libxkbcommon-dev libegl-dev libdecor-0-dev libx11-dev libxext-dev libxrandr-dev '
          'libxcursor-dev libxi-dev libxfixes-dev libxss-dev libxtst-dev libpipewire-0.3-dev libpulse-dev '
          'libasound2-dev libudev-dev libdbus-1-dev', '', '', group='sdl3-own'),
    _need('magick', 'ImageMagick (the menu icon)', ('anycmd', 'magick', 'convert'),
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


# Immutable ("atomic") systems: the root file system is read-only, so no package can be installed and the build
# packages cannot be either. They get the generic AppImage, built in a container (installer/appimage.py).
# os-release ID -> name; VARIANT_ID values of Fedora's atomic desktops; and two markers on the running system.
IMMUTABLE_IDS = {'steamos': 'SteamOS', 'bazzite': 'Bazzite', 'bluefin': 'Bluefin', 'aurora': 'Aurora',
                 'opensuse-microos': 'openSUSE MicroOS', 'opensuse-aeon': 'openSUSE Aeon',
                 'opensuse-kalpa': 'openSUSE Kalpa', 'nixos': 'NixOS', 'vanillaos': 'Vanilla OS',
                 'vanilla': 'Vanilla OS', 'endless': 'Endless OS', 'blendos': 'blendOS', 'chimeraos': 'ChimeraOS'}
IMMUTABLE_VARIANTS = ('silverblue', 'kinoite', 'sericea', 'onyx', 'cosmic-atomic', 'atomic', 'coreos', 'iot')
OSTREE_MARKER = '/run/ostree-booted'  # (every rpm-ostree / bootc system: Silverblue, Kinoite, Bazzite, Bluefin...)


def usr_read_only(path='/usr'):
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return False


def immutable(osr, markers=True, exists=os.path.exists, read_only=usr_read_only):
    """-> the system's name when it is an immutable one (read-only root: no packages can be installed), else None.
    markers=False looks at the os-release fields only (tests, and an os-release that is not this system's)."""
    ids = [osr.get('ID', '').lower()] + osr.get('ID_LIKE', '').lower().split()
    name = osr.get('NAME') or osr.get('ID') or 'This system'
    for i in ids:
        if i in IMMUTABLE_IDS:
            return osr.get('NAME') or IMMUTABLE_IDS[i]
    variant = osr.get('VARIANT_ID', '').lower()
    if any(variant == v or variant.endswith('-' + v) or variant.startswith(v + '-') for v in IMMUTABLE_VARIANTS):
        return name
    if markers and (exists(OSTREE_MARKER) or read_only()):
        return name
    return None


# The AppImage is built in a container from this image: Debian 12's C library (2.36, 2022) is old enough that the
# result starts on every current distro, and Debian 12 is a release the build was tried on (docs/installer.md).
CONTAINER_BASE = 'docker.io/library/debian:12'
CONTAINER_OS = {'ID': 'debian', 'VERSION_ID': '12'}
CONTAINER_EXTRA = ('python3', 'squashfs-tools')  # (the base image has no Python; mksquashfs makes the AppImage)


def container_engine(which=shutil.which):
    """-> 'podman' or 'docker' (the first found), else None."""
    for name in ('podman', 'docker'):
        if which(name):
            return name
    return None


class _Nothing:
    """A probe of an empty system: every need is missing (to list the container's packages)."""
    def cmd(self, name): return False
    def pc(self, module, minimum=None): return False
    def py(self, module): return False
    def clang_major(self): return 0
    def cxx(self): return False


def container_packages():
    """The Debian 12 packages the build container installs: every need of this table, as for a bare Debian 12."""
    r = check(CONTAINER_OS, _Nothing())
    pkgs = []
    for n in r['needs']:
        pkgs += [p for p in n['packages'] if p not in pkgs]
    return list(CONTAINER_EXTRA) + [p for p in pkgs if p not in CONTAINER_EXTRA]


def _version(s):
    out = []
    for part in s.split('.'):
        if not part.isdigit():
            break
        out.append(int(part))
    return tuple(out)


def _older(table, osr):
    entry = table.get(osr.get('ID', '').lower())
    have = _version(osr.get('VERSION_ID', ''))
    return entry[1] if entry and have and have < entry[0] else None


def sdl3_since(osr):
    """The first release of this distro with an SDL3 package when this one is older, else None."""
    return _older(SDL3_SINCE, osr)


def shaderc_since(osr):
    """The first release of this distro with a usable shaderc package when this one is older, else None."""
    return _older(SHADERC_SINCE, osr)


def newer_clang_dir(root='/usr/lib'):
    """The bin folder of the newest versioned LLVM (Debian/Ubuntu: /usr/lib/llvm-N/bin) that is new enough."""
    best = (0, None)
    try:
        names = os.listdir(root)
    except OSError:
        return None
    for name in names:
        n = name[5:] if name.startswith('llvm-') else ''
        d = os.path.join(root, name, 'bin')
        if n.isdigit() and int(n) >= CLANG_MIN and int(n) > best[0] and os.path.isfile(os.path.join(d, 'clang')):
            best = (int(n), d)
    return best[1]


def use_newer_clang(probe=None):
    """When the clang on PATH is missing or too old and a newer versioned one is installed, put its folder first
    on this process's PATH (clang, clang++ and ld.lld are then found by their plain names). -> that folder or None"""
    probe = probe or Probe()
    if probe.clang_major() >= CLANG_MIN:
        return None
    d = newer_clang_dir()
    if d:
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
    return d


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

    def clang_major(self):
        """The major version of `clang` on PATH, 0 when there is none."""
        if not (shutil.which('clang') and shutil.which('clang++')):
            return 0
        r = subprocess.run(['clang', '-dumpversion'], capture_output=True, text=True)
        head = r.stdout.strip().split('.')[0]
        return int(head) if head.isdigit() else 0

    def cxx(self):
        if not shutil.which('clang++'):
            return False
        return subprocess.run(['clang++', '-x', 'c++', '-fsyntax-only', '-'], input=b'#include <vector>\n',
                              capture_output=True).returncode == 0


def _ok(need, fam, probe):
    kind, *args = need['check']
    if kind == 'cmd':
        return all(probe.cmd(a) for a in args)
    if kind == 'anycmd':
        return any(probe.cmd(a) for a in args)
    if kind == 'clang':
        return probe.clang_major() >= args[0]
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
    """-> {'family', 'sdl3': 'system'|'own', 'shaderc': 'system'|'own', 'needs': [{key, what, group, ok, packages}],
           'missing': [keys], 'command', 'notes': [text]}

    sdl3 'own': this release has no SDL3 package and none is installed, so tools/build_sdl3.py builds it and
    tools/build_game.py --sdl3 links it in; the 'sdl3-own' needs replace the 'sdl3' one. shaderc 'own': this
    release's shaderc package cannot be used; tools/build_shaderc.py and --shaderc, the same way."""
    probe = probe or Probe()
    fam = family(osr)
    needs, pkgs, notes = [], [], []
    own = sdl3_since(osr) is not None and not probe.pc('sdl3')
    own_sc = shaderc_since(osr) is not None
    renamed = _older(OLD_PACKAGES, osr) or {}
    for n in NEEDS:
        if n['group'] == 'sdl3-own':
            if not own:
                continue
        elif n['group'] == 'own':
            if not (own or own_sc):
                continue
        elif n['group'] not in groups or (own and n['key'] == 'sdl3') or (own_sc and n['key'] == 'shaderc'):
            continue
        ok = _ok(n, fam, probe)
        mine = renamed.get(n['key']) or (n['packages'][fam] if fam else [])
        needs.append({'key': n['key'], 'what': n['what'], 'group': n['group'], 'ok': ok, 'packages': mine})
        if not ok:
            pkgs += [p for p in mine if p not in pkgs]
    missing = [n['key'] for n in needs if not n['ok']]
    if own:
        notes.append(f'This release has no SDL3 package (it starts with {sdl3_since(osr)}): SDL3 is built from its '
                     'source and linked into the game, which adds about a minute.')
    if own_sc:
        notes.append("This release's shaderc package cannot be used (it starts working with "
                     f'{shaderc_since(osr)}): shaderc is built from its source and linked into the game, which '
                     'adds a few minutes.')
    if 'clang' in missing and probe.clang_major():
        notes.append(f'The clang found is version {probe.clang_major()}; version {CLANG_MIN} or newer is needed.')
    if missing and not fam:
        notes.append('Unknown distribution: install the items marked missing with your package manager.')
    command = ''
    if fam and pkgs:
        command = INSTALL[fam] + ' ' + ' '.join(f"'{p}'" if '(' in p else p for p in pkgs)
    return {'family': fam, 'sdl3': 'own' if own else 'system', 'shaderc': 'own' if own_sc else 'system',
            'needs': needs, 'missing': missing, 'command': command, 'notes': notes}



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
    use_newer_clang()
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
