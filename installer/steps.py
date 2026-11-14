"""Setup steps. Each is resumable: finished work is recorded in hm-install.json and skipped on a rerun; partial
output goes to .partial folders and is renamed into place only when complete and verified."""

import glob
import os
import shutil
import sys
import threading

from . import known, nx
from .events import SetupError
from .hactool import Hactool

GiB = 1 << 30
ORDER = ['check', 'extract', 'lift', 'compile', 'cleanup']  # (no shader step: compiled on first use, docs/DECISIONS.md)


class Ctx:
    def __init__(self, args, events, state, log):
        self.a, self.ev, self.st, self.log = args, events, state, log
        self.dest = os.path.abspath(args.dest)
        self.work = os.path.join(os.path.abspath(args.temp), 'work')
        self.hactool_exe = args.hactool

    def hactool(self):
        return Hactool(self.hactool_exe, self.a.keys, log=self.log, home=os.path.join(self.work, 'hactool-home'))


def _inputs(c):
    files = [('base', c.a.base), ('keys', c.a.keys)] + ([('update', c.a.update)] if c.a.update else [])
    return files


class Watch:
    """Progress from the growth of a folder while an external tool writes it."""

    def __init__(self, c, step, path, expect, lo=0, hi=100):
        self.c, self.step, self.path, self.expect, self.lo, self.hi = c, step, path, max(expect, 1), lo, hi
        self.stop = threading.Event()
        self.t = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop.wait(2):
            frac = min(nx.dir_size(self.path) / self.expect, 0.99)
            self.c.ev.progress(self.step, self.lo + (self.hi - self.lo) * frac)

    def __enter__(self):
        self.t.start()
        return self

    def __exit__(self, *e):
        self.stop.set()
        self.t.join()


def check(c):
    for role, p in _inputs(c):
        if not os.path.isfile(p):
            raise SetupError('missing_input', path=p)
    n, names = nx.keys_summary(c.a.keys)
    c.ev.info('keys_found', n=n)
    if 'header_key' not in names or not any(k.startswith('key_area_key_application_') or k.startswith('master_key_')
                                            for k in names):
        raise SetupError('keys_bad', path=c.a.keys)
    if not ({'master_key_0a', 'key_area_key_application_0a'} & names):
        raise SetupError('keys_old', rev='0x0A')
    if sys.version_info < (3, 11):
        raise SetupError('Python 3.11 or newer is needed')
    for path, need in ((c.dest, 4), (os.path.dirname(c.work), 6)):
        os.makedirs(path, exist_ok=True)
        st = os.statvfs(path)
        free = st.f_bavail * st.f_frsize / GiB
        if free < need:
            raise SetupError('disk_space', path=path, free=f'{free:.1f}', need=need)
    with c.hactool() as h:
        for role, p in _inputs(c):
            if role == 'keys':
                continue
            ok, out = h.run('-t', _ctype(p), p, what='check')
            if not ok:
                raise SetupError('container_bad', path=p, detail=(out.strip().splitlines() or ['?'])[-1])
    c.ev.progress('check', 100)
    return {}


def _ctype(path):
    with open(path, 'rb') as f:
        head = f.read(0x110)
    if head[0x100:0x104] == b'HEAD':
        return 'xci'
    if head[:4] == b'PFS0':
        return 'pfs0'
    raise SetupError('container_bad', path=path, detail='neither XCI nor NSP')


def _sub_done(c, name):
    return name in (c.st['extract_sub'] or [])


def _sub_mark(c, name):
    c.st['extract_sub'] = (c.st['extract_sub'] or []) + [name]


