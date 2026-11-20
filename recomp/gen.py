"""Generate C for a whole NSO module (ARM64 -> C), one C function per guest function.

  python3 recomp/gen.py <name> <nso> <base> <outdir> [--hle FILE] [--hooks FILE] [--simd c|asm] [--chunk N] [--jobs N]

Function hooks (recomp/hooks.txt by default, `<module> <guest address> <host function>` per line): the guest function
at that address becomes f_<addr>_orig and f_<addr> calls `<host function>(Cpu *c, GuestFn orig)` instead, which runs
the original through orig when it wants to (runtime/hle/game_menu.c). Addresses are for the supported game version only.

Adapted from LAS Recomp's tools/gen.py (MIT, see THIRD_PARTY_NOTICES.md): function partitioning, scanning and the C
emitter follow it. Changes: jump tables are resolved by recomp/jumptables.py (no Unicorn), the Link's Awakening
hooks, patches and randomizer variants are gone (per-version patch logic will be located at install time,
recomp/patches.py), every output file carries the content marker, and chunks are emitted by parallel workers.
"""

import argparse
import multiprocessing as mp
import os
import platform
import re
import struct
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jumptables import run_window, writes_gpr_from_simd  # noqa: E402
from lifter import Insn, Lifter, Unsupported, bits, emit_asm_batch, hx, sext  # noqa: E402
from nso import Nso, R_AARCH64_RELATIVE  # noqa: E402

# Must match tools/check_content.py GENERATED_MARKER.
MARKER = '/* HYLIAN-MELODIES-GENERATED: do not commit. Generated from the user\'s own game files. */\n'


def sext26(w):
    v = w & 0x03FFFFFF
    return v - 0x04000000 if v & 0x02000000 else v


def fname(a):
    return f'f_{a:x}'


def sanitize(sym):
    return 'hle_' + re.sub(r'[^A-Za-z0-9_]', '_', sym)


def eh_frame_functions(n, base):
    img, hdr = n.image, n.eh_start
    if not hdr or hdr + 4 > len(img):
        return []
    ver, ptr_enc, cnt_enc, tbl_enc = img[hdr:hdr + 4]
    if ver != 1 or tbl_enc != 0x3B:
        return []
    off = hdr + 4

    def enc(off, e):
        fmt = e & 0x0F
        size = {0x03: 4, 0x0B: 4, 0x04: 8, 0x0C: 8}[fmt]
        v = int.from_bytes(img[off:off + size], 'little', signed=fmt in (0x0B, 0x0C))
        if (e & 0x70) == 0x10:
            v += off
        return v, size
    _, s = enc(off, ptr_enc)
    off += s
    count, s = enc(off, cnt_enc)
    off += s
    out = []
    for i in range(count):
        out.append(struct.unpack_from('<i', img, off + i * 8)[0] + hdr)
    return out


