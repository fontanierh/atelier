"""Final data finishing preserves coast geometry while bounding every exported ground child."""
from collections import Counter
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def finish(monkeypatch):
    world = Path(__file__).resolve().parents[1] / 'world'
    monkeypatch.syspath_prepend(str(world))
    import yori  # noqa: F401
    return importlib.import_module('brinecove.geometry_finish')


def test_flat_paving_query_uses_exact_rectangles_and_minimum_underlaps(finish):
    query = finish.paving_limit([(0, 10, 0, 10, 4), (5, 15, 5, 15, 3)])
    assert query(2, 2) == 3.95
    assert query(5, 5) == 2.95
    assert query(15, 15) == 2.95
    assert query(20, 20) == float('inf')
    with pytest.raises(ValueError): finish.paving_limit([(0, 1, 0, 1, float('nan'))])


def test_unbounded_ground_must_split_without_changing_any_face_fields(finish, monkeypatch):
    monkeypatch.setattr(finish, 'MIXED_TRIANGLE_LIMIT', 8)
    ox, oy = finish.R.OUTER[:2]
    builder = finish.Builder('SM_BC_Ground_0_0')
    for k in range(16):
        x, y = ox + k % 4 * 64, oy + k // 4 * 64
        builder.face([(x, y, 0), (x + 1, y, 0), (x + 1, y + 1, 0), (x, y + 1, 0)],
                     'terrain', [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 0, 1)] * 4)
    def rows(part):
        return Counter((part.mats[n], tuple(part.verts[i] for i in face),
                        tuple(part.uvs[i] for i in face), tuple(part.normals[i] for i in face))
                       for n, face in enumerate(part.faces))
    output = finish.bounded_parts({(0, 0, False): builder}, 'Ground')
    actual = Counter()
    for key, child in output.items():
        assert key[:3] == (0, 0, False)
        assert sum(len(face) - 2 for face in child.faces) <= 8
        actual.update(rows(child))
    assert len(output) == 4 and actual == rows(builder)


def test_ground_remapping_cannot_silently_skip_its_paving_dependency(finish):
    with pytest.raises(ValueError, match='complete explicit paving'):
        finish.split(finish.Builder('Ground'), 'Ground', None, finish.GROUND_REMAP)


def test_final_rim_projection_stops_unread_interior_changes_but_keeps_boundary_changes(finish, tmp_path):
    import json
    from brinecove import rim_data
    from terrain_product import Mesh, save
    x0, y0, x1, y1 = finish.R.OUTER_WORLD
    points = [[x0, y0, 2], [x1, y0, 2], [x1, y1, 2], [x0, y1, 2],
              [(x0+x1)/2, (y0+y1)/2, 9]]
    faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    path = tmp_path / 'final.npz'
    def publish():
        save(path, Mesh.from_polygons(points, faces), owner='FarHills', stage='final', city=True)
        value = rim_data.project(path)
        current, world = rim_data.read(json.loads(json.dumps(value)))
        expected, expected_world = finish.rim(path)
        assert current.sides == expected.sides and world == expected_world
        return value
    first = publish()
    points[4][2] += 40
    assert publish() == first
    points[0][2] += 1
    assert publish() != first
    save(path, Mesh.from_polygons(points, faces), owner='FarHills', stage='natural', city=True)
    with pytest.raises(ValueError, match='owner, stage or city mode'):
        rim_data.project(path)
