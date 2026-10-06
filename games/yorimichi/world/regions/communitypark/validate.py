"""Audit the private source, ground support, riding collision and imported Unreal triangles.

    uv run python games/yorimichi/world/regions/communitypark/validate.py [--imported]

Writes evidence under build/yorimichi/communitypark; never embeds recovered data
in the repository. Import comparison tolerates 0.01 cm FBX float conversion only.
"""
import argparse
from collections import defaultdict
from itertools import permutations, product
import json
from functools import lru_cache
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori
import numpy as np
from communitypark.source import scene
from communitypark import layout as L
from communitypark import structures as S
from communitypark import collision as C, murals, props
from hidamari.layout import north_surface


@lru_cache(maxsize=1)
def placed():
    return L.place(scene().triangles())


def surface_at(x, y):
    """Highest original triangle at a vertical trace, in island metres."""
    hits = S.heights(placed(), x, y, flat=1e-10, edge=1e-8)
    if not len(hits):
        raise ValueError(f'No park surface at {x}, {y}')
    return float(hits.max())


def source_audit():
    s = scene(); t = placed()
    valid = np.linalg.norm(np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]), axis=1) > 1e-10
    riding = t[L.upward(t)]
    samples = []
    # Subdivide large triangles so checking only vertices cannot miss a hill
    # poking through the middle of a flat deck or the floor of a bowl.
    length = np.linalg.norm(riding-np.roll(riding, 1, axis=1), axis=2).max(1)
    subdivisions = np.maximum(1, np.ceil(length/2).astype(int))
    for n in np.unique(subdivisions):
        triangles = riding[subdivisions == n]
        uv = np.array([(i/n, j/n) for i in range(n+1) for j in range(n+1-i)])
        q = triangles[:, None, 0]+uv[None, :, :1]*(triangles[:, None, 1]-triangles[:, None, 0])+uv[None, :, 1:]*(triangles[:, None, 2]-triangles[:, None, 0])
        samples.append(q.reshape(-1, 3))
    points = np.concatenate(samples)
    gap = points[:, 2]-L.ground(points[:, 0], points[:, 1], north_surface)
    assert float(gap.min()) >= .12, ('ground intersects riding surface', float(gap.min()))
    path = L.access(); distance = np.linalg.norm(np.diff(path[:, :2], axis=0), axis=1)
    grade = float((abs(np.diff(path[:, 2]))/distance).max())
    assert grade < .10, grade
    assert abs(surface_at(*L.ENTRY[:2])-L.ENTRY[2]) < .001
    assert abs(surface_at(*L.SPAWN[:2])-L.SPAWN[2]) < .001
    tangent = path[-1, :2]-path[-2, :2]
    normal = np.array([-tangent[1], tangent[0]])/np.linalg.norm(tangent)
    for side in np.linspace(-L.WIDTH/2, L.WIDTH/2, 5):
        point = L.ENTRY[:2]+normal*side
        assert abs(surface_at(*point)-L.ENTRY[2]) < .001, ('entrance crosses a bowl', point.tolist())
    x, y, z = L.grid(north_surface)
    perimeter = np.zeros(z.shape, bool); perimeter[[0, -1], :] = True; perimeter[:, [0, -1]] = True
    np.testing.assert_allclose(z[perimeter], L.carve_access(x, y, north_surface(x, y))[perimeter], atol=1e-8)
    return {'instances': len(s.instances), 'triangles': len(t), 'zero_area_faces': int((~valid).sum()),
            'upward_surface_samples': len(points), 'minimum_ground_clearance_m': float(gap.min()),
            'access_length_m': float(distance.sum()), 'maximum_access_grade': grade,
            'spawn_height_m': surface_at(*L.SPAWN[:2]), 'entry_width_samples': 5}


@lru_cache(maxsize=1)
def riding():
    s = scene()
    parts = [(p['vertices'], p['faces']) for p in s.parts]
    obstacles = {k for k, p in enumerate(s.parts) if p['mesh'] in S.SLENDER}
    return parts, obstacles, C.riding_collision(parts, obstacles)


