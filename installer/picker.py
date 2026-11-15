"""Picking a file: the desktop's own dialog when there is a desktop, else nothing (the caller offers its in-terminal
browser; installer/screens.py). docs/installer.md, section 3.

Order: the desktop portal (org.freedesktop.portal.FileChooser) through PyGObject when it is installed, then zenity,
then kdialog. The portal answers with a Response signal sent only to the process that asked, so a separate
`gdbus monitor` (the first design) never sees it; PyGObject makes the call and receives the answer on one
connection. Nothing here is required: without any of them the in-terminal browser is used.
"""

import os
import shutil
import subprocess
import urllib.parse

# What each question looks for: (name shown in the dialog, patterns)
KINDS = {
    'base': ('Cartridge dump', ['*.xci', '*.XCI']),
    'update': ('Update', ['*.nsp', '*.NSP']),
    'keys': ('Console keys', ['*.keys']),
    'folder': ('Folder', []),  # (a folder, not a file)
}


def graphical(env=None):
    """True when a desktop dialog can be shown: a display, and not over SSH."""
    env = os.environ if env is None else env
    return bool(env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')) and not env.get('SSH_CONNECTION')


def _from_uri(uri):
    if not uri.startswith('file://'):
        return None
    return urllib.parse.unquote(urllib.parse.urlparse(uri).path)


def portal(title, kind, start, timeout=600):
    """-> the chosen path, '' when cancelled, None when the portal cannot be reached."""
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
    except (ImportError, ValueError):
        return None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        token = 'hm%d' % os.getpid()
        sender = bus.get_unique_name()[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        result, loop = {}, GLib.MainLoop()

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            code, results = params.unpack()
            uris = results.get('uris') or []
            result['path'] = (_from_uri(uris[0]) or '') if code == 0 and uris else ''
            loop.quit()
        sub = bus.signal_subscribe('org.freedesktop.portal.Desktop', 'org.freedesktop.portal.Request', 'Response',
                                   path, None, Gio.DBusSignalFlags.NONE, on_response)
        name, patterns = KINDS.get(kind, ('Files', ['*']))
        opts = {'handle_token': GLib.Variant('s', token), 'modal': GLib.Variant('b', True)}
        if kind == 'folder':
            opts['directory'] = GLib.Variant('b', True)
        else:
            opts['filters'] = GLib.Variant('a(sa(us))', [(name, [(0, p) for p in patterns]), ('All files', [(0, '*')])])
        if start and os.path.isdir(start):
            opts['current_folder'] = GLib.Variant('ay', os.fsencode(start) + b'\0')
        bus.call_sync('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                      'org.freedesktop.portal.FileChooser', 'OpenFile',
                      GLib.Variant('(ssa{sv})', ('', title, opts)), GLib.VariantType('(o)'),
                      Gio.DBusCallFlags.NONE, 10000, None)
        GLib.timeout_add_seconds(timeout, loop.quit)
        loop.run()
        bus.signal_unsubscribe(sub)
        return result.get('path', '')
    except Exception:  # (no portal service, no session bus, an old portal: fall through to the next way)
        return None


def zenity(title, kind, start, run=subprocess.run):
    if not shutil.which('zenity'):
        return None
    name, patterns = KINDS.get(kind, ('Files', ['*']))
    cmd = ['zenity', '--file-selection', '--title', title]
    cmd += ['--directory'] if kind == 'folder' else [f'--file-filter={name} | {" ".join(patterns)}',
                                                      '--file-filter=All files | *']
    if start and os.path.isdir(start):
        cmd.append('--filename=' + os.path.join(start, ''))
    return _run(cmd, run)


def kdialog(title, kind, start, run=subprocess.run):
    if not shutil.which('kdialog'):
        return None
    name, patterns = KINDS.get(kind, ('Files', ['*']))
    where = start if start and os.path.isdir(start) else os.path.expanduser('~')
    if kind == 'folder':
        return _run(['kdialog', '--title', title, '--getexistingdirectory', where], run)
    return _run(['kdialog', '--title', title, '--getopenfilename', where, f'{" ".join(patterns)}|{name}'], run)


def _run(cmd, run):
    try:
        r = run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None
    if r.returncode == 0:
        return r.stdout.strip()
    return '' if r.returncode == 1 else None  # (1: cancelled; anything else: it did not work)


def desktop_pick(title, kind, start, env=None, ways=None):
    """-> a path, '' when the player cancelled, None when no desktop dialog could be shown (use the terminal)."""
    if not graphical(env):
        return None
    for way in ways or (portal, zenity, kdialog):
        got = way(title, kind, start)
        if got is not None:
            return got
    return None
