"""Selected v4 placement data; the established native-to-island frame stays fixed."""
from functools import lru_cache
import json
import math
from pathlib import Path

import numpy as np

from . import dsl, v4_config


def document():
    doc = v4_config.load_document()
    if float(doc.get('frame', {}).get('lift', 680.)) != 680.:
        raise ValueError('v4 frame.lift must match the established 680 m coordinate frame')
    return doc


def depth(default=45.):
    """Read an explicit natural-caldera depth; other excavation kinds need an implementation."""
    dig = document().get('ground', {}).get('dig')
    if not dig:
        return default
    if dig.get('kind') != 'depth':
        raise ValueError('v4 world terrain currently requires ground.dig.kind=depth')
    value = float(dig['DEPTH'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('v4 caldera DEPTH must be finite and positive')
    return value


def site_polygon():
    """The explicit design envelope is an exclusion mask, not design acceptance."""
    doc = document()
    site = dict(doc.get('site', {}))
    source = v4_config.design_path()
    ref = site.get('file')
    for candidate in site.get('prefer', []):
        p = Path(candidate).expanduser()
        if (p if p.is_absolute() else source.parent / p).is_file():
            ref = candidate
            break
    if ref:
        p = Path(ref).expanduser()
        external = json.loads((p if p.is_absolute() else source.parent / p).read_text())
        site = {**external, **site}
    polygon = site.get('buildable')
    if polygon is None:
        polygon = site.get('buildable_polygon', {}).get('coordinates', [None])[0]
    if doc.get('editor'):
        # the editor's inner terrain grid (native x, z), which bounds everything the editor can place
        meta = json.loads((v4_config.design_path().parent / 'data' / 'terrain.json').read_text())['inner']
        x0, z0, x1, z1 = meta['x0'], meta['z0'], meta['x0'] + meta['G'] * meta['nx'], meta['z0'] + meta['G'] * meta['nz']
        polygon = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]]
    q = np.asarray(polygon, 'f8')
    if q.ndim != 2 or q.shape[0] < 3 or q.shape[1] != 2 or not np.isfinite(q).all():
        raise ValueError('v4 site needs an explicit finite native xz buildable polygon')
    return q