def riding_audit():
    """No joint lip the skate cannot roll over (12 mm) is left on a riding edge of the hidden collision."""
    parts, obstacles, (vertices, faces, owner, report) = riding()
    before = C.steps(*C.weld(parts), obstacles); after = C.steps(vertices, faces, owner, obstacles)
    pieces = [(p.round(3).tolist(), round(r*1000, 1)) for p, r, k in after if k >= 0]
    assert not pieces, ('joint lips over 12 mm', pieces[:8])
    # Where a ramp's run ends against a third piece (a bowl wall or pad corner), its side cheek keeps up to the
    # original lip there. Those corner samples are counted, not yet ramped.
    return report | {'lips_over_12mm_before': len(before), 'lips_over_12mm_after': len(pieces),
                     'ramp_cheek_samples_over_12mm': len(after)-len(pieces)}


def triangle_error(expected, actual, tolerance=.01):
    """Pair every triangle once, independently of FBX face/vertex ordering.

    Near-duplicate source placements cannot be paired by rounded sorting: a
    rounding boundary can reorder them. Centroid buckets find candidates;
    full precision vertex distances choose the matching face, exactly once.
    """
    assert expected.shape == actual.shape, (expected.shape, actual.shape)
    buckets = defaultdict(list)
    for i, point in enumerate(np.floor(actual.mean(1)).astype(int)):
        buckets[tuple(point)].append(i)
    used = np.zeros(len(actual), bool); orders = np.array(list(permutations(range(3))))
    neighbours = list(product((-1, 0, 1), repeat=3)); worst = 0.
    for triangle in expected:
        centre = np.floor(triangle.mean(0)).astype(int)
        candidates = [i for delta in neighbours for i in buckets.get(tuple(centre+delta), ()) if not used[i]]
        assert candidates, 'Missing imported triangle'
        error = abs(actual[candidates][:, orders]-triangle).max(axis=(2, 3)).min(axis=1)
        k = int(error.argmin()); gap = float(error[k])
        assert gap < tolerance, ('source triangle drift in cm', gap)
        used[candidates[k]] = True; worst = max(worst, gap)
    assert used.all(), 'Unexpected imported triangles'
    return worst


def import_audit():
    s = scene(); report = json.loads((yori.OUT/'communitypark/build-report.json').read_text())
    errors = {}
    for index in range(len(s.gltf['meshes'])):
        expected = np.concatenate([p['vertices'][p['faces']] for p in s.parts if p['mesh'] == index])
        area = np.linalg.norm(np.cross(expected[:, 1]-expected[:, 0], expected[:, 2]-expected[:, 0]), axis=1)
        expected = expected[area > 1e-10]*[100., -100., 100.]
        name = next(n for n in report['meshes'] if n.startswith(f'SM_CP_{index:02d}_'))
        actual = np.fromfile(yori.OUT/'communitypark/import-audit'/f'{name}.triangles.f64', dtype='<f8').reshape(-1, 3, 3)
        assert actual.shape == expected.shape, (name, actual.shape, expected.shape)
        error = triangle_error(expected, actual)
        errors[name] = error
    additions = {}
    structures, metadata = S.build(north_surface)
    decoration = props.build(north_surface, [item['legs'] for item in metadata['frame_footings']])[0]
    for mesh in structures+murals.build()[0]+decoration:
        expected = L.local(mesh.triangles())*[100., -100., 100.]
        actual = np.fromfile(yori.OUT/'communitypark/import-audit'/f'{mesh.name}.triangles.f64', dtype='<f8').reshape(-1, 3, 3)
        additions[mesh.name] = triangle_error(expected, actual)
    vertices, faces = riding()[2][:2]
    actual = np.fromfile(yori.OUT/'communitypark/import-audit/SM_CP_Collision.triangles.f64', dtype='<f8').reshape(-1, 3, 3)
    collision = triangle_error(vertices[faces]*[100., -100., 100.], actual)
    return {'source_meshes': len(errors), 'maximum_triangle_error_cm': max(errors.values()), 'meshes': errors,
            'structures': additions, 'riding_collision_cm': collision}


def member_probes(member):
    """Sample a member's width and depth, rather than only its centreline."""
    a, b = np.array(member['a']), np.array(member['b']); d = b-a
    count = max(1, math.ceil(np.linalg.norm(d[:2])/.25))
    u, v = S.beam_axes(d, member['width'], member['depth'])
    offsets = np.unique(np.round([s*u[:2]+t*v[:2] for s in (-.98, 0, .98) for t in (-.98, 0, .98)], 8), axis=0)
    return (np.linspace(a, b, count+1)[:, None, :2]+offsets).reshape(-1, 2)


