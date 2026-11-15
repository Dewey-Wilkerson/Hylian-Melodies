"""What the player chose (the plan), whether it can work, and the record of what was installed (the manifest).

No questions and no terminal here: the prompts (installer/tui.py) and the --answers file both fill a Plan, the flow
(installer/flow.py) carries it out, and tests drive all of it without a terminal.
"""

import hashlib
import json
import os

# Outputs. Only 'package' is built so far. The others are named so plans, answers files and the manifest keep one
# vocabulary when they arrive: 'appimage' is the channel for immutable systems such as SteamOS, where no package can
# be installed (docs/installer.md, section 4).
OUTPUTS = {'package': "A package for this system's package manager (pacman, apt, dnf, zypper)"}
PLANNED = {'folder': 'a plain folder', 'appimage': 'an AppImage (for immutable systems such as SteamOS)',
           'flatpak': 'a Flatpak'}
MARCH = {'v2': 'Generic: runs on any x86-64 CPU since about 2009, also on other computers',
         'v3': "Optimized for 2013+ CPUs (AVX2): may be a little faster, won't start on an older CPU",
         'native': "Optimized for exactly this computer's CPU: won't start on a different one"}
GiB = 1 << 30
NEED_WORK_GIB, NEED_OUT_GIB = 12, 2  # extraction + generated C + objects + the package tree; the package file


def cache_home(env=None):
    env = os.environ if env is None else env
    base = env.get('XDG_CACHE_HOME', '')
    return os.path.join(base if base.startswith('/') else os.path.join(env.get('HOME', ''), '.cache'),
                        'hylian-melodies')


def data_home(env=None):
    env = os.environ if env is None else env
    base = env.get('XDG_DATA_HOME', '')
    return os.path.join(base if base.startswith('/') else os.path.join(env.get('HOME', ''), '.local', 'share'),
                        'hylian-melodies')


def clean_path(text):
    """A path as typed or dropped into a terminal: quotes and a file:// prefix removed, ~ expanded."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in '"\'':
        t = t[1:-1]
    if t.startswith('file://'):
        from urllib.parse import unquote
        t = unquote(t[7:])
    return os.path.abspath(os.path.expanduser(t)) if t else ''


def cpu_has_v3():
    try:
        with open('/proc/cpuinfo') as f:
            flags = f.read().split('flags', 1)[1].split('\n', 1)[0].split()
    except (OSError, IndexError):
        return False
    return {'avx2', 'fma', 'bmi2', 'movbe'} <= set(flags)


class Plan:
    FIELDS = ('base', 'update', 'keys', 'output', 'march', 'keep_cache', 'work', 'out')

    def __init__(self, env=None, **kw):
        self.base = self.update = self.keys = ''
        self.output, self.march, self.keep_cache = 'package', 'v2', False
        self.work = os.path.join(cache_home(env), 'temp')
        self.out = os.path.join(cache_home(env), 'packages')
        self.toolchain = os.path.join(cache_home(env), 'toolchain')
        self.manifest = os.path.join(data_home(env), 'installs.json')
        unknown = set(kw) - set(self.FIELDS)
        if unknown:
            raise ValueError('unknown plan field(s): ' + ', '.join(sorted(unknown)))
        for k, v in kw.items():
            if k in ('base', 'update', 'keys', 'work', 'out'):
                v = clean_path(v) if v else getattr(self, k)
            setattr(self, k, v)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.FIELDS}

    @property
    def stage(self):
        return os.path.join(self.work, 'stage', 'hylian-melodies')


def _free_gib(path):
    while path and not os.path.isdir(path):
        path = os.path.dirname(path)
    st = os.statvfs(path or '/')
    return st.f_bavail * st.f_frsize / GiB


def validate(plan, fmt=None, has_v3=None, free_gib=_free_gib):
    """-> [(field, text)]: everything wrong with the plan, in the order the questions are asked."""
    bad = []
    for field, what in (('base', 'cartridge dump'), ('keys', 'keys file'), ('update', 'update file')):
        p = getattr(plan, field)
        if not p:
            if field != 'update':
                bad.append((field, f'No {what} given'))
        elif not os.path.isfile(p):
            bad.append((field, f'The {what} is not a file: {p}'))
        elif not os.access(p, os.R_OK):
            bad.append((field, f'The {what} cannot be read: {p}'))
    if plan.output in PLANNED:
        bad.append(('output', f'This version cannot build {PLANNED[plan.output]} yet; choose: ' + ', '.join(OUTPUTS)))
    elif plan.output not in OUTPUTS:
        bad.append(('output', f'Unknown output "{plan.output}"; choose: ' + ', '.join(OUTPUTS)))
    if plan.march not in MARCH:
        bad.append(('march', f'Unknown CPU level "{plan.march}"; choose: ' + ', '.join(MARCH)))
    elif plan.march == 'v3' and not (cpu_has_v3() if has_v3 is None else has_v3):
        bad.append(('march', "This computer's CPU lacks AVX2/FMA/BMI2: a v3 build could not start here; use v2"))
    if not isinstance(plan.keep_cache, bool):
        bad.append(('keep_cache', 'keep_cache must be true or false'))
    if fmt == 'rpm':
        for field in ('work', 'out'):
            if ' ' in getattr(plan, field):
                bad.append((field, f'rpmbuild cannot work in a path with a space in it: {getattr(plan, field)}'))
    for field, need in (('work', NEED_WORK_GIB), ('out', NEED_OUT_GIB)):
        try:
            free = free_gib(getattr(plan, field))
        except OSError:
            bad.append((field, f'Cannot look at {getattr(plan, field)}'))
            continue
        if free < need:
            bad.append((field, f'Not enough free space in {getattr(plan, field)}: {free:.1f} GiB free, about '
                               f'{need} GiB needed'))
    return bad


def sha256_file(path, progress=None):
    h = hashlib.sha256()
    size, done = os.path.getsize(path) or 1, 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(100 * done // size)
    return h.hexdigest()


# ------------------------------------------------------------------ the manifest

def load_manifest(path):
    try:
        with open(path) as f:
            m = json.load(f)
    except (OSError, ValueError):
        return {'format': 1, 'installs': []}
    if not isinstance(m, dict) or not isinstance(m.get('installs'), list):
        return {'format': 1, 'installs': []}
    return m


def save_manifest(path, m):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.new'
    with open(tmp, 'w') as f:
        json.dump(m, f, indent=1)
        f.write('\n')
    os.replace(tmp, path)


def record_install(path, entry):
    """Add the entry; an older one with the same id (same output and place) is replaced."""
    m = load_manifest(path)
    m['installs'] = [e for e in m['installs'] if e.get('id') != entry['id']] + [entry]
    save_manifest(path, m)


def forget_install(path, install_id):
    m = load_manifest(path)
    m['installs'] = [e for e in m['installs'] if e.get('id') != install_id]
    save_manifest(path, m)
