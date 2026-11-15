"""The player-facing installer: asks what is needed, shows what will happen, runs it, says how to install.

  python3 -m installer.tui [--answers FILE.json] [--plain] [--root REPO]

Full-screen curses screens on a terminal of 80x24 or more (installer/screens.py), else (or with --plain, or with
TERM=dumb) the same questions as plain numbered prompts; both run the same Plan and flow. With --answers nothing
is asked: the file holds the plan's fields (base, keys, and optionally update, output, march, keep_cache, work,
out, settings = {"fullscreen": true, "gpu": 1}: keys of the game's ini, installer/options.py) and the exit status
says how it went: 0 built, 1 failed, 2 the plan is wrong, 3 packages are missing (the
command to install them is printed). The installer never runs as root: at the end it offers to run the
package manager's install command (sudo asks for the password on the terminal), or prints it; --answers only prints it.
"""

import argparse
import json
import os
import shlex
import subprocess
import sys

from . import flow as F
from . import options as O
from . import plan as P

WELCOME = '''Hylian Melodies installer

This builds a native Linux version of your own copy of Cadence of Hyrule on this computer. It needs your
cartridge dump (.xci) and your console's keys (prod.keys). Both are only read where they are: nothing is copied,
uploaded or sent anywhere. The result contains the game: it is for you alone, never share it.
'''

FILE_HINT = ('Press Ctrl+O (or F2) to choose the file in a file window, or type the path (Tab completes it), or drag '
             'the file onto this terminal.')


def run_command(argv):
    """Runs a command on this terminal (the package manager: sudo asks for the password there). -> exit status"""
    try:
        return subprocess.run(argv).returncode
    except OSError as e:
        print(f'{argv[0]}: {e.strerror}')
        return 127


class Console:
    """Questions on a terminal. Tests pass an object with the same two methods."""

    def __init__(self, stdin=None, stdout=None):
        self.stdin, self.stdout = stdin or sys.stdin, stdout or sys.stdout

    def say(self, text=''):
        self.stdout.write(text + '\n')
        self.stdout.flush()

    def ask(self, question, default=''):
        self.stdout.write(f'{question} [{default}]: ' if default else f'{question}: ')
        self.stdout.flush()
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.strip() or default


def section(io, title):
    """A new screen (installer/screens.py); a blank line on the plain console."""
    if hasattr(io, 'section'):
        io.section(title)
    else:
        io.say()


def pause(io, again, stop='Quit'):
    """-> True to go on (try again), False to stop."""
    return choose(io, 'What now?', [('again', again), ('q', stop)], 'again') == 'again'


def choose(io, title, options, default):
    """options: [(key, text)] -> the chosen key. Enter takes the default; a number or the key itself picks."""
    if hasattr(io, 'choose'):
        return io.choose(title, options, default)
    io.say(title)
    for i, (key, text) in enumerate(options, 1):
        io.say(f'  {i}. {text}' + ('  (default)' if key == default else ''))
    keys = [k for k, _ in options]
    while True:
        a = io.ask('Choice', str(keys.index(default) + 1))
        if a in keys:
            return a
        if a.isdigit() and 1 <= int(a) <= len(keys):
            return keys[int(a) - 1]
        io.say('  Please answer with one of the numbers.')


def ask_file(io, question, default, field, plan):
    while True:
        a = io.ask_path(question, default, field) if hasattr(io, 'ask_path') else io.ask(question, default)
        setattr(plan, field, P.clean_path(a) if a else '')
        bad = [t for f, t in P.validate(plan) if f == field]
        if not bad:
            return
        io.say('  ' + bad[0])


