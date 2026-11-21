"""installer/screens.py and installer/picker.py: the edit field, the folder list and the dialog order without a
terminal; then the real curses screens driven through a pseudo-terminal against the fake flow."""
import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from installer import picker  # noqa: E402
from installer.screens import Browser, TextField  # noqa: E402


class Models(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-scr-')
        self.addCleanup(shutil.rmtree, self.t)
        for d in ('Games', 'Gadgets', '.hidden', 'Cart.xci'):  # (a folder named like a dump, as some tools make)
            os.makedirs(os.path.join(self.t, d))
        for f in ('notes.txt', 'b.XCI', 'a.xci', '.dot.xci'):
            open(os.path.join(self.t, f), 'w').close()

    def test_field(self):
        f = TextField('ab')
        for k in ('left', 'X', 'home', 'Y', 'end', 'backspace', 'delete', '\x07'):
            f.key(k)
        self.assertEqual((f.text, f.pos), ('YaX', 3))
        f.key('clear')
        self.assertEqual((f.text, f.pos), ('', 0))

    def test_completion(self):
        f = TextField(os.path.join(self.t, 'G'))
        self.assertEqual(f.complete(), ['Gadgets', 'Games'])
        self.assertEqual(f.text, os.path.join(self.t, 'Ga'))
        f.key('m')
        f.complete()
        self.assertEqual(f.text, os.path.join(self.t, 'Games', ''))  # (one folder: completed with its slash)
        f = TextField('"' + os.path.join(self.t, 'no'))
        f.complete()
        self.assertEqual(f.text, '"' + os.path.join(self.t, 'notes.txt'))  # (a dropped path's quote kept)
        self.assertEqual(TextField('/nonexistent/x').complete(), [])

    def test_reflow(self):
        from installer.screens import reflow
        self.assertEqual(reflow('One\ntwo.\n\nThree:\n  a command\n  - item\nend'),
                         ['One two.', '', 'Three:', '  a command', '  - item', 'end'])

    def test_browser(self):
        b = Browser(self.t, picker.KINDS['base'][1])
        names = [n for n, _ in b.entries]
        self.assertEqual(names, ['..', 'Cart.xci', 'Gadgets', 'Games', 'a.xci', 'b.XCI', 'notes.txt'])
        self.assertEqual(b.entries[b.sel][0], 'a.xci')  # (starts on the first dump)
        self.assertEqual(b.enter(), os.path.join(self.t, 'a.xci'))
        b.sel = 1
        self.assertIsNone(b.enter())  # (a folder opens, even one named .xci)
        self.assertEqual(b.cwd, os.path.join(self.t, 'Cart.xci'))
        b.up()
        self.assertEqual((b.cwd, b.entries[b.sel][0]), (self.t, 'Cart.xci'))
        b.toggle_hidden()
        self.assertIn('.dot.xci', [n for n, _ in b.entries])
        self.assertEqual(b.entries[b.sel][0], 'Cart.xci')
        b.move(-100)
        self.assertEqual(b.sel, 0)
        self.assertEqual(Browser('/nonexistent', ['*']).cwd, os.path.expanduser('~'))
        f = Browser(self.t, [], folders=True)  # (choosing a folder)
        self.assertEqual([n for n, _ in f.entries], ['.', '..', 'Cart.xci', 'Gadgets', 'Games'])
        self.assertEqual(f.sel, 0)
        f.sel = 3
        self.assertIsNone(f.enter())
        self.assertEqual(f.enter(), os.path.join(self.t, 'Gadgets'))  # (its first line: this folder)


class Picker(unittest.TestCase):
    def test_order(self):
        self.assertFalse(picker.graphical({}))
        self.assertFalse(picker.graphical({'DISPLAY': ':0', 'SSH_CONNECTION': 'x'}))
        self.assertTrue(picker.graphical({'WAYLAND_DISPLAY': 'w'}))
        calls = []

        def way(result):
            def f(*a):
                calls.append(result)
                return result
            return f
        env = {'DISPLAY': ':0'}
        self.assertEqual(picker.desktop_pick('t', 'base', '', env, [way(None), way('/x.xci'), way('/y')]), '/x.xci')
        self.assertEqual(calls, [None, '/x.xci'])
        self.assertEqual(picker.desktop_pick('t', 'base', '', env, [way('')]), '')  # (cancelled: no terminal list)
        self.assertIsNone(picker.desktop_pick('t', 'base', '', env, [way(None)]))
        self.assertIsNone(picker.desktop_pick('t', 'base', '', {}, [way('/never')]))

    def test_dialogs(self):
        seen = []

        def run(code, out=''):
            def r(cmd, **k):
                seen.append(cmd)
                return subprocess.CompletedProcess(cmd, code, out)
            return r
        if shutil.which('zenity'):
            self.assertEqual(picker.zenity('Pick', 'keys', '/tmp', run(0, '/k/prod.keys\n')), '/k/prod.keys')
            self.assertIn('--file-filter=Console keys | *.keys', seen[-1])
            self.assertEqual(picker.zenity('Pick', 'keys', '', run(1)), '')
            self.assertIsNone(picker.zenity('Pick', 'keys', '', run(5)))
        if shutil.which('kdialog'):
            self.assertEqual(picker.kdialog('Pick', 'base', '/tmp', run(0, '/a.xci\n')), '/a.xci')
            self.assertEqual(seen[-1][-2:], ['/tmp', '*.xci *.XCI|Cartridge dump'])
        self.assertEqual(picker._from_uri('file:///home/p/My%20Game.xci'), '/home/p/My Game.xci')
        self.assertIsNone(picker._from_uri('https://x/y'))


DRIVER = r'''
import os, sys
sys.path[:0] = [sys.argv[1], os.path.join(sys.argv[1], 'tests')]
from installer import tui
from test_tui import FakeFlow
FakeFlow.calls, FakeFlow.packed_settings = [], None
sys.exit(tui.main(['--source-note', 'a test'], make_flow=FakeFlow, env={'HOME': sys.argv[2]}, gpus=lambda: [],
                  run=lambda argv: print('(would run: ' + ' '.join(argv) + ')') or 0, immutable=None))
'''


class Screens(unittest.TestCase):
    """The curses screens in a pseudo-terminal of 100x30: keys in, the terminal's output and the exit status out."""

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-pty-')
        self.addCleanup(shutil.rmtree, self.t)
        self.xci, self.keys = os.path.join(self.t, 'my game.xci'), os.path.join(self.t, 'prod.keys')
        for p in (self.xci, self.keys):
            with open(p, 'w') as f:
                f.write('x')

    def drive(self, keys):
        pid, fd = pty.fork()
        if pid == 0:
            env = {'PATH': os.environ['PATH'], 'TERM': 'xterm-256color', 'HOME': self.t, 'LANG': 'C.UTF-8'}
            os.execve(sys.executable, [sys.executable, '-c', DRIVER, ROOT, self.t], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
        out = b''

        def read(seconds):
            nonlocal out
            end = time.time() + seconds
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        return False
                    if not chunk:
                        return False
                    out += chunk
            return True
        read(1.0)
        for k in keys:
            os.write(fd, k.encode())
            if not read(0.25):
                break
        read(1.5)
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        return os.waitstatus_to_exitcode(status), out.decode(errors='replace')

    def test_straight_through(self):
        enter, ctrl_o = '\r', '\x0f'
        keys = [enter,  # welcome: go on
                enter,  # what to build: the package
                self.t + '/', ctrl_o, enter,  # the dump: the folder typed, then the in-terminal list, on its first dump
                '\x15' + self.keys, enter,  # the keys typed
                enter, enter, enter,  # CPU level, keep the build files, build in the cache folder
                enter, enter, enter,  # window, no update check, no troubleshooting
                enter,  # start
                enter,  # install it now: the (stand-in) package manager runs outside the screens
                enter,  # back to the installer
                enter]  # delete the package file
        rc, out = self.drive(keys)
        self.assertEqual(rc, 0, out[-2000:])
        self.assertIn('Source: a test', out)
        self.assertIn('(would run: sudo apt install ', out)
        self.assertIn('Press Enter to go back to the installer.', out)
        tail = out[out.rfind('Done. The package'):]
        self.assertIn('Installed. Start it from the menu', tail)

    def test_quit(self):
        rc, out = self.drive(['\x1b', 'j', '\r'])  # Esc, down to "Yes, quit", Enter
        self.assertEqual(rc, 1, out[-2000:])
        self.assertIn('Stopped. Nothing was installed.', out)


if __name__ == '__main__':
    unittest.main()
