"""Planning cannot silently drop evaluated static geometry before export admission."""
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('kind,modifiers,shape_keys', [
    ('CURVE', [], None), ('MESH', ['ARRAY'], None), ('MESH', [], object())])
def test_unfinished_geometry_is_refused_before_creating_output(tmp_path, monkeypatch, kind, modifiers, shape_keys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    obj = SimpleNamespace(name='Part', type=kind, modifiers=modifiers,
                          data=SimpleNamespace(shape_keys=shape_keys))
    root = tmp_path / 'planned'
    with pytest.raises(ValueError, match='completed static mesh'):
        planner.plan(obj, root)
    assert not root.exists()


def planned_pair(root):
    import json
    import numpy as np
    from atelier import mesh_ir
    from atelier.export_manifest import sha
    root.mkdir()
    matrix = np.eye(4); matrix[0, 3] = 11
    hull = dict(vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
                faces=[[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], matrix=np.eye(4).tolist())
    piece = dict(positions=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]],
                 normals=[[0, 0, 1]] * 3, materials=[0], smooth=[False],
                 uvs=[('UVMap', [[0, 0], [1, 0], [0, 1]])], colours=[])
    rows = []
    for index, key in enumerate(('One', 'Two')):
        path = root / (key + '.npz')
        mesh_ir.write(path, mesh_ir.encode(piece, key=key, slots=['Material'], matrix=matrix.tolist(),
            options={}, collisions=[hull] if index == 0 else []))
        rows.append(dict(name=key, payload=path.name, sha256=sha(path), triangles=1, polygons=1,
                         min=[11, 0, 0], max=[12, 1, 0], collision_hulls=1 if index == 0 else 0))
    value = dict(schema=1, parent='Whole', complete=True, triangle_limit=32768,
                 source_triangles=2, source_polygons=2, source_collision_hulls=1,
                 slots=['Material'], matrix=matrix.tolist(), pieces=rows)
    (root / 'plan.json').write_text(json.dumps(value))
    return value


def test_logical_parent_retains_authored_collision_policy_beyond_zero_hull_child(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    root = tmp_path / 'planned'
    value = planned_pair(root)
    actual = planner.validate(root)
    assert actual['source_collision_hulls'] == 1
    assert [row['collision_hulls'] for row in actual['pieces']] == [1, 0]
    assert actual['matrix'][0][3] == 11
    assert actual == value


@pytest.mark.parametrize('mutation', ['bounds', 'polygons', 'collision', 'slots', 'frame'])
def test_planned_parent_metadata_cannot_disagree_with_current_child_bytes(tmp_path, monkeypatch, mutation):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    planner = importlib.import_module('region_mesh_parts')
    root = tmp_path / 'planned'
    value = planned_pair(root)
    if mutation == 'bounds': value['pieces'][1]['min'][0] = 10
    if mutation == 'polygons': value['source_polygons'] = 3
    if mutation == 'collision': value['source_collision_hulls'] = 0
    if mutation == 'slots': value['slots'] = ['Different']
    if mutation == 'frame': value['matrix'][0][3] = 12
    with pytest.raises(ValueError):
        planner.validate(root, value)
