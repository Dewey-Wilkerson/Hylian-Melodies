"""python -m installer --base FILE [--update FILE] --keys FILE --dest DIR [--temp DIR] [--root DIR]
                      [--hactool EXE] [--imgui DIR] [--vma DIR] [--sdl3 DIR] [--shaderc DIR] [--march v2|v3|native] [--until STEP]

Prints one JSON event per line on stdout (installer/events.py); the full log goes to <temp>/run-*/logs/install.log.
Exit status 0 only when the final result is ok."""

import argparse
import os
import time
import traceback

from . import deps
from . import steps as S
from .events import Events, SetupError
from .state import State


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m installer', description='Hylian Melodies setup')
    ap.add_argument('--base', required=True, help='base game dump (.xci or .nsp)')
    ap.add_argument('--update', help='update .nsp (not needed when the cartridge carries the update)')
    ap.add_argument('--keys', required=True, help='prod.keys of your console')
    ap.add_argument('--dest', required=True, help='install folder (the game is staged here)')
    ap.add_argument('--temp', help='work and log folder (default: <dest>/../install-temp)')
    ap.add_argument('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help='repository root')
    ap.add_argument('--hactool', help='hactool built by tools/build_hactool.py (default: <root>/toolchain/hactool/hactool)')
    ap.add_argument('--imgui', help='Dear ImGui source fetched by tools/fetch_imgui.py (default: <root>/toolchain/src/imgui)')
    ap.add_argument('--vma', help='Vulkan Memory Allocator source fetched by tools/fetch_vma.py (default: <root>/toolchain/src/vma)')
    ap.add_argument('--sdl3', help='static SDL3 built by tools/build_sdl3.py, for systems without an SDL3 package (default: the system SDL3)')
    ap.add_argument('--shaderc', help='static shaderc built by tools/build_shaderc.py, for systems whose shaderc package cannot be used (default: the system shaderc)')
    ap.add_argument('--march', choices=('v2', 'v3', 'native'), default='v2',
                    help='CPU level of the compiled game: v2 runs on any x86-64 CPU since ~2009 (default); '
                         'v3 or native optimize for this computer and may not start on others')
    ap.add_argument('--until', choices=S.ORDER, help='stop after this step (development)')
    a = ap.parse_args(argv)
    deps.use_newer_clang()  # (Debian 12: the usable clang is a versioned one outside PATH)
    a.dest = os.path.abspath(a.dest)
    a.temp = os.path.abspath(a.temp or os.path.join(os.path.dirname(a.dest), 'install-temp'))
    a.imgui = os.path.abspath(a.imgui) if a.imgui else os.path.join(a.root, 'toolchain', 'src', 'imgui')
    a.vma = os.path.abspath(a.vma) if a.vma else os.path.join(a.root, 'toolchain', 'src', 'vma')
    a.hactool = a.hactool or os.path.join(a.root, 'toolchain', 'hactool', 'hactool')
    run = os.path.join(a.temp, time.strftime('run-%Y%m%d-%H%M%S'))
    os.makedirs(os.path.join(run, 'logs'), exist_ok=True)
    a.log_path = os.path.join(run, 'logs', 'install.log')
    ev = Events(a.log_path)
    os.makedirs(a.dest, exist_ok=True)
    st = State(a.dest)
    c = S.Ctx(a, ev, st, ev.write_log)
    todo = S.ORDER[:S.ORDER.index(a.until) + 1] if a.until else S.ORDER
    ev.start(todo)
    ev.write_log(f'dest={a.dest} temp={a.temp} hactool={a.hactool}')
    try:
        if not os.path.isfile(a.hactool):
            raise SetupError('missing_input', path=a.hactool)
        redo = False  # (once a step runs again, every later one does too)
        for name in todo:
            ev.step(name)
            src = S.source_hash(c, name)
            rec = st.data['steps'].get(name, {})
            if name != 'check' and st.done(name) and not redo and rec.get('source') == src:
                ev.info('resume', step=name)
                ev.progress(name, 100)
                continue
            if name != 'check' and st.done(name):
                ev.write_log(f'{name}: done before, but its sources changed since: again')
                redo = True
            info = S.STEPS[name](c) or {}
            if src:
                info['source'] = src
            st.mark(name, **info)
    except SetupError as e:
        ev.error(e.msg, **e.args_)
        ev.end('error', log=a.log_path)
        return 1
    except Exception as e:  # noqa: BLE001
        ev.write_log(traceback.format_exc())
        ev.error('failed', log=a.log_path, detail=f'{type(e).__name__}: {e}')
        ev.end('error', log=a.log_path)
        return 1
    finally:
        import shutil
        shutil.rmtree(os.path.join(c.work, 'hactool-home'), ignore_errors=True)
    ev.end('ok', dest=a.dest)
    return 0
