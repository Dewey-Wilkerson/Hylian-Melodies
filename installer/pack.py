"""Wrap a finished setup folder (python -m installer --dest DIR) into this distro's package.

  python3 -m installer.pack --stage DIR --out DIR [--work DIR] [--format arch|deb|rpm] [--root REPO]

One package tree is laid out for all three formats (same paths, launcher, menu entry and hooks as
docs/packaging.md), then the distro's own tool wraps it: makepkg, dpkg-deb or rpmbuild. Nothing is installed and
nothing runs as root: the last line printed is a JSON object with the package file and the command the player runs
to install it. THE PACKAGE CONTAINS THE GAME: it is for the computer's owner only and must never be shared.

Run-time dependencies are not a written list (library package names change with every release): pacman and deb
packages get the packages that own the libraries the built executable loads; rpmbuild finds them itself.
"""

import argparse
import errno
import json
import os
import shutil
import subprocess
import sys

from . import deps
from . import options

NAME = 'hylian-melodies-recomp'
SUMMARY = 'Native Linux build of your own Cadence of Hyrule (static recompilation; personal use only)'
LONG = ('Built on this computer from its owner\'s cartridge dump. The package contains the game: it is for '
        'personal use only and must never be shared.')
GAME = 'opt/hylian-melodies'
SUPPORT = 'usr/share/' + NAME
KEEP = ('exefs', 'romfs', 'aoc', 'hylian-melodies')  # of the setup folder; the rest is the setup's or a player's own
HOOKS = 'packaging/arch/hylian-melodies-recomp.install'
FORMATS = {'arch': 'arch', 'debian': 'deb', 'fedora': 'rpm', 'suse': 'rpm'}
INSTALL = {'arch': 'sudo pacman -U {}', 'debian': 'sudo apt install {}', 'fedora': 'sudo dnf install {}',
           'suse': 'sudo zypper install --allow-unsigned-rpm {}'}
REMOVE = {'arch': 'sudo pacman -R ' + NAME, 'debian': 'sudo apt remove ' + NAME, 'fedora': 'sudo dnf remove ' + NAME,
          'suse': 'sudo zypper remove ' + NAME}
OPTIONAL = ('fontconfig', 'xdg-user-dirs')  # (same names on all four families)

# What a statically linked SDL3 loads by name at run time (tools/build_sdl3.py): not in the executable's DT_NEEDED,
# so the packages that own them become recommendations.
SDL_LOADS = ('libwayland-client.so.0', 'libwayland-cursor.so.0', 'libwayland-egl.so.1', 'libxkbcommon.so.0',
             'libdecor-0.so.0', 'libX11.so.6', 'libXext.so.6', 'libXcursor.so.1', 'libXi.so.6', 'libXfixes.so.3',
             'libXrandr.so.2', 'libXss.so.1', 'libpipewire-0.3.so.0', 'libpulse.so.0', 'libasound.so.2',
             'libudev.so.1', 'libdbus-1.so.3')


class PackError(Exception):
    pass


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ------------------------------------------------------------------ the package tree

def link_tree(src, dst):
    """Copy a folder as hard links (no extra space); plain copies when the two are on different file systems."""
    for d, dirs, files in os.walk(src):
        out = os.path.join(dst, os.path.relpath(d, src))
        os.makedirs(out, exist_ok=True)
        for f in files:
            a, b = os.path.join(d, f), os.path.join(out, f)
            if os.path.islink(a):
                os.symlink(os.readlink(a), b)
                continue
            try:
                os.link(a, b)
            except OSError as e:
                if e.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK):
                    raise
                shutil.copy2(a, b)


def make_icon(stage, repo, root):
    """The menu icon: the game's own (the setup extracts icon.jpg from the dump) as a 256 px PNG, else the project's
    SVG as it is. -> the path inside the tree"""
    tool = shutil.which('magick') or shutil.which('convert')
    jpg = os.path.join(stage, 'icon.jpg')
    if tool and os.path.isfile(jpg):
        rel = 'usr/share/icons/hicolor/256x256/apps/hylian-melodies.png'
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        if run([tool, jpg, '-resize', '256x256', os.path.join(root, rel)]).returncode == 0:
            return rel
    rel = 'usr/share/icons/hicolor/scalable/apps/hylian-melodies.svg'
    os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
    shutil.copy(os.path.join(repo, 'packaging', 'hylian-melodies.svg'), os.path.join(root, rel))
    return rel


