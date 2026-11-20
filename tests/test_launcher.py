"""M9: the launcher against a fake install and a fake HOME (brief 8.5)."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, 'packaging', 'hylian-melodies.sh')
FAKE_EXE = '#!/bin/sh\necho "ran $(pwd) $*" > "$HOME/ran.txt"\necho "${HM_GAME_DIR:-unset}" > "$HOME/gamedir.txt"\n# v%d\n'


class Launcher(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-launch-')
        self.addCleanup(shutil.rmtree, self.t)
        self.game, self.support, self.home = (os.path.join(self.t, d) for d in ('game', 'support', 'home'))
        for d in (self.game, self.support, self.home):
            os.makedirs(d)
        self.write_exe(1)
        os.makedirs(os.path.join(self.game, 'romfs'))
        open(os.path.join(self.game, 'romfs', 'a.dat'), 'w').close()
        open(os.path.join(self.game, 'data.txt'), 'w').close()
        os.makedirs(os.path.join(self.game, 'cache'))
        open(os.path.join(self.game, 'cache', 'pack'), 'w').close()
        with open(os.path.join(self.support, 'hylian-melodies.ini'), 'w') as f:
            f.write('default=1\n')
        self.dir = os.path.join(self.home, '.local', 'share', 'hylian-melodies')

    def write_exe(self, v):
        p = os.path.join(self.game, 'hylian-melodies')
        with open(p, 'w') as f:
            f.write(FAKE_EXE % v + '#' * v)
        os.chmod(p, 0o755)
        t = time.time() + v
        os.utime(p, (t, t))

    def run_launcher(self, *args):
        env = dict({k: v for k, v in os.environ.items() if k != 'XDG_DATA_HOME'}, HOME=self.home, HM_GAME_DIR=self.game, HM_SUPPORT_DIR=self.support)
        r = subprocess.run(['sh', LAUNCHER, *args], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def p(self, *n):
        return os.path.join(self.dir, *n)

    def test_first_run(self):
        self.run_launcher('--x', 'y z')
        self.assertTrue(os.path.isfile(self.p('.hylian-melodies')))
        self.assertTrue(os.path.isdir(self.p('profile')))
        self.assertTrue(os.path.isfile(self.p('hylian-melodies')) and not os.path.islink(self.p('hylian-melodies')))
        self.assertTrue(os.path.islink(self.p('romfs')) and os.path.islink(self.p('data.txt')))
        self.assertTrue(os.path.isdir(self.p('cache')) and not os.path.islink(self.p('cache')))
        self.assertTrue(os.path.islink(self.p('cache', 'pack')))
        with open(self.p('hylian-melodies.ini')) as f:
            self.assertEqual(f.read(), 'default=1\n')
        with open(os.path.join(self.home, 'ran.txt')) as f:
            self.assertEqual(f.read().strip(), f'ran {self.dir} --x y z')
        with open(os.path.join(self.home, 'gamedir.txt')) as f:  # (the game uses the player's folder, not the install)
            self.assertEqual(f.read().strip(), 'unset')

    def test_links_into_an_earlier_appimage_mount_go(self):
        os.makedirs(self.dir)
        old = '/tmp/.mount_HylianXXXXXX/opt/hylian-melodies/dropped.dat'  # (gone: the image is mounted elsewhere now)
        os.symlink(old, self.p('dropped.dat'))
        os.symlink('/no/such/file', self.p('mine'))  # (the player's own dead link: left alone)
        self.run_launcher()
        self.assertFalse(os.path.lexists(self.p('dropped.dat')))
        self.assertTrue(os.path.islink(self.p('mine')))

    def test_copy_renewed_when_install_changes(self):
        self.run_launcher()
        self.write_exe(2)
        self.run_launcher()
        with open(self.p('hylian-melodies')) as f:
            self.assertIn('# v2', f.read())
        self.assertFalse(os.path.exists(self.p('hylian-melodies.new')))

    def test_symlinked_exe_replaced_by_copy(self):
        self.run_launcher()
        os.remove(self.p('hylian-melodies'))
        os.symlink(os.path.join(self.game, 'hylian-melodies'), self.p('hylian-melodies'))
        self.run_launcher()
        self.assertFalse(os.path.islink(self.p('hylian-melodies')))

    def test_dangling_links_pruned(self):
        self.run_launcher()
        os.remove(os.path.join(self.game, 'data.txt'))
        os.remove(os.path.join(self.game, 'cache', 'pack'))
        self.run_launcher()
        self.assertFalse(os.path.lexists(self.p('data.txt')))
        self.assertFalse(os.path.lexists(self.p('cache', 'pack')))

    def test_user_file_never_overwritten(self):
        os.makedirs(self.dir)
        with open(self.p('data.txt'), 'w') as f:
            f.write('mine')
        self.run_launcher()
        self.run_launcher()
        self.assertFalse(os.path.islink(self.p('data.txt')))
        with open(self.p('data.txt')) as f:
            self.assertEqual(f.read(), 'mine')

    def test_settings_seeded_once(self):
        self.run_launcher()
        with open(self.p('hylian-melodies.ini'), 'w') as f:
            f.write('mine=1\n')
        with open(os.path.join(self.support, 'hylian-melodies.ini'), 'w') as f:
            f.write('default=2\n')
        self.run_launcher()
        with open(self.p('hylian-melodies.ini')) as f:
            self.assertEqual(f.read(), 'mine=1\n')
        os.remove(self.p('hylian-melodies.ini'))
        with open(self.p('hylian-melodies.ini.upgrade-keep'), 'w') as f:
            f.write('kept=1\n')
        self.run_launcher()
        with open(self.p('hylian-melodies.ini')) as f:
            self.assertEqual(f.read(), 'kept=1\n')

    def test_xdg_data_home(self):
        xdg = os.path.join(self.t, 'xdg')
        env = {k: v for k, v in os.environ.items() if k != 'XDG_DATA_HOME'}
        env.update(HOME=self.home, XDG_DATA_HOME=xdg, HM_GAME_DIR=self.game, HM_SUPPORT_DIR=self.support)
        r = subprocess.run(['sh', LAUNCHER], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(xdg, 'hylian-melodies', '.hylian-melodies')))
        self.assertFalse(os.path.exists(self.dir))

    def test_missing_install_fails_clearly(self):
        os.remove(os.path.join(self.game, 'hylian-melodies'))
        env = dict({k: v for k, v in os.environ.items() if k != 'XDG_DATA_HOME'}, HOME=self.home, HM_GAME_DIR=self.game, HM_SUPPORT_DIR=self.support)
        r = subprocess.run(['sh', LAUNCHER], env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('is hylian-melodies-recomp installed', r.stderr)

    def test_relative_home_rejected(self):
        env = dict(os.environ, HOME='relative', HM_GAME_DIR=self.game)
        r = subprocess.run(['sh', LAUNCHER], env=env, capture_output=True, text=True, cwd=self.t)
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