def extract(c):
    nca_dir = os.path.join(c.work, 'nca')
    meta_dir = os.path.join(c.work, 'meta')
    with c.hactool() as h:
        # a. unpack the containers' NCAs into the work folder
        if not _sub_done(c, 'unpack'):
            shutil.rmtree(nca_dir, ignore_errors=True)
            os.makedirs(nca_dir)
            srcs = [c.a.base] + ([c.a.update] if c.a.update else [])
            expect = sum(os.path.getsize(p) for p in srcs)
            with Watch(c, 'extract', nca_dir, expect, 0, 25):
                for p in srcs:
                    t = _ctype(p)
                    opt = '--securedir=' if t == 'xci' else '--outdir='
                    ok, _ = h.run('-t', t, opt + nca_dir, p, what='unpack')
                    if not ok:
                        raise SetupError('hactool_failed', what='unpack', log=c.a.log_path)
            _sub_mark(c, 'unpack')
        c.ev.progress('extract', 25)

        # b. metadata: content hashes, titles, versions, title keys
        shutil.rmtree(meta_dir, ignore_errors=True)
        os.makedirs(meta_dir)
        metas = []
        for f in sorted(glob.glob(os.path.join(nca_dir, '*.cnmt.nca'))):
            d = os.path.join(meta_dir, os.path.basename(f))
            ok, _ = h.run('--section0dir=' + d, f, what='meta')
            for cn in glob.glob(os.path.join(d, '*.cnmt')):
                with open(cn, 'rb') as fh:
                    metas.append(nx.parse_cnmt(fh.read()))
        titles = {}
        for m in metas:
            if m['title'] & ~0xFFF == known.APP_TITLE & ~0xFFF or m['title'] in known.AOC_TITLES:
                titles.setdefault(m['type'], []).append(m)
        if not metas or 'Application' not in titles:
            if metas:
                raise SetupError('wrong_title', title=f'{metas[0]["title"]:016X}')
            raise SetupError('no_program')
        app = titles['Application'][0]
        patches = sorted(titles.get('Patch', []), key=lambda m: m['version'])
        by_ver = {v['patch_version']: k for k, v in known.VERSIONS.items()}
        patch = next((p for p in reversed(patches) if p['version'] in by_ver), None)
        if patch is None:
            raise SetupError('no_update', supported=', '.join(known.SUPPORTED),
                             found=', '.join(f'v{p["version"]}' for p in patches) or 'none')
        version = by_ver[patch['version']]
        aocs = [m for m in titles.get('AddOnContent', []) if m['title'] in known.AOC_TITLES]
        c.ev.info('found_version', base='1.0.0', version=version, aoc=len(aocs))

        def nca_of(meta, ctype):
            for r in meta['contents']:
                if r['type'] == ctype:
                    return r
            return None

        needed = [nca_of(app, 'Program'), nca_of(patch, 'Program')] + [nca_of(m, 'Data') for m in aocs]
        if None in needed[:2]:
            raise SetupError('no_program')
        needed = [r for r in needed if r]
        if not _sub_done(c, 'hashes'):
            total = sum(r['size'] for r in needed)
            done = [0]

            def prog(n):
                done[0] += n
                c.ev.progress('extract', 25 + 15 * done[0] / total)
            for r in needed:
                p = os.path.join(nca_dir, r['id'] + '.nca')
                if not os.path.isfile(p) or nx.sha256_file(p, prog) != r['sha256']:
                    raise SetupError('nca_hash', name=r['id'] + '.nca')
            want = known.VERSIONS[version]['program_nca_sha256']
            if needed[0]['sha256'] != want['base'] or needed[1]['sha256'] != want['patch']:
                raise SetupError('unknown_version', version=version, supported=', '.join(known.SUPPORTED))
            _sub_mark(c, 'hashes')
        tks = {}
        for t in glob.glob(os.path.join(nca_dir, '*.tik')):
            try:
                rid, key = nx.ticket_title_key(t)
                tks[rid] = key
            except ValueError:
                pass
        h.set_title_keys(tks)

        # c. ExeFS + RomFS with the update merged
        ver = known.VERSIONS[version]
        if not _sub_done(c, 'game'):
            part = os.path.join(c.dest, '.partial')
            shutil.rmtree(part, ignore_errors=True)
            os.makedirs(part)
            base_p = os.path.join(nca_dir, needed[0]['id'] + '.nca')
            patch_p = os.path.join(nca_dir, needed[1]['id'] + '.nca')
            with Watch(c, 'extract', part, ver['romfs']['bytes'] + 25 * (1 << 20), 40, 75):
                ok, _ = h.run('--basenca=' + base_p, '--exefsdir=' + os.path.join(part, 'exefs'),
                              '--romfsdir=' + os.path.join(part, 'romfs'), patch_p, what='game')
            if not ok:
                raise SetupError('hactool_failed', what='game', log=c.a.log_path)
            for name, sha in ver['exefs_sha256'].items():
                p = os.path.join(part, 'exefs', name)
                if not os.path.isfile(p) or nx.sha256_file(p) != sha:
                    raise SetupError('exefs_hash', name=name, version=version)
            total = ver['romfs']['bytes']
            done = [0]

            def prog2(n):
                done[0] += n
                c.ev.progress('extract', 75 + 15 * done[0] / total)
            man, n, size = nx.tree_manifest(os.path.join(part, 'romfs'), prog2)
            if (man, n, size) != (ver['romfs']['manifest_sha256'], ver['romfs']['files'], ver['romfs']['bytes']):
                raise SetupError('romfs_hash', version=version, detail=f'{n} files, {size} bytes')
            for d in ('exefs', 'romfs'):
                dst = os.path.join(c.dest, d)
                shutil.rmtree(dst, ignore_errors=True)
                os.rename(os.path.join(part, d), dst)
            os.rmdir(part)
            _sub_mark(c, 'game')
        c.ev.progress('extract', 90)

        # d. DLC RomFS, one folder per title
        if not _sub_done(c, 'aoc'):
            aoc_root = os.path.join(c.dest, 'aoc')
            for m in aocs:
                r = nca_of(m, 'Data')
                tid = f'{m["title"]:016x}'
                part = os.path.join(c.dest, '.partial-aoc-' + tid)
                shutil.rmtree(part, ignore_errors=True)
                ok, _ = h.run('--romfsdir=' + part, os.path.join(nca_dir, r['id'] + '.nca'), what='aoc')
                if not ok:
                    raise SetupError('hactool_failed', what='aoc ' + tid, log=c.a.log_path)
                os.makedirs(aoc_root, exist_ok=True)
                dst = os.path.join(aoc_root, tid)
                shutil.rmtree(dst, ignore_errors=True)
                os.rename(part, dst)
            _sub_mark(c, 'aoc')

        # e. the game's own menu icon (control archive, a 256x256 JPEG per language) for the desktop entry; the
        # package converts it (packaging/arch/PKGBUILD). Optional: without it the project's own icon is used.
        if not _sub_done(c, 'icon'):
            r = nca_of(patch, 'Control') or nca_of(app, 'Control')
            ctl = os.path.join(c.work, 'control')
            shutil.rmtree(ctl, ignore_errors=True)
            got = False
            if r:
                ok, _ = h.run('--romfsdir=' + ctl, os.path.join(nca_dir, r['id'] + '.nca'), what='icon')
                names = sorted(glob.glob(os.path.join(ctl, 'icon_*.dat')))
                pick = [n for n in names if n.endswith('icon_AmericanEnglish.dat')] or names
                if ok and pick:
                    shutil.copyfile(pick[0], os.path.join(c.dest, 'icon.jpg'))
                    got = True
            if not got:
                c.ev.warning('no_icon')
            shutil.rmtree(ctl, ignore_errors=True)
            _sub_mark(c, 'icon')
    c.ev.progress('extract', 100)
    shutil.rmtree(nca_dir, ignore_errors=True)
    shutil.rmtree(meta_dir, ignore_errors=True)
    shutil.rmtree(os.path.join(c.work, 'hactool-home'), ignore_errors=True)
    return {'version': version, 'aoc': [f'{m["title"]:016x}' for m in aocs]}


