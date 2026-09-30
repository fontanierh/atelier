"""Skate pier, its path and the trick skateboard (docs/SKATE.md).

blender -b --threads 6 --python-exit-code 1 --python japan/skatepark/build.py [-- --review]

Writes build/yorimichi/skatepark/{assets,board}/*.fbx, SkatePark.blend, build-report.json and the
committed gameplay contract japan/skatepark/park.json. --review also renders the review
images into build/yorimichi/skatepark/review/ (EEVEE).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import layout as L
import geom
import board
import features

OUT = yori.OUT / 'skatepark'
PARK_MESHES = [('SM_SkatePier', True, 'concrete deck, edge beam, perimeter railing (blocks, not grindable), lamp posts'),
               ('SM_SkatePierPilings', True, 'concrete piles and pile caps under the deck'),
               ('SM_SkateParkFeatures', True, 'ramps (painted concrete), ledges, stairs, steel coping/edges, painted rails'),
               ('SM_SkatePath', True, 'concrete path from the road to the pier, with retaining skirts'),
               ('SM_SkateParkDecals', False, 'faded floor paint 4 mm above the deck (visual only, no collision)')]


def material():
    mat = bpy.data.materials.new('SkateParkPalette'); mat.use_nodes = True
    nodes = mat.node_tree.nodes; vc = nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Color'
    bsdf = nodes.get('Principled BSDF')
    mat.node_tree.links.new(vc.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = .92
    bsdf.inputs['Specular IOR Level'].default_value = .10
    return mat


def bounds(m):
    V = np.array(m.verts); return V.min(axis=0), V.max(axis=0)


# ----------------------------------------------------------------------------- checks
def check_board(deck, truck, wheel):
    c = board.contract(); out = {}
    lo, hi = bounds(deck)
    V = np.array(deck.verts)
    top_centre = max(V[np.hypot(V[:, 0], V[:, 1]) < 1e-9][:, 2])
    under = V[(np.abs(V[:, 0] - c['truck_x']) < 1e-9) & (np.abs(V[:, 1]) < 1e-9) & (V[:, 2] < -1e-3)][:, 2]
    tip = V[np.abs(V[:, 0] - c['length'] / 2) < 1e-9]
    out['deck'] = {'length_top_cm': round(100 * (tip[:, 0].max() - (-tip[:, 0].max())), 3),
                   'width_cm': round(100 * (hi[1] - lo[1]), 3),
                   'top_centre_z_cm': round(100 * float(top_centre), 4),
                   'nose_rise_cm': round(100 * float(tip[:, 2].max()), 3),
                   'concave_cm': round(100 * float(V[(np.abs(V[:, 0]) < 1e-9)][:, 2].max()), 3),
                   'underside_at_truck_cm': [round(100 * float(z), 3) for z in under],
                   'bounds_cm': [list(np.round(100 * lo, 2)), list(np.round(100 * hi, 2))], 'triangles': deck.triangles}
    Vt = np.array(truck.verts); lo, hi = bounds(truck)
    axle = Vt[np.abs(Vt[:, 1]) > 0.09]
    out['truck'] = {'origin': 'baseplate top centre (0,0,0)', 'top_z_cm': round(100 * float(hi[2]), 4),
                    'axle_z_cm': round(100 * float(axle[:, 2].mean()), 3), 'axle_ends_cm': round(100 * float(np.abs(Vt[:, 1]).max()), 2),
                    'bounds_cm': [list(np.round(100 * lo, 2)), list(np.round(100 * hi, 2))], 'triangles': truck.triangles}
    Vw = np.array(wheel.verts); lo, hi = bounds(wheel)
    out['wheel'] = {'radius_cm': round(100 * float(np.hypot(Vw[:, 0], Vw[:, 2]).max()), 3), 'width_cm': round(100 * float(hi[1] - lo[1]), 3),
                    'centre_cm': list(np.round(100 * (lo + hi) / 2, 4)), 'triangles': wheel.triangles}
    placed_axle = c['truck_z'] + out['truck']['axle_z_cm'] / 100
    out['assembled'] = {'axle_z_cm': round(100 * placed_axle, 3), 'ground_z_cm': round(100 * (placed_axle - out['wheel']['radius_cm'] / 100), 3),
                        'wheel_centres_y_cm': [-100 * c['wheel_y'], 100 * c['wheel_y']], 'truck_x_cm': [-100 * c['truck_x'], 100 * c['truck_x']],
                        'triangles_total': deck.triangles + 2 * truck.triangles + 4 * wheel.triangles}
    assert abs(out['deck']['top_centre_z_cm']) < 1e-6
    assert abs(out['deck']['length_top_cm'] - 80) < 0.01 and abs(out['deck']['width_cm'] - 20.5) < 0.01
    assert abs(out['deck']['nose_rise_cm'] - 4.5) < 0.01 and abs(out['deck']['concave_cm'] - 0.9) < 0.01
    assert all(abs(z + 1.2) < 1e-6 for z in out['deck']['underside_at_truck_cm'])
    assert abs(out['truck']['top_z_cm']) < 1e-6 and abs(out['assembled']['axle_z_cm'] + 6.35) < 1e-6
    assert abs(out['wheel']['radius_cm'] - 2.65) < 0.02
    return out


def segment_angles(prof):
    a = np.array(prof); d = np.diff(a, axis=0); ang = np.degrees(np.arctan2(d[:, 1], np.abs(d[:, 0])))
    return float(np.abs(np.diff(ang)).max()), float(ang[0]), float(ang[-1])


def check_profiles():
    out = {}
    p, toe, radii = L.big_qp_profile()
    s, a0, a1 = segment_angles(p[:-1])
    out['big_quarter'] = {'toe_x': toe, 'lip_x': L.BIG_QP['lip_x'], 'height': p[-1][1], 'transition_height': p[-2][1], 'vertical_extension': p[-1][1] - p[-2][1],
                          'radius_floor_to_top': radii, 'max_step_deg': s, 'toe_angle_deg': a0, 'top_angle_deg': a1, 'width': L.BIG_QP['y1'] - L.BIG_QP['y0']}
    p, toe, top = L.mini_qp_profile(); s, a0, a1 = segment_angles(p)
    out['mini_quarter'] = {'toe_x': toe, 'lip_x': L.MINI_QP['lip_x'], 'height': p[-1][1], 'radius': L.MINI_QP['radius'], 'max_step_deg': s,
                           'toe_angle_deg': a0, 'top_angle_deg': top, 'width': L.MINI_QP['y1'] - L.MINI_QP['y0']}
    p, r, ang = L.kicker_profile(); s, a0, a1 = segment_angles(p)
    out['kicker'] = {'height': p[-1][1], 'run': p[-1][0] - p[0][0], 'radius': r, 'exit_angle_deg': ang, 'max_step_deg': s, 'toe_angle_deg': a0}
    p, flat = L.funbox_profile(); s, a0, a1 = segment_angles(p)
    out['funbox'] = {'height': L.FUNBOX['height'], 'flat_top': flat, 'length': p[-1][0] - p[0][0], 'max_step_deg': s, 'toe_angle_deg': a0,
                     'bank_angle_deg': math.degrees(math.atan2(L.FUNBOX['height'], L.FUNBOX['top0'] - L.FUNBOX['x0']))}
    p = L.platform_bank_profile(); s, a0, a1 = segment_angles(p)
    out['platform_bank'] = {'toe_y': p[0][0], 'top_y': p[-1][0], 'height': p[-1][1], 'length': p[0][0] - p[-1][0], 'max_step_deg': s, 'toe_angle_deg': a0, 'top_angle_deg': a1}
    p = L.south_bank_profile(); s, a0, a1 = segment_angles(p)
    out['south_bank'] = {'toe_y': p[0][0], 'top_y': p[-1][0], 'height': p[-1][1], 'max_step_deg': s, 'toe_angle_deg': a0, 'face_angle_deg': a1}
    for k, v in out.items():
        assert v['max_step_deg'] <= 5.0 + 1e-6, (k, v['max_step_deg'])
        assert abs(v['toe_angle_deg']) < 3.0, (k, 'ramp does not meet the floor tangentially')
    return out


def check_rails(rails, meshes):
    """Every rail point must lie on the modelled surface (within 1 cm)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    verts = []; polys = []
    for m in meshes:
        b = len(verts); verts += m.verts; polys += [tuple(i + b for i in f) for f in m.faces]
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)
    out = {}
    for r in rails:
        d = [tree.find_nearest(Vector(p))[3] for p in r['points']]
        out[r['id']] = round(max(d) * 1000, 2)
    worst = max(out.values())
    assert worst < 10.0, ('rail off its edge (mm)', {k: v for k, v in out.items() if v >= 10})
    return {'max_distance_mm': out, 'worst_mm': worst}


