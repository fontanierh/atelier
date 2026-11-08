"""Export the real geometry around both ferry berths, as the game places it, for site.py's swept-path checks.

Use the ordinary `uv run atelier build yorimichi world.ferry_probes` workflow.
The input is the current checkout's build/yorimichi. Each harbour's triangles inside its plan bounds (site.BOUNDS) are written
to world_<harbour>.npz beside site.json, split into ground (the seabed and shore the keel is checked against) and solid
(everything else the hull outline must keep clear of: quays, piers, breakwater, moored boats, ships, rocks and props),
with the sha256 of every file read, so site.json binds the exact export it was checked against.

- Hidamari (world metres): ground is hidamari/assets/HD_Terrain.fbx and, south of the city, the far hills' product
  terrain/FarHills/final.npz. Solid is HD_Harbor.fbx plus every hidamari/city.json instance whose position lies inside
  the bounds, each asset's exported FBX at the instance's position, yaw (Blender degrees; Unreal applies -yaw) and scale.
  Placements of meshes exported elsewhere (trees, poles, street props) are listed in the probe's meta, and the probe
  fails if one stands at water level.
- Brinecove (region-local metres, the export frame; runtime.json records origin_cm): every brinecove/runtime.json group
  at each of its transforms, read back from Unreal (cm, y flipped, left-handed quaternion) into Blender's frame.
  SM_BC_Ground_* groups are ground; plant groups are left out (they stand on land); every other group is solid.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import importlib.util

import bpy
import numpy as np
from mathutils import Matrix, Quaternion

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('ferry_site', HERE / 'site.py')   # not the stdlib site module
S = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(S)

OUT = S.OUT
Z_BAND = (-(S.DRAFT + S.KEEL_CLEARANCE), S.SHIP_TOP)      # solids that can meet the hull, anywhere along its height
WATER_Z = 0.5                 # a placement this low stands in the water: its mesh must be in the probe


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def import_file(path):
    print(f'FERRY PROBE importing {path.name}', flush=True)
    before = set(bpy.data.objects)
    if path.suffix == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        bpy.ops.import_scene.gltf(filepath=str(path))
    objects = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    print(f'FERRY PROBE imported {path.name}: {len(objects)} meshes', flush=True)
    return objects


def triangles(objs, matrix=Matrix.Identity(4)):
    """World-space triangles (n, 3, 3) of objects, after an extra placement matrix."""
    deps = bpy.context.evaluated_depsgraph_get(); out = []
    for o in objs:
        me = o.evaluated_get(deps).to_mesh(); me.calc_loop_triangles()
        M = np.array(matrix @ o.matrix_world)
        v = np.array([tuple(p.co) for p in me.vertices], float).reshape(-1, 3)
        v = v @ M[:3, :3].T + M[:3, 3]
        t = np.array([tuple(lt.vertices) for lt in me.loop_triangles], int).reshape(-1, 3)
        if len(t):
            out.append(v[t])
        o.evaluated_get(deps).to_mesh_clear()
    return np.concatenate(out) if out else np.zeros((0, 3, 3))


def clip(tris, bounds, band=None):
    """Triangles whose plan box meets the bounds (and whose height range meets the band, when given)."""
    if not len(tris):
        return tris.astype(np.float32)
    lo, hi = tris.min(1), tris.max(1)
    x0, y0, x1, y1 = bounds
    keep = (hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)
    if band is not None:
        keep &= (hi[:, 2] >= band[0]) & (lo[:, 2] <= band[1])
    return tris[keep].astype(np.float32)


def legacy_hidamari(build, bounds=None):
    bounds = S.BOUNDS['hidamari'] if bounds is None else bounds; sources = {}; names = []; skipped = []
    clear_scene()
    path = build / 'hidamari/assets/HD_Terrain.fbx'; sources[str(path.relative_to(build))] = sha(path)
    ground = [clip(triangles(import_file(path)), bounds)]
    clear_scene()
    path = build / 'terrain/FarHills/final.npz'; sources[str(path.relative_to(build))] = sha(path)
    hills = np.load(path)
    ground.append(clip(hills['vertices'][hills['triangles']], bounds))
    path = build / 'hidamari/assets/HD_Harbor.fbx'; sources[str(path.relative_to(build))] = sha(path)
    solid = [clip(triangles(import_file(path)), bounds, Z_BAND)]; names = ['HD_Harbor']
    clear_scene()
    city = build / 'hidamari/city.json'; sources[str(city.relative_to(build))] = sha(city)
    x0, y0, x1, y1 = bounds
    for asset, rows in sorted(json.loads(city.read_text())['instances'].items()):
        rows = [r for r in rows if x0 - 30 <= r[0] <= x1 + 30 and y0 - 30 <= r[1] <= y1 + 30]
        path = build / 'hidamari/assets' / f'{asset}.fbx'
        if rows and not path.exists():          # instanced from another product (trees, poles, props): recorded, and
            skipped += [[asset] + [round(v, 2) for v in r] for r in rows]   # refused below if it stands in the water
        if not rows or not path.exists():
            continue
        sources[str(path.relative_to(build))] = sha(path)
        objs = import_file(path)
        for x, y, z, yaw, scale in rows:
            M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Scale(scale, 4)
            solid.append(clip(triangles(objs, M), bounds, Z_BAND)); names.append(asset)
        clear_scene()
    wet = [r for r in skipped if r[3] <= WATER_Z]
    if wet:
        raise SystemExit(f'hidamari: placements whose mesh is not in hidamari/assets stand in the water: {wet}')
    return np.concatenate(ground), solid, names, sources, {'frame': 'world metres', 'skipped_placements': skipped}


def unreal_to_blender(t):
    """A runtime.json transform (Unreal cm, y flipped, left-handed rotation) as a Blender-frame matrix in metres."""
    x, y, z = t['translation_cm']; qx, qy, qz, qw = t['rotation_xyzw']
    F = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
    R = F @ Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4() @ F
    return Matrix.Translation((x / 100, -y / 100, z / 100)) @ R @ Matrix.Diagonal((*t['scale'], 1.0))


def label(name):
    """SM_BC_Harbor_3_3_Soft -> SM_BC_Harbor: one obstacle label per exported module, not per tile."""
    base, separator, tail = name.rpartition('_')
    if separator and tail.startswith('Piece') and tail[5:] and all(c in '0123' for c in tail[5:]):
        name = base
    parts = [p for p in name.split('_') if not p.isdigit() and p != 'Soft']
    return '_'.join(parts)


def legacy_brinecove(build, bounds=None):
    bounds = S.BOUNDS['brinecove'] if bounds is None else bounds; sources = {}; names = []; ground = []; solid = []
    runtime = build / 'products/brinecove/clearance.json'; sources[str(runtime.relative_to(build))] = sha(runtime)
    data = json.loads(runtime.read_text())
    report = {m['name']: m for m in data['meshes']}
    x0, y0, x1, y1 = bounds
    for g in data['groups']:
        name = g['asset'].rsplit('.', 1)[-1]
        if g['plant'] or name not in report:
            continue
        (lx, ly, _), (hx, hy, _) = report[name]['bounds_m']
        r = math.hypot(hx - lx, hy - ly) / 2 * max(max(t['scale']) for t in g['transforms'])
        cx, cy = (lx + hx) / 2, (ly + hy) / 2
        ts = [t for t in g['transforms'] if x0 - r <= cx + t['translation_cm'][0] / 100 <= x1 + r
              and y0 - r <= cy - t['translation_cm'][1] / 100 <= y1 + r]
        if not ts:
            continue
        path = build / 'brinecove' / report[name]['path']; sources[str(path.relative_to(build))] = sha(path)
        objs = import_file(path)
        for t in ts:
            tris = triangles(objs, unreal_to_blender(t))
            if name.startswith('SM_BC_Ground_'):
                ground.append(clip(tris, bounds))
            else:
                solid.append(clip(tris, bounds, Z_BAND)); names.append(label(name))
        clear_scene()
    return (np.concatenate(ground), solid, names, sources,
            {'frame': 'brinecove-local metres', 'origin_cm': data['origin_cm']})



def city_placement(row):
    x, y, z, yaw, scale = row
    return Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Scale(scale, 4)


def hidamari(build, bounds=None):
    from regions.ferry import query_geometry
    return query_geometry.hidamari(build, S.BOUNDS['hidamari'] if bounds is None else bounds,
        clip=clip, placement=city_placement, z_band=Z_BAND, water_z=WATER_Z)


def brinecove(build, bounds=None):
    from regions.ferry import query_geometry
    return query_geometry.brinecove(build, S.BOUNDS['brinecove'] if bounds is None else bounds,
        clip=clip, placement=unreal_to_blender, z_band=Z_BAND)


def crossing(build):
    """Export every final surface/solid along the sea corridor in the same placement frames as the game."""
    sys.path.insert(0, str(S.REPO / 'games/yorimichi/world'))
    from regions.ferry.route import BOUNDS
    ground, solid, names, sources, _ = hidamari(build, BOUNDS)
    ground = [ground]
    runtime = json.loads((build / 'brinecove-data/query-data.json').read_text())
    ox, oy, oz = runtime['origin_cm']
    origin = np.array((ox / 100, -oy / 100, oz / 100))
    x0, y0, x1, y1 = BOUNDS
    bg, bs, bn, bp, _ = brinecove(build, (x0 - origin[0], y0 - origin[1], x1 - origin[0], y1 - origin[1]))
    ground.append(bg + origin)
    solid += [t + origin for t in bs]; names += bn; sources.update(bp)
    path = build / 'world.json'; sources[str(path.relative_to(build))] = sha(path)
    world = json.loads(path.read_text())
    from region_query import load as query_load, triangles as query_triangles
    for name, rows in sorted(world['instances'].items()):
        if not name.startswith('SW_'):
            continue
        path = build / 'southwest/query' / f'{name}.npz'
        surfaces = query_load(path, owner=name, stage='final')
        sources[str(path.relative_to(build))] = sha(path)
        for x, y, z, yaw, scale in rows:
            matrix = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Scale(scale, 4)
            tris = query_triangles(surfaces, placement=np.asarray(matrix), roles=('render',))
            solid.append(clip(tris, BOUNDS, Z_BAND)); names.append(name)
            if name == 'SW_Island':
                ground.append(clip(tris, BOUNDS))
        print(f'crossing placed {name}: {len(rows)} instances', flush=True)
    return np.concatenate(ground), solid, names, sources, {'frame': 'world metres'}


def main():
    build = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    sys.path.insert(0, str(S.REPO / 'games/yorimichi/world'))
    sys.path.insert(0, str(S.REPO / 'games/yorimichi/world/regions'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (('hidamari', hidamari), ('brinecove', brinecove), ('crossing', crossing)):
        ground, parts, names, sources, frame = fn(build)
        labels = sorted(set(names))
        solid = np.concatenate(parts)
        solid_label = np.concatenate([np.full(len(p), labels.index(n), np.int16) for p, n in zip(parts, names)])
        if not len(ground) or not len(solid):
            raise SystemExit(f'{name}: no ground or no solid geometry inside {S.BOUNDS[name]}')
        np.savez_compressed(OUT / f'world_{name}.npz', ground=ground, solid=solid, solid_label=solid_label,
                            meta=json.dumps({'harbour': name, 'bounds': S.BOUNDS[name] if name != 'crossing' else __import__('regions.ferry.route', fromlist=['BOUNDS']).BOUNDS, 'z_band': Z_BAND, 'labels': labels,
                                             'sources': sources, **frame}))
        print(name, len(ground), 'ground and', len(solid), 'solid triangles from', len(sources), 'files', flush=True)
    print('WORLD PROBE DONE')


if __name__ == '__main__':
    main()