def not_yet(name):
    def step(c):
        raise SetupError('not_implemented', step=name)
    return step


LIFT_MODULES = (('main', 0x7000000000), ('sdk', 0x7004000000))  # must match runtime/rt.h MAIN_BASE, SDK_BASE


def lift(c):
    import subprocess
    gen_dir = os.path.join(os.path.dirname(c.work), 'generated')
    gen_py = os.path.join(c.a.root, 'recomp', 'gen.py')
    for k, (name, base) in enumerate(LIFT_MODULES):
        cmd = [sys.executable, gen_py, name, os.path.join(c.dest, 'exefs', name), hex(base),
               os.path.join(gen_dir, name)]
        c.log('lift: ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        for line in p.stdout:
            c.log('  ' + line.rstrip())
            if ': progress ' in line:
                done, total = line.rsplit(' ', 1)[1].split('/')
                c.ev.progress('lift', 100 * (k + int(done) / int(total)) / len(LIFT_MODULES))
        if p.wait():
            raise SetupError('lift_failed', module=name, log=c.a.log_path)
    return {'generated': gen_dir}


def compile_game(c):
    import re
    import subprocess
    temp = os.path.dirname(c.work)
    gen_dir, build_dir = os.path.join(temp, 'generated'), os.path.join(temp, 'build')
    cmd = [sys.executable, os.path.join(c.a.root, 'tools', 'build_game.py'), '--gen', gen_dir, '--out', build_dir,
           '--target', 'game', '--imgui', getattr(c.a, 'imgui', None) or os.path.join(c.a.root, 'toolchain', 'src', 'imgui')]
    c.log('compile: ' + ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    for line in p.stdout:
        c.log('  ' + line.rstrip())
        m = re.match(r'\[(\d+)/(\d+)\]', line)
        if m:
            c.ev.progress('compile', 99 * int(m.group(1)) / int(m.group(2)))
    if p.wait():
        raise SetupError('compile_failed', log=c.a.log_path)
    exe = os.path.join(build_dir, 'hylian-melodies')
    part = os.path.join(c.dest, 'hylian-melodies.new')
    shutil.copy2(exe, part)
    os.chmod(part, 0o755)
    os.replace(part, os.path.join(c.dest, 'hylian-melodies'))
    return {'executable': 'hylian-melodies'}


def cleanup(c):
    temp = os.path.dirname(c.work)
    for d in ('work', 'generated', 'build'):  # (the run logs stay)
        shutil.rmtree(os.path.join(temp, d), ignore_errors=True)
    for name in os.listdir(c.dest):
        if name.startswith('.partial'):
            shutil.rmtree(os.path.join(c.dest, name), ignore_errors=True)
    c.ev.progress('cleanup', 100)
    return {}


STEPS = {'check': check, 'extract': extract, 'lift': lift, 'compile': compile_game, 'cleanup': cleanup}
