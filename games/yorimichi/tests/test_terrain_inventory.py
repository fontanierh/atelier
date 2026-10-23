"""Freeze shipped topology/evaluation order before extracting terrain products."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME/'world'))
sys.path.insert(0, str(GAME/'tools'))
import yori  # noqa: E402,F401
from terrain_inventory import inventory  # noqa: E402
from terrain_fixture_cases import cases, sampled_heights  # noqa: E402

BASELINE = Path(__file__).with_name('fixtures')/'terrain-r8.json'


def test_r8_ordered_geometry_and_query_fixtures():
    baseline = json.loads(BASELINE.read_text())
    assert baseline['source_revision'] == '4ff62dabbc1a20350a3a849e58f00196db8a3dff'
    actual = cases()
    assert actual.keys() == baseline['cases'].keys()
    for name, (vertices, faces, metadata, queries) in actual.items():
        old = baseline['cases'][name]
        # Preserve every vertex and its order, not just a few height samples.
        np.testing.assert_allclose(vertices, old['vertices'], rtol=0., atol=1.e-9, err_msg=name)
        np.testing.assert_array_equal(faces, old['triangles'], err_msg=name)
        assert metadata == old['metadata'], name
        assert queries == old['queries'], name
        expected = np.array([np.nan if z is None else z for z in old['heights']])
        current = np.array([np.nan if z is None else z for z in sampled_heights(vertices, faces, queries)])
        np.testing.assert_allclose(current, expected, rtol=0., atol=1.e-9, equal_nan=True, err_msg=name)
        assert inventory(np.asarray(old['vertices']), np.asarray(old['triangles']),
                         owner='FarHills-fixture', stage='final') == old['inventory']
    assert baseline['cases']['portal_opening']['metadata']['report']['hole_triangles'] > 0
    assert baseline['cases']['portal_opening']['heights'][1] is None
    assert baseline['cases']['selected_retained_shared_edge']['metadata']['report']['conforming_neighbors'] == 1


def test_inventory_retains_order_duplicates_and_inputs():
    vertices = np.array([[0., 0., 0.], [2., 0., 1.], [0., 3., 2.], [0., 0., 0.]])
    faces = np.array([[0, 1, 2], [3, 2, 1]])
    before = vertices.copy(), faces.copy()
    report = inventory(vertices, faces, owner='FarHills', stage='natural')
    assert report['vertices'] == 4 and report['triangles'] == 2
    assert report['index_edges'] == {'boundary': 4, 'paired': 1, 'nonmanifold': 0}
    assert report['upward_triangles'] == 1 and report['downward_triangles'] == 1
    assert inventory(vertices, faces[::-1], owner='FarHills', stage='natural')['ordered_indices_sha256'] != report['ordered_indices_sha256']
    changed = vertices.copy(); changed[3, 2] = .000001
    assert inventory(changed, faces, owner='FarHills', stage='natural')['ordered_positions_sha256'] != report['ordered_positions_sha256']
    np.testing.assert_array_equal(vertices, before[0])
    np.testing.assert_array_equal(faces, before[1])
    # Canonical endian/width conversion is explicit and independent of storage.
    assert inventory(vertices.astype('>f8'), faces.astype('>i4'), owner='FarHills', stage='natural') == report


@pytest.mark.parametrize('vertices,faces', [
    ([[0., 0., float('nan')]], [[0, 0, 0]]),
    ([[0., 0., 0.]], [[0., 0., 0.]]),
    ([[0., 0., 0.]], [[0, 0, 1]]),
    ([[0., 0., 0.]], [[-1, 0, 0]]),
    ([[0., 0.]], [[0, 0, 0]]),
])
def test_inventory_rejects_invalid_geometry(vertices, faces):
    with pytest.raises(ValueError):
        inventory(vertices, faces, owner='FarHills', stage='final')


def test_empty_inventory_and_explicit_ownership():
    v, f = np.empty((0, 3)), np.empty((0, 3), int)
    assert inventory(v, f, owner='FarHills', stage='final')['bounds'] is None
    for owner, stage in [('', 'final'), ('FarHills', 'rendered')]:
        with pytest.raises(ValueError):
            inventory(v, f, owner=owner, stage=stage)


def test_inventory_distinguishes_vertical_degenerate_and_nonmanifold_faces():
    v = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    f = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 2], [0, 0, 0]])
    report = inventory(v, f, owner='fixture', stage='final')
    assert report['zero_area_triangles'] == 1
    assert report['vertical_triangles'] == 1
    assert report['upward_triangles'] == 2
    assert report['index_edges']['nonmanifold'] == 2
