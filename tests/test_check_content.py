"""M1 acceptance: the pre-commit hook rejects keys, game binaries and blobs, and accepts ordinary source.

Each case runs a real `git commit` in a throwaway repository that uses this repo's hook and checker.
  python3 -m unittest discover -s tests
"""

import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import check_content  # noqa: E402


class HookTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='hm-hook-')
        self.addCleanup(shutil.rmtree, self.dir)
        os.makedirs(os.path.join(self.dir, 'tools'))
        shutil.copy(os.path.join(ROOT, 'tools', 'check_content.py'), os.path.join(self.dir, 'tools'))
        shutil.copytree(os.path.join(ROOT, '.githooks'), os.path.join(self.dir, '.githooks'))
        self.git('init', '-q')
        self.git('config', 'core.hooksPath', '.githooks')
        self.git('config', 'user.email', 'test@invalid')
        self.git('config', 'user.name', 'test')

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', self.dir, *args], capture_output=True, text=True, check=check)

    def commit(self, name, data):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        self.git('add', '-f', name)
        return self.git('commit', '-q', '-m', 'test', check=False)

    def assertRejected(self, name, data):
        r = self.commit(name, data)
        self.assertNotEqual(r.returncode, 0, f'{name} was committed')
        self.assertIn('check_content', r.stderr)

    def test_prod_keys_rejected(self):
        rnd = random.Random(1)
        fake = ''.join(f'fake_key_{i:02d} = {rnd.getrandbits(128):032x}\n' for i in range(5))
        self.assertRejected('prod.keys', fake.encode())

    def test_keys_content_under_other_name_rejected(self):
        rnd = random.Random(2)
        self.assertRejected('notes.txt', f'header_key = {rnd.getrandbits(256):064x}\n'.encode())

    def test_nso_rejected(self):
        self.assertRejected('exefs/main.nso', b'NSO0' + bytes(64))

    def test_extensionless_module_rejected(self):
        self.assertRejected('dump/main', b'NSO0' + bytes(64))

    def test_large_blob_rejected(self):
        self.assertRejected('docs/big.txt', b'a' * (check_content.SIZE_LIMIT + 1))

    def test_random_binary_rejected(self):
        self.assertRejected('assets/blob.dat', os.urandom(4096))

    def test_high_entropy_text_rejected(self):
        import base64
        self.assertRejected('src/table.h', b'const char *x = "' + base64.b64encode(os.urandom(600)) + b'";\n')

    def test_generated_code_rejected(self):
        self.assertRejected('src/fn.c', f'/* {check_content.GENERATED_MARKER} */\nint f(void);\n'.encode())

    def test_game_dir_rejected(self):
        self.assertRejected('generated/x.c', b'int x;\n')

    def test_source_accepted(self):
        r = self.commit('src/ok.c', b'/* sha256 of nothing in particular */\nint main(void) { return 0; }\n')
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_hash_with_context_accepted(self):
        r = self.commit('docs/x.md', ('sha256 ' + 'ab' * 32 + '\n').encode())
        self.assertEqual(r.returncode, 0, r.stderr)


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, '.git')), 'not a git checkout (a release tarball or zip)')
class RepoTest(unittest.TestCase):
    def test_tracked_files_clean(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'check_content.py'), '--tracked'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
