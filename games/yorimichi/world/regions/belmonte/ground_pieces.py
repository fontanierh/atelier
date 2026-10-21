"""Final query surfaces remain whole; native rendering/collision uses bounded pieces."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401

from atelier.gltf import glb_parts
from atelier.gltf_partition import split
from atelier.model_files import regular_files, retain_files


LIMIT = 32768
NORTH = {'SM_BM_NorthApron', 'SM_BM_NorthCountry'}


def is_ground(name):
    return name in NORTH or name.startswith('SM_BM_BT_Terrain_')


def _plain(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Final ground requires unlinked generated paths')


def prepare(entry, path, folder, *, triangle_limit=LIMIT):
    """@cc [owner:fontanierh,label:correctness] bounded-native-final-ground
    Final ground MUST retain a canonical whole query surface before native subdivision.
    Every native piece MUST preserve the exact encoded triangles/corner attributes and
    fit the declared budget. Queries MUST use the whole final surface, never natural or
    a stale parent mesh. Origin, material slots and identity placements remain unchanged.
    """
    path, folder = Path(path), Path(folder)
    name = entry['name']
    if not is_ground(name) or not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+', name) or entry.get('collision'):
        raise ValueError('Unsupported final ground owner')
    _plain(path); _plain(folder)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('Final ground bytes differ from the producer record')
    low, high = entry['bounds_m']
    bounds = tuple(math.floor(low[i]/512)*512 for i in range(2))
    bounds += tuple(max(bounds[i]+512, math.ceil(high[i]/512)*512) for i in range(2))
    parts = split(raw, bounds, triangle_limit=triangle_limit)
    if sum(part['triangles'] for part in parts) != entry['triangles']:
        raise ValueError('Final ground triangle inventory differs from its geometry')
    doc, _ = glb_parts(raw)
    slots = [int(material['name'].split('_')[1]) for material in doc['materials']]
    surface = {key: entry[key] for key in ('name', 'sha256', 'bounds_m', 'triangles')}
    surface['path'] = 'ground/glb/'+name+'.glb'
    query = folder / surface['path']
    destinations = [path.with_name(name+('_Piece'+part['suffix'] if part['suffix'] else '')+'.glb')
                    for part in parts]
    for destination in [query, *destinations]: _plain(destination)
    query.parent.mkdir(parents=True, exist_ok=True)
    query.write_bytes(raw)
    if len(parts) == 1 and not parts[0]['suffix']:
        return surface, [(entry, slots, True)]
    result = []
    for destination, part in zip(destinations, parts):
        destination.write_bytes(part['data'])
        current = dict(entry, name=destination.stem, path='glb/'+destination.name,
                       sha256=hashlib.sha256(part['data']).hexdigest(), triangles=part['triangles'],
                       bounds_m=[list(row) for row in part['bounds']], parent_bounds_m=entry['bounds_m'],
                       parent_material_slots=slots)
        result.append((current, [slots[i] for i in part['materials']], True))
    return surface, result


def publish(folder, surfaces, origin_cm):
    """Publish only after complete final query membership exists and matches its records."""
    folder = Path(folder)
    data = dict(schema=1, origin_cm=origin_cm, surfaces=surfaces)
    target = folder/'ground/membership.json'; _plain(target)
    _validate(folder, data, complete=False)
    retain_files(folder/'ground/glb', [Path(entry['path']).name for entry in surfaces])
    target.write_text(json.dumps(data, sort_keys=True, separators=(',', ':'))+'\n')


def _validate(folder, data, *, complete):
    _plain(folder)
    if not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('Invalid final ground schema')
    origin = data.get('origin_cm')
    if not isinstance(origin, list) or len(origin) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin):
        raise ValueError('Invalid final ground origin')
    entries = data.get('surfaces')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Missing final ground inventory')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict): raise ValueError('Invalid final ground member')
        name = entry.get('name')
        if (not isinstance(name, str) or not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+', name)
                or not is_ground(name) or name in seen or entry.get('path') != 'ground/glb/'+name+'.glb'
                or type(entry.get('triangles')) is not int or entry['triangles'] < 1):
            raise ValueError('Invalid final ground membership')
        seen.add(name)
        bounds = entry.get('bounds_m')
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(not isinstance(row, list) or len(row) != 3 for row in bounds)
                or any(type(v) not in (int, float) or not math.isfinite(v) for row in bounds for v in row)
                or any(a > b for a, b in zip(*bounds))):
            raise ValueError('Invalid final ground bounds')
        path = folder/entry['path']; _plain(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            raise ValueError('Final ground bytes differ from their complete inventory')
    if not NORTH <= seen:
        raise ValueError('Final northern ground is incomplete')
    if complete and regular_files(folder/'ground/glb') != {Path(e['path']).name for e in entries}:
        raise ValueError('Final ground membership contains undeclared files')
    return data


def load(folder):
    folder = Path(folder)
    path = folder/'ground/membership.json'; _plain(path)
    return _validate(folder, json.loads(path.read_text()), complete=True)


def project(folder, destination):
    data = load(folder)
    destination = Path(destination); _plain(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, sort_keys=True, separators=(',', ':'))+'\n')
    print('BELMONTE FINAL GROUND COMPLETE: '+str(len(data['surfaces']))+' verified query surfaces', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 3: raise ValueError('Expected final ground folder and product path')
    project(sys.argv[1], sys.argv[2])
