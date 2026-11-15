"""The installer's curses screens (stdlib only): the same questions as the plain prompts, one screen each.

CursesIO has the plain console's methods (say, ask) plus section, choose, ask_path and progress, which
installer/tui.py uses when they are there; so the question flow, the plan and its checks are shared and tested
once (tests/test_tui.py), and the screens only draw. What a screen shows: a title bar, the text said since the
last question, the question (a list to move through with the arrow keys, or an edit field), and the keys at the
bottom. The text of the last screen is printed to the terminal when the screens close, so the install command
stays there to copy. docs/installer.md, section 2.

TextField and Browser hold the editing and the folder listing without curses (tests/test_screens.py).
"""

import curses
import locale
import os
import textwrap

from . import picker

MIN_W, MIN_H = 80, 24


def usable(stdin, stdout, env):
    """-> None when the screens can be used here, else why not (the plain prompts are used instead)."""
    term = env.get('TERM', '')
    if not (stdin.isatty() and stdout.isatty()):
        return 'not a terminal'
    if not term or term == 'dumb':
        return 'TERM is ' + (term or 'not set')
    try:
        size = os.get_terminal_size(stdout.fileno())
    except OSError:
        return 'unknown terminal size'
    if size.columns < MIN_W or size.lines < MIN_H:
        return f'the terminal is {size.columns}x{size.lines}; the screens need {MIN_W}x{MIN_H}'
    return None


class Quit(KeyboardInterrupt):
    """The player chose to quit (handled like Ctrl+C: nothing was installed)."""


# ------------------------------------------------------------------ models (no curses)

class TextField:
    def __init__(self, text=''):
        self.text, self.pos = text, len(text)

    def key(self, k):
        """k: a character (str) or a name ('left', 'right', 'home', 'end', 'backspace', 'delete', 'clear')."""
        t, p = self.text, self.pos
        if k == 'left':
            self.pos = max(0, p - 1)
        elif k == 'right':
            self.pos = min(len(t), p + 1)
        elif k == 'home':
            self.pos = 0
        elif k == 'end':
            self.pos = len(t)
        elif k == 'backspace' and p:
            self.text, self.pos = t[:p - 1] + t[p:], p - 1
        elif k == 'delete':
            self.text = t[:p] + t[p + 1:]
        elif k == 'clear':
            self.text, self.pos = '', 0
        elif len(k) == 1 and k.isprintable():
            self.text, self.pos = t[:p] + k + t[p:], p + 1

    def complete(self):
        """Tab: the path before the cursor completed as far as it is unambiguous. -> the candidates' names."""
        before = self.text[:self.pos]
        quote = before[:1] if before[:1] in '\'"' else ''
        path = os.path.expanduser(before[len(quote):])
        folder, stem = os.path.split(path)
        try:
            names = sorted(n for n in os.listdir(folder or '.') if n.startswith(stem)
                           and (stem.startswith('.') or not n.startswith('.')))
        except OSError:
            return []
        if not names:
            return []
        common = os.path.commonprefix(names)
        done = os.path.join(folder, common)
        if len(names) == 1 and os.path.isdir(done):
            done = os.path.join(done, '')
        if before[len(quote):].startswith('~'):
            home = os.path.expanduser('~')
            done = '~' + done[len(home):] if done.startswith(home) else done
        new = quote + done
        self.text, self.pos = new + self.text[self.pos:], len(new)
        return names