class Progress:
    """Events as lines: a heading per step, progress every 10 %."""

    def __init__(self, io):
        self.io, self.shown = io, {}

    def __call__(self, ev):
        if hasattr(self.io, 'progress'):
            return self.io.progress(ev)
        kind = ev.get('event')
        if kind == 'step':
            self.io.say(f"==> {ev.get('msg') or ev.get('step')}")
        elif kind == 'progress':
            pct = ev.get('pct', 0) // 10 * 10
            if pct and pct < 100 and self.shown.get(ev.get('step')) != pct:
                self.shown[ev.get('step')] = pct
                self.io.say(f'    {pct}%')
        elif kind in ('info', 'warning', 'error'):
            self.io.say(f"    {'' if kind == 'info' else kind + ': '}{ev.get('text') or ev.get('msg')}")


def show_needs(io, result):
    io.say('This system lacks some things the build needs:')
    for n in result['needs']:
        io.say(f"  - {n['what']}")
    for t in result['notes']:
        io.say(t)
    if result['command']:
        io.say('Run this in another terminal:')
        io.say('  ' + result['command'])


def ask_settings(io, cur, gpus):
    """The game settings the installer asks about (installer/options.py): fullscreen, the graphics card when there
    are several, and the troubleshooting settings behind one question. cur: {key: value} now (the player's ini).
    -> {key: value} for every setting"""
    new = dict(cur)
    o = O.BY_KEY['fullscreen']
    io.say(o.title + ': ' + o.text)
    new['fullscreen'] = choose(io, 'Start the game in fullscreen?', [('no', 'No, in a window'), ('yes', 'Yes')],
                               'yes' if cur['fullscreen'] else 'no') == 'yes'
    cards = gpus()
    if len(cards) > 1:
        io.say(O.BY_KEY['gpu'].text)
        pick = [('auto', 'Let the game choose (recommended)')] + [(str(i), name) for i, name in cards]
        a = choose(io, 'Which graphics card should draw the game?', pick,
                   str(cur['gpu']) if str(cur['gpu']) in dict(pick) else 'auto')
        new['gpu'] = 'auto' if a == 'auto' else int(a)
    trouble = O.offered('troubleshooting')
    on = [o.title for o in trouble if cur[o.key] != o.default]
    io.say('Troubleshooting settings are for when something is wrong; a normal game needs none.'
           + (' On now: ' + ', '.join(on) + '.' if on else ''))
    a = choose(io, 'Troubleshooting settings?',
               [('keep', 'Leave them as they are' if on else 'None'), ('pick', 'Choose them one by one')]
               + ([('none', 'Turn them all off')] if on else []), 'keep')
    for o in trouble:
        if a == 'none':
            new[o.key] = o.default
        elif a == 'pick':
            io.say(o.text)
            yes = choose(io, o.title + '?', [('no', 'No'), ('yes', 'Yes')],
                         'yes' if cur[o.key] != o.default else 'no') == 'yes'
            new[o.key] = (cur[o.key] if cur[o.key] != o.default else o.trouble) if yes else o.default
    return new


def settings_summary(values):
    parts = ['fullscreen' if values.get('fullscreen') else 'in a window']
    if values.get('gpu', 'auto') != 'auto':
        parts.append(f"graphics card {values['gpu']}")
    parts += [o.title.lower() for o in O.offered('troubleshooting') if values.get(o.key, o.default) != o.default]
    return ', '.join(parts)


def change_settings(io, plan, repo, gpus):
    """Settings of something already built: asked and written to the player's ini; no rebuild."""
    values = ask_settings(io, O.current(plan.settings_file), gpus)
    O.write_settings(plan.settings_file, values, F.default_settings(repo))
    io.say('Saved in ' + plan.settings_file + ': the game starts ' + settings_summary(values)
           + '. Nothing needs rebuilding; the in-game menu (F1) changes the same file.')


