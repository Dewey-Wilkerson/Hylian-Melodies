"""Carry out a plan: check the system, build the tools and libraries the build needs, run the setup, wrap the
result as a package, record it.

  run(plan, repo, emit) -> {'result': 'ok', 'file', 'install', 'remove'}
                         | {'result': 'deps', 'command', 'needs', 'notes'}   (nothing was built: packages are missing)
                         | {'result': 'error', 'text', 'log'}

`emit` gets the same events the setup prints (installer/events.py: step, progress, info, warning, error), with this
module's own steps added around them. Nothing is installed and nothing runs as root.
"""

import json
import os
import shutil
import subprocess
import sys
import time

from . import deps, pack
from . import options as O
from . import plan as P

STEPS = {
    'deps': 'Checking what this system has',
    'hactool': 'Building hactool',
    'sdl3': 'Building SDL3 (this system has no SDL3 package)',
    'shaderc': "Building shaderc (this system's shaderc package cannot be used)",
    'pack': 'Making the package',
    'record': 'Recording the install',
}


def default_settings(repo):
    """The package's default hylian-melodies.ini (what the launcher copies for a new player)."""
    return os.path.join(repo, 'packaging', O.INI)


class FlowError(Exception):
    pass


class Flow:
    def __init__(self, plan, repo, emit, osr=None, probe=None):
        self.plan, self.repo, self.emit, self.probe = plan, os.path.abspath(repo), emit, probe
        if osr is None:
            try:
                with open('/etc/os-release') as f:
                    osr = deps.parse_os_release(f.read())
            except OSError:
                osr = {}
        self.osr = osr
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

    def setup(self, until=None):
        """python -m installer, its events passed on. until='check': only look at the files."""
        p = self.plan
        cmd = [sys.executable, '-m', 'installer', '--base', p.base, '--keys', p.keys, '--dest', p.stage,
               '--temp', os.path.join(p.work, 'install-temp'), '--root', self.repo,
               '--hactool', self.tc('hactool', 'hactool'), '--imgui', self.tc('src', 'imgui'),
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
