"""The player-facing installer: asks what is needed, shows what will happen, runs it, says how to install.

  python3 -m installer.tui [--answers FILE.json] [--root REPO]

Plain numbered prompts for now (the curses screens come on top of the same Plan and flow). With --answers nothing
is asked: the file holds the plan's fields (base, keys, and optionally update, output, march, keep_cache, work,
out) and the exit status says how it went: 0 built, 1 failed, 2 the plan is wrong, 3 packages are missing (the
command to install them is printed). Nothing is installed from here and nothing runs as root.
"""

import argparse
import json
import os
import sys

from . import flow as F
from . import plan as P

WELCOME = '''Hylian Melodies installer

This builds a native Linux version of your own copy of Cadence of Hyrule on this computer. It needs your
cartridge dump (.xci) and your console's keys (prod.keys). Both are only read where they are: nothing is copied,
uploaded or sent anywhere. The result contains the game: it is for you alone, never share it.
'''


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


def choose(io, title, options, default):
    """options: [(key, text)] -> the chosen key. Enter takes the default; a number or the key itself picks."""
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
        a = io.ask(question, default)
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


def existing(io, plan):
    """What to do about installs the manifest lists. -> an entry to build again from, or None for a fresh start"""
    m = P.load_manifest(plan.manifest)
    if not m['installs']:
        return None
    io.say('Already built on this computer:')
    for e in m['installs']:
        io.say(f"  - version {e.get('version')}, {e.get('built', '?')}: {e.get('package', {}).get('file', '?')}")
    e = m['installs'][-1]
    a = choose(io, 'What now?', [('again', 'Build it again (after an update, or with other options)'),
                                  ('remove', 'Remove it'), ('fresh', 'Start over with other files')], 'again')
    if a == 'remove':
        io.say('The package manager removes it (your saves and settings stay):')
        io.say('  ' + e.get('package', {}).get('remove', ''))
        if choose(io, 'Forget this build here once you have run that?', [('yes', 'Yes'), ('no', 'No')], 'yes') == 'yes':
            P.forget_install(plan.manifest, e['id'])
        return 'quit'
    return e if a == 'again' else None


def interactive(io, plan, repo, make_flow):
    io.say(WELCOME)
    prev = existing(io, plan)
    if prev == 'quit':
        return 0
    if prev:
        plan.base, plan.keys = prev['inputs']['base']['path'], prev['inputs']['keys']['path']
        plan.update = prev['inputs'].get('update', {}).get('path', '')
        plan.march = prev.get('build', {}).get('march', plan.march)
        plan.keep_cache = bool(prev.get('build', {}).get('keep_cache', False))
    flow = make_flow(plan, repo, Progress(io))
    while True:  # 1. what the system lacks
        need = flow.check_system()
        if not need:
            break
        show_needs(io, need)
        if io.ask('Press Enter to check again, or q to quit', '') == 'q':
            return 3
    io.say()  # 2. the files, checked at once
    while True:
        ask_file(io, 'Your cartridge dump (.xci); type the path or drop the file here', plan.base, 'base', plan)
        ask_file(io, "Your console's keys (prod.keys)", plan.keys, 'keys', plan)
        try:
            flow.build_tools()
            flow.check_inputs()
            break
        except F.FlowError as e:
            io.say('  ' + flow.error(e)['text'])
            if io.ask('Press Enter to choose the files again, or q to quit', '') == 'q':
                return 1
    io.say()  # 3. options
    levels = [(k, t) for k, t in P.MARCH.items() if k != 'v3' or P.cpu_has_v3()]
    plan.march = choose(io, 'Which CPUs should the game run on?', levels,
                        plan.march if plan.march in dict(levels) else 'v2')
    plan.keep_cache = choose(io, 'Keep the build files (several GiB) so a later rebuild is faster?',
                             [('no', 'No'), ('yes', 'Yes')], 'yes' if plan.keep_cache else 'no') == 'yes'
    bad = P.validate(plan, fmt=flow.format)
    if bad:
        for _, t in bad:
            io.say('  ' + t)
        return 2
    io.say()  # 4. summary
    io.say('Ready to build:')
    io.say(f'  cartridge dump   {plan.base}')
    io.say(f'  keys             {plan.keys}')
    io.say(f'  result           a {flow.format} package in {plan.out}')
    io.say(f'  CPU level        {plan.march}')
    io.say(f'  work folder      {plan.work}' + ('  (kept afterwards)' if plan.keep_cache else '  (emptied afterwards)'))
    io.say('  This takes a few minutes, mostly compiling.')
    if choose(io, 'Start?', [('yes', 'Yes'), ('no', 'No')], 'yes') != 'yes':
        return 0
    try:
        flow.setup()
        return finish(io, flow.record(flow.make_package()))
    except F.FlowError as e:
        return finish(io, flow.error(e))


def finish(io, result):
    if result['result'] == 'ok':
        io.say()
        io.say('Done. The package: ' + result['file'])
        io.say('Install it with:')
        io.say('  ' + result['install'])
        io.say("Then start it from the menu or with 'hylian-melodies'. To remove it later: " + result['remove'])
        return 0
    if result['result'] == 'deps':
        show_needs(io, result)
        return 3
    io.say()
    io.say('It did not work: ' + result['text'])
    io.say('The full log: ' + str(result.get('log')))
    return 1


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
    return finish(io, F.run(plan, repo, flow.emit, flow=flow))


def main(argv=None, io=None, make_flow=F.Flow, env=None):
    ap = argparse.ArgumentParser(prog='python -m installer.tui', description=__doc__.splitlines()[0])
    ap.add_argument('--answers', help='a JSON file with the plan: nothing is asked')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='repository root')
    a = ap.parse_args(argv)
    io = io or Console()
    if a.answers:
        return from_answers(io, a.answers, a.root, make_flow, env)
    try:
        return interactive(io, P.Plan(env), a.root, make_flow)
    except (EOFError, KeyboardInterrupt):
        io.say()
        io.say('Stopped. Nothing was installed.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
