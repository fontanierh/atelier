"""A finished regional set preserves heterogeneous slot tables and complete runtime policy."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from atelier import mesh_ir
from atelier.export_manifest import sha


def fixture(root):
    root.mkdir()
    rows = []
    for index, key in enumerate(('Whole_A', 'Whole_B')):
        slots = ['MaterialA'] if index == 0 else ['MaterialB', 'MaterialC']
        geometry = dict(positions=[[0, 0, 0], [1, 0, 0], [0, 1, 0]], faces=[[0, 1, 2]],
            normals=[[0, 0, 1]] * 3, materials=[index], smooth=[False], uvs=[], colours=[])
        path = root / (key + '.npz')
        mesh_ir.write(path, mesh_ir.encode(geometry, key=key, slots=slots, matrix=np.eye(4).tolist(), options={}, collisions=[]))
        rows.append(dict(name=key, payload=path.name, sha256=sha(path), triangles=1, polygons=1,
                         min=[0, 0, 0], max=[1, 1, 0], collision_hulls=0, slots=slots))
    value = dict(schema=1, kind='mesh_set', parent='Whole', complete=True, triangle_limit=32768,
        source_triangles=2, source_polygons=2, source_collision_hulls=0,
        slots=['MaterialA', 'MaterialB', 'MaterialC'], matrix=np.eye(4).tolist(), pieces=rows,
        metadata={'Whole_A': dict(collision=True, shadow=True), 'Whole_B': dict(collision=False, shadow=False)})
    (root / 'plan.json').write_text(json.dumps(value))
    return value


@pytest.fixture
def planner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    return importlib.import_module('region_mesh_parts')


def test_complete_mesh_set_retains_each_actual_material_table_and_runtime_role(tmp_path, planner):
    root = tmp_path / 'planned'
    value = fixture(root)
    assert planner.validate(root) == value
    assert value['pieces'][0]['slots'] != value['pieces'][1]['slots']
    assert value['metadata']['Whole_A']['collision'] and not value['metadata']['Whole_B']['collision']


@pytest.mark.parametrize('mutation', ['piece_table', 'union', 'missing_policy', 'foreign_policy', 'extra_file', 'unfinished'])
def test_mesh_set_cannot_claim_incomplete_or_changed_receiving_ownership(tmp_path, planner, mutation):
    root = tmp_path / 'planned'
    value = fixture(root)
    if mutation == 'piece_table': value['pieces'][1]['slots'] = ['MaterialA']
    elif mutation == 'union': value['slots'].pop()
    elif mutation == 'missing_policy': value['metadata'].pop('Whole_B')
    elif mutation == 'foreign_policy': value['metadata']['Foreign'] = {}
    elif mutation == 'extra_file': (root / 'foreign').write_text('untouched')
    elif mutation == 'unfinished': (root / '.plan-transaction.json').write_text('{}')
    (root / 'plan.json').write_text(json.dumps(value))
    with pytest.raises(ValueError): planner.validate(root)
    if mutation == 'extra_file': assert (root / 'foreign').read_text() == 'untouched'
