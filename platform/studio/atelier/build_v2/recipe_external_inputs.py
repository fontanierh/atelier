"""Import explicitly requested external source-cache inputs as frozen checkout sources.

Each external file or folder that an extracted row names under a known source-cache root is
cloned (or copied) into build/v2-source-inputs/<root>/<original relative path>, its complete
no-follow membership hashed before and after, and the row rewritten to that checkout path.
The cache and generated products are never modified; nothing unrelated is scanned.
"""
from copy import deepcopy
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys

IMPORT_ROOT = 'build/v2-source-inputs'
CACHE_ROOTS = ('atelier-cache',)
RECEIPT = 'receipt.json'


class Unsupported(ValueError):
    """An external input cannot be frozen completely and unambiguously."""


def _relative(value):
    if (not isinstance(value, str) or not value or value.startswith('/') or '\\' in value
            or str(PurePosixPath(value)) != value or any(p in ('.', '..') for p in value.split('/'))):
        raise Unsupported(f'noncanonical external path {value!r}')
    return value


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb', opener=lambda p, f: os.open(p, f | os.O_NOFOLLOW)) as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _members(source):
    """Complete regular-file membership under source (a file or folder); links/specials refuse."""
    info = os.lstat(source)
    if stat.S_ISLNK(info.st_mode):
        raise Unsupported(f'linked external input {source}')
    if stat.S_ISREG(info.st_mode):
        return {'': (info.st_size, _digest(source))}  # a single file: membership keyed by ''

    if not stat.S_ISDIR(info.st_mode):
        raise Unsupported(f'special external input {source}')
    found = {}
    for directory, names, files in os.walk(source, followlinks=False):
        for name in sorted(names):
            if os.path.islink(os.path.join(directory, name)):
                raise Unsupported(f'linked external folder {os.path.join(directory, name)}')
        for name in sorted(files):
            path = os.path.join(directory, name)
            member = os.lstat(path)
            if not stat.S_ISREG(member.st_mode):
                raise Unsupported(f'linked or special external file {path}')
            found[Path(path).relative_to(source).as_posix()] = (member.st_size, _digest(path))
    return found


_CLONE = None


def _copy(source, target):
    """APFS clone when available (no extra disk), else a byte copy; never a link."""
    global _CLONE
    if _CLONE is None:
        _CLONE = False
        if sys.platform == 'darwin':
            try:
                libc = ctypes.CDLL(None, use_errno=True)
                libc.clonefile.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
                _CLONE = libc.clonefile
            except (OSError, AttributeError):
                _CLONE = False
    temporary = target.with_name(f'.{target.name}.importing')
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    if not (_CLONE and _CLONE(os.fsencode(source), os.fsencode(temporary), 1) == 0):  # CLONE_NOFOLLOW
        shutil.copyfile(source, temporary, follow_symlinks=False)
    os.chmod(temporary, 0o444)
    temporary.replace(target)


def _import(source, target, *, label):
    """Freeze source at target; an existing target is kept only if byte-identical and complete."""
    before = _members(source)
    if os.path.islink(target):
        raise Unsupported(f'{label}: linked import destination {target}')
    if '' in before:
        if os.path.lexists(target):
            if _members(target) != before:
                raise Unsupported(f'{label}: import destination {target} differs from its source')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy(source, target)
    else:
        # An existing folder may hold an identical subset (an inner file imported first); never extras.
        current = _members(target) if os.path.lexists(target) else {}
        if any(member not in before or current[member] != before[member] for member in current):
            raise Unsupported(f'{label}: import destination {target} conflicts with its source')
        for member in sorted(set(before) - set(current)):
            destination = target / member
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy(Path(source) / member, destination)
    if _members(target) != before:
        raise Unsupported(f'{label}: imported bytes differ from the source')
    if _members(source) != before:
        raise Unsupported(f'{label}: external source changed during import')
    return before


def import_external_inputs(rows, *, checkout, source_cache):
    """@cc [owner:fontanierh,label:correctness;safety] frozen-external-source-inputs
    Every input and deferred setting rooted in a source cache MUST become a frozen,
    checkout-relative imported source with complete no-follow membership, equal before and
    after import, so the runtime receives only keyed files. The cache MUST NOT be modified
    and nothing it holds beyond the named paths may be read. Conflicting existing imports
    refuse. Returns (rewritten rows, receipt); the receipt is also written under build/.
    """
    checkout = Path(checkout).resolve()
    roots = {'atelier-cache': Path(source_cache).resolve()}
    rows = deepcopy(list(rows))
    imported = {}

    def freeze(root, path, *, optional, label):
        path = _relative(path)
        if root not in CACHE_ROOTS:
            raise Unsupported(f'{label}: unknown external root {root}')
        relative = f'{IMPORT_ROOT}/{root}/{path}'
        if (root, path) not in imported:
            source = roots[root] / path
            if not os.path.lexists(source):
                if not optional:
                    raise Unsupported(f'{label}: missing external input {root}/{path}')
                imported[(root, path)] = None
            else:
                imported[(root, path)] = _import(source, checkout / relative, label=label)
        return relative

    for row in rows:
        for entry in row['inputs']:
            if entry.get('root', 'checkout') in ('checkout', 'blender'):
                continue
            entry['path'] = freeze(entry['root'], entry['path'], optional=entry['optional'], label=row['id'])
            entry['root'] = 'checkout'

        def settings(value, label):
            if isinstance(value, dict) and set(value) == {'path', 'root'}:
                return {'path': freeze(value['root'], value['path'], optional=False, label=label)}
            if isinstance(value, list):
                return [settings(item, label) for item in value]
            return value
        for provider in row.get('deferred', []):
            provider['settings'] = settings(provider['settings'], f'{row["id"]} deferred {provider["name"]}')
    receipt = {'schema': 1, 'imports': [
        {'root': root, 'path': path, 'destination': f'{IMPORT_ROOT}/{root}/{path}',
         'absent': members is None,
         'files': [] if members is None else [{'path': member, 'size': size, 'sha256': digest}
                                              for member, (size, digest) in sorted(members.items())]}
        for (root, path), members in sorted(imported.items())]}
    if imported:
        target = checkout / IMPORT_ROOT / RECEIPT
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name('.receipt.importing')
        temporary.write_text(json.dumps(receipt, sort_keys=True, indent=1) + '\n')
        temporary.replace(target)
    return rows, receipt
