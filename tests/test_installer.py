"""Installer units (no game files needed), plus an extraction round trip when HM_TEST_XCI and HM_TEST_KEYS are set.

  python3 -m unittest discover -s tests
  HM_TEST_XCI=cadence-base.xci HM_TEST_KEYS=prod.keys HM_TEST_HACTOOL=... python3 -m unittest tests.test_installer
"""

import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from installer import events, hactool, nx, state  # noqa: E402


class Units(unittest.TestCase):
    def test_filter_drops_key_lines_and_masks_hex(self):
        out = hactool.filter_output('Title ID: 0100\nKey Area Key 0: ' + 'ab' * 16 + '\nSection CTR: ' + 'cd' * 16)
        self.assertNotIn('Key Area', out)
        self.assertNotIn('cd' * 16, out)
        self.assertIn('Title ID', out)

    def test_parse_cnmt(self):
        hdr = struct.pack('<QIBBHHH', 0x01000B900D8B0800, 393216, 0x81, 0, 0x10, 1, 0).ljust(0x20, b'\0')
        rec = bytes(range(32)) + bytes(range(16)) + (1234).to_bytes(6, 'little') + bytes([1, 0])
        m = nx.parse_cnmt(hdr + bytes(0x10) + rec)
        self.assertEqual(m['type'], 'Patch')
        self.assertEqual(m['contents'][0]['type'], 'Program')
        self.assertEqual(m['contents'][0]['size'], 1234)
        self.assertEqual(m['contents'][0]['id'], bytes(range(16)).hex())

    def test_ticket(self):
        body = 0x140
        t = bytearray(0x2C0)
        struct.pack_into('<I', t, 0, 0x10004)
        t[body + 0x40: body + 0x50] = b'K' * 16
        t[body + 0x160: body + 0x170] = bytes(range(16))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(t)
        self.addCleanup(os.unlink, f.name)
        rid, key = nx.ticket_title_key(f.name)
        self.assertEqual(rid, bytes(range(16)).hex())
        self.assertEqual(key, b'K' * 16)

    def test_keys_summary_counts_without_values(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write('header_key = ' + '00' * 32 + '\nmaster_key_0a = ' + '11' * 16 + '\n# comment\n')
        self.addCleanup(os.unlink, f.name)
        n, names = nx.keys_summary(f.name)
        self.assertEqual(n, 2)
        self.assertEqual(names, {'header_key', 'master_key_0a'})

    def test_events_are_json_lines(self):
        buf = io.StringIO()
        e = events.Events(stream=buf)
        e.start(['check'])
        e.step('check')
        for p in (0, 3, 3, 50, 100):
            e.progress('check', p)
        e.end('ok')
        evs = [json.loads(line) for line in buf.getvalue().splitlines()]
        self.assertEqual([v['event'] for v in evs], ['start', 'step', 'progress', 'progress', 'progress',
                                                     'progress', 'end'])

    def test_state_roundtrip(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        s = state.State(d)
        s.mark('check', x=1)
        self.assertTrue(state.State(d).done('check'))
        self.assertFalse(state.State(d).done('extract'))

    def test_cli_missing_input_fails_with_error_event(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        fake = os.path.join(d, 'hactool')
        open(fake, 'w').close()
        r = subprocess.run([sys.executable, '-m', 'installer', '--base', os.path.join(d, 'nope.xci'), '--keys',
                            os.path.join(d, 'nope.keys'), '--dest', os.path.join(d, 'dest'), '--hactool', fake],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        evs = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual(evs[-1], {'event': 'end', 'result': 'error', 'log': evs[-1]['log']})
        self.assertTrue(any(v['event'] == 'error' and v['msg'] == 'missing_input' for v in evs))


class SourceHash(unittest.TestCase):
    """A step done before is redone when the project's sources it depends on changed (makepkg -f after a commit)."""

    def test_changes_with_sources(self):
        from installer import steps
        root = tempfile.mkdtemp(prefix='hm-src-')
        self.addCleanup(shutil.rmtree, root)
        for f in ('recomp/gen.py', 'runtime/ui/menu.cpp', 'tools/build_game.py', 'VERSION'):
            os.makedirs(os.path.dirname(os.path.join(root, f)) or root, exist_ok=True)
            with open(os.path.join(root, f), 'w') as fh:
                fh.write('1')
        c = type('C', (), {})()
        c.a = type('A', (), {'root': root})()
        self.assertIsNone(steps.source_hash(c, 'extract'))
        lift, comp = steps.source_hash(c, 'lift'), steps.source_hash(c, 'compile')
        self.assertEqual(comp, steps.source_hash(c, 'compile'))
        with open(os.path.join(root, 'runtime', 'ui', 'menu.cpp'), 'w') as fh:
            fh.write('2')
        self.assertNotEqual(comp, steps.source_hash(c, 'compile'))
        self.assertEqual(lift, steps.source_hash(c, 'lift'))
        v2 = steps.source_hash(c, 'compile')
        c.a.march = 'v2'
        self.assertEqual(v2, steps.source_hash(c, 'compile'))  # (v2 is the default)
        c.a.march = 'v3'
        self.assertNotEqual(v2, steps.source_hash(c, 'compile'))
        self.assertEqual(lift, steps.source_hash(c, 'lift'))


@unittest.skipUnless(os.environ.get('HM_TEST_XCI') and os.environ.get('HM_TEST_KEYS'), 'needs the game files')
class Extraction(unittest.TestCase):
    def test_extract_twice_resumes_and_repo_stays_clean(self):
        d = tempfile.mkdtemp(dir=os.path.expanduser('~/.cache/hylian-melodies'))
        self.addCleanup(shutil.rmtree, d)
        cmd = [sys.executable, '-m', 'installer', '--base', os.environ['HM_TEST_XCI'], '--keys',
               os.environ['HM_TEST_KEYS'], '--dest', os.path.join(d, 'dest'), '--temp', os.path.join(d, 'temp'),
               '--until', 'extract']
        if os.environ.get('HM_TEST_HACTOOL'):
            cmd += ['--hactool', os.environ['HM_TEST_HACTOOL']]
        for i in range(2):
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:])
            evs = [json.loads(line) for line in r.stdout.splitlines()]
            self.assertEqual(evs[-1]['result'], 'ok')
            if i == 1:
                self.assertTrue(any(v.get('msg') == 'resume' for v in evs))
        st = subprocess.run(['git', '-C', ROOT, 'status', '--porcelain', '--ignored'], capture_output=True,
                            text=True).stdout
        self.assertNotIn('romfs', st)
        self.assertNotIn('exefs', st)


if __name__ == '__main__':
    unittest.main()