def riding_clearance(mesh, metadata, original, source_parts, report_file=None):
    """Check closed steel members against the park's previously usable airspace.

    A vertical pole's top and bottom can both lie outside the body band, so
    testing only surface hits misses it. Each closed member's solid interval
    must stay clear, including the rider's width and up to three metres of
    existing clearance for skating. Normal legs inside recovered grind-feature
    footprints are recorded separately; the main frames get no such exception.
    """
    upward = L.upward(original)
    offsets = np.cumsum([0]+[len(p['faces']) for p in source_parts])
    assert offsets[-1] == len(original)
    parts = [original[a:b] for a, b in zip(offsets, offsets[1:])]
    riding = [part[upward[a:b]] for part, a, b in zip(parts, offsets, offsets[1:])]
    lo = np.asarray([part.min((0, 1))[:2] for part in parts])
    hi = np.asarray([part.max((0, 1))[:2] for part in parts])
    cache = {}
    def query(x, y):
        key = (round(float(x), 6), round(float(y), 6))
        if key not in cache:
            mask = (lo[:, 0] <= x+1e-7) & (hi[:, 0] >= x-1e-7) & (lo[:, 1] <= y+1e-7) & (hi[:, 1] >= y-1e-7)
            solids = []; hits = []; floors = []
            for owner in np.flatnonzero(mask):
                values = np.unique(np.round(S.heights(parts[owner], x, y), 6))
                hits.extend(values)
                floors.extend(S.heights(riding[owner], x, y))
                if len(values) % 2 == 0:
                    solids.extend(zip(values[::2], values[1::2]))
            cache[key] = (np.asarray(hits), np.asarray(floors), solids)
        return cache[key]
    vertices = np.asarray(mesh.vertices); faces = mesh.triangle_faces()
    probes = 0; violations = []
    for index in metadata['ride_support_members']:
        member = mesh.members[index]; first = member['first_face']*2
        triangles = vertices[np.asarray(faces[first:first+12])]
        for x, y in member_probes(member):
            hits = S.heights(triangles, x, y)
            if not len(hits): continue
            low, high = float(hits.min()), float(hits.max())
            existing, local_floors, solids = query(x, y)
            for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35), (.25, .25), (-.25, .25), (.25, -.25), (-.25, -.25)]:
                unused, floors, unused_solids = query(x+dx, y+dy)
                for floor in np.unique(np.round(floors, 6)):
                    # Use the original step the body actually crosses, rather
                    # than treating an existing 32 cm step as new body intrusion.
                    steps = local_floors[(local_floors >= floor-.02) & (local_floors <= floor+.45)]
                    if len(steps): floor = max(floor, float(steps.max()))
                    if any(bottom < floor+1.55 and top > floor+.15 for bottom, top in solids):
                        continue  # The recovered solid already occupies this body position.
                    above = existing[existing > floor+.02]
                    ceiling = float(above.min()) if len(above) else np.inf
                    if ceiling-floor < 1.55: continue  # Cairo's capsule is 1.51 m tall.
                    limit = min(floor+3., ceiling-.02)
                    probes += 1
                    if high > floor+.02 and low < limit:
                        violations.append({'member': index, 'xy': [float(x), float(y)], 'floor_m': float(floor),
                                           'steel_interval_m': [low, high], 'protected_top_m': float(limit)})
    if report_file is not None:
        report_file.write_text(json.dumps(violations, indent=2)+'\n')
    assert not violations, ('support intrudes into usable skating space', violations[:12], 'total', len(violations))
    return {'solid_member_probes': probes, 'protected_skating_clearance_m': 3., 'riding_surface_tolerance_m': .02,
            'exterior_frame_footings': len(metadata['frame_footings'])}