def desktop_copy_path(env=None):
    """Where the post-install hook puts a desktop shortcut for the person building the package."""
    env = env or os.environ
    home = env.get('HOME', '')
    desk = ''
    if shutil.which('xdg-user-dir'):
        desk = run(['xdg-user-dir', 'DESKTOP'], env=env).stdout.strip()
    if not desk or desk == home:
        desk = os.path.join(home, 'Desktop')
    return os.path.join(desk, 'hylian-melodies.desktop')


def build_root(stage, repo, root, settings=None):
    """Lay out the package tree in `root` (must not exist). -> the files and folders it holds, as package paths"""
    exe = os.path.join(stage, 'hylian-melodies')
    if not os.path.isfile(exe) or not os.path.isdir(os.path.join(stage, 'romfs')):
        raise PackError(f'{stage} is not a finished setup folder (no game executable or no romfs)')
    if os.path.exists(root):
        raise PackError(f'{root} exists already')
    game = os.path.join(root, GAME)
    os.makedirs(game)
    for name in KEEP:
        src = os.path.join(stage, name)
        if os.path.isdir(src):
            link_tree(src, os.path.join(game, name))
    # the executable without debug data: a copy, never the setup folder's own file. Crash reports name host
    # functions from its dynamic symbols, which stay.
    shutil.copy2(exe, os.path.join(game, 'hylian-melodies'))
    r = run(['strip', '--strip-debug', os.path.join(game, 'hylian-melodies')])
    if r.returncode:
        raise PackError('strip failed: ' + r.stderr.strip())

    def put(src, rel, mode=0o644):
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(repo, src), dst)
        os.chmod(dst, mode)
    put('packaging/arch/hylian-melodies.sh', 'usr/bin/hylian-melodies', 0o755)
    put('packaging/arch/hylian-melodies.desktop', 'usr/share/applications/hylian-melodies.desktop')
    put('packaging/hylian-melodies.ini', SUPPORT + '/hylian-melodies.ini')
    if settings:  # the installer's choices in the default a player's first start copies (installer/options.py)
        options.write_settings(os.path.join(root, SUPPORT, options.INI), settings)
    put('LICENSE', f'usr/share/licenses/{NAME}/LICENSE')
    icon = make_icon(stage, repo, root)
    with open(os.path.join(root, SUPPORT, 'desktop-copy'), 'w') as f:
        f.write(desktop_copy_path() + '\n')
    for d, dirs, files in os.walk(root):  # readable by every player, writable by the owner (root, once installed)
        os.chmod(d, 0o755)
        for f in files:
            p = os.path.join(d, f)
            if not os.path.islink(p):
                os.chmod(p, 0o755 if os.access(p, os.X_OK) else 0o644)
    return ['/' + GAME, '/usr/bin/hylian-melodies', '/usr/share/applications/hylian-melodies.desktop', '/' + icon,
            '/' + SUPPORT, f'/usr/share/licenses/{NAME}']


def tree_kib(root):
    seen, total = set(), 0
    for d, dirs, files in os.walk(root):
        for f in files:
            st = os.lstat(os.path.join(d, f))
            if st.st_ino not in seen:
                seen.add(st.st_ino)
                total += st.st_size
    return (total + 1023) // 1024


def version(repo):
    with open(os.path.join(repo, 'VERSION')) as f:
        return f.read().strip()


def hooks_text(repo):
    with open(os.path.join(repo, HOOKS)) as f:
        return f.read()


# ------------------------------------------------------------------ run-time dependencies

def needed(exe):
    """The executable's DT_NEEDED names."""
    r = run(['readelf', '-d', exe])
    if r.returncode:
        raise PackError('readelf failed: ' + r.stderr.strip())
    return [ln.split('[', 1)[1].rstrip().rstrip(']') for ln in r.stdout.splitlines() if '(NEEDED)' in ln]


def library_paths(exe):
    """soname -> path, as the dynamic loader resolves them for this executable."""
    out = {}
    for ln in run(['ldd', exe]).stdout.splitlines():
        f = ln.split()
        if len(f) >= 3 and f[1] == '=>' and f[2].startswith('/'):
            out[f[0]] = f[2]
    return out


def loader_paths(sonames):
    """soname -> path from the loader's cache, for libraries the executable only opens by name."""
    cache = {}
    for ln in run(['ldconfig', '-p']).stdout.splitlines():
        f = ln.split()
        if len(f) >= 4 and f[-2] == '=>' and 'x86-64' in ln:
            cache.setdefault(f[0], f[-1])
    return {s: cache[s] for s in sonames if s in cache}


def owners(paths, query):
    """The packages owning these files, in order, each once. query(path) -> package name or None"""
    out = []
    for p in paths:
        name = query(os.path.realpath(p)) or query(p)
        if name and name not in out:
            out.append(name)
    return out


