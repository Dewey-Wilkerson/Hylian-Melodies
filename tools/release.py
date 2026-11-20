#!/usr/bin/env python3
"""Make the files of one release: the source tarball and the install.sh that pins it (docs/installer.md, section 1).

  python3 tools/release.py --repo-url https://github.com/OWNER/REPO [--tag vX.Y.Z] [--out DIR]

Needs an existing tag (default: v + the VERSION file) whose VERSION file matches it. Writes into DIR (default
~/.cache/hylian-melodies/release/vX.Y.Z/):
  hylian-melodies-vX.Y.Z.tar.gz   `git archive` of the tag, gzip without a timestamp: the same bytes every time
  install.sh                      the repository's install.sh with the tag, the tarball's SHA-256 and the URL filled in
  SHA256SUMS
The bootstrap downloads <repo-url>/releases/download/vX.Y.Z/hylian-melodies-vX.Y.Z.tar.gz, so the tarball is
uploaded as that release's asset (not GitHub's generated "Source code" archive, whose bytes are not promised to
stay the same; docs/DECISIONS.md). Nothing is pushed or uploaded from here: that is the owner's step.
The tagged tree goes through tools/check_content.py first.
"""

import argparse
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEFT_OUT = set()  # (paths of the tag's tree kept out of the tarball; none now)
PLACEHOLDERS = ('@HM_TAG@', '@HM_SHA256@', '@HM_REPO_URL@')


class ReleaseError(Exception):
    pass


def git(*args, root=ROOT, binary=False):
    r = subprocess.run(['git', '-C', root, *args], capture_output=True, text=not binary)
    if r.returncode:
        raise ReleaseError(f'git {" ".join(args)}: ' + (r.stderr if not binary else r.stderr.decode(errors='replace'))
                           .strip())
    return r.stdout


def tarball(tag, root=ROOT):
    """-> the release tarball's bytes: the tag's tree under hylian-melodies-<tag>/, minus LEFT_OUT, gzip with no
    timestamp or file name (so the same tag always gives the same bytes)."""
    raw = git('archive', '--format=tar', f'--prefix=hylian-melodies-{tag}/', tag, root=root, binary=True)
    src = tarfile.open(fileobj=io.BytesIO(raw))
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.PAX_FORMAT) as dst:
        for m in src.getmembers():
            if m.name.split('/', 1)[-1] in LEFT_OUT:
                continue
            m.pax_headers = {}  # (git's commit id comment: not needed, and keeps the output to plain entries)
            dst.addfile(m, src.extractfile(m) if m.isfile() else None)
    buf = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=buf, mtime=0, compresslevel=9) as z:
        z.write(out.getvalue())
    return buf.getvalue()


def check_tree(data):
    """The content guard (tools/check_content.py) over every file of the tarball, by its path in the repository."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import check_content
    bad = []
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                path = m.name.split('/', 1)[1]
                bad += [f'{path}: {p}' for p in check_content.check(path, tf.extractfile(m).read())]
    if bad:
        raise ReleaseError('the content guard refuses the tagged tree:\n  ' + '\n  '.join(bad))


def fill(script, tag, sha, url):
    for p in PLACEHOLDERS:
        if script.count(p) != 1:
            raise ReleaseError(f'install.sh should hold {p} exactly once')
    return script.replace('@HM_TAG@', tag).replace('@HM_SHA256@', sha).replace('@HM_REPO_URL@', url)


def make(tag, repo_url, out, root=ROOT):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)?', tag):
        raise ReleaseError(f'not a release tag: {tag} (vX.Y.Z)')
    if not re.fullmatch(r'https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~-]+)+', repo_url):
        raise ReleaseError(f'--repo-url: an https:// address of the repository, without a trailing slash: {repo_url}')
    git('rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}', root=root)
    version = git('show', f'{tag}:VERSION', root=root).strip()
    if 'v' + version != tag:
        raise ReleaseError(f'the VERSION file at {tag} says {version}')
    data = tarball(tag, root)
    check_tree(data)
    sha = hashlib.sha256(data).hexdigest()
    script = fill(git('show', f'{tag}:install.sh', root=root), tag, sha, repo_url)
    os.makedirs(out, exist_ok=True)
    name = f'hylian-melodies-{tag}.tar.gz'
    for fn, content in ((name, data), ('install.sh', script.encode()),
                        ('SHA256SUMS', f'{sha}  {name}\n'.encode())):
        tmp = os.path.join(out, fn + '.new')
        with open(tmp, 'wb') as f:
            f.write(content)
        os.replace(tmp, os.path.join(out, fn))
    os.chmod(os.path.join(out, 'install.sh'), 0o755)
    return {'tag': tag, 'sha256': sha, 'tarball': os.path.join(out, name), 'install': os.path.join(out, 'install.sh'),
            'asset_url': f'{repo_url}/releases/download/{tag}/{name}'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--repo-url', required=True, help='https://github.com/OWNER/REPO (where the release is uploaded)')
    ap.add_argument('--tag', help='default: v + the VERSION file')
    ap.add_argument('--out', help='default: ~/.cache/hylian-melodies/release/<tag>')
    a = ap.parse_args(argv)
    if not a.tag:
        with open(os.path.join(ROOT, 'VERSION')) as f:
            a.tag = 'v' + f.read().strip()
    out = a.out or os.path.join(os.path.expanduser('~'), '.cache', 'hylian-melodies', 'release', a.tag)
    try:
        r = make(a.tag, a.repo_url, out)
    except ReleaseError as e:
        print('release: ' + str(e), file=sys.stderr)
        return 1
    print(f"Release {r['tag']}: SHA-256 {r['sha256']}")
    print(f"  {r['tarball']}\n  {r['install']}")
    print('To publish (the owner\'s step): push the tag, create the release, upload the tarball as its asset so it')
    print(f"is at {r['asset_url']}, and publish install.sh where the curl line points.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