class Browser:
    """An in-terminal file list: folders first, files of the wanted kind marked. folders: choose a folder (only
    folders listed, and a first line that picks the one shown)."""

    HERE = '.'  # (the "use this folder" line in folder mode)

    def __init__(self, start, patterns, folders=False):
        self.patterns = [p.lstrip('*').lower() for p in patterns]
        self.folders = folders
        self.hidden = False
        self.sel = 0
        self.go(start if start and os.path.isdir(start) else os.path.expanduser('~'))

    def wanted(self, name):
        return any(name.lower().endswith(p) for p in self.patterns)

    def go(self, folder, select=None):
        self.cwd = os.path.abspath(folder)
        try:
            names = os.listdir(self.cwd)
        except OSError as e:
            self.entries, self.error, self.sel = [('..', True)], f'cannot open: {e.strerror}', 0
            return
        self.error = ''
        names = [n for n in names if self.hidden or not n.startswith('.')]
        dirs = sorted((n for n in names if os.path.isdir(os.path.join(self.cwd, n))), key=str.lower)
        files = sorted((n for n in names if not os.path.isdir(os.path.join(self.cwd, n))),
                       key=lambda n: (not self.wanted(n), n.lower()))
        self.entries = (([(self.HERE, True)] if self.folders else []) + ([('..', True)] if self.cwd != '/' else [])
                        + [(d, True) for d in dirs] + ([] if self.folders else [(f, False) for f in files]))
        self.sel = next((i for i, (n, _) in enumerate(self.entries) if n == select), 0)
        if select is None:  # (the first wanted file, when there is one)
            self.sel = next((i for i, (n, d) in enumerate(self.entries) if not d and self.wanted(n)), 0)

    def move(self, d):
        if self.entries:
            self.sel = max(0, min(len(self.entries) - 1, self.sel + d))

    def up(self):
        if self.cwd != '/':
            old = os.path.basename(self.cwd)
            self.go(os.path.dirname(self.cwd), select=old)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        cur = self.entries[self.sel][0] if self.entries else None
        self.go(self.cwd, select=cur)

    def enter(self):
        """-> the chosen file's path, or None after opening a folder."""
        if not self.entries:
            return None
        name, is_dir = self.entries[self.sel]
        if name == self.HERE and self.folders:
            return self.cwd
        if name == '..':
            self.up()
        elif is_dir:
            self.go(os.path.join(self.cwd, name))
        else:
            return os.path.join(self.cwd, name)
        return None


# ------------------------------------------------------------------ the screens

def reflow(text):
    """One say()'s text -> lines: the lines of a paragraph joined (the plain prompts' text is broken for a narrow
    console), indented lines (commands, lists) and blank lines kept as they are."""
    out = []
    for line in text.split('\n'):
        if out and out[-1].strip() and line.strip() and not line.startswith(' ') and not out[-1].startswith(' '):
            out[-1] += ' ' + line.strip()
        else:
            out.append(line)
    return out


def wrap(lines, width):
    out = []
    for line in lines:
        if not line.strip():
            out.append('')
            continue
        indent = len(line) - len(line.lstrip(' '))
        out += textwrap.wrap(line, width, initial_indent='', subsequent_indent=' ' * (indent + 2 if indent else 0),
                             break_on_hyphens=False, break_long_words=True, drop_whitespace=True) or ['']
    return out


