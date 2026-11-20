"""What the player chose (the plan), whether it can work, and the record of what was installed (the manifest).

No questions and no terminal here: the prompts (installer/tui.py) and the --answers file both fill a Plan, the flow
(installer/flow.py) carries it out, and tests drive all of it without a terminal.
"""

import hashlib
import json
import os

from . import options as O

# Outputs. 'appimage' is the generic one: built in a Debian 12 container for x86-64-v2, it runs on any current
# distro, and it is the only output on an immutable system such as SteamOS or Bazzite, where no package can be
# installed (installer/appimage.py). The others are named so plans, answers files and the manifest keep one vocabulary
# when they arrive (docs/installer.md, section 4).
OUTPUTS = {'package': "A package for this system's package manager (pacman, apt, dnf, zypper)",
           'appimage': 'A generic AppImage: one file that runs on any current x86-64 Linux, also on immutable systems '
                       'such as SteamOS and Bazzite (built in a container: needs podman or Docker)'}
PLANNED = {'folder': 'a plain folder', 'flatpak': 'a Flatpak'}
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
    FIELDS = ('base', 'update', 'keys', 'output', 'march', 'keep_cache', 'work', 'out', 'settings')

    def __init__(self, env=None, **kw):
        self.base = self.update = self.keys = ''
        self.output, self.march, self.keep_cache = 'package', 'v2', False
        self.work = os.path.join(cache_home(env), 'temp')
        self.out = os.path.join(cache_home(env), 'packages')
        self.toolchain = os.path.join(cache_home(env), 'toolchain')
        self.manifest = os.path.join(data_home(env), 'installs.json')
        self.settings = {}  # game settings to write ({key: value}, installer/options.py); no rebuild when they change
        self.settings_file = os.path.join(data_home(env), O.INI)  # (the player's own, also saved by the in-game menu)
        unknown = set(kw) - set(self.FIELDS)
        if unknown:
            raise ValueError('unknown plan field(s): ' + ', '.join(sorted(unknown)))
        for k, v in kw.items():
            if k in ('base', 'update', 'keys', 'work', 'out'):
                v = clean_path(v) if v else getattr(self, k)
            setattr(self, k, v)

    @property
    def container_toolchain(self):
        """The AppImage build's own tools (built in the container, against its older C library)."""
        return self.toolchain + '-appimage'

    @property
    def stage(self):
        return os.path.join(self.work, 'stage', 'hylian-melodies')


def _free_gib(path):
    while path and not os.path.isdir(path):
        path = os.path.dirname(path)
    st = os.statvfs(path or '/')
    return st.f_bavail * st.f_frsize / GiB


def validate(plan, fmt=None, has_v3=None, free_gib=_free_gib, immutable=None):
    """-> [(field, text)]: everything wrong with the plan, in the order the questions are asked. immutable: the name
    of this system when it is an immutable one (installer/deps.py), where only the AppImage can be built."""
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
    elif immutable and plan.output != 'appimage':
        bad.append(('output', f'{immutable} is an immutable system: no package can be installed on it; only the '
                              'generic AppImage can be built (output "appimage")'))
    if plan.output == 'appimage' and plan.march != 'v2':
        bad.append(('march', 'The generic AppImage is always built for any x86-64 CPU (CPU level v2)'))
    elif plan.march not in MARCH:
        bad.append(('march', f'Unknown CPU level "{plan.march}"; choose: ' + ', '.join(MARCH)))
    elif plan.march == 'v3' and not (cpu_has_v3() if has_v3 is None else has_v3):
        bad.append(('march', "This computer's CPU lacks AVX2/FMA/BMI2: a v3 build could not start here; use v2"))
    if not isinstance(plan.keep_cache, bool):
        bad.append(('keep_cache', 'keep_cache must be true or false'))
    bad += [('settings', t) for t in O.check_settings(plan.settings)]
    if plan.output == 'appimage':  # (each is given to the container as "-v PATH:PATH")
        for field in ('base', 'keys', 'update', 'work', 'out'):
            if ':' in getattr(plan, field):
                bad.append((field, f'The AppImage build cannot use a path with ":" in it: {getattr(plan, field)}'))
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


def build_folder(plan, env=None):
    """-> the folder the work files and the package go in: the cache folder by default, else the player's choice."""
    work = os.path.dirname(plan.work)
    return cache_home(env) if work == cache_home(env) else os.path.dirname(work)


def place_build(plan, folder, env=None):
    """The work folder and the package in folder: the cache folder's own temp/ and packages/, or a hylian-melodies
    folder inside any other (so nothing is scattered among the player's files)."""
    folder = os.path.abspath(os.path.expanduser(folder))
    base = folder if folder == cache_home(env) else os.path.join(folder, 'hylian-melodies')
    plan.work, plan.out = os.path.join(base, 'temp'), os.path.join(base, 'packages')


def space(plan, free_gib=_free_gib):
    """-> [(what, folder, GiB needed, GiB free or None)] for the summary."""
    out = []
    for what, path, need in (('while building', plan.work, NEED_WORK_GIB), ('for the package', plan.out, NEED_OUT_GIB)):
        try:
            free = free_gib(path)
        except OSError:
            free = None
        out.append((what, path, need, free))
    return out


def du(path):
    """-> bytes under path (symbolic links counted as links, not followed); 0 when it is not there."""
    if os.path.islink(path) or os.path.isfile(path):
        try:
            return os.lstat(path).st_size
        except OSError:
            return 0
    total = 0
    for d, dirs, files in os.walk(path):
        for f in files + [x for x in dirs if os.path.islink(os.path.join(d, x))]:
            try:
                total += os.lstat(os.path.join(d, f)).st_size
            except OSError:
                pass
    return total


def size_text(n):
    for unit, step in (('GiB', GiB), ('MiB', 1 << 20), ('KiB', 1 << 10)):
        if n >= step:
            return f'{n / step:.1f} {unit}'
    return f'{n} bytes'


def leftovers(plan, repo, package=None):
    """What the install leaves on this computer besides the installed package's own files, for the last screen.
    -> [(path, bytes, what it is, True when it can be deleted)] of the ones that exist."""
    cache = os.path.dirname(plan.toolchain)  # (the plan's own cache folder, as the build used it)
    items = []
    if package and os.path.isfile(package):
        items.append((package, 'the AppImage, where it was built: keep it, or let the installer move it to '
                               '~/Applications' if plan.output == 'appimage' else
                      'the package file: not needed once it is installed', plan.output != 'appimage'))
    if os.path.isdir(plan.work) and os.listdir(plan.work):
        items.append((plan.work, 'build files' + (' kept for a faster rebuild' if plan.keep_cache else
                                                  ' (logs; the game files were removed)'), True))
    items.append((plan.toolchain, 'tools the build made (hactool and the like); made again when needed', True))
    items.append((plan.container_toolchain, 'tools the AppImage build made in its container; made again when needed',
                  True))
    src = os.path.join(cache, 'src')
    if os.path.realpath(repo).startswith(os.path.realpath(src) + os.sep):
        items.append((src, "the installer's source that install.sh downloaded", True))
    data = os.path.dirname(plan.manifest)
    items.append((data, 'your saves, settings and the list of builds: keep this (removing the package keeps it)',
                  False))
    seen, out = set(), []
    for path, what, removable in items:
        if os.path.exists(path) and path not in seen:
            seen.add(path)
            out.append((path, du(path), what, removable))
    return out


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