def existing(io, plan, repo, gpus):
    """What to do about installs the manifest lists. -> an entry to build again from, or None for a fresh start"""
    m = P.load_manifest(plan.manifest)
    if not m['installs']:
        return None
    section(io, 'Your build')
    io.say('Already built on this computer:')
    for e in m['installs']:
        io.say(f"  - version {e.get('version')}, {e.get('built', '?')}: {e.get('package', {}).get('file', '?')}")
    e = m['installs'][-1]
    a = choose(io, 'What now?', [('again', 'Build it again (after an update, or with other build options)'),
                                  ('settings', 'Change the game settings (fullscreen, graphics card, '
                                               'troubleshooting); no rebuild'),
                                  ('remove', 'Remove it'), ('fresh', 'Start over with other files')], 'again')
    if a == 'settings':
        change_settings(io, plan, repo, gpus)
        return 'quit'
    if a == 'remove':
        io.say('The package manager removes it (your saves and settings stay):')
        io.say('  ' + e.get('package', {}).get('remove', ''))
        if choose(io, 'Forget this build here once you have run that?', [('yes', 'Yes'), ('no', 'No')], 'yes') == 'yes':
            P.forget_install(plan.manifest, e['id'])
        return 'quit'
    return e if a == 'again' else None


def ask_build_folder(io, plan, env=None, free_gib=None):
    """Where the build happens and the package is written: the cache folder, or another folder (with room)."""
    free = free_gib or P._free_gib
    default = P.cache_home(env)
    io.say(f'The build needs about {P.NEED_WORK_GIB} GiB of free space while it runs and {P.NEED_OUT_GIB} GiB for '
           'the package. Another folder (on a bigger disk, say) gets a hylian-melodies folder inside it.')
    cur = P.build_folder(plan, env)
    while True:
        def label(path):
            try:
                return f'{path}  ({free(path):.0f} GiB free)'
            except OSError:
                return f'{path}  (free space unknown)'
        opts = [('default', label(default))] + ([('cur', label(cur))] if cur != default else []) + \
               [('other', 'Another folder...')]
        a = choose(io, 'Where should the build happen?', opts, 'cur' if cur != default else 'default')
        before = plan.work, plan.out
        if a == 'default':
            P.place_build(plan, default, env)
        elif a == 'other':
            q = 'The folder to build in'
            got = io.ask_path(q, cur, 'folder') if hasattr(io, 'ask_path') else io.ask(q, cur)
            folder = os.path.expanduser(P.clean_path(got)) if got else ''
            if not folder or not os.path.isdir(folder):
                io.say(f'  Not a folder: {folder or "(nothing given)"}')
                continue
            P.place_build(plan, folder, env)
        bad = [t for f, t in P.validate(plan, free_gib=free) if f in ('work', 'out')]
        if not bad:
            return
        for t in bad:
            io.say('  ' + t)
        plan.work, plan.out = before  # (asked again with the folder it was, not the one refused)


