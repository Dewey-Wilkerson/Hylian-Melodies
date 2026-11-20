"""installer/pack.py: the package tree, the generated control file / spec / pacman PKGBUILD, derived dependencies."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from installer import pack  # noqa: E402


class Pack(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm pack-')  # (a space in the path on purpose)
        self.addCleanup(shutil.rmtree, self.t)
        self.stage = os.path.join(self.t, 'stage')
        for d in ('romfs/video', 'exefs', 'aoc/0100', 'profile', 'cache', 'logs'):
            os.makedirs(os.path.join(self.stage, d))
        for f in ('romfs/video/a.bin', 'exefs/main', 'aoc/0100/x', 'profile/save', 'hm-install.json',
                  'hylian-melodies.ini', 'cache/c'):
            with open(os.path.join(self.stage, f), 'w') as fh:
                fh.write(f)
        shutil.copy(shutil.which('true'), os.path.join(self.stage, 'hylian-melodies'))  # (a real ELF for strip)
        self.root = os.path.join(self.t, 'root')

    def listing(self):
        out = []
        for d, ds, fs in os.walk(self.root):
            out += [os.path.relpath(os.path.join(d, f), self.root) for f in fs]
        return sorted(out)

    def test_settings_in_the_default(self):
        from installer import options
        pack.build_root(self.stage, ROOT, self.root, {'fullscreen': True, 'gpu': 'auto'})
        ini = os.path.join(self.root, 'usr/share/hylian-melodies-recomp/hylian-melodies.ini')
        self.assertEqual(options.read_settings(ini), {'fullscreen': True})
        with open(ini) as f:
            self.assertIn('# volume = 1.0', f.read())

    def test_tree(self):
        files = pack.build_root(self.stage, ROOT, self.root)
        got = self.listing()
        for want in ('opt/hylian-melodies/hylian-melodies', 'opt/hylian-melodies/romfs/video/a.bin',
                     'opt/hylian-melodies/exefs/main', 'opt/hylian-melodies/aoc/0100/x', 'usr/bin/hylian-melodies',
                     'usr/share/applications/hylian-melodies.desktop',
                     'usr/share/hylian-melodies-recomp/hylian-melodies.ini',
                     'usr/share/hylian-melodies-recomp/desktop-copy',
                     'usr/share/licenses/hylian-melodies-recomp/LICENSE'):
            self.assertIn(want, got)
        # nothing of a player's or the setup's own ships
        for bad in ('profile', 'cache', 'logs', 'hm-install.json', 'opt/hylian-melodies/hylian-melodies.ini'):
            self.assertFalse([g for g in got if g.startswith('opt/hylian-melodies/' + bad) or g == bad], bad)
        self.assertEqual(len([g for g in got if '/icons/hicolor/' in g]), 1)  # (no icon.jpg here: the project's SVG)
        self.assertIn('/usr/share/icons/hicolor/scalable/apps/hylian-melodies.svg', files)
        # game data is hard-linked, the executable is a copy (it gets stripped), the launcher is executable
        a = os.stat(os.path.join(self.stage, 'romfs/video/a.bin'))
        b = os.stat(os.path.join(self.root, 'opt/hylian-melodies/romfs/video/a.bin'))
        self.assertEqual(a.st_ino, b.st_ino)
        self.assertNotEqual(os.stat(os.path.join(self.stage, 'hylian-melodies')).st_ino,
                            os.stat(os.path.join(self.root, 'opt/hylian-melodies/hylian-melodies')).st_ino)
        self.assertTrue(os.access(os.path.join(self.root, 'usr/bin/hylian-melodies'), os.X_OK))
        self.assertEqual(os.stat(os.path.join(self.root, 'opt/hylian-melodies/romfs')).st_mode & 0o777, 0o755)
        with open(os.path.join(self.root, 'usr/share/hylian-melodies-recomp/desktop-copy')) as f:
            self.assertTrue(f.read().strip().endswith('/hylian-melodies.desktop'))
        self.assertGreater(pack.tree_kib(self.root), 0)

    def test_not_a_setup_folder(self):
        os.remove(os.path.join(self.stage, 'hylian-melodies'))
        with self.assertRaises(pack.PackError):
            pack.build_root(self.stage, ROOT, self.root)

    def test_runtime_packages(self):
        owner = {'/l/libSDL3.so.0': 'sdl3', '/l/libavcodec.so.61': 'libavcodec61', '/l/libc.so.6': 'libc6',
                 '/l/libX11.so.6': 'libx11-6', '/l/libpulse.so.0': 'libpulse0'}.get
        keep = pack.needed, pack.library_paths, pack.loader_paths
        self.addCleanup(lambda: [setattr(pack, n, f) for n, f in zip(('needed', 'library_paths', 'loader_paths'), keep)])
        pack.library_paths = lambda exe: {n: '/l/' + n for n in ('libSDL3.so.0', 'libavcodec.so.61', 'libc.so.6')}
        pack.loader_paths = lambda names: {n: '/l/' + n for n in ('libX11.so.6', 'libpulse.so.0', 'libc.so.6')}
        pack.needed = lambda exe: ['libSDL3.so.0', 'libavcodec.so.61', 'libc.so.6', 'libc.so.6']
        self.assertEqual(pack.runtime_packages('x', owner),
                         (['sdl3', 'libavcodec61', 'libc6'], ['fontconfig', 'xdg-user-dirs']))
        # our own SDL3 is linked in: what it opens by name becomes recommendations (minus what is needed anyway)
        pack.needed = lambda exe: ['libavcodec.so.61', 'libc.so.6']
        self.assertEqual(pack.runtime_packages('x', owner),
                         (['libavcodec61', 'libc6'], ['libx11-6', 'libpulse0', 'fontconfig', 'xdg-user-dirs']))
        pack.needed = lambda exe: ['libgone.so.1']
        with self.assertRaises(pack.PackError):
            pack.runtime_packages('x', owner)

    def test_real_executable_dependencies(self):
        exe = shutil.which('true')
        self.assertTrue(any(n.startswith('libc.so') for n in pack.needed(exe)))
        self.assertTrue(set(pack.needed(exe)) <= set(pack.library_paths(exe)))

    def test_generated_texts(self):
        hooks = pack.hooks_text(ROOT)
        c = pack.deb_control('0.1.0', ['libc6', 'libsdl3-0'], ['fontconfig'], 2048)
        self.assertIn('Package: hylian-melodies-recomp\nVersion: 0.1.0\nArchitecture: amd64\n', c)
        self.assertIn('Depends: libc6, libsdl3-0\nRecommends: fontconfig\n', c)
        self.assertTrue(c.endswith('\n') and '\n\n' not in c)
        self.assertNotIn('Recommends', pack.deb_control('0.1.0', ['libc6'], [], 1))
        post = pack.deb_script(hooks, 'case "$1" in configure) post_install ;; esac')
        self.assertTrue(post.startswith('#!/bin/sh\n') and post.rstrip().endswith('exit 0'))
        r = subprocess.run(['sh', '-n'], input=post, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = pack.rpm_spec('0.1.0', '/w/pkgroot', ['/opt/hylian-melodies', '/usr/bin/hylian-melodies'], hooks)
        self.assertIn('stat -c %%U', spec)        # (rpm would expand a single %)
        self.assertNotIn('stat -c %U', spec.replace('%%U', ''))
        for want in ('AutoProv: no', '%define _binary_payload w0.ufdio', '%global __os_install_post %{nil}',
                     'if [ "$1" = 0 ]; then pre_remove; fi', '%defattr(-,root,root,-)\n/opt/hylian-melodies\n'):
            self.assertIn(want, spec)
        pb = pack.arch_pkgbuild('0.1.0-rc1', "/w/it's here/pkgroot", ['sdl3', 'glibc'], ['fontconfig'])
        self.assertIn('pkgver=0.1.0.rc1\n', pb)
        self.assertIn('depends=(sdl3 glibc vulkan-driver)', pb)
        self.assertIn("options=(!strip !debug)", pb)
        r = subprocess.run(['bash', '-n'], input=pb, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rpm_refuses_a_path_with_a_space(self):
        with self.assertRaises(pack.PackError):
            pack.pack_rpm(self.root, ROOT, self.t, self.t, [])

    @unittest.skipUnless(shutil.which('dpkg-deb') and shutil.which('dpkg-query'), 'needs dpkg')
    def test_deb_builds(self):
        out = os.path.join(self.t, 'out')
        target = pack.pack(self.stage, ROOT, out, os.path.join(self.t, 'work'), 'deb')
        info = subprocess.run(['dpkg-deb', '-f', target, 'Package', 'Depends'], capture_output=True, text=True).stdout
        self.assertIn('hylian-melodies-recomp', info)
        self.assertIn('libc6', info)
        names = subprocess.run(['dpkg-deb', '-c', target], capture_output=True, text=True).stdout
        self.assertIn('./opt/hylian-melodies/romfs/video/a.bin', names)
        self.assertIn('root/root', names)


if __name__ == '__main__':
    unittest.main()
