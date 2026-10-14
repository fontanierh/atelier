"""Deterministic metadata for explicitly portable, static Blender FBX exports.

The installed exporter is part of the action's tool identity. This narrow adapter scopes its
header clock and ID allocator to one export; it does not alter geometry or material slots.
"""
from contextlib import contextmanager
import datetime
import hashlib
import json


def stable_id(key):
    if isinstance(key, int) and 0 <= key < 2 ** 63:
        return key
    if not isinstance(key, (str, tuple)):
        raise ValueError(f'Unsupported FBX identifier key: {type(key).__name__}')
    encoded = json.dumps(key, ensure_ascii=True, separators=(',', ':')).encode()
    return max(1, int.from_bytes(hashlib.sha256(encoded).digest()[:8], 'little') & (2 ** 63 - 1))


@contextmanager
def stable_export():
    """@cc [owner:fontanierh,label:correctness] deterministic-fbx-metadata
    Portable exports MUST use stable metadata and IDs independent of process hash seeds,
    wall time and preceding exports. Exporter state MUST be restored even on failure.
    """
    from io_scene_fbx import export_fbx_bin, fbx_utils

    header, allocate = export_fbx_bin.fbx_header_elements, fbx_utils._key_to_uuid
    keys, ids = fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys

    def fixed_header(root, scene_data):
        return header(root, scene_data, time=datetime.datetime(1970, 1, 1))

    def fixed_id(used, key):
        value = stable_id(key)
        if value in used:
            raise ValueError('FBX identifier collision; export cannot be certified deterministic')
        return fbx_utils.UUID(value)

    export_fbx_bin.fbx_header_elements = fixed_header
    fbx_utils._key_to_uuid = fixed_id
    fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys = {}, {}
    try:
        yield
    finally:
        export_fbx_bin.fbx_header_elements = header
        fbx_utils._key_to_uuid = allocate
        fbx_utils._keys_to_uuids, fbx_utils._uuids_to_keys = keys, ids
