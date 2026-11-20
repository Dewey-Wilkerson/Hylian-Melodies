"""installer/appimage.py and the AppImage route through flow.py and tui.py: the container command, AppRun's choice of
libraries, the AppDir, the menu entry, install and remove. No container is started and no game is built."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from installer import appimage as A, flow as F, plan as P, tui  # noqa: E402
from test_tui import Base, FakeFlow, Script  # noqa: E402

FAKE_GAME = '#!/bin/sh\necho "LD=${LD_LIBRARY_PATH:-} GAME=${HM_GAME_DIR:-} ARGS=$*"\n'


class Pieces(Base):
    def test_image_and_run_command(self):
        self.assertIn('FROM docker.io/library/debian:12', A.containerfile())
        self.assertIn('squashfs-tools', A.containerfile())
        self.assertTrue(A.image_tag().startswith('localhost/hylian-melodies-builder:'))
        self.assertEqual(A.image_tag(), A.image_tag())
        plan = P.Plan(self.env, base=self.xci, keys=self.keys, output='appimage')
        cmd = A.run_cmd('podman', 'img', plan, '/repo dir', '/tc', ['-m', 'x'], uid=1000, gid=1000)
        self.assertEqual(cmd[:3], ['podman', 'run', '--rm'])
        self.assertIn('--userns=keep-id', cmd)
        self.assertIn('label=disable', cmd)
        vols = [cmd[i + 1] for i, c in enumerate(cmd) if c == '-v']
        self.assertEqual(vols, ['/repo dir:/repo dir:ro', f'{self.xci}:{self.xci}:ro', f'{self.keys}:{self.keys}:ro',
                                f'{plan.work}:{plan.work}', f'{plan.out}:{plan.out}', '/tc:/tc'])
        self.assertEqual(cmd[-3:], ['python3', '-m', 'x'])
        self.assertIn('--user', A.run_cmd('docker', 'img', plan, '/r', '/tc', [], uid=1, gid=2))
        plan.work = '/a:b'
        with self.assertRaises(A.AppImageError):
            A.run_cmd('podman', 'img', plan, '/r', '/tc', [])

    def test_host_only_libraries(self):
        for n in ('libc.so.6', 'ld-linux-x86-64.so.2', 'libstdc++.so.6', 'libgcc_s.so.1', 'libvulkan.so.1',
                  'libGLX.so.0', 'libdrm.so.2', 'libm.so.6'):
            self.assertTrue(A.host_only(n), n)
        for n in ('libavcodec.so.59', 'libz.so.1', 'libX11.so.6', 'libmp3lame.so.0'):
            self.assertFalse(A.host_only(n), n)

    def test_libraries_from_ldd(self):
        out = ('\tlinux-vdso.so.1 (0x00007ffd)\n\tlibavcodec.so.59 => /usr/lib/x86_64-linux-gnu/libavcodec.so.59 (0x1)\n'
               '\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x2)\n\t/lib64/ld-linux-x86-64.so.2 (0x3)\n'
               '\t/usr/lib64/ld-linux-x86-64.so.2 => /usr/lib/ld-linux-x86-64.so.2 (0x4)\n')
        real = A.run
        A.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, '')
        try:
            self.assertEqual(A.libraries('/x'), {'libavcodec.so.59': '/usr/lib/x86_64-linux-gnu/libavcodec.so.59'})
            A.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '\tlibfoo.so.1 => not found\n', '')
            with self.assertRaises(A.AppImageError):
                A.libraries('/x')
        finally:
            A.run = real

    def test_apprun_uses_a_copy_only_when_the_host_lacks_it(self):
        d = os.path.join(self.t, 'AppDir')
        for lib in ('libnot-on-any-host.so.9', 'libc.so.6'):  # (libc: every host has it)
            os.makedirs(os.path.join(d, 'usr', 'lib', lib))
        os.makedirs(os.path.join(d, 'usr', 'bin'))
        with open(os.path.join(d, 'AppRun'), 'w') as f:
            f.write(A.APPRUN)
        with open(os.path.join(d, 'usr', 'bin', 'hylian-melodies'), 'w') as f:
            f.write(FAKE_GAME)
        os.chmod(os.path.join(d, 'usr', 'bin', 'hylian-melodies'), 0o755)
        env = {k: v for k, v in os.environ.items() if k != 'LD_LIBRARY_PATH'}
        r = subprocess.run(['sh', os.path.join(d, 'AppRun'), '--fullscreen'], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('ARGS=--fullscreen', r.stdout)
        self.assertIn(f'GAME={d}/opt/hylian-melodies', r.stdout)
        ld = r.stdout.split('LD=', 1)[1].split(' GAME=')[0].split(':')
        self.assertIn(os.path.join(d, 'usr', 'lib', 'libnot-on-any-host.so.9'), ld)
        if shutil.which('ldconfig') or os.path.exists('/sbin/ldconfig') or os.path.exists('/usr/sbin/ldconfig'):
            self.assertNotIn(os.path.join(d, 'usr', 'lib', 'libc.so.6'), ld)

    @unittest.skipUnless(shutil.which('strip'), 'needs strip')
    def test_appdir(self):
        stage = os.path.join(self.t, 'stage')
        os.makedirs(os.path.join(stage, 'romfs'))
        shutil.copy(shutil.which('true') or '/bin/true', os.path.join(stage, 'hylian-melodies'))
        d = os.path.join(self.t, 'AppDir')
        icon = A.make_appdir(stage, ROOT, d, {'fullscreen': True})
        for p in ('AppRun', 'hylian-melodies.desktop', '.DirIcon', 'opt/hylian-melodies/hylian-melodies',
                  'usr/bin/hylian-melodies', 'usr/share/hylian-melodies-recomp/hylian-melodies.ini'):
            self.assertTrue(os.path.lexists(os.path.join(d, p)), p)
        self.assertTrue(os.access(os.path.join(d, 'AppRun'), os.X_OK))
        self.assertEqual(os.path.dirname(icon), d)
        self.assertFalse(os.path.exists(os.path.join(d, 'usr/share/hylian-melodies-recomp/desktop-copy')))
        for lib in os.listdir(os.path.join(d, 'usr', 'lib')) if os.path.isdir(os.path.join(d, 'usr', 'lib')) else []:
            self.assertFalse(A.host_only(lib), lib)  # (true's libc is not copied in)

    def test_desktop_entry_quotes_the_path(self):
        t = A.desktop_entry('/home/p/My "Apps"/$x.AppImage', 'hylian-melodies-appimage')
        self.assertIn('Exec="/home/p/My \\"Apps\\"/\\$x.AppImage"\n', t)
        self.assertIn('Exec="/home/p/My \\"Apps\\"/\\$x.AppImage" --fullscreen\n', t)

    def test_install_and_remove(self):
        out = os.path.join(self.t, 'out')
        os.makedirs(out)
        img, icon = os.path.join(out, A.NAME), os.path.join(out, 'hylian-melodies-icon.png')
        for p in (img, icon):
            with open(p, 'w') as f:
                f.write('x')
        got = A.install(img, icon, self.env)
        self.assertEqual(got['file'], os.path.join(self.t, 'Applications', A.NAME))
        self.assertTrue(os.access(got['file'], os.X_OK))
        self.assertFalse(os.path.exists(img) or os.path.exists(icon))
        entry = os.path.join(self.t, '.local/share/applications/hylian-melodies-appimage.desktop')
        self.assertIn(entry, got['files'])
        with open(entry) as f:
            self.assertIn(f'Exec="{got["file"]}"', f.read())
        self.assertEqual(sorted(A.remove(got['files'])), sorted(got['files']))
        self.assertFalse(any(os.path.exists(p) for p in got['files']))


class FakeAppFlow(FakeFlow):
    def make_package(self):
        type(self).calls.append('make_package')
        os.makedirs(self.plan.out, exist_ok=True)
        target, self.icon = os.path.join(self.plan.out, A.NAME), os.path.join(self.plan.out, 'hylian-melodies-icon.png')
        for p in (target, self.icon):
            with open(p, 'wb') as f:
                f.write(b'a' * 100)
        return target

    def record(self, target):
        type(self).calls.append('record')
        entry = {'id': 'appimage', 'output': 'appimage', 'location': target, 'version': '0',
                 'inputs': {'base': {'path': self.plan.base}, 'keys': {'path': self.plan.keys}},
                 'build': {'march': 'v2'}, 'appimage': {'file': target, 'icon': self.icon, 'files': [target]}}
        P.record_install(self.plan.manifest, entry)
        return {'result': 'ok', 'output': 'appimage', 'file': target, 'icon': self.icon, 'entry': entry,
                'install': target, 'remove': 'rm ' + target}


class Route(Base):
    def run_tui(self, *answers, argv=(), immutable=None):
        io = Script(*answers)
        rc = tui.main(list(argv), io=io, make_flow=FakeAppFlow, env=self.env, gpus=lambda: [],
                      run=lambda argv: 0, immutable=immutable)
        return rc, io

    def test_immutable_gets_the_appimage_only(self):
        # (no output question; no CPU question) files, keep files, folder, window, troubleshooting, start, move it
        rc, io = self.run_tui(self.xci, self.keys, '', '', '', '', '', '', immutable='SteamOS')
        self.assertEqual(rc, 0, io.text())
        self.assertNotIn('What should the installer build?', io.said)
        self.assertNotIn('Which CPUs should the game run on?', io.said)
        t = io.text()
        self.assertIn('SteamOS is an immutable system', t)
        self.assertIn('the generic AppImage in', t)
        self.assertIn('Add a Non-Steam Game', t)
        dest = os.path.join(self.t, 'Applications', A.NAME)
        self.assertTrue(os.path.isfile(dest))
        e = P.load_manifest(P.Plan(self.env).manifest)['installs'][0]
        self.assertEqual((e['output'], e['location']), ('appimage', dest))
        self.assertIn(os.path.join(self.t, '.local/share/applications/hylian-melodies-appimage.desktop'),
                      e['appimage']['files'])
        # again: remove it
        rc, io = self.run_tui('3', '')
        self.assertEqual(rc, 0, io.text())
        self.assertFalse(os.path.exists(dest))
        self.assertEqual(P.load_manifest(P.Plan(self.env).manifest)['installs'], [])

    def test_chosen_on_an_ordinary_system(self):
        rc, io = self.run_tui('2', self.xci, self.keys, '', '', '', '', '', 'no')  # AppImage; leave it where it is
        self.assertEqual(rc, 0, io.text())
        self.assertIn('What should the installer build?', io.said)
        self.assertNotIn('Which CPUs should the game run on?', io.said)
        self.assertTrue(os.path.isfile(os.path.join(P.Plan(self.env).out, A.NAME)))
        self.assertFalse(os.path.exists(os.path.join(self.t, 'Applications')))

    def test_answers(self):
        path = os.path.join(self.t, 'a.json')
        with open(path, 'w') as f:
            json.dump({'base': self.xci, 'keys': self.keys, 'output': 'appimage'}, f)
        rc, io = self.run_tui(argv=['--answers', path])
        self.assertEqual((rc, io.asked), (0, []), io.text())
        self.assertTrue(os.path.isfile(os.path.join(P.Plan(self.env).out, A.NAME)))  # (an answers file never moves it)
        with open(path, 'w') as f:
            json.dump({'base': self.xci, 'keys': self.keys, 'output': 'appimage', 'march': 'native'}, f)
        self.assertEqual(self.run_tui(argv=['--answers', path])[0], 2)


class ContainerFlowTests(Base):
    def engine(self, body):
        """A stand-in container engine: a script that answers `image exists` and prints the given events."""
        p = os.path.join(self.t, 'fake-engine')
        with open(p, 'w') as f:
            f.write('#!/bin/sh\ncase "$1" in image) exit 0 ;; esac\n' + body)
        os.chmod(p, 0o755)
        return p

    def flow(self, engine, osr='ID=arch\n'):
        self.events = []
        plan = P.Plan(self.env, base=self.xci, keys=self.keys, output='appimage')
        from installer import deps
        return F.Flow(plan, ROOT, self.events.append, deps.parse_os_release(osr), engine=engine)

    def test_flow_gives_the_container_flow(self):
        f = self.flow('podman')
        self.assertIsInstance(f, F.ContainerFlow)
        self.assertEqual(f.format, 'appimage')
        self.assertNotIsInstance(F.Flow(P.Plan(self.env), ROOT, print, {'ID': 'arch'}), F.ContainerFlow)
        self.assertNotIsInstance(F.Flow(f.plan, ROOT, print, {'ID': 'debian', 'VERSION_ID': '12'}, inside=True),
                                 F.ContainerFlow)

    def test_no_engine(self):
        r = self.flow('').check_system()
        self.assertEqual((r['result'], r['command']), ('deps', 'sudo pacman -S --needed podman'))
        r = self.flow('', 'NAME="SteamOS"\nID=steamos\nID_LIKE=arch\n').check_system()
        self.assertEqual(r['command'], '')  # (nothing to install with pacman on a read-only system)
        self.assertIn('SteamOS', r['notes'][0])
        self.assertIsNone(self.flow('podman').check_system())

    def test_events_come_through(self):
        out = os.path.join(P.Plan(self.env).out, A.NAME)
        f = self.flow(self.engine(
            'echo \'{"event": "step", "step": "compile", "msg": "Compiling the game"}\'\necho noise\n'
            f'echo \'{{"event": "end", "result": "ok", "file": "{out}", "icon": "/i.png"}}\'\n'))
        self.assertEqual(f.make_package(), out)
        self.assertEqual(f.icon, '/i.png')
        self.assertIn({'event': 'step', 'step': 'compile', 'msg': 'Compiling the game'}, self.events)
        with open(os.path.join(f.plan.work, 'container-plan.json')) as fh:
            sent = json.load(fh)
        self.assertEqual((sent['output'], sent['toolchain']), ('appimage', f.plan.container_toolchain))
        r = f.record(out)
        self.assertEqual((r['output'], r['file']), ('appimage', out))
        self.assertEqual(P.load_manifest(f.plan.manifest)['installs'][0]['build']['march'], 'v2')

    def test_a_failure_inside(self):
        f = self.flow(self.engine('echo \'{"event": "end", "result": "error", "text": "no clang", "log": "/l"}\'\n'))
        with self.assertRaises(F.FlowError) as c:
            f.setup()
        self.assertEqual(c.exception.args, ('no clang', '/l'))
        f = self.flow(self.engine('exit 125\n'))
        with self.assertRaises(F.FlowError) as c:
            f.check_inputs()
        self.assertIn('exit status 125', c.exception.args[0])


if __name__ == '__main__':
    unittest.main()
