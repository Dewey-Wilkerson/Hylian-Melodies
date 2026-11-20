"""Game settings the installer asks about, and the one list of the game's HM_* environment variables.

The player's choices go into the game's own settings file, hylian-melodies.ini: the package's default copy (which
the launcher copies at a player's first start) and the player's own in ${XDG_DATA_HOME:-~/.local/share}/
hylian-melodies/ when it exists, the same file the in-game menu (F1) reads and saves, so the two never disagree. The installer edits only the keys it asks about and keeps every other line (docs/DECISIONS.md:
the ini, not a launch.env). No rebuild is needed when they change.

Every `getenv("HM_...")` / `ENV("HM_...")` in runtime/ is in exactly one group here (tests/test_options.py checks
both ways):
  player           a setting the installer asks about (the variable, when set, still wins over the ini)
  troubleshooting  a setting offered under "something is wrong"; leave off otherwise
  developer        for work on the port: listed by name in docs/env-vars.md, never offered
  internal         set by the game for itself
There is no "no audio" option on purpose (owner: a rhythm game is played by ear); HM_NO_AUDIO stays a developer
variable.

  python3 -m installer.options            the generated docs/env-vars.md on stdout
"""

import os
import re
import shutil
import subprocess

INI = 'hylian-melodies.ini'


class Setting:
    """One key of hylian-melodies.ini. kind: 'bool', 'gpu' ('auto' or a device number) or 'seconds'.
    trouble: the value that turns a troubleshooting setting on."""

    def __init__(self, key, group, title, text, kind='bool', default=False, trouble=None, env=None):
        self.key, self.group, self.title, self.text = key, group, title, text
        self.kind, self.default, self.trouble, self.env = kind, default, trouble, env

    def check(self, value):
        """-> None when value is one this key takes, else the reason."""
        if self.kind == 'bool':
            ok = isinstance(value, bool)
        elif self.kind == 'gpu':
            ok = value == 'auto' or (isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 100)
        else:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 3600
        return None if ok else f'{self.key}: {value!r} is not a value it takes (for example {self.trouble if self.trouble is not None else self.default!r})'

    def text_of(self, value):
        if self.kind == 'bool':
            return '1' if value else '0'
        if self.kind == 'seconds':
            return f'{value:g}'
        return str(value)

    def parse(self, text):
        """The ini's text -> a value, or the default when it does not parse (as the game does)."""
        try:
            v = float(text.split()[0])
        except (ValueError, IndexError):
            return self.default
        if self.kind == 'bool':
            return v != 0
        if self.kind == 'gpu':
            return int(v) if v >= 0 else 'auto'
        return v if v > 0 else 0


