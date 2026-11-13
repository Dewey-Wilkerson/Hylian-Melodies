"""Message catalog: event message IDs -> English text. The PKGBUILD's events.py prints these."""

STEPS = {
    'check': 'Checking files',
    'extract': 'Extracting game files',
    'lift': 'Recompiling game code to C',
    'compile': 'Compiling the game',
    'cleanup': 'Cleaning up',
}

MESSAGES = {
    'missing_input': 'Input file not found: {path}',
    'keys_found': 'Keys file found, {n} entries',
    'keys_bad': 'The keys file has no usable keys (need header_key and key_area_key_application_*): {path}',
    'keys_old': 'The keys file lacks the master key revision {rev} this game needs; dump keys from an updated console',
    'container_bad': 'Cannot read {path} as XCI or NSP with these keys: {detail}',
    'no_program': 'No game program found in the given files (is this Cadence of Hyrule?)',
    'wrong_title': 'Not Cadence of Hyrule: title {title}',
    'no_update': 'No supported update found. Supported versions: {supported}. Found: {found}',
    'unknown_version': 'Unsupported game version {version}. Supported: {supported}',
    'nca_hash': 'Damaged dump: {name} does not match its content hash',
    'exefs_hash': 'Extracted {name} does not match the official {version} file; the dump is damaged or modified',
    'romfs_hash': 'Extracted RomFS does not match the official {version} files ({detail})',
    'hactool_failed': 'hactool failed during {what} (log: {log})',
    'disk_space': 'Not enough free space in {path}: {free} GiB free, about {need} GiB needed',
    'found_version': 'Found base {base} with update {version} and {aoc} DLC pack(s)',
    'resume': 'Resuming: {step} already done',
    'compile_failed': 'Compiling the game failed (log: {log})',
    'lift_failed': 'Recompiling {module} failed (log: {log})',
    'not_implemented': 'Step {step} is not implemented yet in this version of the installer',
    'done': 'Setup finished: {dest}',
    'failed': 'Setup failed; full log: {log}',
}


def text(msg, args=None):
    t = MESSAGES.get(msg, msg)
    try:
        return t.format(**(args or {}))
    except (KeyError, IndexError):
        return t
