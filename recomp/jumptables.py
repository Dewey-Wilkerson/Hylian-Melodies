"""Jump-table resolution without an emulator library.

A tiny concrete interpreter for the A64 integer subset that switch lowering uses (address materialisation, adds,
shifts, extends, moves, logical immediates and table loads from the module image). For each index value it runs the
instructions between the bounds check and the `br`, and collects the branch targets. Anything it does not model
makes the destination register unknown; an unknown `br` register means "unresolved" and the caller falls back to
dispatching over every instruction of the function, which is always correct, only slower.

Replaces LAS Recomp's Unicorn-based resolver (GPL-2.0, not used here); the search for the bounds check follows
LAS Recomp's `tools/gen.py` (MIT).
"""


from lifter import bits, decode_bit_masks, sext

M64 = (1 << 64) - 1


def writes_gpr_from_simd(w):
    """FP/SIMD-class words (bits 27-25 = 111) that write a general register: FMOV/FCVT*/FJCVTZS to Xd/Wd, UMOV/SMOV."""
    if (w & 0x5F200000) == 0x1E200000 and bits(w, 10, 6) == 0:   # conversion between FP and integer
        rmode_op = (bits(w, 19, 2) << 3) | bits(w, 16, 3)
        return rmode_op not in (0b00010, 0b00011, 0b00111, 0b01111)  # (SCVTF, UCVTF, FMOV to FP: write Vd)
    if (w & 0x9FE08400) == 0x0E000400 and bits(w, 11, 4) in (0b0101, 0b0111):  # SMOV / UMOV
        return True
    return False


def _ext(v, option, shift):
    v &= M64
    if option == 0: v &= 0xFF
    elif option == 1: v &= 0xFFFF
    elif option == 2: v &= 0xFFFFFFFF
    elif option == 4: v = sext(v & 0xFF, 8) & M64
    elif option == 5: v = sext(v & 0xFFFF, 16) & M64
    elif option == 6: v = sext(v & 0xFFFFFFFF, 32) & M64
    return (v << shift) & M64


def _shift(v, typ, amt, size):
    mask = (1 << size) - 1
    v &= mask
    if typ == 0: return (v << amt) & mask
    if typ == 1: return v >> amt
    if typ == 2: return (sext(v, size) >> amt) & mask
    return ((v >> amt) | (v << (size - amt))) & mask if amt else v


