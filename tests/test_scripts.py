"""The shell scripts the package installs parse with sh (the launcher and the install / remove hooks)."""

import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGING = os.path.join(ROOT, 'packaging')


class Scripts(unittest.TestCase):
    def test_syntax(self):
        for f in ('hylian-melodies.sh', 'hylian-melodies-recomp.install'):
            r = subprocess.run(['sh', '-n', os.path.join(PACKAGING, f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + ': ' + r.stderr)


if __name__ == '__main__':
    unittest.main()
