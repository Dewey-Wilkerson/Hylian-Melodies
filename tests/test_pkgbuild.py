"""M9: the PKGBUILD and the shell scripts parse; the PKGBUILD names what brief section 8 requires."""

import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, 'packaging', 'arch')


class Pkgbuild(unittest.TestCase):
    def test_syntax(self):
        for f, sh in (('PKGBUILD', 'bash'), ('hylian-melodies.sh', 'sh'), ('hylian-melodies-recomp.install', 'sh')):
            r = subprocess.run([sh, '-n', os.path.join(ARCH, f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + ': ' + r.stderr)

    def test_required_parts(self):
        with open(os.path.join(ARCH, 'PKGBUILD')) as f:
            s = f.read()
        for want in ('pkgname=hylian-melodies-recomp', 'install=hylian-melodies-recomp.install', "PKGEXT='.pkg.tar'",
                     'options=(!strip !debug !lto !buildflags)', 'cp -al', 'grep -rlIF', 'chmod -R u+w,go+rX,go-w',
                     '/usr/bin/hylian-melodies', 'desktop-copy', 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS',
                     'PERSONAL USE ONLY', '/opt/hylian-melodies'):
            self.assertIn(want, s)


if __name__ == '__main__':
    unittest.main()
