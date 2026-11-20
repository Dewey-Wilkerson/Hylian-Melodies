"""Carry out a plan: check the system, build the tools and libraries the build needs, run the setup, wrap the
result as a package (or the generic AppImage), record it.

  run(plan, repo, emit) -> {'result': 'ok', 'file', 'install', 'remove'}
                         | {'result': 'deps', 'command', 'needs', 'notes'}   (nothing was built: packages are missing)
                         | {'result': 'error', 'text', 'log'}

`emit` gets the same events the setup prints (installer/events.py: step, progress, info, warning, error), with this
module's own steps added around them. Nothing is installed and nothing runs as root.

The AppImage (plan.output 'appimage') is built in a Debian 12 container (installer/appimage.py): Flow() then gives a
ContainerFlow, which runs each of the same steps inside it as `python3 -m installer.flow --inside PLAN --do STEP`
and passes its events on.
"""

import json
import os
import shutil
import subprocess
import sys
import time

from . import appimage, deps, pack
from . import options as O
from . import plan as P

STEPS = {
    'deps': 'Checking what this system has',
    'hactool': 'Building hactool',
    'sdl3': 'Building SDL3 (this system has no SDL3 package)',
    'shaderc': "Building shaderc (this system's shaderc package cannot be used)",
    'pack': 'Making the package',
    'image': 'Preparing the build container (the first time: downloads Debian 12 and the build tools)',
    'appimage': 'Making the AppImage',
    'record': 'Recording the install',
}


def default_settings(repo):
    """The package's default hylian-melodies.ini (what the launcher copies for a new player)."""
    return os.path.join(repo, 'packaging', O.INI)


class FlowError(Exception):
    pass


def read_os_release():
    try:
        with open('/etc/os-release') as f:
            return deps.parse_os_release(f.read())
    except OSError:
        return {}


