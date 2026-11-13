"""Small readers for Switch container metadata (facts only): keys file sanity, CNMT, tickets, file hashes."""

import hashlib
import os
import re
import struct

CONTENT_TYPES = {0: 'Meta', 1: 'Program', 2: 'Data', 3: 'Control', 4: 'HtmlDocument', 5: 'LegalInformation',
                 6: 'DeltaFragment'}
META_TYPES = {0x80: 'Application', 0x81: 'Patch', 0x82: 'AddOnContent'}


def keys_summary(path):
    """(entry count, set of key names). Values are read only to count lines; never returned."""
    names = set()
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = re.match(r'\s*([A-Za-z0-9_]+)\s*=\s*[0-9A-Fa-f]+\s*$', line)
            if m:
                names.add(m.group(1).lower())
    return len(names), names


def parse_cnmt(data):
    tid, ver, mtype = struct.unpack_from('<QIB', data, 0)
    ext_size, count = struct.unpack_from('<HH', data, 0xE)
    recs = []
    off = 0x20 + ext_size
    for i in range(count):
        r = data[off + i * 0x38: off + (i + 1) * 0x38]
        sha = r[:32].hex()
        ncaid = r[32:48].hex()
        size = int.from_bytes(r[48:54], 'little')
        ctype = r[54]
        recs.append({'sha256': sha, 'id': ncaid, 'size': size, 'type': CONTENT_TYPES.get(ctype, ctype)})
    return {'title': tid, 'version': ver, 'type': META_TYPES.get(mtype, mtype), 'contents': recs}


def ticket_title_key(path):
    """(rights_id_hex, encrypted title key bytes) from a common ticket file."""
    with open(path, 'rb') as f:
        data = f.read()
    sig = struct.unpack_from('<I', data, 0)[0]
    body = {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x80, 0x10003: 0x240, 0x10004: 0x140,
            0x10005: 0x80}.get(sig)
    if body is None:
        raise ValueError('unknown ticket signature type')
    key = data[body + 0x40: body + 0x50]
    rid = data[body + 0x160: body + 0x170].hex()
    return rid, key


def sha256_file(path, progress=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
            if progress:
                progress(len(b))
    return h.hexdigest()


def tree_manifest(root, progress=None):
    """(sha256 of the manifest, file count, total bytes) for a directory tree; see installer/known.py."""
    h = hashlib.sha256()
    n = total = 0
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for name in sorted(fn):
            p = os.path.join(dp, name)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            size = os.path.getsize(p)
            h.update(f'{rel}\t{size}\t{sha256_file(p, progress)}\n'.encode())
            n += 1
            total += size
    return h.hexdigest(), n, total


def dir_size(root):
    total = 0
    for dp, _, fn in os.walk(root):
        for name in fn:
            try:
                total += os.path.getsize(os.path.join(dp, name))
            except OSError:
                pass
    return total
