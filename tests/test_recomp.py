"""Lifter units on hand-written instruction words (no game code): the jump-table interpreter and the marker."""

import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'recomp'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import check_content  # noqa: E402
import gen  # noqa: E402
from jumptables import Mini, run_window  # noqa: E402


def adr(rd, off):
    imm = off & 0x1FFFFF
    return 0x10000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | rd


def adrp(rd, pages):
    imm = pages & 0x1FFFFF
    return 0x90000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | rd


def add_imm(rd, rn, imm):
    return 0x91000000 | (imm << 10) | (rn << 5) | rd


def cmp_imm_w(rn, imm):        # subs wzr, wn, #imm
    return 0x7100001F | (imm << 10) | (rn << 5)


def b_cond(off_insns, cond):
    return 0x54000000 | ((off_insns & 0x7FFFF) << 5) | cond


def ldrb_reg(rt, rn, rm):      # ldrb wt, [xn, xm]
    return 0x38606800 | (rm << 16) | (rn << 5) | rt


def add_ext_sxtb_lsl2(rd, rn, rm):  # add xd, xn, wm, sxtb #2
    return 0x8B208000 | (rm << 16) | (4 << 13) | (2 << 10) | (rn << 5) | rd


def br(rn):
    return 0xD61F0000 | (rn << 5)


class FakeNso:
    def __init__(self, image, text_size):
        self.image = image
        self.data = (text_size, len(image) - text_size)


class FakeMod:
    def __init__(self, words, table, base=0x1000):
        text = struct.pack(f'<{len(words)}I', *words)
        self.nso = FakeNso(bytearray(text + table), len(text))
        self.base, self.lo = base, base
        self.words = words

    def word(self, a):
        return self.words[(a - self.lo) // 4]


class JumpTables(unittest.TestCase):
    def test_byte_table_relative_to_adr(self):
        # 0: cmp w0,#3 ; 4: b.hi +9 ; 8: adr x8, table ; c: ldrb w9,[x8,x0] ; 10: adr x10, case0 ;
        # 14: add x10,x10,w9,sxtb #2 ; 18: br x10 ; 1c..28: four cases (ret); table after the code
        n_words = 12
        words = [cmp_imm_w(0, 3), b_cond(9, 8), adr(8, n_words * 4 - 8), ldrb_reg(9, 8, 0), adr(10, 0x1c - 0x10),
                 add_ext_sxtb_lsl2(10, 10, 9), br(10)] + [0xD65F03C0] * 5
        table = bytes([0, 1, 2, 3])
        m = FakeMod(words, table)
        t = run_window(m, 0x1000, 0x1000 + n_words * 4, 0x1000, 0x1000, 0x1018, [0], 4)
        self.assertEqual(t, [0x101c, 0x1020, 0x1024, 0x1028])

    def test_unknown_register_gives_none(self):
        words = [cmp_imm_w(0, 1), b_cond(4, 8), 0xF9400008, br(8), 0xD65F03C0]  # ldr x8,[x0] (unknown memory)
        m = FakeMod(words, b'')
        self.assertIsNone(run_window(m, 0x1000, 0x1014, 0x1000, 0x1000, 0x100c, [0], 2))

    def test_adrp_add(self):
        mi = Mini(bytearray(16), 0x10000, 16)
        mi.step(adrp(1, 2), 0x10ffc)
        mi.step(add_imm(1, 1, 0x34), 0x11000)
        self.assertEqual(mi.r[1], 0x12034)


class SimdWrites(unittest.TestCase):
    """FP/SIMD words name V registers in their destination field, except the moves/conversions to a GPR."""

    def test_classification(self):
        from jumptables import writes_gpr_from_simd
        fsub_d8 = 0x1E603800 | (15 << 16) | (2 << 5) | 8      # fsub d8, d2, d15: writes v8, not x8
        scvtf_d10 = 0x1E620000 | (8 << 5) | 10               # scvtf d10, w8: writes v10
        fmov_x0_d1 = 0x9E660020                              # fmov x0, d1: writes x0
        fcvtzs_w0 = 0x1E780000 | (1 << 5)                    # fcvtzs w0, s1: writes w0
        umov_w0 = 0x0E043C20                                 # umov w0, v1.s[0]: writes w0
        self.assertFalse(writes_gpr_from_simd(fsub_d8))
        self.assertFalse(writes_gpr_from_simd(scvtf_d10))
        self.assertTrue(writes_gpr_from_simd(fmov_x0_d1))
        self.assertTrue(writes_gpr_from_simd(fcvtzs_w0))
        self.assertTrue(writes_gpr_from_simd(umov_w0))

    def test_table_through_fp_work(self):
        # cmp/b.hi guard, table lookup, then FP work writing d8 before `br x8` (the case that crashed the game)
        n = 14
        words = [cmp_imm_w(0, 3), b_cond(n - 1, 8), adr(9, n * 4 - 8), ldrb_reg(10, 9, 0), adr(8, 0x28 - 0x10),
                 add_ext_sxtb_lsl2(8, 8, 10), 0x1E603800 | (15 << 16) | (2 << 5) | 8, 0x1E603800 | (3 << 16) | (4 << 5) | 9,
                 br(8)] + [0xD65F03C0] * 5
        m = FakeMod(words, bytes([0, 1, 2, 3]))
        t = run_window(m, 0x1000, 0x1000 + n * 4, 0x1000, 0x1000, 0x1020, [0], 4)
        self.assertEqual(t, [0x1028, 0x102c, 0x1030, 0x1034])


class Marker(unittest.TestCase):
    def test_generator_marker_matches_checker(self):
        self.assertIn(check_content.GENERATED_MARKER, gen.MARKER)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(os.environ.get('HM_TEST_EXEFS'), 'needs extracted game files (HM_TEST_EXEFS=<dest>/exefs)')
class LiftAndLink(unittest.TestCase):
    """M3 acceptance: both modules lift with no unsupported instruction and link with no unresolved symbol."""

    def test_lift_and_link(self):
        import subprocess
        import tempfile
        work = tempfile.mkdtemp(dir=os.path.expanduser('~/.cache/hylian-melodies'), prefix='m3-')
        exefs = os.environ['HM_TEST_EXEFS']
        for name, base in (('main', '0x7000000000'), ('sdk', '0x7004000000')):
            r = subprocess.run([sys.executable, os.path.join(ROOT, 'recomp', 'gen.py'), name,
                                os.path.join(exefs, name), base, os.path.join(work, 'gen', name)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn('unsupported instruction sites: 0', r.stderr)
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'build_game.py'), '--gen',
                            os.path.join(work, 'gen'), '--out', os.path.join(work, 'build'), '-j', '12'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        import shutil
        shutil.rmtree(work)