class Flow:
    def __new__(cls, plan, *args, inside=False, **kw):
        if cls is Flow and plan.output == 'appimage' and not inside:
            cls = ContainerFlow
        return super().__new__(cls)

    def __init__(self, plan, repo, emit, osr=None, probe=None, inside=False):
        self.plan, self.repo, self.emit, self.probe = plan, os.path.abspath(repo), emit, probe
        mine = osr is None  # (this system's own os-release: the markers of an immutable system count too)
        if mine:
            osr = read_os_release()
        self.osr = osr
        self.immutable = deps.immutable(osr, markers=mine)
        self.family = deps.family(osr)
        self.format = pack.FORMATS.get(self.family)
        self.log_path = os.path.join(plan.work, 'logs', time.strftime('installer-%Y%m%d-%H%M%S.log'))
        self.extra = []  # (--sdl3 / --shaderc for the setup, once those are built)

    # -- helpers
    def step(self, name):
        self.emit({'event': 'step', 'step': name, 'msg': STEPS[name]})

    def log(self, text):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, 'a') as f:
            f.write(time.strftime('%H:%M:%S ') + text.rstrip('\n') + '\n')

    def tool(self, name, script, *args):
        """Run one of the repository's build tools; its output goes to the log."""
        self.step(name)
        cmd = [sys.executable, os.path.join(self.repo, 'tools', script), *args]
        self.log(' '.join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.log(r.stdout + r.stderr)
        if r.returncode:
            raise FlowError(((r.stdout + r.stderr).strip().splitlines() or [f'{script} failed'])[-1])
        self.emit({'event': 'progress', 'step': name, 'pct': 100})

    def tc(self, *parts):
        return os.path.join(self.plan.toolchain, *parts)

    # -- the steps
    def check_system(self):
        """-> None when everything needed is there, else the 'deps' result."""
        self.step('deps')
        deps.use_newer_clang(self.probe)
        self.deps = deps.check(self.osr, self.probe)
        if self.deps['missing']:
            return {'result': 'deps', 'command': self.deps['command'], 'notes': self.deps['notes'],
                    'needs': [n for n in self.deps['needs'] if not n['ok']]}
        if not self.format:
            raise FlowError('No package format is known for this distribution')
        return None

    def build_tools(self):
        self.extra = []
        self.tool('hactool', 'build_hactool.py', '--src', self.tc('src', 'hactool'), '--out', self.tc('hactool'))
        for lib in ('sdl3', 'shaderc'):
            if self.deps[lib] == 'own':
                self.tool(lib, f'build_{lib}.py', '--src', self.tc('src', lib), '--out', self.tc(lib))
                self.extra += ['--' + lib, self.tc(lib)]

    def own_libs(self):
        """The --sdl3 / --shaderc arguments for libraries build_tools() built earlier (the container's later steps)."""
        self.extra = []
        for lib in ('sdl3', 'shaderc'):
            if self.deps[lib] == 'own':
                self.extra += ['--' + lib, self.tc(lib)]

    def setup(self, until=None):
        """python -m installer, its events passed on. until='check': only look at the files."""
        p = self.plan
        cmd = [sys.executable, '-m', 'installer', '--base', p.base, '--keys', p.keys, '--dest', p.stage,
               '--temp', os.path.join(p.work, 'install-temp'), '--root', self.repo,
               '--hactool', self.tc('hactool', 'hactool'),
               '--vma', self.tc('src', 'vma'), '--march', p.march, *self.extra]
        if p.update:
            cmd += ['--update', p.update]
        if until or p.keep_cache:  # (keep_cache: stop before the cleanup step, the generated C and objects stay)
            cmd += ['--until', until or 'compile']
        self.log(' '.join(cmd))
        proc = subprocess.Popen(cmd, cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        end, last_error = None, None
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                self.log(line)
                continue
            if ev.get('event') == 'end':
                end = ev
            elif ev.get('event') != 'start':
                if ev.get('event') == 'error':
                    last_error = ev.get('text')
                self.emit(ev)
        proc.wait()
        if not end or end.get('result') != 'ok':
            raise FlowError(last_error or 'The setup stopped unexpectedly', (end or {}).get('log'))

    def check_inputs(self):
        self.setup(until='check')  # (the setup's own "Checking files" step is the heading)

    def make_package(self):
        self.step('pack')
        p = self.plan
        try:
            target = pack.pack(p.stage, self.repo, p.out, os.path.join(p.work, 'pack'), self.format, p.settings)
        except pack.PackError as e:
            raise FlowError(str(e)) from None
        self.emit({'event': 'progress', 'step': 'pack', 'pct': 100})
        shutil.rmtree(os.path.join(p.work, 'pack'), ignore_errors=True)  # (makepkg / rpmbuild keep a copy there)
        if not p.keep_cache:  # the package holds the game now
            shutil.rmtree(os.path.dirname(p.stage), ignore_errors=True)
        return target

    def make_appimage(self):
        """(inside the container) The finished setup folder as the AppImage. -> (the file, its icon)"""
        self.step('appimage')
        p = self.plan
        try:
            target, icon = appimage.build(p.stage, self.repo, p.out, os.path.join(p.work, 'appimage'), p.toolchain,
                                          p.settings)
        except appimage.AppImageError as e:
            raise FlowError(str(e)) from None
        self.emit({'event': 'progress', 'step': 'appimage', 'pct': 100})
        if not p.keep_cache:  # the AppImage holds the game now
            shutil.rmtree(os.path.dirname(p.stage), ignore_errors=True)
        return target, icon

    def save_settings(self):
        """The plan's game settings into the player's ini when the player has one already. A new player gets them
        from the package's default ini (make_package), which the launcher copies at the first start wherever the
        player's folder is. Not in the manifest, where the in-game menu could not keep them current."""
        if self.plan.settings and os.path.isfile(self.plan.settings_file):
            O.write_settings(self.plan.settings_file, self.plan.settings, default_settings(self.repo))

    def record(self, target):
        self.step('record')
        p = self.plan
        install, remove = pack.commands(self.format, target, self.family)
        with open(os.path.join(self.repo, 'VERSION')) as f:
            ver = f.read().strip()
        entry = {
            'id': 'package:' + pack.NAME, 'output': 'package', 'location': '/opt/hylian-melodies', 'version': ver,
            'built': time.strftime('%Y-%m-%dT%H:%M:%S'), 'source': {'path': self.repo},
            'inputs': {'base': {'path': p.base, 'sha256': P.sha256_file(p.base)}, 'keys': {'path': p.keys}},
            'build': {'march': p.march, 'keep_cache': p.keep_cache, 'sdl3': self.deps['sdl3'],
                      'shaderc': self.deps['shaderc'], 'work': p.work},
            'package': {'name': pack.NAME, 'format': self.format, 'file': target, 'install': install,
                        'remove': remove},
        }
        self.save_settings()
        if p.update:
            entry['inputs']['update'] = {'path': p.update}
        P.record_install(p.manifest, entry)
        self.emit({'event': 'progress', 'step': 'record', 'pct': 100})
        return {'result': 'ok', 'file': target, 'install': install, 'remove': remove}

    def error(self, e):
        text = str(e.args[0]) if e.args else 'failed'
        log = e.args[1] if len(e.args) > 1 and e.args[1] else self.log_path
        self.log('error: ' + text)
        return {'result': 'error', 'text': text, 'log': log}


class ContainerFlow(Flow):
    """The generic AppImage: the same steps, each run inside the Debian 12 build container (installer/appimage.py).
    Here, on the host, only the container engine is needed; the build packages are in the image."""

    def __init__(self, plan, repo, emit, osr=None, probe=None, inside=False, engine=None):
        super().__init__(plan, repo, emit, osr, probe)
        self.engine = deps.container_engine() if engine is None else engine
        self.format = 'appimage'
        self.deps = {'sdl3': 'own', 'shaderc': 'own'}  # (Debian 12 lacks both: built from source in the container)
        self.icon = None

    def check_system(self):
        self.step('deps')
        if self.engine:
            return None
        what = {'what': 'podman (or Docker): the AppImage is built in a container', 'ok': False,
                'packages': ['podman']}
        if self.immutable:
            notes = [f'{self.immutable} normally comes with podman (SteamOS 3.5 and newer, Bazzite, Fedora '
                     'Silverblue/Kinoite); if it is missing, update the system or add podman the way it allows, '
                     'then check again.']
            command = ''
        else:
            notes = ['The AppImage is built in a Debian 12 container, so that it runs on any current distro.']
            command = deps.INSTALL[self.family] + ' podman' if self.family else ''
        return {'result': 'deps', 'command': command, 'notes': notes, 'needs': [what]}

    def ensure_image(self):
        self.step('image')
        tag = appimage.image_tag()
        if not appimage.image_exists(self.engine, tag):
            ctx = os.path.join(self.plan.work, 'container')
            os.makedirs(ctx, exist_ok=True)
            with open(os.path.join(ctx, 'Containerfile'), 'w') as f:
                f.write(appimage.containerfile())
            cmd = appimage.build_image_cmd(self.engine, tag, ctx)
            self.log(' '.join(cmd))
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.log(r.stdout)
            if r.returncode:
                raise FlowError(f'Could not prepare the build container ({self.engine} build failed)')
        self.emit({'event': 'progress', 'step': 'image', 'pct': 100})
        return tag

    def inside(self, step):
        """Run one step in the container; its events come through. -> its end event"""
        p = self.plan
        for d in (p.work, p.out, p.container_toolchain, os.path.join(p.work, 'container-home')):
            os.makedirs(d, exist_ok=True)
        plan_file = os.path.join(p.work, 'container-plan.json')
        with open(plan_file, 'w') as f:
            json.dump(dict({k: getattr(p, k) for k in P.Plan.FIELDS}, toolchain=p.container_toolchain), f)
        try:
            cmd = appimage.run_cmd(self.engine, appimage.image_tag(), p, self.repo, p.container_toolchain,
                                   ['-m', 'installer.flow', '--inside', plan_file, '--do', step])
        except appimage.AppImageError as e:
            raise FlowError(str(e)) from None
        self.log(' '.join(cmd))
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)
        end, last_error = None, None
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                self.log(line)
                continue
            if ev.get('event') == 'end':
                end = ev
            elif ev.get('event') != 'start':
                if ev.get('event') == 'error':
                    last_error = ev.get('text')
                self.emit(ev)
        proc.wait()
        if not end or end.get('result') != 'ok':
            raise FlowError((end or {}).get('text') or last_error or
                            f'The build container stopped unexpectedly (exit status {proc.returncode})',
                            (end or {}).get('log'))
        return end

    def build_tools(self):
        self.ensure_image()
        self.inside('tools')

    def check_inputs(self):
        self.inside('check')

    def setup(self, until=None):
        self.inside('setup')

    def make_package(self):
        end = self.inside('appimage')
        self.icon = end.get('icon')
        return end['file']

    def record(self, target):
        self.step('record')
        p = self.plan
        with open(os.path.join(self.repo, 'VERSION')) as f:
            ver = f.read().strip()
        entry = {
            'id': 'appimage', 'output': 'appimage', 'location': target, 'version': ver,
            'built': time.strftime('%Y-%m-%dT%H:%M:%S'), 'source': {'path': self.repo},
            'inputs': {'base': {'path': p.base, 'sha256': P.sha256_file(p.base)}, 'keys': {'path': p.keys}},
            'build': {'march': 'v2', 'keep_cache': p.keep_cache, 'sdl3': 'own', 'shaderc': 'own', 'work': p.work,
                      'container': {'engine': self.engine, 'image': appimage.image_tag()}},
            'appimage': {'file': target, 'icon': self.icon, 'files': [target]},
        }
        self.save_settings()
        if p.update:
            entry['inputs']['update'] = {'path': p.update}
        P.record_install(p.manifest, entry)
        self.emit({'event': 'progress', 'step': 'record', 'pct': 100})
        return {'result': 'ok', 'output': 'appimage', 'file': target, 'icon': self.icon, 'entry': entry,
                'install': target, 'remove': 'rm ' + target}


def inside_main(plan_file, do, repo, out=None):
    """(in the build container) One step of the AppImage flow; events and a last 'end' line as JSON on stdout."""
    out = out or sys.stdout

    def emit(ev):
        out.write(json.dumps(ev) + '\n')
        out.flush()
    with open(plan_file) as f:
        fields = json.load(f)
    toolchain = fields.pop('toolchain')
    plan = P.Plan(**fields)
    plan.toolchain = toolchain
    f = Flow(plan, repo, emit, inside=True)
    try:
        need = f.check_system()
        if need:
            raise FlowError('The build container lacks: ' + ', '.join(n['what'] for n in need['needs']))
        if do == 'tools':
            f.build_tools()
        else:
            f.own_libs()
        if do == 'check':
            f.check_inputs()
        elif do == 'setup':
            f.setup()
        elif do == 'appimage':
            target, icon = f.make_appimage()
            emit({'event': 'end', 'result': 'ok', 'file': target, 'icon': icon})
            return 0
        emit({'event': 'end', 'result': 'ok'})
        return 0
    except FlowError as e:
        r = f.error(e)
        emit({'event': 'end', 'result': 'error', 'text': r['text'], 'log': r['log']})
        return 1


def run(plan, repo, emit, osr=None, probe=None, flow=None):
    """The whole thing. A plan that validate() accepts is assumed."""
    f = flow or Flow(plan, repo, emit, osr, probe)
    try:
        need = f.check_system()
        if need:
            return need
        f.build_tools()
        f.check_inputs()
        f.setup()
        return f.record(f.make_package())
    except FlowError as e:
        return f.error(e)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(prog='python -m installer.flow', description='one step of the AppImage build, run '
                                 'inside its container by the installer (not for running by hand)')
    ap.add_argument('--inside', required=True, metavar='PLAN.json')
    ap.add_argument('--do', required=True, choices=('tools', 'check', 'setup', 'appimage'))
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a = ap.parse_args()
    sys.exit(inside_main(a.inside, a.do, a.root))
