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
from installer import flow as F, options as O, plan as P, tui  # noqa: E402
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
        type(self).packed_settings = dict(self.plan.settings)  # (what pack.pack would put in the default ini)
        os.makedirs(self.plan.out, exist_ok=True)
        target = os.path.join(self.plan.out, 'x.deb')
        with open(target, 'wb') as f:
            f.write(b'p' * 3000)
        return target

    def record(self, target):
        type(self).calls.append('record')
        F.Flow.save_settings(self)
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
        FakeFlow.calls, FakeFlow.packed_settings = [], None


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

    def test_leftovers(self):
        plan = P.Plan(self.env)
        repo = os.path.join(P.cache_home(self.env), 'src', 'v1.0.0')
        for d in (repo, plan.toolchain, plan.work, os.path.dirname(plan.manifest)):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(plan.work, 'setup.log'), 'w') as f:
            f.write('x' * 100)
        os.symlink('/usr', os.path.join(os.path.dirname(plan.manifest), 'romfs'))  # (a link into the install: not counted)
        got = {path: (size, removable) for path, size, _, removable in P.leftovers(plan, repo, '/no/package')}
        self.assertEqual(set(got), {plan.work, plan.toolchain, os.path.join(P.cache_home(self.env), 'src'),
                                    os.path.dirname(plan.manifest)})
        self.assertEqual(got[plan.work], (100, True))
        self.assertFalse(got[os.path.dirname(plan.manifest)][1])  # (the saves: keep)
        self.assertLess(got[os.path.dirname(plan.manifest)][0], 1000)
        self.assertNotIn(os.path.join(P.cache_home(self.env), 'src'),
                         [p for p, *_ in P.leftovers(plan, ROOT)])  # (run from a checkout: no download to list)
        self.assertEqual(P.size_text(3 << 30), '3.0 GiB')

    def test_record_and_error(self):
        f = self.flow('debian13')
        f.check_system()
        f.plan.settings = {'fullscreen': True}
        os.makedirs(os.path.dirname(f.plan.settings_file))
        with open(f.plan.settings_file, 'w') as fh:  # (a player who has started the game before)
            fh.write('volume = 0.5\n')
        r = f.record('/pkgs/hylian-melodies-recomp_0.1.0_amd64.deb')
        self.assertEqual(r['install'], 'sudo apt install /pkgs/hylian-melodies-recomp_0.1.0_amd64.deb')
        e = P.load_manifest(f.plan.manifest)['installs'][0]
        self.assertEqual((e['output'], e['package']['format'], e['inputs']['base']['path']), ('package', 'deb', self.xci))
        self.assertEqual(len(e['inputs']['base']['sha256']), 64)
        self.assertNotIn('sha256', e['inputs']['keys'])  # (the keys: their path only)
        self.assertNotIn('x', json.dumps(e['inputs']['keys']).replace(self.keys, ''))
        self.assertEqual(O.read_settings(f.plan.settings_file), {'fullscreen': True})
        os.remove(f.plan.settings_file)
        f.record('/pkgs/x.deb')
        self.assertFalse(os.path.exists(f.plan.settings_file))  # (none yet: left to the package's default)
        r = f.error(F.FlowError('it broke', '/the.log'))
        self.assertEqual(r, {'result': 'error', 'text': 'it broke', 'log': '/the.log'})