def interactive(io, plan, repo, make_flow, gpus=O.gpus, run=run_command, env=None):
    io.say(WELCOME.split('\n', 2)[2] if hasattr(io, 'section') else WELCOME)  # (screens: the title is in the bar)
    if hasattr(io, 'section') and not P.load_manifest(plan.manifest)['installs']:  # (screens: the welcome alone first)
        if choose(io, 'Ready?', [('go', 'Go on'), ('q', 'Quit')], 'go') != 'go':
            return 0
    prev = existing(io, plan, repo, gpus)
    if prev == 'quit':
        return 0
    if prev:
        plan.base, plan.keys = prev['inputs']['base']['path'], prev['inputs']['keys']['path']
        plan.update = prev['inputs'].get('update', {}).get('path', '')
        plan.march = prev.get('build', {}).get('march', plan.march)
        plan.keep_cache = bool(prev.get('build', {}).get('keep_cache', False))
    flow = make_flow(plan, repo, Progress(io))
    section(io, 'System check')
    while True:  # 1. what the system lacks
        need = flow.check_system()
        if not need:
            break
        show_needs(io, need)
        if not pause(io, 'Check again (after running that command)'):
            return 3
    section(io, 'Your files')  # 2. the files, checked at once
    while True:
        io.say('The build needs two files of yours: the cartridge dump and the keys of the console it came from. '
               'They are read where they are; nothing is copied.')
        if hasattr(io, 'ask_path'):
            io.say(FILE_HINT)
        ask_file(io, 'Your cartridge dump (.xci); type the path or drop the file here', plan.base, 'base', plan)
        io.say("The keys file (usually prod.keys) was dumped from your own console together with the cartridge.")
        if hasattr(io, 'ask_path'):
            io.say(FILE_HINT)
        ask_file(io, "Your console's keys (prod.keys)", plan.keys, 'keys', plan)
        try:
            flow.build_tools()
            flow.check_inputs()
            break
        except F.FlowError as e:
            io.say('  ' + flow.error(e)['text'])
            if not pause(io, 'Choose the files again'):
                return 1
    section(io, 'Build options')  # 3. options
    levels = [(k, t) for k, t in P.MARCH.items() if k != 'v3' or P.cpu_has_v3()]
    plan.march = choose(io, 'Which CPUs should the game run on?', levels,
                        plan.march if plan.march in dict(levels) else 'v2')
    plan.keep_cache = choose(io, 'Keep the build files (several GiB) so a later rebuild is faster?',
                             [('no', 'No'), ('yes', 'Yes')], 'yes' if plan.keep_cache else 'no') == 'yes'
    ask_build_folder(io, plan, env)
    section(io, 'Game settings')
    plan.settings = ask_settings(io, O.current(plan.settings_file), gpus)
    bad = P.validate(plan, fmt=flow.format)
    if bad:
        for _, t in bad:
            io.say('  ' + t)
        return 2
    section(io, 'Summary')  # 4. summary
    io.say('Ready to build:')
    io.say(f'  cartridge dump   {plan.base}')
    io.say(f'  keys             {plan.keys}')
    io.say(f'  result           a {flow.format} package in {plan.out}')
    io.say(f'  CPU level        {plan.march}')
    io.say(f'  game starts      {settings_summary(plan.settings)}')
    io.say(f'  work folder      {plan.work}' + ('  (kept afterwards)' if plan.keep_cache else '  (emptied afterwards)'))
    for what, path, need, free in P.space(plan):
        io.say(f'  disk space       about {need} GiB {what}, ' + (f'{free:.0f} GiB free' if free is not None else
                                                                   'free space unknown'))
    io.say('  This takes a few minutes, mostly compiling.')
    if choose(io, 'Start?', [('yes', 'Yes'), ('no', 'No')], 'yes') != 'yes':
        return 0
    section(io, 'Building')
    try:
        flow.setup()
        return finish(io, flow.record(flow.make_package()), run, plan, repo, env)
    except F.FlowError as e:
        return finish(io, flow.error(e))


def finish(io, result, run=None, plan=None, repo=None, env=None):
    """The end: the package and how to install it, then what stays on this computer. run: offer to install it now
    with that runner (the questions; an answers file only prints the command)."""
    if result['result'] == 'ok':
        section(io, 'Done')
        io.say('Done. The package: ' + result['file'])
        if not (run and install_now(io, result, run)):
            io.say('Install it with:')
            io.say('  ' + result['install'])
            io.say("Then start it from the menu or with 'hylian-melodies'. To remove it later: " + result['remove'])
        if plan:
            show_leftovers(io, plan, repo, result['file'], env)
        return 0
    if result['result'] == 'deps':
        show_needs(io, result)
        return 3
    section(io, 'It did not work')
    io.say('It did not work: ' + result['text'])
    io.say('The full log: ' + str(result.get('log')))
    return 1


def show_leftovers(io, plan, repo, package, env=None):
    """What stays on this computer besides the installed game, with sizes, so the player can delete what they wish."""
    items = P.leftovers(plan, repo, package)
    if not items:
        return
    io.say()
    io.say('Files this left on your computer (the installed game itself is managed by the package manager):')
    for path, size, what, removable in items:
        io.say(f'  {P.size_text(size):>10}  {path}')
        io.say(f'              {what}' + ('  [can be deleted]' if removable else ''))
    gone = [path for path, _, _, removable in items if removable]
    if gone:
        io.say('To delete the ones marked "can be deleted" (a later build makes again what it needs):')
        io.say('  rm -rf ' + ' '.join(shlex.quote(p) for p in gone))