class Mini:
    """regs: list of 32 ints or None (unknown); index 31 is SP for the instructions that use SP."""

    def __init__(self, image, base, readable_end):
        self.img, self.base, self.end = image, base, base + readable_end
        self.r = [None] * 32

    def get(self, n, sp=False):
        if n == 31:
            return self.r[31] if sp else 0
        return self.r[n]

    def put(self, n, v, sf, sp=False):
        if n == 31 and not sp:
            return
        self.r[n] = None if v is None else (v & (M64 if sf else 0xFFFFFFFF))

    def load(self, a, size, signed):
        if a is None or not (self.base <= a and a + size <= self.end):
            return None
        off = a - self.base
        v = int.from_bytes(self.img[off:off + size], 'little')
        return sext(v, size * 8) & M64 if signed else v

    def step(self, w, pc):
        """Execute one word. Returns False when the instruction is control flow (the caller decides)."""
        rd = w & 31
        if (w & 0x1F000000) == 0x10000000:                       # ADR / ADRP
            imm = (bits(w, 5, 19) << 2) | bits(w, 29, 2)
            imm = sext(imm, 21)
            self.put(rd, ((pc & ~0xFFF) + (imm << 12)) if w >> 31 else pc + imm, 1)
            return True
        if (w & 0x1F000000) == 0x11000000:                       # ADD/SUB(S) imm
            sf, op, s = w >> 31, bits(w, 30, 1), bits(w, 29, 1)
            imm = bits(w, 10, 12) << (12 if bits(w, 22, 1) else 0)
            a = self.get(bits(w, 5, 5), sp=True)
            v = None if a is None else (a - imm if op else a + imm)
            self.put(rd, v, sf, sp=not s)
            return True
        if (w & 0x1F200000) == 0x0B000000:                       # ADD/SUB(S) shifted reg
            sf, op = w >> 31, bits(w, 30, 1)
            a, b = self.get(bits(w, 5, 5)), self.get(bits(w, 16, 5))
            if a is None or b is None:
                self.put(rd, None, sf)
            else:
                b = _shift(b, bits(w, 22, 2), bits(w, 10, 6), 64 if sf else 32)
                self.put(rd, a - b if op else a + b, sf)
            return True
        if (w & 0x1F200000) == 0x0B200000:                       # ADD/SUB(S) extended reg
            sf, op, s = w >> 31, bits(w, 30, 1), bits(w, 29, 1)
            a, b = self.get(bits(w, 5, 5), sp=True), self.get(bits(w, 16, 5))
            if a is None or b is None:
                self.put(rd, None, sf, sp=not s)
            else:
                b = _ext(b, bits(w, 13, 3), bits(w, 10, 3))
                self.put(rd, a - b if op else a + b, sf, sp=not s)
            return True
        if (w & 0x1F000000) == 0x0A000000:                       # logical shifted reg
            sf, opc, n = w >> 31, bits(w, 29, 2), bits(w, 21, 1)
            a, b = self.get(bits(w, 5, 5)), self.get(bits(w, 16, 5))
            if a is None or b is None:
                self.put(rd, None, sf)
            else:
                size = 64 if sf else 32
                b = _shift(b, bits(w, 22, 2), bits(w, 10, 6), size)
                if n:
                    b = ~b & ((1 << size) - 1)
                self.put(rd, [a & b, a | b, a ^ b, a & b][opc], sf)
            return True
        if (w & 0x1F800000) == 0x12000000:                       # logical imm
            sf, opc = w >> 31, bits(w, 29, 2)
            try:
                imm, _ = decode_bit_masks(bits(w, 22, 1), bits(w, 10, 6), bits(w, 16, 6), 64 if sf else 32, True)
            except Exception:
                self.put(rd, None, sf, sp=opc != 3)
                return True
            a = self.get(bits(w, 5, 5))
            v = None if a is None else [a & imm, a | imm, a ^ imm, a & imm][opc]
            self.put(rd, v, sf, sp=opc != 3)
            return True
        if (w & 0x1F800000) == 0x12800000:                       # MOVN/MOVZ/MOVK
            sf, opc, hw, imm = w >> 31, bits(w, 29, 2), bits(w, 21, 2), bits(w, 5, 16)
            if opc == 0:
                self.put(rd, ~(imm << (16 * hw)), sf)
            elif opc == 2:
                self.put(rd, imm << (16 * hw), sf)
            elif opc == 3:
                old = self.get(rd)
                self.put(rd, None if old is None else (old & ~(0xFFFF << (16 * hw))) | (imm << (16 * hw)), sf)
            else:
                self.put(rd, None, sf)
            return True
        if (w & 0x1F800000) == 0x13000000:                       # SBFM/BFM/UBFM
            sf, opc = w >> 31, bits(w, 29, 2)
            immr, imms = bits(w, 16, 6), bits(w, 10, 6)
            a = self.get(bits(w, 5, 5))
            size = 64 if sf else 32
            if a is None or opc == 1:
                self.put(rd, None, sf)
                return True
            a &= (1 << size) - 1
            if imms >= immr:
                width = imms - immr + 1
                v = (a >> immr) & ((1 << width) - 1)
                if opc == 0:
                    v = sext(v, width)
            else:
                width = imms + 1
                v = (a & ((1 << width) - 1))
                if opc == 0:
                    v = sext(v, width)
                v <<= size - immr
            self.put(rd, v, sf)
            return True
        if (w & 0x3B200C00) == 0x38200800:                       # LDR* (register offset)
            size, opc = bits(w, 30, 2), bits(w, 22, 2)
            if opc == 0:                                         # store
                return True
            a, b = self.get(bits(w, 5, 5), sp=True), self.get(bits(w, 16, 5))
            amt = size if bits(w, 12, 1) else 0
            addr = None if a is None or b is None else (a + _ext(b, bits(w, 13, 3), amt)) & M64
            self._ld(rd, addr, size, opc)
            return True
        if (w & 0x3B000000) == 0x39000000:                       # LDR* (unsigned imm)
            size, opc = bits(w, 30, 2), bits(w, 22, 2)
            if opc == 0:
                return True
            a = self.get(bits(w, 5, 5), sp=True)
            addr = None if a is None else a + (bits(w, 10, 12) << size)
            self._ld(rd, addr, size, opc)
            return True
        if (w & 0x7C000000) == 0x14000000 or (w & 0xFE000000) == 0x54000000 or (w & 0x7E000000) == 0x34000000 \
                or (w & 0x7E000000) == 0x36000000 or (w & 0xFE000000) == 0xD6000000:
            return False                                         # B, B.cond, CBZ/CBNZ, TBZ/TBNZ, BR/BLR/RET
        if (w & 0x0A000000) == 0x08000000 and bits(w, 22, 1) == 0:
            return True                                          # other stores (no GPR written, mostly)
        if (w >> 25) & 7 == 7:                                   # FP/SIMD data processing: V registers, except
            if writes_gpr_from_simd(w):                          # the moves/conversions into a general register
                self.put(rd, None, 1)
            return True
        if (w & 0xFFFFF01F) == 0xD503201F:
            return True                                          # hints (NOP)
        self.put(rd, None, 1, sp=True)                           # unknown: forget the destination
        return True

    def _ld(self, rd, addr, size, opc):
        nbytes = 1 << size
        if opc == 1:
            v = self.load(addr, nbytes, False)
            self.put(rd, v, 1 if size == 3 else 0)
        elif opc == 2:   # sign-extend to 64
            self.put(rd, self.load(addr, nbytes, True), 1)
        else:            # sign-extend to 32 (or PRFM for size 3)
            v = self.load(addr, nbytes, True)
            self.put(rd, None if v is None else v & 0xFFFFFFFF, 0)


def run_window(mod, entry, end, start, set_at, br_pc, idx_regs, count):
    """Targets of the br at br_pc for idx in range(count), or None if any is unknown or outside the function."""
    img, base = mod.nso.image, mod.base
    readable = mod.nso.data[0] + mod.nso.data[1]
    rn = bits(mod.word(br_pc), 5, 5)
    targets = set()
    for i in range(count):
        m = Mini(img, base, readable)
        a = entry
        while a < start:                                         # address materialisation only
            w = mod.word(a)
            if (w & 0x1F000000) == 0x10000000 or (w & 0xFF800000) == 0x91000000:
                m.step(w, a)
            a += 4
        a = start
        while a < br_pc:
            if a == set_at:
                for r in idx_regs:
                    m.r[r] = i
            w = mod.word(a)
            if not m.step(w, a):
                # only the bounds-check branch may sit in the window; fall through it (the in-range path)
                if (w & 0xFF000010) != 0x54000000:
                    return None
            a += 4
        if set_at == br_pc:
            return None
        t = m.get(rn)
        if t is None or t % 4 or not (entry <= t < end):
            return None
        targets.add(t)
    return sorted(targets)
