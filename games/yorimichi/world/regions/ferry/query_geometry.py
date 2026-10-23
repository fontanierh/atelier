"""Ferry query composition from explicit geometry data, before any mesh export."""
import json
import math
from pathlib import Path

import numpy as np

from atelier.export_manifest import real_directory, sha
import region_query
from hidamari.logical_catalogue import ASSETS as CITY
from brinecove.logical_catalogue import PARENTS as COAST


def regular(build, relative, sources):
    path = Path(build) / relative
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or linked ferry query input: ' + relative)
    sources[relative] = sha(path)
    return path


def surface(build, owner, sources, *, city=False):
    raw = city and owner == 'HD_Harbor'
    relative = ('hidamari' if city else 'brinecove') + '/query-data/' + owner + ('.raw.npz' if raw else '.npz')
    path = regular(build, relative, sources)
    result = region_query.load(path, owner=owner, stage='raw' if raw else 'final')
    if sha(path) != sources[relative]:
        raise ValueError('Ferry query input changed while reading')
    return result


def hidamari(build, bounds, *, clip, placement, z_band, water_z):
    """@cc [owner:fontanierh,label:correctness;performance] ferry-city-query-before-cut
    The sweep MUST consume raw Harbor and final terrain/placed source data before
    final Harbor cutting or any city FBX export. Apply the original instance frame
    exactly once, include every actual whole hull once, and retain refusal for
    foreign placements standing in water. No export fallback is permitted.
    """
    sources, names, skipped = {}, ['HD_Harbor'], []
    ground = [clip(region_query.triangles(surface(build, 'HD_Terrain', sources, city=True)), bounds)]
    path = regular(build, 'terrain/FarHills/final.npz', sources)
    with np.load(path, allow_pickle=False) as hills:
        ground.append(clip(hills['vertices'][hills['triangles']], bounds))
    solid = [clip(region_query.triangles(surface(build, 'HD_Harbor', sources, city=True)), bounds, z_band)]
    path = regular(build, 'hidamari/layout-data.json', sources)
    city = json.loads(path.read_text())
    x0, y0, x1, y1 = bounds
    for owner, rows in sorted(city['instances'].items()):
        if (not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != 5
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
                or row[4] == 0 for row in rows)):
            raise ValueError('Invalid city ferry instance frame')
        rows = [row for row in rows if x0-30 <= row[0] <= x1+30 and y0-30 <= row[1] <= y1+30]
        if rows and owner not in CITY:
            skipped.extend([[owner] + [round(value, 2) for value in row] for row in rows])
        if not rows or owner not in CITY: continue
        geometry = surface(build, owner, sources, city=True)
        for row in rows:
            solid.append(clip(region_query.triangles(geometry, placement=placement(row)), bounds, z_band))
            names.append(owner)
    wet = [row for row in skipped if row[3] <= water_z]
    if wet:
        raise ValueError('City foreign placements stand in the ferry water: ' + str(wet))
    for relative, expected in sources.items():
        if sha(Path(build) / relative) != expected:
            raise ValueError('City ferry input changed during composition')
    return np.concatenate(ground), solid, names, sources, dict(frame='world metres', skipped_placements=skipped)


def brinecove(build, bounds, *, clip, placement, z_band):
    """@cc [owner:fontanierh,label:correctness;performance] ferry-coastal-query-before-exports
    Require the complete logical coastal query roster and exact per-source hashes.
    Use its original transforms and origin, never a rendered child or exported GLB.
    Keep ground, hero obstacles and procedural solids in their original roles.
    Missing, extra, duplicate or stale geometry MUST refuse rather than disappear.
    """
    sources, names, ground, solid = {}, [], [], []
    path = regular(build, 'brinecove-data/query-data.json', sources)
    data = json.loads(path.read_text())
    if (set(data) != {'schema', 'stage', 'origin_cm', 'models'}
            or data.get('schema') != 1 or data.get('stage') != 'final' or not isinstance(data.get('models'), list)
            or len(data['models']) != len(COAST) or {row['owner'] for row in data['models']} != set(COAST)):
        raise ValueError('Incomplete coastal ferry query ownership')
    origin = np.asarray(data['origin_cm'])
    if origin.shape != (3,) or origin.dtype.kind not in 'fi' or not np.isfinite(origin).all():
        raise ValueError('Invalid coastal ferry query origin')
    for row in data['models']:
        owner = row['owner']
        expected = 'brinecove/query-data/' + owner + '.npz'
        if (set(row) != {'owner', 'path', 'sha256', 'transforms'}
                or row['path'] != expected or not isinstance(row['transforms'], list) or not row['transforms']):
            raise ValueError('Invalid coastal ferry source or placements')
        geometry = surface(build, owner, sources)
        if sources[expected] != row['sha256']:
            raise ValueError('Coastal ferry query differs from its current source data')
        for transform in row['transforms']:
            sizes = {'translation_cm': 3, 'rotation_xyzw': 4, 'scale': 3}
            if (not isinstance(transform, dict) or set(transform) != set(sizes)
                    or any(not isinstance(transform[key], list) or len(transform[key]) != size
                           or any(type(v) not in (int, float) or not math.isfinite(v) for v in transform[key])
                           for key, size in sizes.items())
                    or any(value == 0 for value in transform['scale'])
                    or abs(sum(value*value for value in transform['rotation_xyzw'])-1) > 1e-3):
                raise ValueError('Invalid coastal ferry instance frame')
            triangles = region_query.triangles(geometry, placement=placement(transform))
            if owner == 'SM_BC_Ground': ground.append(clip(triangles, bounds))
            else:
                solid.append(clip(triangles, bounds, z_band)); names.append(owner)
    for relative, expected in sources.items():
        if sha(Path(build) / relative) != expected:
            raise ValueError('Coastal ferry input changed during composition')
    return np.concatenate(ground), solid, names, sources, dict(frame='brinecove-local metres', origin_cm=data['origin_cm'])