def check_path(pl, rows, h):
    from village.layout import upper_surface
    ox, oy, oz = L.ORIGIN
    R = np.array(rows) + np.array([ox, oy, oz])            # (samples, offsets, 3) world
    centre = R[:, len(L.PATH_OFFSETS) // 2]
    ds = np.linalg.norm(np.diff(centre[:, :2], axis=0), axis=1)
    grade_c = np.abs(np.diff(centre[:, 2])) / ds
    edge_grades = []
    for j in (0, len(L.PATH_OFFSETS) - 1):
        e = R[:, j]; de = np.linalg.norm(np.diff(e[:, :2], axis=0), axis=1)
        edge_grades.append(float((np.abs(np.diff(e[:, 2])) / de)[1:].max()))
    # dense clearance over the whole surface against the upper triangulation envelope
    clear = []
    for k in range(len(R) - 1):
        for a in np.linspace(0, 1, 4):
            for j in range(len(L.PATH_OFFSETS) - 1):
                for b in np.linspace(0, 1, 4):
                    p = (R[k, j] * (1 - b) + R[k, j + 1] * b) * (1 - a) + (R[k + 1, j] * (1 - b) + R[k + 1, j + 1] * b) * a
                    clear.append(p[2] - float(upper_surface(h, p[0], p[1])))
    clear = np.array(clear)
    skirt = []
    for j in (0, len(L.PATH_OFFSETS) - 1):
        e = R[:, j]; skirt.append(e[:, 2] - np.array([float(upper_surface(h, x, y)) for x, y in e[:, :2]]))
    skirt = np.max(skirt, axis=0); s_ = np.r_[0, np.cumsum(ds)]
    bands = {f'{a}-{b}m': round(float(skirt[(s_ >= a) & (s_ < b)].max()), 2) for a, b in ((0, 10), (10, 25), (25, 45), (45, 65), (65, 85), (85, 100), (100, 112))}
    end = R[-1]
    heading = np.degrees(np.arctan2(np.diff(centre[:, 1]), np.diff(centre[:, 0])))
    turn = np.abs((np.diff(heading) + 180) % 360 - 180)
    out = {'length_m': float(np.sum(ds)), 'start_world': centre[0].round(3).tolist(), 'end_world': centre[-1].round(3).tolist(),
           'max_grade_centre_pct': float(grade_c[1:].max() * 100), 'max_grade_edges_pct': [g * 100 for g in edge_grades],
           'min_clearance_above_terrain_m': float(clear.min()), 'mean_height_above_terrain_m': float(clear.mean()),
           'max_height_above_terrain_m': float(clear.max()), 'end_ring_local_z_m': float(np.abs(end[:, 2] - oz).max()),
           'end_ring_local_y_m': float(end[0, 1] - oy), 'min_turn_radius_m': float(min(r for r in pl['radii'])),
           'max_heading_change_per_sample_deg': float(turn.max()), 'max_edge_height_above_terrain_by_distance_m': bands}
    assert out['max_grade_centre_pct'] <= 10.0 and max(out['max_grade_edges_pct']) <= 10.0, out
    assert out['min_clearance_above_terrain_m'] > 0.0, out
    assert out['end_ring_local_z_m'] < 1e-6 and abs(out['end_ring_local_y_m'] - L.HALF_Y) < 1e-6
    return out


def house_clearance(pl, world):
    """Distances from the path's edges to the houses on the main road (world['houses']): to the nearest roof
    footprint and to the nearest lot outline (hedge, kerb and walls). Lots are in their own frame (houses/layout.py)."""
    P = pl['P']; n = pl['n']; E = np.concatenate([P + n * o for o in (-L.PATH_HALF, L.PATH_HALF)])[:, :2]
    roof, lot_edge = [], []
    for lot in world['houses']['lots']:
        a = math.radians(lot['yaw']); c, s = math.cos(a), math.sin(a)
        dx = E[:, 0] - lot['centre'][0]; dy = E[:, 1] - lot['centre'][1]
        lx = dx * c + dy * s; ly = -dx * s + dy * c
        fx0, fx1, fy0, fy1 = lot['house_roof']
        roof.append(float(np.hypot(np.maximum(0, np.maximum(fx0 - lx, lx - fx1)), np.maximum(0, np.maximum(fy0 - ly, ly - fy1))).min()))
        Q = np.array(lot['polygon'], float); A = Q; B = np.roll(Q, -1, axis=0); D = B - A
        X = np.stack([lx, ly], 1)[:, None, :]
        t = np.clip(((X - A) * D).sum(-1) / (D * D).sum(-1), 0, 1)
        dist = np.linalg.norm(X - (A + t[..., None] * D), axis=-1).min(1)
        inside = np.zeros(len(X), bool)                       # even-odd rule
        for (x0, y0), (x1, y1) in zip(A, B):
            cross = (y0 > ly) != (y1 > ly)
            inside ^= cross & (lx < x0 + (ly - y0) * (x1 - x0) / np.where(y1 == y0, 1e-9, y1 - y0))
        lot_edge.append(float(np.where(inside, -dist, dist).min()))
    return min(roof), min(lot_edge)


def check_joins(pier, feats, path):
    """Ramp toes and the path's last ring share vertices with the deck floor: no lips, no cracks."""
    floor = {tuple(np.round(v, 5)) for v in pier.verts if abs(v[2]) < 1e-9}
    toes = set()
    for f, tag in zip(feats.faces, feats.tags):
        if tag == 'paint':
            for i in f:
                v = feats.verts[i]
                if abs(v[2]) < 1e-9: toes.add(tuple(np.round(v, 5)))
    missing = [t for t in toes if t not in floor]
    end = [tuple(np.round(v, 5)) for v in path.verts if abs(v[1] - L.HALF_Y) < 1e-6 and abs(v[2]) < 1e-6]
    path_missing = [t for t in end if t not in floor]
    assert not missing, ('ramp toe vertices off the floor grid', missing[:5])
    assert end and not path_missing, ('path end ring off the deck edge', path_missing[:5])
    return {'ramp_toe_vertices': len(toes), 'toe_vertices_not_on_floor': len(missing), 'path_end_vertices': len(end), 'path_end_not_on_floor': len(path_missing)}


def fbx_roundtrip(meshes):
    """Re-import every exported FBX and compare its bounds with the source (units and axes)."""
    out = {}
    for m, path in meshes:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(path))
        new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        V = np.array([o.matrix_world @ v.co for o in new for v in o.data.vertices])
        lo, hi = bounds(m)
        err = float(max(np.abs(V.min(axis=0) - lo).max(), np.abs(V.max(axis=0) - hi).max()))
        out[m.name] = round(err * 1000, 3)
        for o in new: bpy.data.objects.remove(o, do_unlink=True)
    assert max(out.values()) < 1.0, ('FBX round trip moved geometry (mm)', out)
    return {'max_bounds_error_mm': out}