SETTINGS = [
    Setting('fullscreen', 'player', 'Start in fullscreen',
            "Borderless, at the desktop's resolution. F11 or Alt+Enter switches while playing, and the in-game menu "
            '(F1) has the same setting.'),
    Setting('gpu', 'player', 'Graphics card',
            'Which graphics card draws the game, on a computer with more than one. Left on auto, the game takes the '
            'separate (faster) card when there is one. The number is the one in the log lines "[vk] gpu N: ...".',
            kind='gpu', default='auto', env='HM_GPU'),
    Setting('frame_pacing', 'troubleshooting', 'Turn off frame pacing',
            "Lets the game run on its own limiter (about 61 pictures a second) instead of the console's steady 60. "
            'Try it if the picture stutters evenly; the beat may then drift against the picture. Also in the '
            'in-game menu.', default=True, trouble=False, env='HM_FRAME_PACING'),
    Setting('shader_cache', 'troubleshooting', 'Rebuild the shaders at every start',
            'Ignores the saved shader cache. Try it once if the picture is wrong after a graphics driver update; '
            'starting takes longer.', default=True, trouble=False, env='HM_VK_NO_SPIRV_CACHE'),
    Setting('vk_validation', 'troubleshooting', 'Check graphics calls (Vulkan validation)',
            "Writes the graphics driver's complaints to the log, for a bug report. Needs the Vulkan validation "
            'layers installed; slower.', trouble=True, env='HM_VK_VALIDATION'),
    Setting('log_input', 'troubleshooting', 'Log controller and keyboard input',
            'Writes which buttons the game receives to the log, to find out why a controller or key does nothing.',
            trouble=True, env='HM_LOG_INPUT'),
    Setting('audio_stats', 'troubleshooting', 'Log audio timing',
            'Writes a line about the sound output every 10 seconds (rate, gaps, queue), for crackling or drifting '
            'sound.', kind='seconds', default=0, trouble=10, env='HM_AUDIO_STATS'),
]
BY_KEY = {s.key: s for s in SETTINGS}
INTERNAL = {
    'HM_LOG_APPEND': 'set when the game restarts itself: the new process appends to the same log',
    'HM_REEXEC': 'counts those restarts (the address range the game needs was taken)',
}
DEVELOPER = {
    'kernel, loader, files': '''
        HM_DEBUG_CV_LATE_WAIT HM_DISPLAY_W HM_DUMP_AT HM_FNPROF HM_FNPROF_BT HM_FNPROF_OUT HM_GAME_DIR HM_HANG_DUMP
        HM_HEADLESS HM_HEADLESS_SECONDS HM_HLE_SKIP HM_KTRACE HM_LOG_HEAPS HM_PROF_SVC HM_RUN_SECONDS HM_SAVE_DIR
        HM_SOFT_WRITE_TRACKING HM_TICK_SCALE HM_TRACE_SVC HM_UNIT_HEAP_SCALE HM_VSYNC_BT HM_WRITE_TRACKING''',
    'movies': 'HM_LOG_MOVIE HM_MOVIE_CPU_CONVERT HM_MOVIE_EOS_CODE HM_MOVIE_NO_FORMAT_EVENT HM_NO_MOVIE_AUDIO',
    'audio': 'HM_AUDIO_GAIN HM_AUDIO_LOG HM_AUDIO_PERIOD HM_AUDIO_QUEUE_MS HM_AUDOUT_WAV HM_NO_AUDIO',
    'input and menu': 'HM_DEBUG_KEYS HM_INPUT_SCRIPT HM_MENU_FONT HM_MENU_TAB',
    'NVN front end, pacing, shader preparation': '''
        HM_DYN_NO_GPU HM_DYN_START HM_DYN_TEST HM_KEEP_DISCARD HM_LOG_BINDS HM_LOG_DYNRES HM_LOG_INTERVAL
        HM_LOG_PACE HM_LOG_PACKAGED HM_LOG_SYNC HM_LOG_TEXELS HM_PACE HM_RECORD_KEYS HM_RENDER_THREAD
        HM_RQ_STALL_AT HM_RQ_START_DELAY_MS HM_RQ_TRACE HM_SCALE HM_SHADER_LIST HM_SHADER_PREP HM_SHADER_SEEN
        HM_SLOW_FRAME_MS HM_SPIKE_EVERY HM_SPIKE_FROM HM_SPIKE_IDLE HM_SPIKE_MS HM_SPIKE_UNTIL HM_SYNC_ALL
        HM_SYNC_FLUSH HM_TEX_FASTHASH HM_TRACE_COUNT''',
    'Vulkan renderer and window': '''
        HM_AO_SCALED HM_BC5_UNORM HM_BRX_ALL_LABELS HM_CHUNK_PASSES HM_COPY_TRACE HM_DEBUG_DATA HM_DEBUG_FRAME
        HM_DEBUG_FRAMES HM_DEPTH_UP_NEAREST HM_DUMP_3D HM_DYNRES_COUNT_PRESENT HM_EXIT_AFTER_SHOT HM_FENCE_FLUSH
        HM_FPS_INTERVAL HM_GPUPROF_AT HM_GPU_OVERLAP HM_HIDDEN HM_KEEP_TARGETS HM_LOD_MIN HM_LOG_CLEARS
        HM_LOG_COUNTER HM_LOG_CS_SBUF HM_LOG_FSHASH HM_LOG_GFAST HM_LOG_GMEM_SBUF HM_LOG_HITCH_MS HM_LOG_SKIPS
        HM_MENU_AT HM_NEW_TARGET_FILL HM_NO_DEPTH_BIAS HM_NO_DEPTH_TEST HM_NO_DISCARD HM_NO_FEEDBACK
        HM_NO_FRAME_CLEAR HM_NO_SCALE HM_NO_SHADOW HM_NO_SNAPSHOT_REUSE HM_NO_USER_INPUT HM_OVERLAP_SNAP
        HM_OVERLAP_WATCH HM_PREP_CHECK HM_SAMPLER_TEST HM_SAVE_MSL HM_SCREENSHOT_EVERY HM_SCREENSHOT_FROM
        HM_SHADOW_SLOT_LOG HM_SHOT_AT HM_SIM_SLOW_FRAME_MS HM_SKIP_CS HM_SKIP_FSHASH HM_SLOW_FRAME_UNTIL
        HM_SYNC_SHADERS HM_SYNC_SUBMIT HM_TEST_COUNTER_DELAY_MS HM_TEX_FULLHASH HM_VK_COPY_OPT HM_VK_COPY_VERTICES
        HM_VK_COUNTER HM_VK_D24 HM_VK_DEPTH_BLIT_VIA_COLOR HM_VK_DEVLOST_TRACE HM_VK_DYN_VERTEX HM_VK_EQUAL_TOL
        HM_VK_EXACT_H2F HM_VK_FLIP_WINDING HM_VK_GMEM_CHUNK_MB HM_VK_GMEM_DIRECT HM_VK_GMEM_FAST
        HM_VK_GMEM_FS_MISS HM_VK_GMEM_LAZY HM_VK_GPL_PROBE HM_VK_GPU_TIMER HM_VK_HEAP_DMABUF HM_VK_HEAP_PLACED
        HM_VK_LEAN_USAGE HM_VK_LOG_PASSES HM_VK_NO_CBUF_LEAN HM_VK_NO_GMEM HM_VK_NO_KEY_MEMO HM_VK_NO_SCAN_ONCE
        HM_VK_NO_SET_BATCH HM_VK_NO_SET_RECYCLE HM_VK_NO_SET_REUSE HM_VK_NO_TEX_MEMO HM_VK_OPT
        HM_VK_OVERLAY_DIRECT HM_VK_PASS_RESTART HM_VK_PLACEHOLDER_COLOR HM_VK_PRESENT HM_VK_PROF HM_VK_RECORDER
        HM_VK_RECORDER_MB HM_VK_RECORDER_WAIT_PIPES HM_VK_RING_BAR HM_VK_RING_SYSMEM HM_VK_SIM_HEAP_OOM
        HM_VK_STATE_FILTER HM_VK_TEX_WATCH HM_VK_TRACE HM_VK_VALIDATION_STOP HM_VK_VCACHE HM_WINDOW
        HM_WINDOW_SHOT''',
}
# Read by the launcher or the build, not by the game: named so nobody takes them for settings.
OUTSIDE = {
    'HM_GAME_DIR': 'the launcher too: the installed game instead of /opt/hylian-melodies (the AppImage, tests)',
    'HM_SUPPORT_DIR': 'the launcher: the support files instead of /usr/share/hylian-melodies-recomp (the AppImage, tests)',
}


