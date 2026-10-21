"""Exact stored-mesh geometry checks and local, non-authoritative unit hints.

The native snapshot stream uses float32 corner attributes, not render buffers.
These records never certify an action or make a failed enclosing build succeed.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import tempfile


MAGIC = b'ATELIER-MESH-1\n'
SIDECARS = ('.uasset', '.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _uint(value):
    if type(value) is not int or not 0 <= value < 2**32:
        raise ValueError('Expected an unsigned 32-bit integer')
    return struct.pack('<I', value)


def _floats(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError('Invalid corner attribute width')
    if any(type(value) not in (float, int) or not math.isfinite(value) for value in values):
        raise ValueError('Nonfinite or nonnumeric mesh attribute')
    try:
        result = struct.pack('<' + 'f' * count, *values)
    except (OverflowError, struct.error) as error:
        raise ValueError('Mesh attribute does not fit float32') from error
    if any(not math.isfinite(value) for value in struct.unpack('<' + 'f' * count, result)):
        raise ValueError('Mesh attribute does not fit finite float32')
    return result


def _geometry_chunks(levels, uv_channels):
    """One encoder for expected hashes and bounded native transport."""
    if not isinstance(levels, (list, tuple)) or not levels:
        raise ValueError('Expected at least one LOD')
    if type(uv_channels) is not int or not 1 <= uv_channels <= 8:
        raise ValueError('Invalid UV channel count')
    yield MAGIC
    yield _uint(len(levels))
    for level in levels:
        vertices, faces = level['vertices'], level['faces']
        yield _uint(uv_channels) + _uint(len(faces))
        for face in faces:
            indices = face['v']
            if len(indices) != 3:
                raise ValueError('Expected a triangle')
            yield _uint(face['s'])
            for index in indices:
                if type(index) is not int or not 0 <= index < len(vertices):
                    raise ValueError('Invalid vertex index')
                vertex = vertices[index]
                for field, count in (('p', 3), ('n', 3), ('c', 4)):
                    yield _floats(vertex[field], count)
                channels = vertex.get('uvs')
                if channels is not None and not isinstance(channels, list):
                    raise ValueError('Invalid UV channels')
                for channel in range(uv_channels):
                    pair = channels[channel] if channels is not None and channel < len(channels) else vertex['uv']
                    yield _floats(pair, 2)


def expected_digest(levels, uv_channels):
    """@cc [owner:fontanierh,label:correctness] exact-mesh-corner-stream
    Every triangle slot, winding, position, normal, colour and UV channel MUST
    enter the versioned little-endian stream. Invalid data MUST refuse reuse.
    Settings/material validation is additionally required by the native caller.
    """
    value = hashlib.sha256()
    for chunk in _geometry_chunks(levels, uv_channels):
        value.update(chunk)
    return value.hexdigest()


def write_geometry(levels, uv_channels, path):
    """@cc [owner:fontanierh,label:correctness] bounded-mesh-corner-transport
    Native transport MUST use exactly the expected-digest encoder and versioned stream,
    with bounded chunks rather than a whole-document text/byte buffer. A failed encode
    MUST preserve any prior destination. Linked paths MUST refuse. Publication MUST
    atomically replace the destination only after complete writing and successful sync.
    Source/material/settings/compiled-tool admission remains the native caller's duty.
    """
    target = Path(path).absolute()
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise ValueError('Linked mesh transport path')
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.mesh-geometry-', dir=target.parent)
    try:
        value = hashlib.sha256()
        with os.fdopen(descriptor, 'wb') as handle:
            for chunk in _geometry_chunks(levels, uv_channels):
                handle.write(chunk)
                value.update(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return value.hexdigest()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _regular(path, root):
    root = Path(root).absolute()
    path = Path(path).absolute()
    relative = path.relative_to(root)
    if '..' in relative.parts:
        raise ValueError('Escaping unit path')
    for candidate in (root, *root.parents, *(root / Path(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
        if candidate.is_symlink():
            raise ValueError('Linked unit path')
    if not path.is_file():
        raise ValueError('Missing unit member')
    return path


def package_inventory(content_root, asset_paths):
    """Inventory every present supported sidecar; missing primaries refuse."""
    root = Path(content_root).absolute()
    if not isinstance(asset_paths, (list, tuple)) or not asset_paths or len(set(asset_paths)) != len(asset_paths):
        raise ValueError('Expected unique owned package paths')
    result = {}
    for asset in asset_paths:
        if not isinstance(asset, str) or not asset.startswith('/Game/'):
            raise ValueError('Expected a /Game package path without object suffix')
        relative = asset[len('/Game/'):]
        if not relative or any(part in ('', '.', '..') for part in relative.split('/')) or '.' in relative:
            raise ValueError('Invalid package path')
        for suffix in SIDECARS:
            path = root / (relative + suffix)
            if suffix == '.uasset' or os.path.lexists(path):
                path = _regular(path, root)
                result[path.relative_to(root).as_posix()] = {'sha256': file_digest(path), 'size': path.stat().st_size}
    return result


def _hex(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def save_unit(path, *, identity, policy, content_root, assets, geometry, metadata):
    """@cc [owner:fontanierh,label:correctness] partial-unit-is-not-build-success
    A unit record MUST remain a local hint. Its complete package inventory and
    current input/policy identities MUST be checked on load; the caller MUST
    additionally validate loaded geometry, settings and materials before reuse.
    No whole-task success stamp or portable action certificate is produced.
    """
    if not _hex(identity) or not _hex(policy) or not isinstance(metadata, dict):
        raise ValueError('Invalid unit identity or metadata')
    if not isinstance(geometry, dict) or not geometry or any(not isinstance(k, str) or not _hex(v) for k, v in geometry.items()):
        raise ValueError('Invalid unit geometry digests')
    record = {'schema': 1, 'identity': identity, 'policy': policy, 'assets': list(assets),
              'geometry': geometry, 'metadata': metadata, 'files': package_inventory(content_root, assets)}
    target = Path(path).absolute()
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise ValueError('Linked unit record path')
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, sort_keys=True, allow_nan=False).encode('utf-8')
    descriptor, temporary = tempfile.mkstemp(prefix='.mesh-unit-', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return record


def load_unit(path, *, identity, policy, content_root, assets):
    """Return a byte-checked candidate, or a normal miss on optional bad data."""
    try:
        path = Path(path).absolute()
        _regular(path, path.parent)
        record = json.loads(path.read_text(encoding='utf-8'))
        if (not _hex(identity) or not _hex(policy) or not isinstance(record, dict) or record.get('schema') != 1
                or record.get('identity') != identity or record.get('policy') != policy
                or record.get('assets') != list(assets)
                or not isinstance(record.get('metadata'), dict) or not isinstance(record.get('geometry'), dict)
                or not record['geometry'] or any(not isinstance(k, str) or not _hex(v) for k, v in record['geometry'].items())
                or record.get('files') != package_inventory(content_root, assets)):
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None
