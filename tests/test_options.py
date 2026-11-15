"""installer/options.py: the registry against the code, the generated list, the player's ini."""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from installer import options as O  # noqa: E402


def read_in_code():
    """Every HM_ name the runtime asks the environment for (getenv, or the ENV macro in runtime/hle.h)."""
    names = set()
    for d, _, files in os.walk(os.path.join(ROOT, 'runtime')):
        for f in files:
            if f.endswith(('.c', '.h', '.cpp')):
                with open(os.path.join(d, f), errors='replace') as fh:
                    code = re.sub(r'//[^\n]*', '', fh.read())  # (not the examples in comments)
                    names |= set(re.findall(r'\b(?:getenv|ENV)\("(HM_[A-Z0-9_]+)"\)', code))
    return names


class Registry(unittest.TestCase):
    def test_every_variable_is_in_exactly_one_group(self):
        listed = [o.env for o in O.SETTINGS if o.env] + list(O.INTERNAL) + ' '.join(O.DEVELOPER.values()).split()
        self.assertEqual(sorted(n for n in set(listed) if listed.count(n) > 1), [])
        code = read_in_code()
        self.assertEqual(sorted(code - set(listed)), [], 'read in runtime/ but not in installer/options.py')
        self.assertEqual(sorted(set(listed) - code), [], 'in installer/options.py but no longer read in runtime/')

    def test_the_owners_cut(self):
        self.assertEqual([o.key for o in O.offered('player')], ['fullscreen', 'gpu'])
        self.assertEqual(O.groups()['HM_NO_AUDIO'], 'developer')  # (a rhythm game: never offered)
        for o in O.SETTINGS:
            self.assertIsNone(o.check(o.default), o.key)
            if o.group == 'troubleshooting':
                self.assertIsNone(o.check(o.trouble), o.key)
                self.assertNotEqual(o.trouble, o.default)
            self.assertTrue(o.title and len(o.text) > 40)

    def test_every_key_is_read_by_the_game(self):
        with open(os.path.join(ROOT, 'runtime', 'settings.c')) as f:
            code = f.read()
        with open(os.path.join(ROOT, 'packaging', O.INI)) as f:
            default = f.read()
        for o in O.SETTINGS:
            self.assertIn(f'"{o.key}"', code, 'runtime/settings.c does not read ' + o.key)
            self.assertRegex(default, rf'(?m)^# {o.key} = {re.escape(o.text_of(o.default))}\b', 'not in the default ini')

    def test_doc_is_current(self):
        with open(os.path.join(ROOT, 'docs', 'env-vars.md')) as f:
            self.assertEqual(f.read(), O.env_doc(), 'run: python3 -m installer.options > docs/env-vars.md')


class Settings(unittest.TestCase):
    def test_check(self):
        self.assertEqual(O.check_settings({}), [])
        self.assertEqual(O.check_settings({'fullscreen': True, 'gpu': 1, 'audio_stats': 2.5, 'shader_cache': False}), [])
        for bad in ({'fullscreen': 1}, {'gpu': -1}, {'gpu': '1'}, {'gpu': True}, {'audio_stats': 'x'},
                    {'HM_NO_AUDIO': '1'}, {'volume': 0.5}, [], 'x'):
            self.assertTrue(O.check_settings(bad), bad)
        self.assertIn('a developer environment variable', O.check_settings({'HM_NO_AUDIO': '1'})[0])

    def test_write_keeps_the_players_lines(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, 'sub', O.INI)
            default = os.path.join(ROOT, 'packaging', O.INI)
            O.write_settings(path, {'fullscreen': True, 'gpu': 1, 'log_input': True}, default)
            with open(path) as f:
                text = f.read()
            self.assertIn('\nfullscreen = 1\n', text)
            self.assertRegex(text, r'\ngpu = 1  # which graphics card')  # (the default's example line, comment kept)
            self.assertIn('\nlog_input = 1  # 1: the buttons', text)
            self.assertIn('# volume = 1.0', text)  # (the rest of the default as it was)
            self.assertEqual(O.current(path)['gpu'], 1)
            with open(path, 'a') as f:  # what the menu and the player add
                f.write('volume = 0.40\n\n# --- controls (set in the menu; docs/controls.md)\nkey.a = J\n')
            O.write_settings(path, {'fullscreen': False, 'gpu': 'auto', 'log_input': False, 'audio_stats': 10})
            with open(path) as f:
                text = f.read()
            for want in ('\n# fullscreen = 0\n', '\n# gpu = auto  #', '\n# log_input = 0  #', '\naudio_stats = 10  #',
                         '\nvolume = 0.40\n', '\nkey.a = J\n'):
                self.assertIn(want, text)
            self.assertEqual(O.read_settings(path), {'audio_stats': 10})
            self.assertNotIn('set by the installer', text)

    def test_write_without_a_default_file(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, O.INI)
            with open(path, 'w') as f:
                f.write('fullscreen = 1   # mine\nvolume = 0.5\n')
            O.write_settings(path, {'fullscreen': False, 'shader_cache': False, 'vk_validation': True})
            with open(path) as f:
                self.assertEqual(f.read(), '# fullscreen = 0  # mine\nvolume = 0.5\n\n# --- set by the installer\n'
                                           'shader_cache = 0\nvk_validation = 1\n')
            O.write_settings(path, {'log_input': True})
            with open(path) as f:
                self.assertTrue(f.read().endswith('shader_cache = 0\nvk_validation = 1\nlog_input = 1\n'))

    def test_gpus(self):
        out = ('Devices:\n========\nGPU0:\n\tapiVersion = 1.4.3\n\tdeviceName = Fast Card (X)\n'
               'GPU1:\n\tdeviceName        = Built-in\n')
        if not __import__('shutil').which('vulkaninfo'):
            self.assertEqual(O.gpus(), [])
            return
        run = lambda *a, **k: subprocess.CompletedProcess(a, 0, out, '')  # noqa: E731
        self.assertEqual(O.gpus(run), [(0, 'Fast Card (X)'), (1, 'Built-in')])

        def broken(*a, **k):
            raise OSError('no')
        self.assertEqual(O.gpus(broken), [])


if __name__ == '__main__':
    unittest.main()