class Module:
    def __init__(self, name, path, base, simd):
        self.name = name
        self.nso = Nso(path)
        self.base = base
        n = self.nso
        self.lo = base + n.text[0]
        self.hi = base + n.text[0] + n.text[1]
        self.words = struct.unpack(f'<{n.text[1] // 4}I', bytes(n.image[n.text[0]:n.text[0] + n.text[1]]))
        self.lifter = Lifter(base, simd)
        self.cache = {}
        self.stats = Counter()
        self.unsupported = Counter()

    def in_text(self, a):
        return self.lo <= a < self.hi and a % 4 == 0

    def word(self, a):
        return self.words[(a - self.lo) // 4]

    def lift(self, a):
        ins = self.cache.get(a)
        if ins is None:
            try:
                ins = self.lifter.lift(self.word(a), a)
            except Unsupported as e:
                self.stats['unsupported'] += 1
                self.unsupported[str(e).split(' ')[0][:40]] += 1
                ins = Insn('trap', f'rt_udf(c, {hx(a)}); /* unsupported: {e} */')
            self.cache[a] = ins
        return ins

    def boundaries(self):
        n, b = self.nso, self.base
        starts = {b + a for a in eh_frame_functions(n, b)}
        for name, info, shndx, value, size in n.syms:
            if shndx and (info & 0xF) == 2:
                starts.add(b + value)
        for off, typ, sym, add in n.relocs:
            if typ == R_AARCH64_RELATIVE:
                starts.add(b + add)
        return sorted(a for a in starts if self.in_text(a))

    # ---------------------------------------------------------------- jump tables

    def jump_table(self, br_pc, entry, end):
        return self._jt_fallthrough(br_pc, entry, end) or self._jt_taken(br_pc, entry, end)

    def _index_regs(self, start, at, idx):
        def copy_src(w):
            if (w & 0x7F800000) == 0x12000000:
                return bits(w, 5, 5)
            if (w & 0x7FE0FFE0) == 0x2A0003E0:
                return bits(w, 16, 5)
            if (w & 0x7F800000) in (0x53000000, 0x13000000):
                return bits(w, 5, 5)
            return None
        regs = {idx}
        changed = True
        while changed:
            changed = False
            for a in range(start, at, 4):
                w = self.word(a)
                rd, src = w & 31, copy_src(w)
                if src is None or src >= 31 or rd >= 31:
                    continue
                for x, y in ((rd, src), (src, rd)):
                    if x in regs and y not in regs:
                        regs.add(y)
                        changed = True
        return sorted(regs)

    def _jt_taken(self, br_pc, entry, end):
        s = br_pc
        while s - 4 >= entry and br_pc - (s - 4) <= 4 * 12 and self.lift(s - 4).kind in ('op', 'asm'):
            s -= 4
        for g in range(entry, end, 4):
            w = self.word(g)
            if (w & 0xFF000010) != 0x54000000 or bits(w, 0, 4) not in (9, 3):
                continue
            if g + sext(bits(w, 5, 19), 19) * 4 != s:
                continue
            cw = self.word(g - 4) if g - 4 >= entry else 0
            if (cw & 0x7F80001F) != 0x7100001F or bits(cw, 22, 1):
                continue
            limit = bits(cw, 10, 12)
            count = limit + 1 if bits(w, 0, 4) == 9 else limit
            if 0 < count <= 4096:
                return run_window(self, entry, end, s, s, br_pc, self._index_regs(s, br_pc, bits(cw, 5, 5)), count)
        return None

    def _jt_fallthrough(self, br_pc, entry, end):
        a = br_pc - 4
        guard = cmp = None
        while a >= entry and br_pc - a <= 4 * 32:  # (the compiler may schedule FP work between the check and the br)
            w = self.word(a)
            if (w & 0xFF000010) == 0x54000000 and bits(w, 0, 4) in (8, 2):
                guard = a
                break
            if self.lift(a).kind in ('b', 'bl', 'blr', 'br', 'ret', 'trap'):
                return None
            a -= 4
        if guard is None:
            return None
        a = guard - 4
        while a >= entry and guard - a <= 4 * 8:
            w = self.word(a)
            if (w & 0x7F80001F) == 0x7100001F:
                cmp = a
                break
            if self.lift(a).kind != 'op':
                return None
            a -= 4
        if cmp is None:
            return None
        w = self.word(cmp)
        if bits(w, 22, 1):
            return None
        limit = bits(w, 10, 12)
        count = limit + 1 if bits(self.word(guard), 0, 4) == 8 else limit
        if not 0 < count <= 4096:
            return None
        start = cmp
        while start - 4 >= entry and cmp - (start - 4) <= 4 * 12 and self.lift(start - 4).kind in ('op', 'asm'):
            start -= 4
        return run_window(self, entry, end, start, cmp, br_pc, self._index_regs(start, cmp, bits(w, 5, 5)), count)

    def computed_target(self, br_pc, entry):
        rn = bits(self.word(br_pc), 5, 5)
        a = br_pc - 4
        while a >= entry and br_pc - a <= 4 * 32:
            w = self.word(a)
            if self.lift(a).kind not in ('op', 'asm'):
                return False
            if (w >> 25) & 7 == 7 and not writes_gpr_from_simd(w):
                a -= 4
                continue  # (an FP/SIMD write: its register field names a V register, not x<rn>)
            if (w & 31) == rn:
                return (w & 0x1F000000) == 0x0B000000 or (w & 0x9F000000) == 0x10000000
            a -= 4
        return False

    # ---------------------------------------------------------------- functions

    def scan(self, entry, end):
        labels, ext, tables = {entry}, set(), {}
        terminated = False
        for a in range(entry, end, 4):
            ins = self.lift(a)
            if ins.kind in ('b', 'bcond'):
                t = ins.target
                if entry <= t < end:
                    labels.add(t)
                elif self.in_text(t):
                    ext.add(t)
            elif ins.kind == 'bl':
                if self.in_text(ins.target):
                    ext.add(ins.target)
            elif ins.kind == 'br':
                jt = self.jump_table(a, entry, end)
                if jt:
                    tables[a] = jt
                    labels.update(jt)
                    self.stats['jumptables'] += 1
                elif self.computed_target(a, entry):
                    tables[a] = 'all'
                    self.stats['br_all_labels'] += 1
                else:
                    self.stats['br_dispatch'] += 1
            terminated = ins.kind in ('b', 'br', 'ret', 'trap')
        if not terminated and end < self.hi:
            ext.add(end)
        return labels, ext, tables

    def emit_function(self, entry, end, labels, tables, hle, hooks=None):
        out = [f'void {fname(entry)}(Cpu *c) {{']
        refs = set()
        if hooks and entry in hooks:
            f, h = fname(entry), hooks[entry]
            out = [f'void {h}(Cpu *c, GuestFn orig);', f'static void {f}_orig(Cpu *c);',
                   f'void {f}(Cpu *c) {{ {h}(c, {f}_orig); }}', f'static void {f}_orig(Cpu *c) {{']
        if entry in hle:
            out += [f'    {sanitize(hle[entry])}(c);', '}']
            return out, refs
        out.append(f'    FN_ENTER({hx(entry)});')
        batch = []

        def flush():
            if batch:
                out.append('    ' + emit_asm_batch(batch))
                batch.clear()

        def jump(t):
            if entry <= t < end:
                return f'goto L_{t:x};'
            if not self.in_text(t):
                return f'c->pc = {hx(t)}; __attribute__((musttail)) return rt_dispatch(c);'
            refs.add(t)
            return f'__attribute__((musttail)) return {fname(t)}(c);'

        # A `br` whose table could not be resolved gets the all-instruction fallback (any instruction of the function
        # is a label, reached through a switch): always correct, but heavy for the compiler. A resolved table is
        # complete (recomp/jumptables.py evaluates every index the bounds check admits), so its switch only lists its
        # targets and anything else is a loud failure (rt_jt_miss), never a silent wrong jump.
        all_labels = any(t == 'all' for t in tables.values())
        if all_labels:
            labels = set(range(entry, end, 4))
        last = None
        for a in range(entry, end, 4):
            ins = self.lift(a)
            if a in labels:
                flush()
                out.append(f'L_{a:x}:;')
            k = ins.kind
            if k == 'asm':
                if len(batch) >= 24:
                    flush()
                batch.append(ins.asm)
                try:
                    emit_asm_batch(batch)
                except Unsupported:
                    batch.pop()
                    flush()
                    batch.append(ins.asm)
                last = k
                continue
            flush()
            if k in ('op', 'trap'):
                out.append('    ' + ins.code)
            elif k == 'b':
                out.append('    ' + jump(ins.target))
            elif k == 'bcond':
                out.append(f'    if ({ins.cond}) {{ {jump(ins.target)} }}')
            elif k == 'bl':
                t = ins.target
                if self.in_text(t):
                    refs.add(t)
                    out.append(f'    c->x[30] = {hx(a + 4)}; {fname(t)}(c);')
                else:
                    out.append(f'    c->x[30] = {hx(a + 4)}; c->pc = {hx(t)}; rt_dispatch(c);')
            elif k == 'blr':
                out.append(f'    c->pc = {ins.target}; c->x[30] = {hx(a + 4)}; rt_dispatch(c);')
            elif k == 'br':
                jt = tables.get(a)
                if jt == 'all':
                    out.append(f'    c->pc = {ins.target}; goto L_dispatch;')
                elif jt:
                    cases = ' '.join(f'case {hx(t)}: goto L_{t:x};' for t in jt)
                    out.append(f'    switch ({ins.target}) {{ {cases} default: break; }}')
                    out.append(f'    c->pc = {ins.target}; rt_jt_miss(c, {hx(a)});')
                else:
                    out.append(f'    c->pc = {ins.target}; __attribute__((musttail)) return rt_dispatch(c);')
            elif k == 'ret':
                out.append('    return;')
            last = k
        flush()
        if last not in ('b', 'br', 'ret', 'trap'):
            out.append('    ' + jump(end) if end < self.hi else f'    rt_udf(c, {hx(end)});')
        if all_labels:
            out.append('L_dispatch:')
            cases = ' '.join(f'case {hx(t)}: goto L_{t:x};' for t in range(entry, end, 4))
            out.append(f'    switch (c->pc) {{ {cases} default: break; }}')
            out.append('    __attribute__((musttail)) return rt_dispatch(c);')
        out.append('}')
        return out, refs


def write_if_changed(path, text):
    try:
        with open(path) as f:
            if f.read() == text:
                return False
    except FileNotFoundError:
        pass
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, path)
    return True