def offered(group):
    return [o for o in SETTINGS if o.group == group]


def groups():
    """-> {name: group} for every variable the game reads."""
    g = {o.env: o.group for o in SETTINGS if o.env}
    g.update({n: 'internal' for n in INTERNAL})
    for names in DEVELOPER.values():
        g.update({n: 'developer' for n in names.split()})
    return g


def check_settings(values):
    """-> [text]: everything wrong with a plan's settings ({key: value}; a key left out is not touched)."""
    if not isinstance(values, dict):
        return ['settings must be an object of key: value']
    bad = []
    for key, value in values.items():
        o = BY_KEY.get(key)
        if not o:
            known = groups().get(key)
            bad.append(f'{key} is not a setting the installer writes' + (f' (a {known} environment variable)' if known
                       else '') + '; they are: ' + ', '.join(BY_KEY))
        elif o.check(value):
            bad.append(o.check(value))
    return bad


def _line_is(line, key):
    """2 = "key = ...", 1 = "# key = ..." (the default file's example), 0 = neither (as runtime/settings.c)."""
    m = re.match(r'\s*(#\s*)?' + re.escape(key) + r'\s*=', line)
    return 0 if not m else (1 if m.group(1) else 2)


def read_settings(path):
    """-> {key: value} of the keys the installer knows that the file sets (uncommented); {} without a file."""
    out = {}
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        for o in SETTINGS:
            if o.key not in out and _line_is(line, o.key) == 2:
                out[o.key] = o.parse(line.split('=', 1)[1].split('#')[0])
    return out


