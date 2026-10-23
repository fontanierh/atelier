"""Geometry queries use explicit data and the source's actual triangulation."""
import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def query(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    return importlib.import_module('region_query')


def surfaces():
    frame = np.eye(4); frame[:3, 3] = [7, 11, 0.25]
    points = np.asarray([[0, 0, 0], [1, 0, 0.1], [1, 1, 0], [0, 1, -0.2]], dtype='<f4')
    return [dict(name='Harbor', role='render', positions=points,
                 triangles=np.asarray([[0, 1, 3], [1, 2, 3]], dtype='<i4'), matrix=frame),
            dict(name='UCX_Harbor_0000', role='collision', positions=points,
                 triangles=np.asarray([[0, 1, 2], [0, 2, 3]], dtype='<i4'), matrix=np.eye(4))]


def test_explicit_owner_stage_and_nonfan_triangle_order_roundtrip(query, tmp_path):
    path = tmp_path / 'query.npz'
    original = surfaces()
    assert query.save(path, original, owner='Harbor', stage='raw')
    times = path.stat().st_mtime_ns
    assert not query.save(path, original, owner='Harbor', stage='raw')
    assert path.stat().st_mtime_ns == times
    loaded = query.load(path, owner='Harbor', stage='raw')
    for a, b in zip(original, loaded):
        for key in ('positions', 'triangles', 'matrix'): assert a[key].tobytes() == b[key].tobytes()
    with pytest.raises(ValueError, match='identity'): query.load(path, owner='Harbor', stage='final')
    with pytest.raises(ValueError, match='identity'): query.load(path, owner='Other', stage='raw')


def test_render_and_collision_placement_are_applied_exactly_once(query):
    rows = surfaces()
    placement = np.diag([2., 2., 2., 1.]); placement[:3, 3] = [5, -2, 3]
    actual = query.triangles(rows, placement=placement, roles=('render',))
    expected = (rows[0]['positions'] + [7, 11, .25]) * 2 + [5, -2, 3]
    np.testing.assert_array_equal(actual, expected[rows[0]['triangles']])
    collision = query.triangles(rows, roles=('collision',))
    np.testing.assert_array_equal(collision, rows[1]['positions'][rows[1]['triangles']])


def test_capture_reads_actual_loop_triangles_instead_of_reconstructing_polygon_fans(query):
    class Collection:
        def __init__(self, values): self.values = np.asarray(values)
        def __len__(self): return len(self.values)
        def foreach_get(self, field, destination): destination[:] = self.values.ravel()
    calls = []
    points = surfaces()[0]['positions']
    topology = surfaces()[0]['triangles']
    mesh = SimpleNamespace(shape_keys=None, vertices=Collection(points), loop_triangles=Collection(topology),
                           calc_loop_triangles=lambda: calls.append('tessellated'))
    obj = SimpleNamespace(type='MESH', modifiers=[], data=mesh, name='Harbor', matrix_world=np.eye(4))
    captured = query.capture(obj)
    assert calls == ['tessellated']
    assert captured['triangles'].tolist() == [[0, 1, 3], [1, 2, 3]]
    assert captured['positions'].tobytes() == points.tobytes()


def test_query_only_group_composition_preserves_each_piece_and_never_merges_meshes(query, monkeypatch):
    first, second = object(), object()
    row = surfaces()[0]
    other = {**row, 'positions': row['positions'] + np.asarray([3, 0, 0], dtype='<f4')}
    monkeypatch.setattr(query, 'capture', lambda obj: row if obj is first else other)
    group = query.capture_group([first, second], owner='Harbor')
    assert group['positions'].tobytes() == np.concatenate([row['positions'], other['positions']]).tobytes()
    assert group['triangles'].tolist() == [*row['triangles'].tolist(), *(other['triangles'] + 4).tolist()]
    expected = np.concatenate([query.triangles([row]), query.triangles([other])])
    np.testing.assert_array_equal(query.triangles([group]), expected)
    with pytest.raises(ValueError, match='unique'): query.capture_group([first, first], owner='Harbor')
    other['matrix'] = np.eye(4)
    with pytest.raises(ValueError, match='frame'): query.capture_group([first, second], owner='Harbor')


@pytest.mark.parametrize('mutation', ['float_indices', 'outside_index', 'nan', 'singular', 'wrong_owner', 'duplicate'])
def test_invalid_or_foreign_geometry_refuses_before_publication(query, tmp_path, mutation):
    rows = surfaces()
    if mutation == 'float_indices': rows[0]['triangles'] = rows[0]['triangles'].astype(float)
    if mutation == 'outside_index': rows[0]['triangles'][0, 0] = 99
    if mutation == 'nan': rows[0]['positions'][0, 0] = np.nan
    if mutation == 'singular': rows[0]['matrix'][0] = 0
    if mutation == 'wrong_owner': rows[0]['name'] = 'Other'
    if mutation == 'duplicate': rows.append(rows[1])
    path = tmp_path / 'missing/query.npz'
    with pytest.raises(ValueError): query.save(path, rows, owner='Harbor', stage='raw')
    assert not path.parent.exists()


def test_linked_input_output_and_unknown_fields_refuse(query, tmp_path):
    target = tmp_path / 'target'; target.write_bytes(b'keep')
    linked = tmp_path / 'linked'; linked.symlink_to(target)
    with pytest.raises(ValueError): query.save(linked, surfaces(), owner='Harbor', stage='raw')
    with pytest.raises(ValueError): query.load(linked, owner='Harbor', stage='raw')
    assert target.read_bytes() == b'keep'
    data = query.encode(surfaces(), owner='Harbor', stage='raw')
    with np.load(io.BytesIO(data), allow_pickle=False) as archive:
        arrays = dict(archive)
    arrays['foreign'] = np.asarray([1])
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    with pytest.raises(ValueError, match='foreign'): query.decode(stream.getvalue(), owner='Harbor', stage='raw')
    arrays.pop('foreign')
    meta = json.loads(arrays['metadata'].tobytes()); meta['surfaces'].pop()
    arrays['metadata'] = np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8)
    stream = io.BytesIO(); np.savez_compressed(stream, **arrays)
    with pytest.raises(ValueError, match='foreign'): query.decode(stream.getvalue(), owner='Harbor', stage='raw')
