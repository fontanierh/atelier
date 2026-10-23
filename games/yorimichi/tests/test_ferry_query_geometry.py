"""Ferry sweeps consume source data before exports and bind every actual read."""
import copy
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from atelier.export_manifest import sha
from test_ferry_site import site  # noqa: F401 (shared real sweep module fixture)

GAME = Path(__file__).resolve().parents[1]


@pytest.fixture
def query(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    monkeypatch.syspath_prepend(str(GAME / 'world/regions'))
    return importlib.import_module('regions.ferry.query_geometry')


def save(query, path, key, z=0, *, raw=False):
    query.region_query.save(path, [dict(name=key, role='render', positions=[[0,0,z],[1,0,z],[0,1,z]],
        triangles=np.array([[0,1,2]], dtype='<i4'), matrix=np.eye(4))], owner=key, stage='raw' if raw else 'final')


def clip(value, bounds, band=None):
    return value.astype(np.float32)


def city_frame(row):
    value = np.eye(4); value[:3,3] = row[:3]
    value[:3,:3] *= row[4]
    return value


def test_raw_harbor_and_final_city_geometry_are_available_without_any_exports(tmp_path, query):
    folder = tmp_path / 'hidamari/query-data'; folder.mkdir(parents=True)
    save(query, folder / 'HD_Terrain.npz', 'HD_Terrain', -10)
    save(query, folder / 'HD_Harbor.raw.npz', 'HD_Harbor', raw=True)
    save(query, folder / 'HD_Boat.npz', 'HD_Boat')
    hills = tmp_path / 'terrain/FarHills/final.npz'; hills.parent.mkdir(parents=True)
    np.savez_compressed(hills, vertices=[[0,0,-10],[1,0,-10],[0,1,-10]], triangles=[[0,1,2]])
    city = tmp_path / 'hidamari/layout-data.json'
    city.write_text(json.dumps(dict(instances={'HD_Boat': [[2,3,4,0,2]], 'Tree_Foreign': [[1,1,1,0,1]]})))
    ground, solid, names, sources, _ = query.hidamari(tmp_path, (-20,-20,20,20),
        clip=clip, placement=city_frame, z_band=(-5,20), water_z=.5)
    assert len(ground) == 2 and names == ['HD_Harbor', 'HD_Boat']
    assert np.array_equal(solid[1], [[[2,3,4],[4,3,4],[2,5,4]]])
    assert set(sources) == {'hidamari/query-data/HD_Terrain.npz', 'hidamari/query-data/HD_Harbor.raw.npz',
                           'hidamari/query-data/HD_Boat.npz', 'hidamari/layout-data.json', 'terrain/FarHills/final.npz'}
    assert not (tmp_path / 'hidamari/assets').exists()
    save(query, folder / 'HD_Harbor.raw.npz', 'HD_Harbor')
    with pytest.raises(ValueError, match='identity'):
        query.hidamari(tmp_path, (-20,-20,20,20), clip=clip, placement=city_frame, z_band=(-5,20), water_z=.5)


def coastal(tmp_path, query):
    models = []
    prototypes = {query.plant_name(path.stem):path.stem for path in query.definitions()}
    for key in (*query.COAST,*prototypes):
        prototype = prototypes.get(key)
        relative = 'brinecove/query-data/' + ('plants/'+prototype if prototype else key) + '.npz'
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True)
        save(query, path, key)
        models.append(dict(owner=key, prototype=prototype, path=relative, sha256=sha(path), transforms=[dict(
            translation_cm=[0,0,0], rotation_xyzw=[0,0,0,1], scale=[1,1,1])]))
    value = dict(schema=2, stage='final', origin_cm=[100,200,300], models=models)
    path = tmp_path / 'brinecove-data/query-data.json'; path.parent.mkdir()
    path.write_text(json.dumps(value))
    return path, value


def test_complete_coast_uses_geometry_and_placements_without_glbs(tmp_path, query):
    _, data = coastal(tmp_path, query)
    result = query.brinecove(tmp_path, (-20,-20,20,20), clip=clip, placement=lambda _: np.eye(4), z_band=(-5,20))
    ground, solid, names, sources, frame = result
    assert len(ground) == 1 and len(solid) == 48 and len(names) == 48
    assert len(sources) == 50 and frame['origin_cm'] == data['origin_cm']
    assert not (tmp_path / 'brinecove/glb').exists()


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'hash', 'path', 'transform', 'rotation'])
def test_partial_or_changed_coast_refuses_instead_of_reading_an_export(tmp_path, query, failure):
    path, value = coastal(tmp_path, query)
    value = copy.deepcopy(value)
    if failure == 'missing': value['models'].pop()
    if failure == 'duplicate': value['models'][1] = value['models'][0]
    if failure == 'hash': value['models'][0]['sha256'] = '0'*64
    if failure == 'path': value['models'][0]['path'] = '../Other.npz'
    if failure == 'transform': value['models'][0]['transforms'][0]['scale'][0] = 0
    if failure == 'rotation': value['models'][0]['transforms'][0]['rotation_xyzw'][3] = 2
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        query.brinecove(tmp_path, (-20,-20,20,20), clip=clip, placement=lambda _: np.eye(4), z_band=(-5,20))


def test_sweep_code_receipt_covers_query_consumers_and_both_shared_rosters(site):
    members = set(site.code_inputs())
    assert {GAME / 'world/regions/ferry/query_geometry.py', GAME / 'world/region_query.py',
            GAME / 'world/regions/hidamari/logical_catalogue.py',
            GAME / 'world/regions/brinecove/logical_catalogue.py',
            GAME / 'unreal/Source/Yorimichi/CitySurfaceParents.h'} <= members


def test_far_prototype_instances_are_culled_before_matrix_or_triangle_expansion(tmp_path,query):
    path,value = coastal(tmp_path,query)
    row = next(row for row in value['models'] if row['prototype'] is not None)
    row['transforms'][0]['translation_cm'] = [1.e9,0,0]
    path.write_text(json.dumps(value))
    expanded = []
    def placement(transform):
        expanded.append(transform)
        return np.eye(4)
    result = query.brinecove(tmp_path,(-20,-20,20,20),clip=clip,placement=placement,z_band=(-5,20))
    assert len(result[1])==47 and len(expanded)==48
    assert all(transform['translation_cm'][0]!=1.e9 for transform in expanded)