# ----------------------------------------------------------------------------- park.json
def clearance(pl):
    m = 4.0; ox, oy, _ = L.ORIGIN
    pier = [[ox - L.HALF_X - m, oy - L.HALF_Y - m], [ox + L.HALF_X + m, oy - L.HALF_Y - m], [ox + L.HALF_X + m, oy + L.HALF_Y + m], [ox - L.HALF_X - m, oy + L.HALF_Y + m]]
    P, n, s = pl['P'], pl['n'], pl['s']
    keep = [0] + [k for k in range(1, len(s) - 1) if int(s[k] // 2.0) != int(s[k - 1] // 2.0)] + [len(s) - 1]
    back = P[0] - pl['t'][0] * 2.0                      # reach 2 m back over the road verge
    left = [list(np.round(back + n[0] * 5.0, 2))] + [list(np.round(P[k] + n[k] * 5.0, 2)) for k in keep]
    right = [list(np.round(back - n[0] * 5.0, 2))] + [list(np.round(P[k] - n[k] * 5.0, 2)) for k in keep]
    return [[[float(a), float(b)] for a, b in pier], [[float(a), float(b)] for a, b in left + right[::-1]]]


def park_json(pl, rails):
    ox, oy, oz = L.ORIGIN
    k = int(np.searchsorted(pl['s'], 3.0)); t = pl['t'][k]
    feats = {k_: [round(v, 3) for v in b] for k_, b in L.footprints().items()}
    return {
        'version': 1,
        'doc': 'docs/SKATE.md; built by games/yorimichi/world/regions/skatepark/build.py. Park-local metres: x east, y north, z up (Blender axes), '
               'origin on the deck top at the platform centre. UE: world metres (x, y, z) -> cm (100x, -100y, 100z); '
               'yaw_deg counter-clockwise from +x (UE yaw = -yaw_deg).',
        'origin': [ox, oy, oz], 'yaw_deg': 0.0,
        'deck': {'x': [-L.HALF_X, L.HALF_X], 'y': [-L.HALF_Y, L.HALF_Y], 'top_z': 0.0, 'entrance_x': [L.ENTRANCE_X - 2.5, L.ENTRANCE_X + 2.5]},
        'meshes': [{'name': n_, 'asset': f'/Game/SkatePark/{n_}', 'blocks': b} for n_, b, _ in PARK_MESHES],
        'board': {'deck': '/Game/SkatePark/Board/SM_SkateDeck', 'truck': '/Game/SkatePark/Board/SM_SkateTruck',
                  'wheel': '/Game/SkatePark/Board/SM_SkateWheel', 'truck_offsets_cm': [[18, 0, -1.2], [-18, 0, -1.2]],
                  'back_truck_yaw_deg': 180, 'wheel_offsets_from_truck_cm': [[0, 9.3, -5.15], [0, -9.3, -5.15]], 'wheel_radius_cm': 2.65},
        'rails': rails,
        'spawns': {
            'park': {'pos': [-8.0, 10.0, 0.0], 'yaw_deg': -10.0, 'note': 'park-local; faces the funbox lane and the big quarter pipe'},
            'path_top': {'pos': [round(float(pl['P'][k, 0]), 3), round(float(pl['P'][k, 1]), 3), round(float(pl['z'][k]), 3)],
                         'yaw_deg': round(math.degrees(math.atan2(t[1], t[0])), 2), 'note': 'world metres, 3 m down the path from the road edge'},
        },
        'clearance': clearance(pl),
        'surfaces': {n_: note for n_, _, note in PARK_MESHES},
        'features': feats,
    }


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    review = '--review' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'assets').mkdir(exist_ok=True); (OUT / 'board').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = material()
    world, h = L.load_world()
    report = {}

    # board
    deck, truck, wheel = board.deck(), board.truck(), board.wheel()
    report['board'] = check_board(deck, truck, wheel)
    objs = {}
    for m in (deck, truck, wheel):
        objs[m.name] = geom.to_object(m, mat)
        geom.export_fbx(objs[m.name], OUT / 'board' / f'{m.name}.fbx')
    print('BOARD', report['board']['assembled'], flush=True)

    # park
    pl = L.path_layout(world, h)
    feats = features.park_features()
    pier = features.pier()
    piles = features.pilings(h)
    path, ss, rows = features.path(pl, h)
    paint = features.decals()
    t1 = time.time()
    ao = geom.bake_ao([pier, feats], [pier, feats], skip_tags=('rail', 'railing', 'pole', 'lamp', 'coping'))
    report['ao_seconds'] = round(time.time() - t1, 1)
    report['ao'] = {k: {'mean': round(float(np.mean([c for f in v for c in f])), 3), 'max': round(float(np.max([c for f in v for c in f])), 3),
                        'corners_over_0.3': int(sum(c > 0.3 for f in v for c in f))} for k, v in ao.items()}
    park = {}
    for m in (pier, feats, piles, path, paint):
        cols = geom.shade(m, ao.get(m.name))
        park[m.name] = geom.to_object(m, mat, cols)
        geom.export_fbx(park[m.name], OUT / 'assets' / f'{m.name}.fbx')
    report['meshes'] = {m.name: {'triangles': m.triangles, 'vertices': len(m.verts), 'min': list(np.round(bounds(m)[0], 3)), 'max': list(np.round(bounds(m)[1], 3))}
                        for m in (pier, feats, piles, path, paint, deck, truck, wheel)}

    # contract + checks
    rails = L.rails()
    report['rails'] = check_rails(rails, [feats])
    report['profiles'] = check_profiles()
    report['path'] = check_path(pl, rows, h)
    report['path']['house_roof_clearance_m'], report['path']['house_lot_clearance_m'] = house_clearance(pl, world)
    assert report['path']['house_lot_clearance_m'] > 0, 'the skate path crosses a house lot'
    report['joins'] = check_joins(pier, feats, path)
    report['fbx_roundtrip'] = fbx_roundtrip([(m, OUT / 'assets' / f'{m.name}.fbx') for m in (pier, feats, piles, path, paint)] +
                                            [(m, OUT / 'board' / f'{m.name}.fbx') for m in (deck, truck, wheel)])
    data = park_json(pl, rails)
    (HERE / 'park.json').write_text(json.dumps(data, indent=1) + '\n')
    report['park_json'] = {'origin': data['origin'], 'rails': len(rails), 'rail_points': sum(len(r['points']) for r in rails),
                           'meshes': [m['name'] for m in data['meshes']], 'spawns': data['spawns'], 'bytes': (HERE / 'park.json').stat().st_size}

    # scene for review: board assembled beside the park origin
    for name in ('SM_SkateTruck', 'SM_SkateWheel'):
        objs[name].hide_render = True
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'SkatePark.blend'))
    def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report['identity'] = {'sources': {str(p.relative_to(L.JAPAN)): sha(p) for p in sorted(HERE.glob('*.py'))},
                          'world_sha256': sha(yori.OUT / 'world.json'), 'heightmap_sha256': sha(yori.OUT / 'heightmap.npy'),
                          'exports': {str(p.relative_to(OUT)): sha(p) for p in sorted(list((OUT / 'assets').glob('*.fbx')) + list((OUT / 'board').glob('*.fbx')))},
                          'park_json_sha256': sha(HERE / 'park.json')}
    report['seconds'] = round(time.time() - t0, 1)
    (OUT / 'build-report.json').write_text(json.dumps(report, indent=1, default=float) + '\n')
    print('SKATEPARK BUILD COMPLETE', json.dumps({'triangles': {k: v['triangles'] for k, v in report['meshes'].items()},
                                                 'rails_worst_mm': report['rails']['worst_mm'], 'path': report['path']}, default=float), flush=True)
    if review:
        import review as rv
        rv.render_all(OUT / 'review', park, objs, data, world, h, pl)


if __name__ == '__main__':
    main()