class CursesIO:
    def __init__(self, scr, env=None, desktop_pick=picker.desktop_pick):
        self.scr, self.env, self.desktop_pick = scr, os.environ if env is None else env, desktop_pick
        self.title, self.body, self.steps, self.log_tail = 'Welcome', [], [], []
        self.uni = 'utf' in locale.getpreferredencoding(False).lower()  # (box and arrow characters, else ASCII)
        curses.curs_set(0)
        scr.keypad(True)
        try:
            curses.use_default_colors()
        except curses.error:
            pass

    # --- what tui.py calls

    def section(self, title):
        self.title, self.body, self.steps, self.log_tail = title, [], [], []

    def say(self, text=''):
        self.body += reflow(text)

    def ask(self, question, default=''):
        return self._edit(question, default, None)

    def ask_path(self, question, default, kind):
        return self._edit(question, default, kind)

    def choose(self, title, options, default):
        keys = [k for k, _ in options]
        sel = keys.index(default) if default in keys else 0
        scroll = 0
        while True:
            w = self.scr.getmaxyx()[1]
            rows = []
            for i, (k, text) in enumerate(options):  # (a long option wraps under itself)
                for j, part in enumerate(textwrap.wrap(text, w - 10, break_on_hyphens=False) or ['']):
                    rows.append(('  ' + ('> ' if i == sel and not j else '  ') + ('  ' if j else '') + part, i == sel))
            scroll = self._draw([(title, curses.A_BOLD)] + rows, '↑↓ move   Enter choose   1-9 jump   Esc quit'
                                if self.uni else 'Up/Down move   Enter choose   1-9 jump   Esc quit', scroll)
            k = self._key()
            if k in ('up', 'k'):
                sel = (sel - 1) % len(keys)
            elif k in ('down', 'j'):
                sel = (sel + 1) % len(keys)
            elif k == 'home':
                sel = 0
            elif k == 'end':
                sel = len(keys) - 1
            elif k == 'pgup':
                scroll = max(0, scroll - 5)
            elif k == 'pgdn':
                scroll += 5
            elif len(k) == 1 and k.isdigit() and 1 <= int(k) <= len(keys):
                sel = int(k) - 1
            elif k in ('enter', ' '):
                self.body = []
                return keys[sel]
            elif k in ('esc', 'q'):
                self._confirm_quit()

    def progress(self, ev):
        kind = ev.get('event')
        if kind == 'step':
            for s in self.steps:
                s['done'] = True
            self.steps.append({'name': ev.get('step'), 'msg': ev.get('msg') or ev.get('step'), 'pct': 0, 'done': False})
        elif kind == 'progress' and self.steps:
            for s in reversed(self.steps):
                if s['name'] == ev.get('step'):
                    s['pct'] = ev.get('pct', 0)
                    s['done'] = s['pct'] >= 100
                    break
        elif kind in ('info', 'warning', 'error'):
            self.log_tail = (self.log_tail + [('' if kind == 'info' else kind + ': ') + str(ev.get('text') or ev.get('msg'))])[-6:]
        self._draw_progress()

    def run_outside(self, argv, run):
        """Runs a command on the plain terminal (the package manager: sudo's password, its own questions), then
        comes back to the screens after Enter. -> its exit status"""
        curses.def_prog_mode()
        curses.endwin()
        print('\n$ ' + ' '.join(argv), flush=True)
        try:
            rc = run(argv)
            print(('\nDone.' if rc == 0 else f'\nIt stopped with exit status {rc}.') + ' Press Enter to go back to the '
                  'installer.', flush=True)
            try:
                input()
            except EOFError:
                pass
        finally:
            curses.reset_prog_mode()
            self.scr.clear()
            self.scr.refresh()
        return rc

    def transcript(self):
        """What to leave on the terminal when the screens close: the last screen's text."""
        return '\n'.join(self.body).strip('\n')

    # --- drawing

    def _bars(self, hint):
        h, w = self.scr.getmaxyx()
        top = ' Hylian Melodies installer'
        right = self.title + ' '
        self._put(0, 0, (top + ' ' * w)[:w - len(right)] + right, curses.A_REVERSE)
        self._put(h - 1, 0, (' ' + hint + ' ' * w)[:w - 1], curses.A_REVERSE)

    def _put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.scr.addstr(y, x, text[:max(0, w - x - (1 if y == h - 1 else 0))], attr)
            except curses.error:
                pass

    def _draw(self, widget, hint, scroll=0, cursor=None):
        """widget: [(text, attr or selected-bool)] drawn under the body. -> the scroll used."""
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self._bars(hint)
        body = wrap(self.body, w - 4)
        while body and not body[-1]:
            body.pop()
        room = h - 3 - len(widget) - (1 if body else 0)
        scroll = max(0, min(scroll, len(body) - room)) if len(body) > room else 0
        shown = body[scroll:scroll + max(0, room)]
        for i, line in enumerate(shown):
            self._put(2 + i, 2, line)
        if len(body) > room:
            self._put(1, w - 22, ('more above ↑' if self.uni else 'more above') if scroll else '')
            if scroll + room < len(body):
                self._put(2 + len(shown), w - 22, ('more below ↓  PgDn' if self.uni else 'more below  PgDn'))
        y = h - 1 - len(widget)
        for text, attr in widget:
            a = (curses.A_REVERSE if attr is True else 0) if isinstance(attr, bool) else attr
            self._put(y, 2, text, a)
            y += 1
        if cursor:
            curses.curs_set(1)
            self.scr.move(*cursor)
        else:
            curses.curs_set(0)
        self.scr.refresh()
        return scroll

    def _draw_progress(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self._bars('Ctrl+C stops (the build resumes where it was when you start again)')
        y = 2
        for line in wrap(self.body, w - 4)[:max(0, h - 12 - len(self.steps))]:
            self._put(y, 2, line)
            y += 1
        if self.body:
            y += 1
        ok, run = ('✓', '▸') if self.uni else ('*', '>')
        for s in self.steps[-(h - y - 9):] if h - y - 9 > 0 else []:
            mark = ok if s['done'] else run
            self._put(y, 2, f"{mark} {s['msg']}", 0 if s['done'] else curses.A_BOLD)
            if not s['done'] and s['pct']:
                width = max(10, min(40, w - 12 - len(s['msg'])))
                fill = int(width * s['pct'] / 100)
                full, empty = ('█', '░') if self.uni else ('#', '-')
                self._put(y, 6 + len(s['msg']), f"{full * fill}{empty * (width - fill)} {s['pct']:3d}%")
            y += 1
        y = max(y + 1, h - 2 - len(self.log_tail))
        for line in self.log_tail:
            self._put(y, 2, line[:w - 4], curses.A_DIM)
            y += 1
        self.scr.refresh()

    # --- input

    def _key(self):
        while True:
            try:
                k = self.scr.get_wch()
            except curses.error:
                continue
            names = {curses.KEY_UP: 'up', curses.KEY_DOWN: 'down', curses.KEY_LEFT: 'left', curses.KEY_RIGHT: 'right',
                     curses.KEY_HOME: 'home', curses.KEY_END: 'end', curses.KEY_PPAGE: 'pgup', curses.KEY_NPAGE: 'pgdn',
                     curses.KEY_BACKSPACE: 'backspace', curses.KEY_DC: 'delete', curses.KEY_ENTER: 'enter',
                     curses.KEY_F2: 'browse', curses.KEY_RESIZE: 'resize'}
            if isinstance(k, int):
                if k in names:
                    return names[k]
                continue
            return {'\n': 'enter', '\r': 'enter', '\x1b': 'esc', '\x7f': 'backspace', '\x08': 'backspace',
                    '\t': 'tab', '\x0f': 'browse', '\x01': 'home', '\x05': 'end', '\x15': 'clear'}.get(k, k)

    def _confirm_quit(self):
        keep_body, keep_title = self.body, self.title
        self.body = ['Nothing has been installed. Files the build made so far stay in the work folder, so a later',
                     'start goes on from there.']
        self.title = 'Quit?'
        try:
            sel = 0
            while True:
                rows = [('Quit the installer?', curses.A_BOLD), ('  ' + ('> ' if sel == 0 else '  ') + 'No, go on', sel == 0),
                        ('  ' + ('> ' if sel == 1 else '  ') + 'Yes, quit', sel == 1)]
                self._draw(rows, 'Enter choose   Esc go on')
                k = self._key()
                if k in ('up', 'down', 'k', 'j', 'tab'):
                    sel = 1 - sel
                elif k == 'esc':
                    return
                elif k == 'enter':
                    if sel:
                        raise Quit()
                    return
        finally:
            self.body, self.title = keep_body, keep_title

    def _edit(self, question, default, kind):
        f = TextField(default)
        note, scroll = '', 0
        hint = 'Enter accept   Esc quit'
        if kind:
            hint = 'Ctrl+O or F2 browse   Tab complete   Enter accept   Esc quit'
        while True:
            h, w = self.scr.getmaxyx()
            room = w - 6
            start = max(0, f.pos - room + 1)
            rows = [(question, curses.A_BOLD), ('> ' + f.text[start:start + room], 0), (note, curses.A_DIM)]
            scroll = self._draw(rows, hint, scroll, cursor=(h - 3, 4 + f.pos - start))
            k = self._key()
            note = ''
            if k == 'enter':
                curses.curs_set(0)
                self.body = []
                return f.text.strip() or default
            if k == 'esc':
                self._confirm_quit()
            elif k == 'tab' and kind:
                names = f.complete()
                if len(names) > 1:
                    note = '  '.join(names)[:w - 6]
            elif k == 'browse' and kind:
                got = self._browse(question, f.text or default, kind)
                if got:
                    curses.curs_set(0)
                    self.body = []
                    return got
            elif k == 'pgup':
                scroll = max(0, scroll - 5)
            elif k == 'pgdn':
                scroll += 5
            elif k != 'resize':
                f.key(k)

    def _browse(self, question, current, kind):
        """The desktop's dialog when there is one, else the in-terminal list. -> a path or ''."""
        cur = os.path.expanduser(current.strip('\'"')) if current else ''
        start = cur if kind == 'folder' and os.path.isdir(cur) else os.path.dirname(cur)
        title = question.split(';')[0]
        keep = self.body
        self.body = ['A file window is open on your desktop (it may be behind this terminal).',
                     'Choose the file there, or cancel it to pick it here instead.']
        self._draw([], 'waiting for the file window')
        got = self.desktop_pick(title, kind, start, self.env)
        self.body = keep
        if got:
            return got
        return self._terminal_browser(title, start, kind) or ''

    def _terminal_browser(self, title, start, kind):
        b = Browser(start, picker.KINDS.get(kind, ('', ['*']))[1], folders=kind == 'folder')
        top = 0
        while True:
            self.scr.erase()
            h, w = self.scr.getmaxyx()
            keep_title, self.title = self.title, title
            self._bars('Enter open/choose   ← up   ~ home   . hidden   Esc back' if self.uni else
                       'Enter open/choose   Left up   ~ home   . hidden   Esc back')
            self.title = keep_title
            where = b.cwd + ('   ' + b.error if b.error else '')
            if len(where) > w - 4:  # (the end of a long path is the part that says where)
                where = ('…' if self.uni else '...') + where[-(w - 7):]
            self._put(1, 2, where, curses.A_BOLD)
            rows = h - 4
            if b.sel < top:
                top = b.sel
            elif b.sel >= top + rows:
                top = b.sel - rows + 1
            for i, (name, is_dir) in enumerate(b.entries[top:top + rows]):
                idx = top + i
                label = ('[ Use this folder ]' if name == b.HERE and b.folders else
                         name + ('/' if is_dir and name != '..' else ''))
                attr = curses.A_BOLD if (not is_dir and b.wanted(name)) else (0 if is_dir else curses.A_DIM)
                if idx == b.sel:
                    attr |= curses.A_REVERSE
                self._put(2 + i, 2, (' ' + label + ' ' * w)[:w - 4], attr)
            self.scr.refresh()
            k = self._key()
            if k in ('up', 'k'):
                b.move(-1)
            elif k in ('down', 'j'):
                b.move(1)
            elif k == 'pgup':
                b.move(-rows)
            elif k == 'pgdn':
                b.move(rows)
            elif k == 'home':
                b.sel = 0
            elif k == 'end':
                b.move(len(b.entries))
            elif k in ('left', 'backspace'):
                b.up()
            elif k == '~':
                b.go(os.path.expanduser('~'))
            elif k == '.':
                b.toggle_hidden()
            elif k in ('enter', 'right'):
                got = b.enter()
                if got:
                    return got
            elif k == 'esc':
                return None