def current(path):
    """-> {key: value} for every setting: what the file says, else the game's default."""
    have = read_settings(path)
    return {o.key: have.get(o.key, o.default) for o in SETTINGS}


def write_settings(path, values, default_file=None):
    """Sets values ({key: value}) in the player's hylian-melodies.ini and keeps every other line. A missing file
    starts as default_file (the package's commented default, as the launcher would copy it). A key at its default
    is commented out again; a key with no line at all goes under "# --- set by the installer". -> True if written."""
    lines = []
    for src in (path, default_file):
        if src and os.path.isfile(src):
            with open(src) as f:
                lines = f.read().splitlines()
            break
    tail = []
    for key, value in values.items():
        o = BY_KEY[key]
        at = best = 0
        for i, line in enumerate(lines):
            kind = _line_is(line, key)
            if kind > best:
                best, at = kind, i
            if kind == 2:
                break
        if best:
            rest = lines[at].split('=', 1)[1]
            comment = '  #' + rest.split('#', 1)[1] if '#' in rest else ''  # (a trailing comment is kept)
            lines[at] = ('# ' if value == o.default else '') + f'{key} = {o.text_of(value)}' + comment
        elif value != o.default:
            tail.append(f'{key} = {o.text_of(value)}')
    if tail:
        mark = '# --- set by the installer'
        if mark in lines:
            i = lines.index(mark) + 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('# ---'):
                i += 1
            lines[i:i] = tail
        else:
            lines += ['', mark] + tail
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.new'
    with open(tmp, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)
    return True


def gpus(run=subprocess.run):
    """-> [(index, name)] of this computer's Vulkan devices in the order the game numbers them, [] when unknown."""
    if not shutil.which('vulkaninfo'):
        return []
    try:
        r = run(['vulkaninfo', '--summary'], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    found, cur = [], None
    for line in r.stdout.splitlines():
        m = re.match(r'\s*GPU(\d+):', line)
        if m:
            cur = int(m.group(1))
        m = re.match(r'\s*deviceName\s*=\s*(.+)', line)
        if m and cur is not None:
            found.append((cur, m.group(1).strip()))
            cur = None
    return found


def env_doc():
    """docs/env-vars.md (generated; tests/test_options.py keeps it current)."""
    out = ['# Environment variables', '',
           'Generated by `python3 -m installer.options > docs/env-vars.md` from `installer/options.py`; a test',
           'checks this list against every `getenv`/`ENV("HM_...")` in `runtime/`. Edit the registry, not this file.', '',
           'The installer writes the player\'s choices into the game\'s settings file,',
           '`~/.local/share/hylian-melodies/hylian-melodies.ini` (the same file the in-game menu saves). Each',
           'setting\'s variable, when set in the environment, wins over the file.', '',
           '## Settings the installer asks about', '']
    row = lambda o: (f'- **{o.title}** (`{o.key} = {o.text_of(o.trouble if o.trouble is not None else o.default)}`'  # noqa: E731
                     + (f'; `{o.env}`' if o.env else '') + f'): {o.text}')
    out += [row(o) for o in offered('player')]
    out += ['', '## Troubleshooting (off unless something is wrong)', '']
    out += [row(o) for o in offered('troubleshooting')]
    out += ['', '## Developer variables', '',
            'For work on the port: test runs, traces, switches for parts of the renderer. Not offered by the',
            'installer and not stable; what each does is in the code next to its `getenv`.', '']
    for area, names in DEVELOPER.items():
        out.append(f'- {area}: ' + ', '.join(f'`{n}`' for n in names.split()))
    out += ['', '## Set by the game for itself', '']
    out += [f'- `{n}`: {t}' for n, t in INTERNAL.items()]
    out += ['', '## Read outside the game', '']
    out += [f'- `{n}`: {t}' for n, t in OUTSIDE.items()]
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    print(env_doc(), end='')
