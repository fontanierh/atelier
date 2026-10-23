"""Job-body helpers for build-v2 D1 (py_data) scripts.

Uses only the Python standard library so it can be staged in a unit's declared code closure and
imported inside the sandboxed Python job child without checkout access.
"""
import json
import math
import os
from pathlib import Path
import struct

RUNTIME_MAGIC = b'ATD1'
RUNTIME_VERSION = 1


def _validate_json_structure(value):
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('py_data JSON numbers must be finite')
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_structure(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('py_data JSON object keys must be strings')
            _validate_json_structure(item)
        return
    raise TypeError(f'unsupported py_data JSON value type: {type(value).__name__}')


def canonical_json_bytes(value):
    """Encode a top-level dict or list into deterministic UTF-8 JSON (sorted keys, compact separators, allow_nan=False, refusing scalar top levels); Rust output validation is semantic."""
    if not isinstance(value, (dict, list, tuple)):
        raise ValueError('py_data top-level JSON value must be an object or array')
    _validate_json_structure(value)
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return text.encode('utf-8')


def read_json(context, slot, default=None):
    """Read and parse a declared JSON input slot, or return default when an optional slot is absent."""
    path = context.inputs.get(slot)
    if path is None:
        if slot not in context.inputs:
            raise LookupError(f'input {slot!r} is not declared')
        if default is not None:
            return default
        raise LookupError(f'input {slot!r} is absent')
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(context, output_name, value):
    """Write canonical UTF-8 JSON to a declared output path."""
    data = canonical_json_bytes(value)
    target = context.output(output_name)
    target.write_bytes(data)
    os.chmod(target, 0o644)
    return target


def compute_route_distances(waypoints):
    """Compute cumulative Euclidean distances (rounded to 6 decimals) along a 3D waypoint list."""
    if not isinstance(waypoints, (list, tuple)) or len(waypoints) < 2:
        raise ValueError('route requires at least two waypoints')
    coords = []
    for point in waypoints:
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise ValueError('each route waypoint must be an [x, y, z] triple')
        xyz = [float(c) for c in point]
        if not all(math.isfinite(c) for c in xyz):
            raise ValueError('route waypoint coordinates must be finite')
        coords.append(xyz)
    distances = [0.0]
    total = 0.0
    for prev, curr in zip(coords, coords[1:]):
        seg = math.sqrt(sum((b - a) ** 2 for a, b in zip(prev, curr)))
        total = round(total + seg, 6)
        distances.append(total)
    if distances[-1] <= 0.0:
        raise ValueError('route total distance must be positive')
    return coords, distances


def write_route(context, output_name, route_id, waypoints, distances_m=None, metadata=None):
    """Validate and write a canonical RouteData JSON payload to a declared output path."""
    if not isinstance(route_id, str) or not route_id.strip():
        raise ValueError('route_id must be a non-empty string')
    coords, computed = compute_route_distances(waypoints)
    if distances_m is None:
        distances = computed
    else:
        if len(distances_m) != len(coords):
            raise ValueError('distances_m length must match waypoints length')
        distances = [float(d) for d in distances_m]
        if not all(math.isfinite(d) for d in distances):
            raise ValueError('distances_m must be finite')
        if distances[0] != 0.0 or distances[-1] <= 0.0:
            raise ValueError('distances_m must start at 0.0 and end at a positive distance')
        for prev, curr in zip(distances, distances[1:]):
            if curr < prev:
                raise ValueError('distances_m must be monotone non-decreasing')
    payload = {
        'route_id': route_id,
        'waypoints': coords,
        'distances_m': distances,
    }
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError('route metadata must be a dict')
        payload['metadata'] = metadata
    return write_json(context, output_name, payload)


def pack_runtime_binary(records):
    """Pack one or more non-empty byte records into an ATD1 v1 binary payload."""
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError('RuntimeData requires at least one binary record')
    out = bytearray(RUNTIME_MAGIC)
    out.extend(struct.pack('>BI', RUNTIME_VERSION, len(records)))
    for record in records:
        if not isinstance(record, (bytes, bytearray, memoryview)) or len(record) == 0:
            raise ValueError('each RuntimeData binary record must be non-empty bytes')
        raw = bytes(record)
        out.extend(struct.pack('>I', len(raw)))
        out.extend(raw)
    return bytes(out)


def write_runtime_binary(context, output_name, records, executable=False):
    """Write a framed ATD1 v1 RuntimeData binary file to a declared output path."""
    payload = pack_runtime_binary(records)
    return write_bytes(context, output_name, payload, executable=executable)


def write_bytes(context, output_name, data, executable=False):
    """Write non-empty raw bytes to a declared output path with explicit 0o644 or 0o755 mode."""
    if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) == 0:
        raise ValueError('py_data binary output must be non-empty bytes')
    target = context.output(output_name)
    target.write_bytes(bytes(data))
    os.chmod(target, 0o755 if executable else 0o644)
    return target
