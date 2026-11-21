"""The port's update check (runtime/update_check.c): version parsing, the release JSON, and a whole check against a
file:// release (HM_UPDATE_URL), as the game runs it. Needs curl for the last part; nothing reaches the network."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = shutil.which(os.environ.get('HM_CC', 'clang')) or shutil.which('cc')
MV = shutil.which('mv') or '/bin/mv'  # (the stand-ins run with a PATH of their folder alone)


def desktop_exec_args(line):
    """An Exec value (string escapes already undone) -> argv, by the Desktop Entry spec: arguments split on spaces;
    in double quotes, a backslash makes the next of " ` $ \\ literal."""
    args, cur, i, quoted, have = [], '', 0, False, False
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '\\' and i + 1 < len(line) and line[i + 1] in '"`$\\':
                cur += line[i + 1]
                i += 1
            elif ch == '"':
                quoted = False
            else:
                cur += ch
        elif ch == '"':
            quoted = have = True
        elif ch == ' ':
            if cur or have:
                args.append(cur)
            cur, have = '', False
        else:
            cur += ch
        i += 1
    if cur or have:
        args.append(cur)
    return args


@unittest.skipUnless(CC, 'no C compiler')
class UpdateCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp(prefix='hm-update-')
        cls.exe = os.path.join(cls.t, 'test_update_check')
        subprocess.run([CC, '-std=gnu11', '-Wall', '-Werror', '-I', os.path.join(ROOT, 'runtime'),
                        os.path.join(ROOT, 'tests', 'c', 'test_update_check.c'),
                        os.path.join(ROOT, 'runtime', 'update_check.c'), os.path.join(ROOT, 'runtime', 'settings.c'),
                        '-pthread', '-o', cls.exe], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.t)

    def run_exe(self, *args, env=None):
        r = subprocess.run([self.exe, *args], capture_output=True, text=True, check=True,
                           env={**os.environ, **(env or {})})
        return r.stdout.strip()

    def release(self, body):
        p = os.path.join(self.t, 'release.json')
        with open(p, 'w') as f:
            f.write(body)
        return p

    def test_parse(self):
        for text, want in [('v0.3.1', '0.3.1'), ('0.3', '0.3.0'), ('1', '1.0.0'), ('V2.10.4', '2.10.4'),
                           ('0.4.0-rc1', '0.4.0'), ('dev', 'no'), ('', 'no'), ('v', 'no'), ('1.2.x', 'no'),
                           ('1..2', 'no')]:
            self.assertEqual(self.run_exe('parse', text), want, text)

    def test_newer(self):
        for a, b, want in [('v0.3.1', '0.3.0', 'yes'), ('0.10.0', '0.9.9', 'yes'), ('1.0', '0.99.99', 'yes'),
                           ('0.3.0', '0.3.0', 'no'), ('0.2.9', '0.3.0', 'no'), ('v0.4.0', 'dev', 'no')]:
            self.assertEqual(self.run_exe('newer', a, b), want, (a, b))

    def test_tag(self):
        self.assertEqual(self.run_exe('tag', self.release(json.dumps({'id': 1, 'tag_name': 'v0.4.0'}, indent=2))),
                         'v0.4.0')
        self.assertEqual(self.run_exe('tag', self.release('{"tag_name" :\n "v1.2.3", "name": "x"}')), 'v1.2.3')
        self.assertEqual(self.run_exe('tag', self.release('{"message": "Not Found"}')), 'no')
        self.assertEqual(self.run_exe('tag', self.release('{"tag_name": ""}')), 'no')

    @unittest.skipUnless(shutil.which('curl'), 'no curl')
    def test_whole_check(self):
        url = 'file://' + self.release(json.dumps({'tag_name': 'v0.4.0'}))
        self.assertEqual(self.run_exe('check', '0.3.0', env={'HM_UPDATE_URL': url}), '0.4.0')
        self.assertEqual(self.run_exe('check', '0.4.0', env={'HM_UPDATE_URL': url}), 'none')
        self.assertEqual(self.run_exe('check', 'dev', env={'HM_UPDATE_URL': url}), 'none')
        self.assertEqual(self.run_exe('check', '0.3.0', env={'HM_UPDATE_URL': 'file:///nonexistent/x.json'}), 'none')

    def fake(self, d, name, extra=''):
        """A stand-in program that writes its arguments (and LD_LIBRARY_PATH, HM_GAME_DIR) to <d>/<name>.out."""
        p = os.path.join(d, name)
        with open(p, 'w') as f:
            f.write('#!/bin/sh\n{ printf "%s\\n" "$@"; echo "LD=${LD_LIBRARY_PATH-unset}"; '
                    f'echo "GD=${{HM_GAME_DIR-unset}}"; }} > "{p}.out.tmp" && {MV} "{p}.out.tmp" "{p}.out"\n' + extra)
        os.chmod(p, 0o755)
        return p + '.out'

    def run_installer(self, d, env):
        base = {k: v for k, v in os.environ.items() if k not in ('TERMINAL', 'LD_LIBRARY_PATH', 'HM_GAME_DIR')}
        return self.run_exe('run', env={**base, 'PATH': d, 'HM_UPDATE_INSTALLER': 'echo hi', **env})

    def wait(self, path):
        for _ in range(50):
            if os.path.exists(path):
                with open(path) as f:
                    return f.read().splitlines()
            time.sleep(0.1)
        self.fail(path + ' never written')

    def test_installer_terminals(self):
        # (the default-terminal launcher first; $TERMINAL next; then a known one; the browser; nothing)
        for files, env, want, args in [
                (['xdg-terminal-exec', 'gnome-terminal'], {'TERMINAL': 'kitty'}, 'xdg-terminal-exec', ['sh', '-c']),
                (['myterm', 'xterm'], {'TERMINAL': 'myterm'}, 'myterm', ['-e', 'sh', '-c']),
                (['gnome-terminal', 'xterm'], {}, 'gnome-terminal', ['--', 'sh', '-c']),
                (['wezterm'], {}, 'wezterm', ['start', '--', 'sh', '-c'])]:
            d = tempfile.mkdtemp(dir=self.t)
            outs = {n: self.fake(d, n) for n in files}
            self.assertEqual(self.run_installer(d, env), 'terminal', want)
            self.assertEqual(self.wait(outs[want])[:len(args) + 1], args + ['echo hi'], want)
        d = tempfile.mkdtemp(dir=self.t)
        out = self.fake(d, 'xdg-open')
        self.assertEqual(self.run_installer(d, {}), 'browser')
        self.assertEqual(self.wait(out)[0], 'https://github.com/Dewey-Wilkerson/Hylian-Melodies/releases/latest')
        self.assertEqual(self.run_installer(tempfile.mkdtemp(dir=self.t), {}), 'nothing')

    def test_installer_leaves_the_appimage_behind(self):
        d = tempfile.mkdtemp(dir=self.t)
        out = self.fake(d, 'xterm')
        mount = '/tmp/.mount_HyliaX'
        self.assertEqual(self.run_installer(d, {'HM_GAME_DIR': mount + '/opt/hylian-melodies',
                                                'LD_LIBRARY_PATH': mount + '/usr/lib/libz.so.1:/opt/keep'}), 'terminal')
        got = self.wait(out)
        self.assertIn('LD=/opt/keep', got)
        self.assertIn('GD=unset', got)
        out = self.fake(d, 'xterm')  # (a package install: nothing removed)
        os.remove(out) if os.path.exists(out) else None
        self.assertEqual(self.run_installer(d, {'HM_GAME_DIR': '/opt/hylian-melodies', 'LD_LIBRARY_PATH': '/x'}),
                         'terminal')
        got = self.wait(out)
        self.assertIn('LD=/x', got)
        self.assertIn('GD=/opt/hylian-melodies', got)

    def test_gaming_mode_switch(self):
        d = tempfile.mkdtemp(dir=self.t)
        cfg = os.path.join(self.t, 'config dir')  # (a space: the quoting)
        switch = self.fake(d, 'steamos-session-select')
        game = os.path.join(self.t, 'my "game" $x.AppImage')  # (what the desktop starts again: the AppImage file)
        with open(game, 'w') as f:
            f.write(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{self.t}/game.out"\n')
        os.chmod(game, 0o755)
        base = {k: v for k, v in os.environ.items() if k not in ('XDG_CURRENT_DESKTOP', 'GAMESCOPE_WAYLAND_DISPLAY')}
        out = self.run_exe('desktop', env={**base, 'PATH': d, 'XDG_CURRENT_DESKTOP': 'gamescope',
                                           'XDG_CONFIG_HOME': cfg, 'APPIMAGE': game}).split()
        self.assertEqual(out, ['gaming', 'written'])
        self.assertEqual(self.wait(switch)[0], 'plasma')
        entry = os.path.join(cfg, 'autostart', 'hylian-melodies-update.desktop')
        with open(entry) as f:
            text = f.read()
        self.assertIn('NoDisplay=true', text)
        # the Exec line as a desktop runs it: the file's string escapes, then the spec's quoting
        exec_line = next(l for l in text.splitlines() if l.startswith('Exec='))[5:].replace('\\\\', '\\')
        subprocess.run(desktop_exec_args(exec_line), check=True, env={**base, 'PATH': '/usr/bin:/bin'})
        self.assertFalse(os.path.exists(entry), 'the entry removes itself')
        with open(os.path.join(self.t, 'game.out')) as f:
            self.assertEqual(f.read().split(), ['--run-installer'])
        self.assertEqual(self.run_exe('desktop', env={**base, 'PATH': d, 'XDG_CONFIG_HOME': cfg,
                                                      'APPIMAGE': game}).split()[0], 'desktop')


if __name__ == '__main__':
    unittest.main()