def dpkg_owner(path):
    r = run(['dpkg-query', '-S', path])
    return r.stdout.split(':', 1)[0].strip() if r.returncode == 0 and r.stdout.strip() else None


def pacman_owner(path):
    r = run(['pacman', '-Qqo', path])
    return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else None


def runtime_packages(exe, query):
    """-> (depends, recommends) package names for the built executable on this system."""
    need = needed(exe)
    paths = library_paths(exe)
    missing = [n for n in need if n not in paths]
    if missing:
        raise PackError('the game executable needs libraries this system does not have: ' + ' '.join(missing))
    depends = owners([paths[n] for n in need], query)
    recommends = []
    if not any(n.startswith('libSDL3') for n in need):  # our own SDL3 is linked in
        recommends = [p for p in owners(loader_paths(SDL_LOADS).values(), query) if p not in depends]
    return depends, recommends + [p for p in OPTIONAL if p not in depends and p not in recommends]


# ------------------------------------------------------------------ deb

def deb_control(ver, depends, recommends, kib):
    return (f'Package: {NAME}\nVersion: {ver}\nArchitecture: amd64\nMaintainer: local build <root@localhost>\n'
            f'Installed-Size: {kib}\nDepends: {", ".join(depends)}\n'
            + (f'Recommends: {", ".join(recommends)}\n' if recommends else '')
            + f'Section: games\nPriority: optional\nDescription: {SUMMARY}\n {LONG}\n')


def deb_script(hooks, body):
    # (no `set -e`: the hooks are written for pacman, where a failing test at the end of a function is harmless)
    return '#!/bin/sh\n' + hooks + '\n' + body + '\nexit 0\n'


def pack_deb(root, repo, out, work):
    exe = os.path.join(root, GAME, 'hylian-melodies')
    depends, recommends = runtime_packages(exe, dpkg_owner)
    ver = version(repo)
    kib = tree_kib(root)
    meta = os.path.join(root, 'DEBIAN')
    os.makedirs(meta)
    hooks = hooks_text(repo)
    files = {'control': (deb_control(ver, depends, recommends, kib), 0o644),
             'postinst': (deb_script(hooks, 'case "$1" in configure) post_install ;; esac'), 0o755),
             'prerm': (deb_script(hooks, 'case "$1" in remove) pre_remove ;; esac'), 0o755)}
    for name, (text, mode) in files.items():
        with open(os.path.join(meta, name), 'w') as f:
            f.write(text)
        os.chmod(os.path.join(meta, name), mode)
    os.chmod(meta, 0o755)
    target = os.path.join(out, f'{NAME}_{ver}_amd64.deb')
    # -Znone: gigabytes of already-compressed game data; --root-owner-group: no fakeroot needed
    r = run(['dpkg-deb', '--root-owner-group', '-Znone', '--build', root, target])
    if r.returncode:
        raise PackError('dpkg-deb failed: ' + (r.stderr or r.stdout).strip())
    return target


# ------------------------------------------------------------------ rpm

def rpm_spec(ver, root, files, hooks):
    hooks = hooks.replace('%', '%%')  # (rpm expands % in scriptlets)
    listed = '\n'.join(files)
    return f'''# generated by installer/pack.py
%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%global _build_id_links none
%define _binary_payload w0.ufdio
Name: {NAME}
Version: {ver}
Release: 1
Summary: {SUMMARY}
License: MIT AND LicenseRef-Personal-Copy-Of-The-Game
AutoProv: no
Recommends: {" ".join(OPTIONAL)}

%description
{LONG}

%install
mkdir -p %{{buildroot}}
cp -al "{root}"/. %{{buildroot}}/ 2>/dev/null || cp -a "{root}"/. %{{buildroot}}/

%post
{hooks}
post_install
exit 0

%preun
{hooks}
if [ "$1" = 0 ]; then pre_remove; fi
exit 0

%files
%defattr(-,root,root,-)
{listed}
'''


def pack_rpm(root, repo, out, work, files):
    for p in (root, out, work):
        if ' ' in p:
            raise PackError(f'rpmbuild cannot work in a path with a space in it: {p}')
    ver = version(repo)
    top = os.path.join(work, 'rpmbuild')
    os.makedirs(top, exist_ok=True)
    spec = os.path.join(top, NAME + '.spec')
    with open(spec, 'w') as f:
        f.write(rpm_spec(ver, root, files, hooks_text(repo)))
    r = run(['rpmbuild', '-bb', '--define', f'_topdir {top}', '--define', f'_rpmdir {out}',
             '--define', '_rpmfilename %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm', spec])
    if r.returncode:
        raise PackError('rpmbuild failed: ' + (r.stderr or r.stdout).strip()[-2000:])
    return os.path.join(out, f'{NAME}-{ver}-1.x86_64.rpm')


