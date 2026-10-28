"""Finite ordinary-file output groups for the existing selected-child mechanism.

This helper runs in a producer job after its source files are complete. It has no
scheduler, cache, native import or generated Content discovery authority.
"""
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata

LIMITS = {'max_pieces': 65536, 'max_manifest_bytes': 64 * 1024 * 1024,
          'max_member_bytes': 128 * 1024 * 1024, 'max_total_bytes': 64 * 1024 * 1024 * 1024}
NAME = re.compile('[A-Za-z][A-Za-z0-9_-]*\\Z')


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or PurePosixPath(value).is_absolute()
            or str(PurePosixPath(value)) != value or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('Expected canonical ordinary-file selector/path')
    return value


def _state(value):
    return value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def write_file_set(source_root, output_root, *, parent, selectors, metadata=None, limits=None):
    """@cc [owner:fontanierh,label:correctness;safety] finite-ordinary-file-group
    Only explicit fixed glob selectors within the completed source root MAY choose
    ordinary files. All traversal MUST refuse links/special files and alias or
    duplicate member identities. Copy each selected file into a fresh output root
    and bind exact SHA/metadata in the manifest published last. No native-format,
    geometry, cache or parent/sibling identity claim MAY be issued. Byte/count
    budgets MUST stay finite and source replacement/mutation MUST refuse.
    """
    source, output = Path(source_root), Path(output_root)
    if (not isinstance(parent, str) or not NAME.fullmatch(parent) or not source.is_absolute()
            or source.resolve() != source or source.is_symlink() or not source.is_dir()
            or not output.is_absolute() or output.resolve() != output
            or source == output or source.is_relative_to(output) or output.is_relative_to(source)):
        raise ValueError('File-set roots must be distinct canonical source/output directories')
    if not isinstance(selectors, (list, tuple)) or not selectors or len(selectors) > 64 or len(set(selectors)) != len(selectors):
        raise ValueError('File-set requires explicit unique finite selectors')
    for selector in selectors:
        _relative(selector)
    bounds = dict(LIMITS if limits is None else limits)
    if (set(bounds) != set(LIMITS) or any(type(value) is not int or not 0 < value <= LIMITS[key] for key, value in bounds.items())
            or bounds['max_manifest_bytes'] > bounds['max_member_bytes'] or bounds['max_member_bytes'] > bounds['max_total_bytes']):
        raise ValueError('Invalid bounded file-set limits')
    observed, selected, source_names = {}, [], set()
    def visit(path):
        before = path.lstat()
        relative = path.relative_to(source).as_posix()
        observed[path] = _state(before)
        canonical = unicodedata.normalize('NFD', unicodedata.normalize('NFD', relative).casefold())
        if canonical in source_names:
            raise ValueError('Aliased source-root membership')
        source_names.add(canonical)
        if stat.S_ISDIR(before.st_mode):
            for child in sorted(path.iterdir()): visit(child)
        elif stat.S_ISREG(before.st_mode) and before.st_nlink == 1:
            if any(fnmatch.fnmatchcase(relative, selector) for selector in selectors):
                selected.append((relative, path))
        else:
            raise ValueError('File-set source contains a link, shared or special file')
        if _state(path.lstat()) != _state(before):
            raise ValueError('File-set source changed during inventory')
    visit(source)
    if not selected or len(selected) > bounds['max_pieces']:
        raise ValueError('File-set has no selected files or exceeds piece budget')
    names, payloads = set(), set()
    members = []
    for relative, path in selected:
        name, payload = Path(relative).stem, Path(relative).name
        if (not NAME.fullmatch(name) or name.casefold() in names or payload.casefold() in payloads or payload.casefold() == 'plan.json'):
            raise ValueError('File-set member names/payloads are unsupported or aliased')
        names.add(name.casefold()); payloads.add(payload.casefold())
        members.append((name, payload, path))
    metadata = {name: {} for name, _, _ in members} if metadata is None else metadata
    if not isinstance(metadata, dict) or set(metadata) != {name for name, _, _ in members} or any(not isinstance(value, dict) for value in metadata.values()):
        raise ValueError('File-set requires exact selected-member object metadata')
    # Refuse nonfinite/unsupported metadata before copying any outputs.
    json.dumps(metadata, allow_nan=False)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or output.resolve() != output or any(output.iterdir()):
        raise ValueError('File-set output must be fresh and empty')
    rows, total = [], 0
    for name, payload, path in members:
        digest, size = hashlib.sha256(), 0
        incoming = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if _state(os.fstat(incoming)) != observed[path]:
                raise ValueError('Selected file replaced before copy')
            with os.fdopen(incoming, 'rb', closefd=False) as stream, (output / payload).open('xb') as target:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(chunk)
                    if size > bounds['max_member_bytes'] or total + size > bounds['max_total_bytes']:
                        raise ValueError('File-set byte budget exceeded')
                    digest.update(chunk); target.write(chunk)
            if _state(os.fstat(incoming)) != observed[path] or _state(path.lstat()) != observed[path]:
                raise ValueError('Selected file changed during copy')
        finally:
            os.close(incoming)
        total += size
        (output / payload).chmod(0o444)
        rows.append({'name': name, 'payload': payload, 'sha256': digest.hexdigest(), 'metadata': metadata[name]})
    for path, before in observed.items():
        if _state(path.lstat()) != before:
            raise ValueError('Completed source tree changed before manifest publication')
    manifest = {'schema': 1, 'kind': 'file_set', 'parent': parent, 'complete': True, 'pieces': rows}
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) > bounds['max_manifest_bytes'] or total + len(encoded) > bounds['max_total_bytes']:
        raise ValueError('File-set manifest/total byte budget exceeded')
    with (output / 'plan.json').open('xb') as stream: stream.write(encoded)
    (output / 'plan.json').chmod(0o444)
    return manifest


def emit(source, destination, *, parent, extensions):
    """Existing recipe producer hook: explicit fixed suffixes, no callback discovery."""
    if (not isinstance(extensions, (list, tuple)) or not extensions or len(extensions) > 64
            or any(not isinstance(ext, str) or not re.fullmatch(r'\.[A-Za-z0-9]{1,15}', ext) for ext in extensions)
            or len(set(extensions)) != len(extensions)):
        raise ValueError('Expected unique explicit ordinary-file suffixes')
    return write_file_set(source, destination, parent=parent, selectors=['*' + ext for ext in extensions])
