"""M9: pre_remove of hylian-melodies-recomp.install against a fake install and a fake player home (brief 8.5)."""

import getpass
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL = os.path.join(ROOT, 'packaging', 'arch', 'hylian-melodies-recomp.install')
LAUNCHER = os.path.join(ROOT, 'packaging', 'arch', 'hylian-melodies.sh')


class PreRemove(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-hooks-')
        self.addCleanup(shutil.rmtree, self.t)
        self.game, self.support, self.home = (os.path.join(self.t, d) for d in ('game', 'support', 'home'))
        for d in (self.game, self.support, self.home):
            os.makedirs(d)
        exe = os.path.join(self.game, 'hylian-melodies')
        with open(exe, 'w') as f:
            f.write('#!/bin/sh\nexit 0\n')
        os.chmod(exe, 0o755)
        os.makedirs(os.path.join(self.game, 'romfs'))
        os.makedirs(os.path.join(self.game, 'shader-cache'))
        open(os.path.join(self.game, 'shader-cache', 'pack'), 'w').close()
        self.env = dict(os.environ, HOME=self.home, HM_GAME_DIR=self.game, HM_SUPPORT_DIR=self.support)
        subprocess.run(['sh', LAUNCHER], env=self.env, check=True)
        self.dir = os.path.join(self.home, '.local', 'share', 'hylian-melodies')
        os.makedirs(os.path.join(self.dir, 'profile'), exist_ok=True)
        with open(os.path.join(self.dir, 'profile', 'save.bin.txt'), 'w') as f:
            f.write('save')
        with open(os.path.join(self.dir, 'hylian-melodies.ini'), 'w') as f:
            f.write('mine')
        self.desk = os.path.join(self.t, 'Desktop', 'hylian-melodies.desktop')
        os.makedirs(os.path.dirname(self.desk))
        open(self.desk, 'w').close()
        with open(os.path.join(self.support, 'desktop-copy'), 'w') as f:
            f.write(self.desk + '\n')

    def run_hook(self, fn):
        script = (f'. "{INSTALL}"\n'
                  f'_players() {{ printf "%s %s\\n" "{getpass.getuser()}" "{self.home}"; }}\n'
                  f'{fn}\n')
        return subprocess.run(['sh', '-c', script], env=self.env, capture_output=True, text=True)

    def test_pre_remove_keeps_user_data(self):
        r = self.run_hook('pre_remove')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.desk))
        left = sorted(os.listdir(self.dir))
        self.assertEqual(left, ['hylian-melodies.ini', 'profile'])
        self.assertTrue(os.path.isfile(os.path.join(self.dir, 'profile', 'save.bin.txt')))
        self.assertIn('Kept', r.stdout)

    def test_pre_remove_removes_empty_folders(self):
        os.remove(os.path.join(self.dir, 'profile', 'save.bin.txt'))
        os.remove(os.path.join(self.dir, 'hylian-melodies.ini'))
        r = self.run_hook('pre_remove')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.listdir(self.dir), [])

    def test_pre_remove_leaves_foreign_symlinks_and_desktop_symlink(self):
        os.symlink('/etc/hostname', os.path.join(self.dir, 'mylink'))
        os.remove(self.desk)
        os.symlink('/etc/hostname', self.desk)
        self.run_hook('pre_remove')
        self.assertTrue(os.path.islink(os.path.join(self.dir, 'mylink')))
        self.assertTrue(os.path.islink(self.desk))


if __name__ == '__main__':
    unittest.main()
