"""The port's own texture files (runtime/hle/bntx.c) for the game's loose-texture loader: layout and pixel order."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = shutil.which(os.environ.get('HM_CC', 'clang')) or shutil.which('cc')


@unittest.skipUnless(CC, 'no C compiler')
class Bntx(unittest.TestCase):
    def test_file(self):
        with tempfile.TemporaryDirectory(prefix='hm-bntx-') as t:
            exe = os.path.join(t, 'test_bntx')
            subprocess.run([CC, '-std=gnu11', '-Wall', '-Werror', '-I', os.path.join(ROOT, 'runtime'),
                            os.path.join(ROOT, 'tests', 'c', 'test_bntx.c'),
                            os.path.join(ROOT, 'runtime', 'hle', 'bntx.c'), '-o', exe], check=True)
            r = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'ok'))


if __name__ == '__main__':
    unittest.main()