def install_now(io, result, run):
    """Asks whether to install the package now; if so, runs the package manager on this terminal (sudo asks for
    the password there; the installer itself never runs as root). -> True when it was installed."""
    io.say('Installing it needs administrator rights: the package manager runs with sudo and asks for your password.')
    a = choose(io, 'Install it now?', [('yes', 'Yes, install it now: ' + result['install']),
                                       ('no', 'No, just show me the command')], 'yes')
    if a != 'yes':
        return False
    argv = shlex.split(result['install'])
    rc = io.run_outside(argv, run) if hasattr(io, 'run_outside') else run(argv)
    section(io, 'Done')
    if rc == 0:
        size = P.size_text(P.du(result['file']))
        if choose(io, f'Installed. Delete the package file now? It is {size} and no longer needed.',
                  [('yes', 'Yes, delete it'), ('no', 'No, keep it')], 'yes') == 'yes':
            try:
                os.remove(result['file'])
            except OSError as e:
                io.say(f'  Could not delete it: {e.strerror}')
        section(io, 'Done')
        io.say('Installed. Start it from the menu or with "hylian-melodies".')
        io.say('To remove it later: ' + result['remove'])
        return True
    io.say(f'The package manager stopped (exit status {rc}); nothing may have been installed. The package is kept:')
    io.say('  ' + result['file'])
    return False


def from_answers(io, path, repo, make_flow, env=None):
    try:
        with open(path) as f:
            answers = json.load(f)
        if not isinstance(answers, dict):
            raise ValueError('the answers file must hold one JSON object')
        plan = P.Plan(env, **answers)
    except (OSError, ValueError) as e:
        io.say(f'Cannot use the answers file {path}: {e}')
        return 2
    flow = make_flow(plan, repo, Progress(io))
    bad = P.validate(plan, fmt=flow.format)
    if bad:
        for field, t in bad:
            io.say(f'{field}: {t}')
        return 2
    return finish(io, F.run(plan, repo, flow.emit, flow=flow), None, plan, repo, env)


def screens_usable():
    """-> None when the full-screen interface can run here, else why not (then the plain prompts are used)."""
    try:
        from . import screens
    except ImportError as e:  # (a Python without curses)
        return str(e)
    return screens.usable(sys.stdin, sys.stdout, os.environ)


def run_screens(a, env, make_flow, gpus, run):
    """The questions as curses screens (installer/screens.py); the last screen's text stays on the terminal."""
    import curses
    import locale
    from . import screens
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')  # (Esc answers at once instead of after a second)
    box = {}

    def body(scr):
        io = box['io'] = screens.CursesIO(scr)
        if a.source_note:
            io.say('Source: ' + a.source_note)
            io.say()
        return interactive(io, P.Plan(env), a.root, make_flow, gpus, run, env)
    rc = curses.wrapper(body)
    text = box['io'].transcript()
    if text:
        print(text)
    return rc


def main(argv=None, io=None, make_flow=F.Flow, env=None, gpus=O.gpus, run=run_command):
    ap = argparse.ArgumentParser(prog='python -m installer.tui', description=__doc__.splitlines()[0])
    ap.add_argument('--answers', help='a JSON file with the plan: nothing is asked')
    ap.add_argument('--source-note', default='', help='where this copy came from (install.sh): shown first')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='repository root')
    ap.add_argument('--plain', action='store_true', help='numbered prompts instead of the full-screen interface')
    a = ap.parse_args(argv)
    why_not = 'asked for' if (a.plain or io or a.answers) else screens_usable()
    io = io or Console()
    if a.source_note and why_not:
        io.say('Source: ' + a.source_note)
    if a.answers:
        return from_answers(io, a.answers, a.root, make_flow, env)
    try:
        if not why_not:
            return run_screens(a, env, make_flow, gpus, run)
        return interactive(io, P.Plan(env), a.root, make_flow, gpus, run, env)
    except (EOFError, KeyboardInterrupt):
        io.say()
        io.say('Stopped. Nothing was installed.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
