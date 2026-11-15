"""installer/plan.py, flow.py, tui.py: the plan and its checks, the manifest, the questions and --answers, with a
scripted console and a fake flow (no terminal, no build)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from installer import flow as F, plan as P, tui  # noqa: E402
from test_deps import OS, Fake  # noqa: E402
from installer import deps  # noqa: E402


class Script:
    """A console whose answers are a list; what was said is kept."""

    def __init__(self, *answers):
        self.answers, self.said, self.asked = list(answers), [], []

    def say(self, text=''):
        self.said.append(text)

    def ask(self, question, default=''):
        self.asked.append(question)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0) or default

    def text(self):
        return '\n'.join(self.said)


class FakeFlow:
    """Stands in for flow.Flow: no build. Class attributes steer it."""
    missing_rounds = 0     # how many times check_system reports missing packages first
    bad_inputs_rounds = 0  # how many times the files are refused first
    fail_setup = False
    calls = []

    def __init__(self, plan, repo, emit, osr=None, probe=None):
        self.plan, self.repo, self.emit, self.format, self.family = plan, repo, emit, 'deb', 'debian'
        self.log_path = '/log'

    def check_system(self):
        type(self).calls.append('check_system')
        if type(self).missing_rounds:
            type(self).missing_rounds -= 1
            return {'result': 'deps', 'command': 'sudo apt install ninja-build', 'notes': ['a note'],
                    'needs': [{'what': 'ninja'}]}
        self.deps = {'sdl3': 'system', 'shaderc': 'system'}
        return None

    def build_tools(self):
        type(self).calls.append('build_tools')

    def check_inputs(self):
        type(self).calls.append('check_inputs')
        if type(self).bad_inputs_rounds:
            type(self).bad_inputs_rounds -= 1
            raise F.FlowError('Cannot read the dump with these keys')

    def setup(self, until=None):
        type(self).calls.append('setup')
        self.emit({'event': 'step', 'step': 'compile', 'msg': 'Compiling the game'})
        self.emit({'event': 'progress', 'step': 'compile', 'pct': 57})
        if type(self).fail_setup:
            raise F.FlowError('Compiling the game failed', '/setup.log')

    def make_package(self):
        type(self).calls.append('make_package')
        return os.path.join(self.plan.out, 'x.deb')

    def record(self, target):
        type(self).calls.append('record')
        return {'result': 'ok', 'file': target, 'install': 'sudo apt install ' + target, 'remove': 'sudo apt remove x'}

    error = F.Flow.error

    def log(self, text):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-tui-')
        self.addCleanup(shutil.rmtree, self.t)
        self.env = {'HOME': self.t}
        self.xci, self.keys = os.path.join(self.t, 'my game.xci'), os.path.join(self.t, 'prod.keys')
        for p in (self.xci, self.keys):
            with open(p, 'w') as f:
                f.write('x')
        FakeFlow.missing_rounds = FakeFlow.bad_inputs_rounds = 0
        FakeFlow.fail_setup = False
        FakeFlow.calls = []


class PlanTests(Base):
    def test_defaults_follow_xdg(self):
        p = P.Plan(self.env)
        self.assertEqual(p.work, os.path.join(self.t, '.cache/hylian-melodies/temp'))
        self.assertEqual(p.manifest, os.path.join(self.t, '.local/share/hylian-melodies/installs.json'))
        p = P.Plan({'HOME': self.t, 'XDG_CACHE_HOME': '/c', 'XDG_DATA_HOME': 'relative'})
        self.assertEqual(p.out, '/c/hylian-melodies/packages')
        self.assertEqual(p.manifest, os.path.join(self.t, '.local/share/hylian-melodies/installs.json'))
        self.assertEqual((p.output, p.march, p.keep_cache), ('package', 'v2', False))
        with self.assertRaises(ValueError):
            P.Plan(self.env, colour='red')

    def test_clean_path(self):
        self.assertEqual(P.clean_path(f"  '{self.xci}' "), self.xci)
        self.assertEqual(P.clean_path('file://' + self.xci.replace(' ', '%20')), self.xci)
        self.assertEqual(P.clean_path('~/a'), os.path.join(os.path.expanduser('~'), 'a'))
        self.assertEqual(P.clean_path('  '), '')

    def test_validate(self):
        ok = lambda path: 100.0
        p = P.Plan(self.env, base=self.xci, keys=self.keys)
        self.assertEqual(P.validate(p, has_v3=False, free_gib=ok), [])
        fields = lambda plan, **kw: [f for f, _ in P.validate(plan, free_gib=ok, **kw)]
        self.assertEqual(fields(P.Plan(self.env)), ['base', 'keys'])
        self.assertEqual(fields(P.Plan(self.env, base=self.t, keys=self.keys + '.no')), ['base', 'keys'])
        self.assertEqual(fields(P.Plan(self.env, base=self.xci, keys=self.keys, march='v3'), has_v3=False), ['march'])
        self.assertEqual(fields(P.Plan(self.env, base=self.xci, keys=self.keys, march='v3'), has_v3=True), [])
        self.assertEqual(fields(P.Plan(self.env, base=self.xci, keys=self.keys, march='v9')), ['march'])
        for out in ('appimage', 'folder', 'flatpak', 'tarball'):  # (named already, not built yet / unknown)
            self.assertEqual(fields(P.Plan(self.env, base=self.xci, keys=self.keys, output=out)), ['output'])
        self.assertIn('SteamOS', P.validate(P.Plan(self.env, base=self.xci, keys=self.keys, output='appimage'),
                                            free_gib=ok)[0][1])
        self.assertEqual(fields(P.Plan(self.env, base=self.xci, keys=self.keys, keep_cache='yes')), ['keep_cache'])
        spaced = P.Plan(self.env, base=self.xci, keys=self.keys, work='/tmp/a b/w')
        self.assertEqual(fields(spaced, fmt='rpm'), ['work'])
        self.assertEqual(fields(spaced, fmt='deb'), [])
        self.assertEqual([f for f, _ in P.validate(p, free_gib=lambda path: 1.0)], ['work', 'out'])

    def test_manifest(self):
        path = os.path.join(self.t, 'd', 'installs.json')
        self.assertEqual(P.load_manifest(path)['installs'], [])
        P.record_install(path, {'id': 'package:x', 'version': '1'})
        P.record_install(path, {'id': 'package:x', 'version': '2'})  # (same id: replaced)
        P.record_install(path, {'id': 'folder:/g', 'version': '2'})
        self.assertEqual([e['version'] for e in P.load_manifest(path)['installs']], ['2', '2'])
        P.forget_install(path, 'package:x')
        self.assertEqual([e['id'] for e in P.load_manifest(path)['installs']], ['folder:/g'])
        with open(path, 'w') as f:
            f.write('not json')
        self.assertEqual(P.load_manifest(path)['installs'], [])
        import hashlib
        self.assertEqual(P.sha256_file(self.xci), hashlib.sha256(b'x').hexdigest())


class FlowTests(Base):
    def flow(self, osname, *missing):
        self.events = []
        plan = P.Plan(self.env, base=self.xci, keys=self.keys)
        return F.Flow(plan, ROOT, self.events.append, deps.parse_os_release(OS[osname]), Fake(*missing))

    def test_missing_packages_stop_it(self):
        f = self.flow('ubuntu2404', 'ninja', 'sdl3')
        r = F.run(f.plan, ROOT, f.emit, flow=f)
        self.assertEqual(r['result'], 'deps')
        self.assertEqual(r['command'], 'sudo apt install ninja-build')
        self.assertEqual([n['key'] for n in r['needs']], ['ninja'])
        self.assertFalse(os.path.exists(f.plan.work))  # (nothing was built or written)

    def test_formats_and_own_libraries(self):
        f = self.flow('debian12', 'sdl3')
        self.assertIsNone(f.check_system())
        self.assertEqual((f.format, f.deps['sdl3'], f.deps['shaderc']), ('deb', 'own', 'own'))
        self.assertEqual(self.flow('tumbleweed').format, 'rpm')
        self.assertEqual(self.flow('cachyos').format, 'arch')
        f = self.flow('void')
        with self.assertRaises(F.FlowError):
            f.check_system()

    def test_record_and_error(self):
        f = self.flow('debian13')
        f.check_system()
        r = f.record('/pkgs/hylian-melodies-recomp_0.1.0_amd64.deb')
        self.assertEqual(r['install'], 'sudo apt install /pkgs/hylian-melodies-recomp_0.1.0_amd64.deb')
        e = P.load_manifest(f.plan.manifest)['installs'][0]
        self.assertEqual((e['output'], e['package']['format'], e['inputs']['base']['path']), ('package', 'deb', self.xci))
        self.assertEqual(len(e['inputs']['base']['sha256']), 64)
        self.assertNotIn('sha256', e['inputs']['keys'])  # (the keys: their path only)
        self.assertNotIn('x', json.dumps(e['inputs']['keys']).replace(self.keys, ''))
        r = f.error(F.FlowError('it broke', '/the.log'))
        self.assertEqual(r, {'result': 'error', 'text': 'it broke', 'log': '/the.log'})


class TuiTests(Base):
    def run_tui(self, *answers, argv=()):
        io = Script(*answers)
        rc = tui.main(list(argv), io=io, make_flow=FakeFlow, env=self.env)
        return rc, io

    def test_straight_through(self):
        rc, io = self.run_tui(f'"{self.xci}"', self.keys, '', '', '')
        self.assertEqual(rc, 0, io.text())
        self.assertEqual(FakeFlow.calls, ['check_system', 'build_tools', 'check_inputs', 'setup', 'make_package', 'record'])
        t = io.text()
        for want in ('never share it', 'Ready to build:', self.xci, '==> Compiling the game', '    50%',
                     'Install it with:', 'sudo apt install '):
            self.assertIn(want, t)

    def test_missing_packages_then_check_again(self):
        FakeFlow.missing_rounds = 1
        rc, io = self.run_tui('', self.xci, self.keys, '', '', '')
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  sudo apt install ninja-build', io.said)
        self.assertEqual(FakeFlow.calls[:2], ['check_system', 'check_system'])
        FakeFlow.missing_rounds, FakeFlow.calls = 1, []
        rc, io = self.run_tui('q')
        self.assertEqual((rc, FakeFlow.calls), (3, ['check_system']))

    def test_wrong_files_are_asked_again(self):
        FakeFlow.bad_inputs_rounds = 1
        rc, io = self.run_tui('/no/such.xci', self.xci, self.keys, '', self.xci, self.keys, '', '', '')
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  The cartridge dump is not a file: /no/such.xci', io.said)
        self.assertIn('  Cannot read the dump with these keys', io.said)

    def test_options_and_decline(self):
        rc, io = self.run_tui(self.xci, self.keys, 'native', '2', 'no')
        self.assertEqual(rc, 0)
        self.assertNotIn('setup', FakeFlow.calls)
        self.assertIn('  CPU level        native', io.said)
        self.assertTrue([s for s in io.said if s.startswith('  work folder') and 'kept afterwards' in s])

    def test_failure_and_input_ending(self):
        FakeFlow.fail_setup = True
        rc, io = self.run_tui(self.xci, self.keys, '', '', '')
        self.assertEqual(rc, 1)
        self.assertIn('It did not work: Compiling the game failed', io.said)
        self.assertIn('The full log: /setup.log', io.said)
        rc, io = self.run_tui(self.xci)  # (the terminal went away mid-question)
        self.assertEqual(rc, 1)
        self.assertIn('Stopped. Nothing was installed.', io.said)

    def test_existing_install(self):
        man = P.Plan(self.env).manifest
        P.record_install(man, {'id': 'package:x', 'version': '0.1.0', 'built': 'then',
                               'inputs': {'base': {'path': self.xci}, 'keys': {'path': self.keys}},
                               'build': {'march': 'native', 'keep_cache': True},
                               'package': {'file': '/p/x.deb', 'remove': 'sudo apt remove x'}})
        rc, io = self.run_tui('', '', '', '', '', '')  # again, and every default: the files and options of last time
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  CPU level        native', io.said)
        self.assertIn(f'  cartridge dump   {self.xci}', io.said)
        rc, io = self.run_tui('2', '')  # remove: the command, then forgotten
        self.assertEqual(rc, 0)
        self.assertIn('  sudo apt remove x', io.said)
        self.assertEqual(P.load_manifest(man)['installs'], [])

    def answers(self, **kw):
        path = os.path.join(self.t, 'answers.json')
        with open(path, 'w') as f:
            json.dump(kw, f)
        return ['--answers', path]

    def test_answers(self):
        rc, io = self.run_tui(argv=self.answers(base=self.xci, keys=self.keys, march='v2', keep_cache=True))
        self.assertEqual((rc, io.asked), (0, []), io.text())
        self.assertEqual(FakeFlow.calls, ['check_system', 'build_tools', 'check_inputs', 'setup', 'make_package', 'record'])
        FakeFlow.missing_rounds = 1
        rc, io = self.run_tui(argv=self.answers(base=self.xci, keys=self.keys))
        self.assertEqual(rc, 3)
        self.assertIn('  sudo apt install ninja-build', io.said)
        for bad in (dict(base=self.xci), dict(base=self.xci, keys=self.keys, output='appimage'),
                    dict(base=self.xci, keys=self.keys, nonsense=1)):
            rc, io = self.run_tui(argv=self.answers(**bad))
            self.assertEqual(rc, 2, io.text())
        rc, io = self.run_tui(argv=['--answers', '/no/such/file'])
        self.assertEqual(rc, 2)


if __name__ == '__main__':
    unittest.main()
