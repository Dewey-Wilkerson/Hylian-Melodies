"""M10: settings_save (runtime/settings.c) keeps the player's file and changes only what the menu changed."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = shutil.which(os.environ.get('HM_CC', 'clang')) or shutil.which('cc')
DEFAULT_INI = os.path.join(ROOT, 'packaging', 'hylian-melodies.ini')


@unittest.skipUnless(CC, 'no C compiler')
class SettingsSave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp(prefix='hm-settings-')
        cls.exe = os.path.join(cls.t, 'test_settings')
        subprocess.run([CC, '-std=gnu11', '-Wall', '-Werror', '-I', os.path.join(ROOT, 'runtime'),
                        os.path.join(ROOT, 'tests', 'c', 'test_settings.c'), os.path.join(ROOT, 'runtime', 'settings.c'),
                        '-o', cls.exe], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.t)

    def save(self, text, *changes):
        p = os.path.join(self.t, 'hylian-melodies.ini')
        if text is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            with open(p, 'w') as f:
                f.write(text)
        subprocess.run([self.exe, p, *changes], check=True)
        self.assertFalse(os.path.exists(p + '.tmp'))
        with open(p) as f:
            return f.read()

    def test_default_file_commented_examples_replaced_in_place(self):
        with open(DEFAULT_INI) as f:
            old = f.read()
        new = self.save(old, 'show_fps=1', 'volume=0.5')
        ol, nl = old.splitlines(), new.splitlines()
        self.assertEqual(len(ol), len(nl))
        diff = [(a, b) for a, b in zip(ol, nl) if a != b]
        self.assertEqual(len(diff), 2)
        self.assertTrue(any(b.startswith('show_fps = 1 ') and b.endswith(a.split('#', 2)[2]) for a, b in diff))
        self.assertIn('volume = 0.50', nl)

    def test_uncommented_line_wins_and_others_kept(self):
        old = '# my notes\nfoo = 7\n# fullscreen = 0\nfullscreen = 0   # mine\nkey.a = J\n'
        new = self.save(old, 'fullscreen=1')
        self.assertEqual(new, '# my notes\nfoo = 7\n# fullscreen = 0\nfullscreen = 1   # mine\nkey.a = J\n')

    def test_unchanged_keys_not_written(self):
        old = 'fullscreen = 0\n'
        self.assertEqual(self.save(old, 'volume=0.25'), 'fullscreen = 0\n\n# --- set in the menu\nvolume = 0.25\n')

    def test_missing_file_created(self):
        self.assertEqual(self.save(None, 'frame_pacing=0'), '\n# --- set in the menu\nframe_pacing = 0\n')

    def test_bindings_replace_old_lines_in_place(self):
        old = 'a = 1\nkey.a = J\nb = 2\npad.b = east\n# key.x = C\n'
        new = self.save(old, 'bindings=key.a = X\\npad.a = east\\n')
        self.assertEqual(new, 'a = 1\nkey.a = X\npad.a = east\nb = 2\n# key.x = C\n')

    def test_bindings_reset_removes_lines(self):
        self.assertEqual(self.save('a = 1\nkey.a = J\n', 'bindings='), 'a = 1\n')

    def test_bindings_appended_when_none(self):
        new = self.save('a = 1\n', 'bindings=key.a = X\\n')
        self.assertTrue(new.startswith('a = 1\n\n# --- controls'))
        self.assertTrue(new.endswith('key.a = X\n'))


if __name__ == '__main__':
    unittest.main()