def contains(x, y, margin=0.):
    from .. import placement
    q = site_polygon()
    p = placement.native_to_island(np.c_[q[:, 0], np.zeros(len(q)), q[:, 1]])[:, :2]
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    inside = np.zeros(x.shape, bool)
    distance = np.full(x.shape, np.inf)
    for a, b in zip(p, np.roll(p, -1, axis=0)):
        if abs(b[1]-a[1]) > 1e-12:
            inside ^= ((a[1] > y) != (b[1] > y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
        ab = b-a
        t = np.clip(((x-a[0])*ab[0]+(y-a[1])*ab[1])/max(float(ab@ab), 1e-30), 0, 1)
        distance = np.minimum(distance, np.hypot(x-a[0]-t*ab[0], y-a[1]-t*ab[1]))
    return (inside | (distance <= max(float(margin), 1e-8))) if margin >= 0 else inside & (distance >= -margin)


def geometry_path():
    import yori
    return yori.OUT / 'craterpark' / 'v2' / 'geometry.npz'


def identity():
    """Cache key includes both geometry and its current selected input hashes."""
    path = geometry_path()
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, v4_config.provenance()['source_sha256']


@lru_cache(maxsize=2)
def _geometry(path, mtime_ns, size, ctime_ns, source_sha):
    """@cc [owner:fontanierh,label:correctness] v4-current-placement-geometry
    Placement geometry MUST identify the selected design and input bytes.
    Missing, stale or non-v4 geometry MUST fail without reading legacy meshes.
    """
    with np.load(path, allow_pickle=False) as data:
        index = json.loads(str(data['index']))
        if index.get('v4', {}).get('source_sha256') != source_sha:
            raise ValueError('v4 placement geometry is missing current design provenance; rebuild geometry')
        validation=index.get('validation', {})
        cosmetic=validation.get('preview') and validation.get('failed') and all(
            name in ('outlines','facets','uv_stretch','slivers') for name in validation['failed'])
        supports=validation.get('supports', {})
        # an editor playtest park is the owner's own design, exported as drawn; supports are not built yet (owner)
        if index.get('editor_playtest'):
            pass
        elif (not index.get('accepted') or not validation.get('ran') or not (validation.get('ok') or cosmetic)
                or not supports.get('ran') or not supports.get('ok')):
            raise ValueError('v4 placement requires accepted structural and support validation')
        ground, pieces = [], []
        for i, _ in enumerate(index['render']):
            mesh = dsl.Mesh.from_arrays(data, f'r{i}_')
            triangles = mesh.triangles()
            ground.append(triangles[mesh.role == dsl.ROLE[dsl.GROUND]])
            pieces.append(triangles[np.isin(mesh.role, [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL)])])
        if index.get('ground_grid'):
            # an editor park draws no ground of its own: its ground is the cut grid where the volcano takes it in full
            ground.append(_grid_triangles(index['ground_grid'], data['ground_height'], data['ground_weight']))
        g = np.concatenate(ground) if ground else np.empty((0, 3, 3))
        p = np.concatenate(pieces) if pieces else np.empty((0, 3, 3))
        if not len(g) or not len(p):
            raise ValueError('v4 placement geometry requires ground and riding structure')
        return g, p, index


def _grid_triangles(g, heights, weight):
    """Native triangles (n, 3, 3) of the grid's cells whose four corners have weight 1."""
    full = np.asarray(weight) >= 1
    cell = full[:-1, :-1] & full[1:, :-1] & full[:-1, 1:] & full[1:, 1:]
    x = g['x0'] + (np.arange(g['nx']) + .5) * g['G']
    z = g['z0'] + (np.arange(g['nz']) + .5) * g['G']
    X, Z = np.meshgrid(x, z)
    V = np.c_[X.ravel(), np.asarray(heights, 'f8').ravel(), Z.ravel()]
    jj, ii = np.nonzero(cell)
    a = jj * g['nx'] + ii
    b, c, d = a + 1, a + g['nx'], a + g['nx'] + 1
    return V[np.concatenate([np.c_[a, c, b], np.c_[b, c, d]])]


def ground_grid():
    """The editor park's cut ground as the volcano's terrain takes it: (grid, heights, weight) on the editor's
    cell-centred native grid (heights native y, weight 0-1), or None for a park that draws its own ground."""
    return _ground_grid(*identity())


@lru_cache(maxsize=2)
def _ground_grid(path, mtime_ns, size, ctime_ns, source_sha):
    index = _geometry(path, mtime_ns, size, ctime_ns, source_sha)[2]
    if not index.get('ground_grid'):
        return None
    with np.load(path, allow_pickle=False) as data:
        heights, weight = data['ground_height'].astype('f8'), data['ground_weight'].astype('f8')
    g = index['ground_grid']
    if heights.shape != (g['nz'], g['nx']) or weight.shape != heights.shape or not np.isfinite(heights).all():
        raise ValueError('v4 editor ground grid is malformed; rebuild geometry')
    return g, heights, weight


def triangles(ground):
    from .. import placement
    groups = _geometry(*identity())
    return placement.native_to_island(groups[0 if ground else 1])


def drop_in():
    """Use the same collision-checked first line start exported to the game."""
    document()
    index = _geometry(*identity())[2]
    if not index.get('lines'):
        raise ValueError('v4 geometry has no checked line spawns')
    spawn = index['lines'][0]['spawn']
    ue = np.asarray(spawn['location_cm'], 'f8')
    yaw = float(spawn['yaw_deg'])
    if ue.shape != (3,) or not np.isfinite(ue).all() or not math.isfinite(yaw):
        raise ValueError('v4 checked spawn is invalid')
    p = ue[[0, 1, 2]] * np.array([.01, -.01, .01])
    a = math.radians(yaw)
    return p, p + np.array([-8*math.cos(a), 8*math.sin(a), 6.])


def summary():
    from .. import placement
    points = triangles(True).reshape(-1, 3)
    return {'version': 4, 'centre': placement.CENTRE, 'heading': placement.HEADING, 'lift': placement.LIFT,
            'bounds_min': points.min(0).tolist(), 'bounds_max': points.max(0).tolist(),
            'drop_in': drop_in()[0].tolist(), 'unreal': placement.unreal_transform(),
            'provenance': v4_config.provenance()}