# ---------------------------------------------------------------- parallel emission

_W = {}


def load_hooks(path, module):
    hooks = {}
    if path and os.path.exists(path):
        for line in open(path):
            line = line.split('#', 1)[0].split()
            if len(line) == 3 and line[0] == module:
                hooks[int(line[1], 16)] = line[2]
    return hooks


def _worker_init():
    pass  # (fork: the workers inherit _W, including the module's warm lift cache)


def _emit_chunk(job):
    idx, addrs = job
    m, entries, hle, args, hooks = _W['m'], _W['entries'], _W['hle'], _W['args'], _W['hooks']
    body, refs = [], set()
    for a in addrs:
        end, labels, tables = entries[a]
        lines, r = m.emit_function(a, end, labels, tables, hle, hooks)
        body += lines
        refs |= r
    path = os.path.join(args.outdir, f'{args.name}_{idx:04d}.c')
    text = [MARKER, '#include "cpu.h"\n' + ('#include "simd.h"\n' if m.lifter.sc else '')]
    text += [f'void {fname(r)}(Cpu *c);\n' for r in sorted(refs | set(addrs))]
    text += [f'void {sanitize(hle[a])}(Cpu *c);\n' for a in addrs if a in hle]
    text += ['\n'.join(body), '\n']
    write_if_changed(path, ''.join(text))
    return idx, dict(m.stats), dict(m.unsupported)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('nso')
    ap.add_argument('base', type=lambda s: int(s, 0))
    ap.add_argument('outdir')
    ap.add_argument('--hle', help='file of symbol names whose guest bodies are replaced by host functions')
    ap.add_argument('--hooks', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hooks.txt'),
                    help='function hooks: <module> <address> <host function> per line ("" = none)')
    ap.add_argument('--chunk-insns', type=int, default=60000, help='guest instructions per C file (about)')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--simd', choices=('asm', 'c'),
                    default='asm' if platform.machine().lower() in ('arm64', 'aarch64') else 'c')
    args = ap.parse_args()
    t0 = time.time()
    m = Module(args.name, args.nso, args.base, args.simd)
    starts = m.boundaries()
    hle = {}
    if args.hle and os.path.exists(args.hle):
        want = {line.strip() for line in open(args.hle) if line.strip() and not line.startswith('#')}
        for name, info, shndx, value, size in m.nso.syms:
            if shndx and name in want:
                hle[args.base + value] = name

    start_set = set(starts)
    for i, w in enumerate(m.words):
        if (w & 0xFC000000) == 0x94000000:
            t = m.lo + i * 4 + sext26(w) * 4
            if m.in_text(t):
                start_set.add(t)
    adrp_regs = {}
    for i, w in enumerate(m.words):
        pc = m.lo + i * 4
        if (w & 0x9F000000) == 0x10000000:
            imm = sext(((w >> 5) & 0x7FFFF) << 2 | ((w >> 29) & 3), 21)
            if m.in_text(pc + imm):
                start_set.add(pc + imm)
        elif (w & 0x9F000000) == 0x90000000:
            imm = sext(((w >> 5) & 0x7FFFF) << 2 | ((w >> 29) & 3), 21)
            adrp_regs[w & 31] = ((pc & ~0xFFF) + (imm << 12), i)
        elif (w & 0xFFC00000) == 0x91000000:
            rn = (w >> 5) & 31
            if rn in adrp_regs and i - adrp_regs[rn][1] <= 8:
                t = adrp_regs[rn][0] + ((w >> 10) & 0xFFF)
                if m.in_text(t):
                    start_set.add(t)
    scanned = {}
    rounds = 0
    while True:
        rounds += 1
        order = sorted(start_set)
        new = set()
        for i, a in enumerate(order):
            end = order[i + 1] if i + 1 < len(order) else m.hi
            key = (a, end)
            if key not in scanned:
                scanned[key] = m.scan(a, end)
            new |= scanned[key][1] - start_set
        if not new:
            break
        start_set |= new
    entries = {}
    for i, a in enumerate(order):
        end = order[i + 1] if i + 1 < len(order) else m.hi
        entries[a] = scanned[(a, end)]
        entries[a] = (end, entries[a][0], entries[a][2])
    print(f'{args.name}: {len(starts)} boundaries, {len(entries)} functions, {rounds} rounds, {dict(m.stats)}, '
          f'{time.time() - t0:.0f}s', file=sys.stderr, flush=True)

    os.makedirs(args.outdir, exist_ok=True)
    order = sorted(entries)
    jobs, cur, n = [], [], 0
    for a in order:
        cur.append(a)
        n += (entries[a][0] - a) // 4
        if n >= args.chunk_insns:
            jobs.append((len(jobs), cur))
            cur, n = [], 0
    if cur:
        jobs.append((len(jobs), cur))
    total = Counter(m.stats)
    unsup = Counter(m.unsupported)
    hooks = load_hooks(args.hooks, args.name)
    missing = [a for a in hooks if a not in entries]
    if missing:
        sys.exit(f'{args.name}: hooked address(es) not a function start: {", ".join(hx(a) for a in missing)}')
    if hooks:
        print(f'{args.name}: {len(hooks)} function hook(s)', file=sys.stderr, flush=True)
    _W.update(m=m, entries=entries, hle=hle, args=args, hooks=hooks)
    with mp.get_context('fork').Pool(args.jobs, _worker_init) as pool:
        for k, (idx, st, us) in enumerate(pool.imap_unordered(_emit_chunk, jobs)):
            print(f'{args.name}: progress {k + 1}/{len(jobs)}', file=sys.stderr, flush=True)
    for fn in os.listdir(args.outdir):
        mm = re.fullmatch(re.escape(args.name) + r'_(\d{4})\.c', fn)
        if mm and int(mm.group(1)) >= len(jobs):
            os.remove(os.path.join(args.outdir, fn))
    tab = [MARKER, '#include "cpu.h"\n']
    tab += [f'void {fname(a)}(Cpu *c);\n' for a in order]
    tab.append(f'const uint64_t {args.name}_fn_addrs[] = {{\n' + ',\n'.join(hx(a) for a in order) + '};\n')
    tab.append(f'const GuestFn {args.name}_fn_ptrs[] = {{\n' + ',\n'.join(fname(a) for a in order) + '};\n')
    tab.append(f'const uint64_t {args.name}_fn_count = {len(order)};\n')
    write_if_changed(os.path.join(args.outdir, f'{args.name}_table.c'), ''.join(tab))
    with open(os.path.join(args.outdir, f'{args.name}_stats.txt'), 'w') as f:
        f.write(f'functions {len(order)}\nchunks {len(jobs)}\n')
        for k, v in sorted(total.items()):
            f.write(f'{k} {v}\n')
        for k, v in unsup.most_common():
            f.write(f'unsupported_kind {k} {v}\n')
    print(f'{args.name}: wrote {len(jobs)} chunks, {time.time() - t0:.0f}s total; unsupported instruction sites: '
          f'{sum(unsup.values())}', file=sys.stderr)


if __name__ == '__main__':
    main()
