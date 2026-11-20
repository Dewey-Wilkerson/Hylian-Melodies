"""install.sh and tools/release.py, end to end on a small stand-in repository (a stub installer that records how it
was started), with the release served from a file:// folder laid out like GitHub's release downloads."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import release  # noqa: E402

STUB_TUI = '''import json, os, sys
with open(os.path.join(os.environ['HOME'], 'ran.json'), 'w') as f:
    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd()}, f)
'''


def have(cmd):
    return shutil.which(cmd) is not None


@unittest.skipUnless(have('git') and have('curl') and have('sha256sum'), 'needs git, curl, sha256sum')
class Bootstrap(unittest.TestCase):
    TAG = 'v9.8.7'

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='hm-boot-')
        self.addCleanup(shutil.rmtree, self.t)
        self.repo = os.path.join(self.t, 'repo')
        os.makedirs(os.path.join(self.repo, 'installer'))
        files = {'VERSION': '9.8.7\n', 'installer/__init__.py': '', 'installer/tui.py': STUB_TUI}
        with open(os.path.join(ROOT, 'install.sh')) as f:
            files['install.sh'] = f.read()
        for name, text in files.items():
            with open(os.path.join(self.repo, name), 'w') as f:
                f.write(text)
        g = ['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
             '-c', 'tag.gpgsign=false']
        subprocess.run(['git', 'init', '-q', self.repo], check=True)
        subprocess.run(g + ['add', '-A'], check=True)
        subprocess.run(g + ['commit', '-qm', 'r'], check=True, env=dict(os.environ, GIT_COMMITTER_DATE='2026-01-01T00:00:00Z',
                                                                        GIT_AUTHOR_DATE='2026-01-01T00:00:00Z'))
        subprocess.run(g + ['tag', self.TAG], check=True)
        self.home = os.path.join(self.t, 'home')
        os.makedirs(self.home)
        self.served = os.path.join(self.t, 'served')
        self.url = 'https://example.invalid/owner/hylian-melodies'

    def make(self, out='out'):
        return release.make(self.TAG, self.url, os.path.join(self.t, out), root=self.repo)

    def serve(self, r):
        d = os.path.join(self.served, 'releases', 'download', self.TAG)
        os.makedirs(d, exist_ok=True)
        shutil.copy(r['tarball'], d)

    def sh(self, script, *args, env=None, tty=False):
        e = {'PATH': os.environ['PATH'], 'HOME': self.home, 'HM_REPO_URL': 'file://' + self.served}
        e.update(env or {})
        return subprocess.run(['sh', script, *args], env=e, capture_output=True, text=True, cwd=self.t,
                              start_new_session=not tty, timeout=60)

    def ran(self):
        with open(os.path.join(self.home, 'ran.json')) as f:
            return json.load(f)

    def cache(self, *p):
        return os.path.join(self.home, '.cache', 'hylian-melodies', 'src', *p)

    def test_release_files(self):
        r = self.make()
        self.assertEqual(r['sha256'], self.make('again')['sha256'])  # (the same bytes every time)
        with open(r['tarball'], 'rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), r['sha256'])
        names = subprocess.run(['tar', '-tzf', r['tarball']], capture_output=True, text=True, check=True).stdout.split()
        self.assertIn(f'hylian-melodies-{self.TAG}/installer/tui.py', names)
        with open(r['install']) as f:
            script = f.read()
        self.assertNotIn('@HM_', script)
        self.assertIn(f"HM_SHA256='{r['sha256']}'", script)
        self.assertEqual(r['asset_url'], f'{self.url}/releases/download/{self.TAG}/hylian-melodies-{self.TAG}.tar.gz')
        for tag, url in (('v1.0.0', self.url), (self.TAG, 'http://x.invalid/a'), (self.TAG, self.url + '/'),
                         ('latest', self.url)):
            with self.assertRaises(release.ReleaseError):
                release.make(tag, url, os.path.join(self.t, 'bad'), root=self.repo)

    def test_guard_refuses(self):
        import check_content
        with open(os.path.join(self.repo, 'lifted.c'), 'w') as f:
            f.write('// ' + check_content.GENERATED_MARKER + '\n')
        g = ['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(g + ['add', '-A'], check=True)
        subprocess.run(g + ['commit', '-qm', 'bad', '--no-verify'], check=True)
        subprocess.run(g + ['tag', '-f', self.TAG], check=True, capture_output=True)
        with self.assertRaisesRegex(release.ReleaseError, 'lifted.c'):
            self.make()

    def test_download_check_and_run(self):
        r = self.make()
        self.serve(r)
        p = self.sh(r['install'], '--answers', 'plan.json')
        self.assertEqual(p.returncode, 0, p.stderr)
        got = self.ran()
        src = self.cache(self.TAG)
        self.assertEqual(got['cwd'], src)
        self.assertEqual(got['argv'], ['--root', src, '--source-note', f'release {self.TAG}, SHA-256 checked',
                                       '--answers', os.path.join(self.t, 'plan.json')])
        self.assertEqual(sorted(os.listdir(self.cache())), sorted([self.TAG, f'hylian-melodies-{self.TAG}.tar.gz']))
        shutil.rmtree(self.served)  # offline: the checked tarball of last time is used
        p = self.sh(r['install'], '--answers', 'plan.json')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('downloaded before', p.stdout)

    def test_checksum_mismatch_refused(self):
        r = self.make()
        self.serve(r)
        with open(os.path.join(self.served, 'releases', 'download', self.TAG, os.path.basename(r['tarball'])), 'ab') as f:
            f.write(b'x')
        p = self.sh(r['install'], '--answers', 'plan.json')
        self.assertEqual(p.returncode, 1)
        self.assertIn('does not match', p.stderr)
        self.assertEqual(os.listdir(self.cache()), [])  # (nothing kept, nothing unpacked)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'ran.json')))

    def test_no_terminal(self):
        r = self.make()
        self.serve(r)
        p = self.sh(r['install'])  # (a new session: no terminal to ask on)
        self.assertEqual(p.returncode, 1)
        self.assertIn('no terminal', p.stderr)

    def test_unreleased_copy_and_source(self):
        script = os.path.join(self.repo, 'install.sh')
        p = self.sh(script, '--answers', 'plan.json')
        self.assertEqual(p.returncode, 1)
        self.assertIn('not a release', p.stderr)
        p = self.sh(script, '--source', self.repo, '--answers', 'plan.json')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.ran()['argv'][:4], ['--root', self.repo, '--source-note',
                                                  f'unverified source: the local folder {self.repo}'])
        self.assertFalse(os.path.exists(self.cache()))  # (a local folder: nothing written)
        p = self.sh(script, '--tag', self.TAG, '--sha256', '0' * 64, '--print-only')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f'releases/download/{self.TAG}/hylian-melodies-{self.TAG}.tar.gz', p.stdout)
        for bad in (['--tag', self.TAG], ['--tag', 'v1;rm', '--sha256', '0' * 64], ['--sha256', 'zz'],
                    ['--source', 'https://x.invalid/r'], ['--source', self.repo, '--ref', 'main'], ['--frob'],
                    ['--source', 'https://x.invalid/r', '--ref', '--upload-pack=x']):
            p = self.sh(script, *bad, '--print-only')
            self.assertEqual(p.returncode, 1, (bad, p.stdout))
        p = self.sh(script, '--help')
        self.assertEqual(p.returncode, 0)
        self.assertIn('--print-only', p.stdout)

    def test_git_source(self):
        script = os.path.join(self.repo, 'install.sh')
        p = self.sh(script, '--source', 'file://' + self.repo, '--ref', self.TAG, '--answers', 'plan.json')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.ran()['cwd'], self.cache('ref-' + self.TAG))

    def test_cut_short_runs_nothing(self):
        r = self.make()
        self.serve(r)
        with open(r['install']) as f:
            text = f.read()
        for cut in (len(text) // 4, len(text) // 2, text.index('\nmain "$@"')):
            short = os.path.join(self.t, 'short.sh')
            with open(short, 'w') as f:
                f.write(text[:cut])
            p = self.sh(short, '--answers', 'plan.json')
            self.assertFalse(os.path.exists(self.cache()), cut)
            self.assertFalse(os.path.exists(os.path.join(self.home, 'ran.json')), cut)
            self.assertNotIn('Downloading', p.stdout)


if __name__ == '__main__':
    unittest.main()