def structure_audit():
    meshes, metadata = S.build(north_surface)
    added = np.concatenate([m.triangles() for m in meshes])
    original = placed(); all_triangles = np.concatenate((added, original))
    triangle_lo, triangle_hi = all_triangles.min(1), all_triangles.max(1)
    def route_heights(x, y, low, high):
        mask = ((triangle_lo[:, 0] <= x+1e-7) & (triangle_hi[:, 0] >= x-1e-7) &
                (triangle_lo[:, 1] <= y+1e-7) & (triangle_hi[:, 1] >= y-1e-7) &
                (triangle_lo[:, 2] <= high) & (triangle_hi[:, 2] >= low))
        return S.heights(all_triangles[mask], x, y)
    route = S.stair_route()
    for x, y, z in route:
        hits = route_heights(x, y, z-.4, z+.4)
        bounded = hits[(hits >= z-.4) & (hits <= z+.4)]
        assert len(bounded) and abs(bounded.max()-z) < .025, ('first bounded floor hit', x, y, z, bounded)
        for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
            hits = route_heights(x+dx, y+dy, z+.2, z+1.95)
            assert not np.any((hits > z+.2) & (hits < z+1.95)), ('body clearance', x, y, z, dx, dy)
    for contact in metadata['support_contacts']:
        x, y, z = contact['top']
        assert abs(S.heights(original, x, y)-z).min() < .001, ('unsupported upper contact', contact)
        assert np.any(abs(S.heights(added, x, y)-z) < .02), ('steel does not reach underside', contact)
        x, y, z = contact['bottom']
        below = S.heights(original, x, y)
        ground = float(L.ground(x, y, north_surface))
        assert abs(z-ground) < .03 or np.any(abs(below-z) < .03), ('floating footing', contact)
    raised_nodes = {part[0] for group in S.raised_groups(scene()) for part in group}
    supported_nodes = {node for contact in metadata['support_contacts'] for node in contact['nodes']}
    assert supported_nodes == raised_nodes, ('raised pieces without support', sorted(raised_nodes-supported_nodes))
    legs = np.array([point[:2] for footing in metadata['frame_footings'] for point in (footing['bottom'], *footing['legs'])])
    gap = S.footprint_gap(legs, S.footprints(scene()))
    assert np.all(gap > .65), ('interior main footing', legs[gap <= .65].tolist())
    # A doorway can be blocked between otherwise clear route waypoints.
    clearance_samples = 0
    for a, b in zip(route, route[1:]):
        count = max(1, math.ceil(np.linalg.norm((b-a)[:2])/.25))
        for x, y, z in np.linspace(a, b, count+1):
            for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
                hits = route_heights(x+dx, y+dy, z+.4, z+1.95)
                assert not np.any((hits > z+.4) & (hits < z+1.95)), ('blocked route segment', x, y, z, dx, dy)
                clearance_samples += 1
    # Point probes can step over a thin post; sweep the 22 cm capsule (+3 cm) exactly in plan.
    intrusions = S.body_intrusions(all_triangles, route)
    assert not intrusions, ('swept body intrusion', [(i, route[i].tolist(), route[i+1].tolist()) for i, _ in intrusions[:5]])
    # Coplanar faces that shade differently z-fight (wood flickering through the stair stringers).
    flicker = S.flicker(meshes)
    assert not flicker, ('coplanar faces flicker', sorted(flicker, reverse=True)[:5])
    # Keep the deck lane used by the live riding check open below head height.
    for y in np.linspace(572, 603, 63):
        hits = S.heights(added, 1250, y)
        assert not np.any((hits > S.DECK) & (hits < 50.45)), ('blocked riding lane', y)
    return {'support_contacts': len(metadata['support_contacts']), 'ascent_waypoints': len(route),
            'closed_edge_footings': len(metadata['closed_edge_footings']),
            'supported_raised_source_instances': len(supported_nodes),
            'ascent_length_m': float(np.linalg.norm(np.diff(route, axis=0), axis=1).sum()),
            'height_gain_m': S.TOP-S.DECK, 'step_rise_m': metadata['step_rise_m'],
            'continuous_body_clearance_samples': clearance_samples,
            'swept_body_segments': len(route)-1, 'swept_body_radius_m': .25, 'coplanar_flicker_pairs': len(flicker),
            'riding_clearance': riding_clearance(meshes[0], metadata, original, scene().parts,
                                               yori.OUT/'communitypark/support-intrusions.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--imported', action='store_true')
    args = parser.parse_args(); evidence = source_audit(); evidence['structures'] = structure_audit()
    evidence['riding_collision'] = riding_audit()
    if args.imported:
        evidence['imported'] = import_audit()
    (yori.OUT/'communitypark/validation.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
