"""Audit the private source, ground support and imported Unreal render triangles.

    uv run python games/yorimichi/world/regions/communitypark/validate.py [--imported]

Writes evidence under build/yorimichi/communitypark; never embeds recovered data
in the repository. Import comparison tolerates 0.01 cm FBX float conversion only.
"""
import argparse
from collections import defaultdict
from itertools import permutations, product
import json
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori
import numpy as np
from communitypark.source import scene
from communitypark import layout as L
from communitypark import structures as S
from hidamari.layout import north_surface


def surface_at(x, y):
    """Highest original triangle at a vertical trace, in island metres."""
    t = L.place(scene().triangles()); a, b, c = t[:, 0], t[:, 1], t[:, 2]
    den = (b[:, 1]-c[:, 1])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 1]-c[:, 1])
    den[abs(den) < 1e-10] = np.inf
    u = ((b[:, 1]-c[:, 1])*(x-c[:, 0])+(c[:, 0]-b[:, 0])*(y-c[:, 1]))/den
    v = ((c[:, 1]-a[:, 1])*(x-c[:, 0])+(a[:, 0]-c[:, 0])*(y-c[:, 1]))/den
    hit = np.isfinite(den) & (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8)
    if not hit.any():
        raise ValueError(f'No park surface at {x}, {y}')
    return float((u*a[:, 2]+v*b[:, 2]+(1-u-v)*c[:, 2])[hit].max())


def source_audit():
    s = scene(); t = L.place(s.triangles())
    normal = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    valid = np.linalg.norm(normal, axis=1) > 1e-10
    riding = t[normal[:, 2] > np.linalg.norm(normal, axis=1)*1e-4]
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
            'spawn_height_m': surface_at(*L.SPAWN[:2]), 'entry_width_samples': 5, 'patch_boundary_matches': True}


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
    for mesh in S.build(north_surface)[0]:
        expected = L.local(mesh.triangles())*[100., -100., 100.]
        actual = np.fromfile(yori.OUT/'communitypark/import-audit'/f'{mesh.name}.triangles.f64', dtype='<f8').reshape(-1, 3, 3)
        additions[mesh.name] = triangle_error(expected, actual)
    return {'source_meshes': len(errors), 'maximum_triangle_error_cm': max(errors.values()), 'meshes': errors,
            'structures': additions}


def structure_audit():
    meshes, metadata = S.build(north_surface)
    added = np.concatenate([m.triangles() for m in meshes])
    original = L.place(scene().triangles()); all_triangles = np.concatenate((added, original))
    route = S.stair_route()
    for x, y, z in route:
        hits = S.heights(all_triangles, x, y)
        bounded = hits[(hits >= z-.4) & (hits <= z+.4)]
        assert len(bounded) and abs(bounded.max()-z) < .025, ('first bounded floor hit', x, y, z, bounded)
        for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
            hits = S.heights(all_triangles, x+dx, y+dy)
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
    # A doorway can be blocked between otherwise clear route waypoints.
    clearance_samples = 0
    for a, b in zip(route, route[1:]):
        count = max(1, math.ceil(np.linalg.norm((b-a)[:2])/.25))
        for x, y, z in np.linspace(a, b, count+1):
            for dx, dy in [(0, 0), (.35, 0), (-.35, 0), (0, .35), (0, -.35)]:
                hits = S.heights(all_triangles, x+dx, y+dy)
                assert not np.any((hits > z+.4) & (hits < z+1.95)), ('blocked route segment', x, y, z, dx, dy)
                clearance_samples += 1
    # Keep the deck lane used by the live riding check open below head height.
    for y in np.linspace(572, 603, 63):
        hits = S.heights(added, 1250, y)
        assert not np.any((hits > 48.52) & (hits < 50.45)), ('blocked riding lane', y)
    return {'support_contacts': len(metadata['support_contacts']), 'ascent_waypoints': len(route),
            'supported_raised_source_instances': len(supported_nodes),
            'ascent_length_m': float(np.linalg.norm(np.diff(route, axis=0), axis=1).sum()),
            'height_gain_m': S.TOP-S.DECK, 'step_rise_m': metadata['step_rise_m'],
            'continuous_body_clearance_samples': clearance_samples,
            'footings_and_body_clearance': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--imported', action='store_true')
    args = parser.parse_args(); evidence = source_audit(); evidence['structures'] = structure_audit()
    if args.imported:
        evidence['imported'] = import_audit()
    (yori.OUT/'communitypark/validation.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps(evidence, indent=2))