# ------------------------------------------------------------------ pacman

def arch_pkgbuild(ver, root, depends, recommends):
    q = "'" + root.replace("'", "'\\''") + "'"
    opt = '\n            '.join(f"'{p}'" for p in recommends)
    return f'''# generated by installer/pack.py
pkgname={NAME}
pkgver={ver.replace("-", ".")}
pkgrel=1
pkgdesc='{SUMMARY}'
arch=(x86_64)
url='https://localhost/hylian-melodies'
license=(MIT)
depends=({" ".join(depends)} vulkan-driver)
optdepends=({opt})
options=(!strip !debug)
install={NAME}.install
PKGEXT='.pkg.tar'

package() {{
    cp -al {q}/. "$pkgdir"/ 2>/dev/null || cp -a {q}/. "$pkgdir"/
}}
'''


def pack_arch(root, repo, out, work):
    exe = os.path.join(root, GAME, 'hylian-melodies')
    depends, recommends = runtime_packages(exe, pacman_owner)
    ver = version(repo)
    d = os.path.join(work, 'makepkg')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'PKGBUILD'), 'w') as f:
        f.write(arch_pkgbuild(ver, root, depends, recommends))
    shutil.copy(os.path.join(repo, HOOKS), os.path.join(d, NAME + '.install'))
    # -d: the dependencies were read off this system's own libraries just now; makepkg need not look them up
    r = run(['makepkg', '-f', '-d'], cwd=d, env=dict(os.environ, PKGDEST=out, BUILDDIR=d))
    if r.returncode:
        raise PackError('makepkg failed: ' + (r.stderr or r.stdout).strip()[-2000:])
    return os.path.join(out, f'{NAME}-{ver.replace("-", ".")}-1-x86_64.pkg.tar')


# ------------------------------------------------------------------

def pack(stage, repo, out, work, fmt, settings=None):
    stage, repo, out, work = (os.path.abspath(p) for p in (stage, repo, out, work))
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    root = os.path.join(work, 'pkgroot')
    shutil.rmtree(root, ignore_errors=True)
    files = build_root(stage, repo, root, settings)
    if fmt == 'deb':
        target = pack_deb(root, repo, out, work)
    elif fmt == 'rpm':
        target = pack_rpm(root, repo, out, work, files)
    elif fmt == 'arch':
        target = pack_arch(root, repo, out, work)
    else:
        raise PackError(f'unknown package format {fmt}')
    if not os.path.isfile(target):
        raise PackError(f'the package was not written: {target}')
    shutil.rmtree(root, ignore_errors=True)
    return target


def this_family():
    try:
        with open('/etc/os-release') as f:
            return deps.family(deps.parse_os_release(f.read()))
    except OSError:
        return None


def commands(fmt, target, fam=None):
    """-> (install command, remove command) for a package of this format, worded for this distro family."""
    fam = fam or this_family()
    if FORMATS.get(fam) != fmt:
        fam = {'arch': 'arch', 'deb': 'debian', 'rpm': 'fedora'}[fmt]
    q = "'" + target.replace("'", "'\\''") + "'" if any(c in target for c in ' \'"$') else target
    return INSTALL[fam].format(q), REMOVE[fam]


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m installer.pack', description=__doc__.splitlines()[0])
    ap.add_argument('--stage', required=True, help='the finished setup folder (python -m installer --dest)')
    ap.add_argument('--out', required=True, help='where the package file goes')
    ap.add_argument('--work', help='scratch folder, on the same file system as --stage to save space '
                                   '(default: <out>/pack-work)')
    ap.add_argument('--format', choices=('arch', 'deb', 'rpm'), help="default: this distro's")
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='repository root')
    a = ap.parse_args(argv)
    fmt = a.format or FORMATS.get(this_family())
    if not fmt:
        print(json.dumps({'result': 'error', 'error': 'no package format for this distribution; pass --format'}))
        return 1
    try:
        target = pack(a.stage, a.root, a.out, a.work or os.path.join(a.out, 'pack-work'), fmt)
    except PackError as e:
        print(json.dumps({'result': 'error', 'error': str(e)}))
        return 1
    print(json.dumps({'result': 'ok', 'format': fmt, 'file': target, 'install': commands(fmt, target)[0]}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
