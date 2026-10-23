"""Coastal query composition consumes current source data, never render export files."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def query_data(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    import yori  # noqa: F401
    return importlib.import_module('brinecove.query_data')


def inputs(root):
    import region_query
    parents = ('SM_BC_Harbor', 'SM_BC_Hero_HarborCapstan')
    for owner in parents:
        surface = dict(name=owner, role='render', positions=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype='<f4'),
                       triangles=np.asarray([[0, 1, 2]], dtype='<i4'), matrix=np.eye(4))
        region_query.save(root / 'brinecove/query-data' / (owner + '.npz'), [surface], owner=owner, stage='final')
    hero = dict(translation_cm=[100, -200, 300], rotation_xyzw=[0, 0, 0, 1], scale=[2, 2, 2])
    data = dict(schema=1, heroes={'harbor-capstan': [hero]}, plants={}, scrub={}, quay_z=2.5)
    path = root / 'brinecove-data/placements.json'; path.parent.mkdir(); path.write_text(json.dumps(data))
    return parents, path, data, hero


def test_complete_query_rows_preserve_logical_placement_without_export_or_library_reads(tmp_path, query_data):
    root = tmp_path.resolve(); parents, _, _, hero = inputs(root)
    value = query_data.snapshot(root, parents=parents, heroes=['harbor-capstan'])
    assert not (root / 'brinecove/glb').exists() and not (root / 'brinecove/runtime.json').exists()
    assert [row['owner'] for row in value['models']] == list(parents)
    assert value['models'][0]['transforms'] == [dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])]
    assert value['models'][1]['transforms'] == [hero]
    assert value['stage'] == 'final'
    # Unconsumed planting/metadata edits do not spread into berth/crossing queries.
    path = root / 'brinecove-data/placements.json'
    data = json.loads(path.read_text()); data['plants'] = {'new_land_plant': []}; data['quay_z'] = 99
    path.write_text(json.dumps(data))
    assert query_data.snapshot(root, parents=parents, heroes=['harbor-capstan']) == value


@pytest.mark.parametrize('kind', ['missing-query', 'changed-query', 'missing-hero', 'invalid-transform', 'aliased-owner'])
def test_queries_refuse_incomplete_or_invalid_current_sources(tmp_path, query_data, kind):
    root = tmp_path.resolve(); parents, path, data, _ = inputs(root)
    if kind == 'missing-query': (root / 'brinecove/query-data/SM_BC_Harbor.npz').unlink()
    if kind == 'changed-query': (root / 'brinecove/query-data/SM_BC_Harbor.npz').write_bytes(b'corrupted')
    if kind == 'missing-hero': data['heroes'] = {}
    if kind == 'invalid-transform': data['heroes']['harbor-capstan'][0]['scale'] = [0, 1, 1]
    if kind == 'aliased-owner': parents = (*parents, 'SM_BC_HARBOR')
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        query_data.snapshot(root, parents=parents, heroes=['harbor-capstan'])