class TuiTests(Base):
    def run_tui(self, *answers, argv=(), gpus=(), install_rc=0):
        io = Script(*answers)
        self.ran = []

        def run(argv):
            self.ran.append(argv)
            return install_rc
        rc = tui.main(list(argv), io=io, make_flow=FakeFlow, env=self.env, gpus=lambda: list(gpus), run=run)
        return rc, io

    def test_straight_through(self):
        os.makedirs(P.Plan(self.env).toolchain)  # (what a real build leaves: listed at the end)
        rc, io = self.run_tui(f'"{self.xci}"', self.keys, '', '', '', '', '', '', '', '')  # (install it now, delete it)
        self.assertEqual(rc, 0, io.text())
        self.assertEqual(self.ran, [['sudo', 'apt', 'install', os.path.join(self.t, '.cache', 'hylian-melodies',
                                                                             'packages', 'x.deb')]])
        self.assertIn('Installed. Start it from the menu or with "hylian-melodies".', io.said)
        self.assertFalse(os.path.exists(self.ran[0][-1]))  # (installed, then deleted as offered)
        t = io.text()
        self.assertIn('Files this left on your computer', t)
        self.assertNotIn('x.deb', t[t.index('Files this left'):])  # (gone: not listed)
        self.assertEqual(FakeFlow.calls, ['check_system', 'build_tools', 'check_inputs', 'setup', 'make_package', 'record'])
        self.assertIn('  game starts      in a window', io.said)
        self.assertNotIn('Which graphics card should draw the game?', io.said)  # (one card: not asked)
        t = io.text()
        for want in ('never share it', 'Ready to build:', self.xci, '==> Compiling the game', '    50%',
                     'Install it now?'):
            self.assertIn(want, t)

    def test_missing_packages_then_check_again(self):
        FakeFlow.missing_rounds = 1
        rc, io = self.run_tui('', self.xci, self.keys, '', '', '', '', '', '', 'no')
        self.assertEqual(rc, 0, io.text())
        self.assertEqual(self.ran, [])  # (not now: the command is shown)
        self.assertIn('Install it with:', io.said)
        t = io.text()
        left = t[t.index('Files this left on your computer'):]
        self.assertIn('the package file: not needed once it is installed', left)
        self.assertIn('rm -rf ', left)
        self.assertIn('  sudo apt install ninja-build', io.said)
        self.assertEqual(FakeFlow.calls[:2], ['check_system', 'check_system'])
        FakeFlow.missing_rounds, FakeFlow.calls = 1, []
        rc, io = self.run_tui('q')
        self.assertEqual((rc, FakeFlow.calls), (3, ['check_system']))

    def test_wrong_files_are_asked_again(self):
        FakeFlow.bad_inputs_rounds = 1
        rc, io = self.run_tui('/no/such.xci', self.xci, self.keys, '', self.xci, self.keys, '', '', '', '', '', '', 'no')
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  The cartridge dump is not a file: /no/such.xci', io.said)
        self.assertIn('  Cannot read the dump with these keys', io.said)

    def test_build_folder(self):
        big = os.path.join(self.t, 'big disk')
        os.makedirs(big)
        plan = P.Plan(self.env)
        free = {big: 500.0}
        io = Script('2', '/nowhere', '2', big)  # another folder: not one, then a real one
        tui.ask_build_folder(io, plan, self.env, free_gib=lambda p: next((v for k, v in free.items()
                                                                          if p.startswith(k)), 3.0))
        self.assertEqual((plan.work, plan.out), (os.path.join(big, 'hylian-melodies', 'temp'),
                                                 os.path.join(big, 'hylian-melodies', 'packages')))
        self.assertIn('  Not a folder: /nowhere', io.said)
        self.assertEqual(P.build_folder(plan, self.env), big)
        io = Script('1', '')  # the cache folder has too little room here: said, and asked again
        tui.ask_build_folder(io, plan, self.env, free_gib=lambda p: 500.0 if p.startswith(big) else 3.0)
        self.assertIn('Not enough free space', io.text())
        self.assertEqual(P.build_folder(plan, self.env), big)
        io = Script('')  # next time: the folder of last time is the default
        tui.ask_build_folder(io, plan, self.env, free_gib=lambda p: 500.0)
        self.assertEqual(P.build_folder(plan, self.env), big)
        io = Script('1')
        tui.ask_build_folder(io, plan, self.env, free_gib=lambda p: 500.0)
        self.assertEqual(plan.work, os.path.join(P.cache_home(self.env), 'temp'))

    def test_install_fails(self):
        rc, io = self.run_tui(self.xci, self.keys, '', '', '', '', '', '', 'yes', install_rc=1)
        self.assertEqual(rc, 0, io.text())
        self.assertEqual(len(self.ran), 1)
        t = io.text()
        self.assertIn('The package manager stopped (exit status 1)', t)
        self.assertIn('Install it with:', t)  # (then the command to run by hand)

    def test_answers_never_install(self):
        rc, io = self.run_tui(argv=self.answers(base=self.xci, keys=self.keys))
        self.assertEqual((rc, self.ran), (0, []), io.text())
        self.assertIn('Install it with:', io.said)

    def test_options_and_decline(self):
        rc, io = self.run_tui(self.xci, self.keys, 'native', '2', '', '', '', 'no')
        self.assertEqual(rc, 0)
        self.assertNotIn('setup', FakeFlow.calls)
        self.assertIn('  CPU level        native', io.said)
        self.assertTrue([s for s in io.said if s.startswith('  work folder') and 'kept afterwards' in s])

    def test_failure_and_input_ending(self):
        FakeFlow.fail_setup = True
        rc, io = self.run_tui(self.xci, self.keys, '', '', '', '', '', '')
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
        rc, io = self.run_tui('', '', '', '', '', '', '', '', '', 'no')  # again, and every default: the files and options of last time
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  CPU level        native', io.said)
        self.assertIn(f'  cartridge dump   {self.xci}', io.said)
        rc, io = self.run_tui('3', '')  # remove: the command, then forgotten
        self.assertEqual(rc, 0)
        self.assertIn('  sudo apt remove x', io.said)
        self.assertEqual(P.load_manifest(man)['installs'], [])

    def ini(self):
        return P.Plan(self.env).settings_file

    def test_settings_questions(self):
        cards = [(0, 'Fast Card'), (1, 'Built-in Graphics')]
        # fullscreen yes; the second card; troubleshooting one by one: pacing no, shaders yes, the rest no; start
        rc, io = self.run_tui(self.xci, self.keys, '', '', '', 'yes', '3', 'pick', '', 'yes', '', '', '', '', 'no',
                              gpus=cards)
        self.assertEqual(rc, 0, io.text())
        self.assertIn('  3. Built-in Graphics', io.said)
        self.assertIn('  game starts      fullscreen, graphics card 1, rebuild the shaders at every start', io.said)
        self.assertNotIn('audio', ' '.join(a for a in io.asked if 'timing' not in a).lower())  # (no "no audio" option)
        self.assertEqual({k: v for k, v in FakeFlow.packed_settings.items() if v != O.BY_KEY[k].default},
                         {'fullscreen': True, 'gpu': 1, 'shader_cache': False})
        self.assertFalse(os.path.exists(self.ini()))  # (a new player: the package's default carries them)

    def test_change_settings_without_rebuild(self):
        plan = P.Plan(self.env)
        P.record_install(plan.manifest, {'id': 'package:x', 'version': '0.1.0', 'built': 'then',
                                         'inputs': {'base': {'path': self.xci}, 'keys': {'path': self.keys}},
                                         'package': {'file': '/p/x.deb', 'remove': 'sudo apt remove x'}})
        os.makedirs(os.path.dirname(plan.settings_file), exist_ok=True)
        with open(plan.settings_file, 'w') as f:
            f.write('volume = 0.3\nlog_input = 1\n')  # (the menu's and the player's)
        rc, io = self.run_tui('2', 'yes', '')  # change the settings: fullscreen; troubleshooting left as it is
        self.assertEqual((rc, FakeFlow.calls), (0, []), io.text())
        self.assertIn('On now: Log controller and keyboard input', io.text())
        self.assertEqual(O.read_settings(plan.settings_file), {'fullscreen': True, 'log_input': True})
        rc, io = self.run_tui('2', 'no', 'none')  # and back: a window, troubleshooting all off
        with open(plan.settings_file) as f:
            self.assertEqual(f.read(), 'volume = 0.3\n# log_input = 0\n\n# --- set by the installer\n'
                                       '# fullscreen = 0\n')
        self.assertNotIn('launch', P.load_manifest(plan.manifest)['installs'][0])

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
        rc, io = self.run_tui(argv=self.answers(base=self.xci, keys=self.keys,
                                                settings={'fullscreen': True, 'gpu': 1}))
        self.assertEqual(rc, 0, io.text())
        self.assertEqual(FakeFlow.packed_settings, {'fullscreen': True, 'gpu': 1})
        for bad in (dict(base=self.xci), dict(base=self.xci, keys=self.keys, output='appimage'),
                    dict(base=self.xci, keys=self.keys, settings={'HM_NO_AUDIO': '1'}),
                    dict(base=self.xci, keys=self.keys, settings={'gpu': 'fast; rm -rf'}),
                    dict(base=self.xci, keys=self.keys, nonsense=1)):
            rc, io = self.run_tui(argv=self.answers(**bad))
            self.assertEqual(rc, 2, io.text())
        rc, io = self.run_tui(argv=['--answers', '/no/such/file'])
        self.assertEqual(rc, 2)


if __name__ == '__main__':
    unittest.main()
