"""Actual full valley query products agree with immutable original consumers."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from atelier.gltf import glb_parts

GAME=Path(__file__).resolve().parents[1]
LIBRARY=GAME/'assets/belmonte'


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return tuple(importlib.import_module('belmonte.'+key) for key in
                 ('query_arrays','valley_palette','valley_query','model_sources','source'))


def original(data,source):
    value=json.loads((GAME/'tests/fixtures/belmonte-query-source.json').read_text())
    assert value['revision']=='e0a6e719' and hashlib.sha256(value['source'].encode()).hexdigest()==value['sha256']
    namespace=dict(np=np,FRAME=source.FRAME,glb_parts=glb_parts,LIBRARY=LIBRARY,
        manifest=lambda:data,Surface=source.Surface,TERRAIN_LAYERS=source.TERRAIN_LAYERS)
    exec(compile(value['source'],'immutable-original-belmonte-query','exec'),namespace)
    return namespace


def test_effective_palette_projection_stops_unread_scene_changes(modules):
    _,palette,_,_,_=modules;data=json.loads((LIBRARY/'source.json').read_text())
    first=deepcopy(palette.project(data));assert len(first['sources'])==56
    data['signs'][0]['text']='Unrelated sign edit'
    data['meshes'][-1]['removed_foliage_faces']=-123
    assert palette.project(data)==first
    terrain=next(row for row in data['meshes'] if row['name'].startswith('SM_BM_BT_Terrain_'))
    placement=next(row for row in data['placements'] if row['asset']==terrain['source_asset'])
    material=data['materials'][placement['materials'][0]]
    material['vectors']['Tint']=[.7,.8,.9,1.]
    assert palette.project(data)!=first


def test_all56_natural_query_sources_match_original_triangle_consumer(tmp_path,modules):
    arrays,_,query,definitions,source=modules
    data=json.loads((LIBRARY/'source.json').read_text());selected=definitions.project(data)
    args=['--mode','natural','--library',str(LIBRARY),'--output',str(tmp_path/'BelmonteValley-natural.npz')]
    old=original(data,source);expected=[]
    for key,value in selected.items():
        if not key.startswith('SM_BM_BT_Terrain_'):continue
        path=tmp_path/'definitions'/(key+'.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(value))
        args.extend(('--definition',str(path)));expected.append(old['triangles'](LIBRARY/value['source']['path']))
    query.main(args)
    actual=arrays.read(tmp_path/'BelmonteValley-natural.npz',owner='BelmonteValley',stage='natural')
    assert actual['faces'].tobytes()==source.Surface(np.concatenate(expected)).faces.tobytes()


def test_all56_colour_queries_match_original_positions_values_and_order(tmp_path,modules):
    arrays,palette,query,_,source=modules
    data=json.loads((LIBRARY/'source.json').read_text());selected=tmp_path/'palette.json'
    selected.write_text(json.dumps(palette.project(data)))
    path=tmp_path/'BelmonteValleyColours-natural.npz'
    query.main(['--mode','colours','--palette',str(selected),'--library',str(LIBRARY),'--output',str(path)])
    actual=arrays.read(path,owner='BelmonteValleyColours',stage='natural')
    expected=original(data,source)['terrain_colours']()
    assert actual['faces'].tobytes()==expected.faces.tobytes()
    assert actual['values'].tobytes()==expected.values.tobytes()


def test_query_stage_and_numeric_storage_cannot_fall_back_to_another_product(tmp_path,modules):
    arrays,*_=modules;faces=np.arange(18,dtype='<f8').reshape(2,3,3)
    path=tmp_path/'BelmonteValley-natural.npz'
    arrays.write(path,faces,owner='BelmonteValley',stage='natural');before=path.stat().st_mtime_ns
    arrays.write(path,faces,owner='BelmonteValley',stage='natural')
    assert path.stat().st_mtime_ns==before
    assert arrays.read(path,owner='BelmonteValley',stage='natural')['faces'].tobytes()==faces.tobytes()
    with pytest.raises(ValueError):arrays.read(path,owner='BelmonteValley',stage='final')
    with pytest.raises(ValueError):arrays.read(path,owner='Foreign',stage='natural')
