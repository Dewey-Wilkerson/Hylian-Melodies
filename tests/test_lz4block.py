"""recomp/lz4block.py: hand-built blocks (no LZ4 library needed)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'recomp'))
import lz4block  # noqa: E402


class Lz4Block(unittest.TestCase):
    def test_literals_only(self):
        self.assertEqual(lz4block.decompress(b'\x50hello', 5), b'hello')

    def test_match(self):
        # "abcd", then a 4-byte match at offset 4, then the closing literal "e"
        self.assertEqual(lz4block.decompress(b'\x40abcd\x04\x00\x10e', 9), b'abcdabcde')

    def test_overlapping_match(self):
        # "a", then a 10-byte match at offset 1 (a run), then "b"
        self.assertEqual(lz4block.decompress(b'\x16a\x01\x00\x10b', 12), b'a' * 11 + b'b')

    def test_long_lengths(self):
        lit = bytes(range(256)) + b'xyz'  # 259 literals: 15 + 244
        block = b'\xff' + bytes([244]) + lit + b'\x03\x00' + bytes([255, 5]) + b'\x10!'
        want = lit + (b'xyz' * 100)[:15 + 255 + 5 + 4] + b'!'
        self.assertEqual(lz4block.decompress(block, len(want)), want)

    def test_errors(self):
        for block, size in ((b'\x50hell', 5),               # literals run past the input
                            (b'\x40abcd\x05\x00\x10e', 9),  # offset before the start
                            (b'\x40abcd\x00\x00\x10e', 9),  # offset 0
                            (b'\x40abcd\x04', 9),           # ends inside a sequence
                            (b'\x50hello', 6),              # wrong declared size
                            (b'\x40abcd\x04\x00\x10e', 5)):  # larger than declared
            with self.assertRaises(ValueError):
                lz4block.decompress(block, size)


if __name__ == '__main__':
    unittest.main()
