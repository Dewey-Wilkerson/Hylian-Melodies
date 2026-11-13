"""The only way this project runs hactool.

hactool prints key material (key area keys, title keys, warnings quoting key values) and by default reads the
user's ~/.switch keys. Every call here: passes -k explicitly with --disablekeywarns, runs with HOME set to a private
0700 temp dir (so ~/.switch is never read), and writes only filtered output to the log: lines mentioning keys are
dropped and long hex runs are masked. Title keys go into <temp home>/.switch/title.keys (0600), removed on close.
"""

import os
import re
import shutil
import subprocess
import tempfile

_HEX = re.compile(r'[0-9A-Fa-f]{32,}')
_KEYLINE = re.compile(r'key|kek|sbk|tsec', re.I)


def filter_output(text):
    out = []
    for line in text.splitlines():
        if _KEYLINE.search(line):
            continue
        out.append(_HEX.sub('<hex>', line))
    return '\n'.join(out)


class Hactool:
    def __init__(self, exe, keys, log=None, home=None):
        """home: a fixed private folder (wiped first, so a killed run leaves nothing behind for long), or None
        for a fresh temp dir."""
        self.exe, self.keys, self.log = exe, os.path.abspath(keys), log
        if home:
            shutil.rmtree(home, ignore_errors=True)
            os.makedirs(home, mode=0o700)
            self.home = home
        else:
            self.home = tempfile.mkdtemp(prefix='hm-hactool-')
        os.chmod(self.home, 0o700)
        os.makedirs(os.path.join(self.home, '.switch'), mode=0o700)

    def set_title_keys(self, pairs):
        """pairs: {rights_id_hex: encrypted_title_key_bytes}. Never logged."""
        path = os.path.join(self.home, '.switch', 'title.keys')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            for rid, key in pairs.items():
                f.write(f'{rid} = {key.hex()}\n')

    def run(self, *args, what='hactool'):
        cmd = [self.exe, '-k', self.keys, '--disablekeywarns', *map(str, args)]
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', env=env)
        filtered = filter_output(r.stdout + r.stderr)
        if self.log:
            # Log the arguments except the keys path (fine to show) and the output, filtered.
            self.log(f'hactool {" ".join(map(str, args))} -> {r.returncode}')
            for line in filtered.splitlines():
                if 'Saving' not in line:
                    self.log('  ' + line)
        bad = r.returncode != 0 or re.search(r'^Error|corrupted|Failed to', filtered, re.M | re.I)
        return (not bad), filtered

    def close(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
