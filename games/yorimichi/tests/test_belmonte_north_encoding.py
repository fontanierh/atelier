"""Data-first northern terrain retains the immutable original export byte encoding."""
import hashlib
import importlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from atelier.gltf import glb_parts,glb_pack

GAME=Path(__file__).resolve().parents[1]
WITNESS=json.loads((GAME/'tests/fixtures/belmonte-north-writers.json').read_text())


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return importlib.import_module('hippodrome.build'),importlib.import_module('belmonte.appearance')


def original(label,namespace):
    value=WITNESS[label]
    assert value['revision']=='430adb0b'
    assert hashlib.sha256(value['source'].encode()).hexdigest()==value['sha256']
    exec(compile(value['source'],'immutable-original-'+label,'exec'),namespace)
    return namespace


def mesh(hippo):
    result=hippo.Mesh()
    result.quad((0,0,0),(1,0,.25),(1,2,.5),(0,2,.25))
    result.triangle((1,0,.25),(2,0,.4),(1,2,.5))
    return result


@pytest.mark.parametrize('owner',['SM_BM_NorthApron','SM_BM_NorthCountry'])
def test_in_memory_mesh_encoding_is_byte_identical_to_original_file_writer(tmp_path,modules,owner):
    hippo,_=modules;geometry=mesh(hippo)
    old=original('hippodrome',dict(np=np,json=json,struct=struct))
    path=tmp_path/(owner+'.glb');info=old['write_glb'](path,geometry.p,geometry.n,geometry.t,geometry.i,'BM_000_Ground')
    data,current=hippo.encoded_glb(owner,geometry.p,geometry.n,geometry.t,geometry.i,'BM_000_Ground')
    assert data==path.read_bytes() and info==current


@pytest.mark.parametrize('owner',['SM_BM_NorthApron','SM_BM_NorthCountry'])
@pytest.mark.parametrize('natural',[False,True])
def test_in_memory_colour_finish_matches_original_full_byte_encoding(tmp_path,modules,monkeypatch,owner,natural):
    hippo,appearance=modules;geometry=mesh(hippo)
    monkeypatch.setattr(appearance.source,'terrain_colours',lambda:SimpleNamespace(
        colour=lambda x,y:np.tile([.1,.2,.05],(len(x),1))))
    monkeypatch.setattr(appearance,'forest_weight',lambda x,y:np.linspace(0.,1.,len(x)))
    from train import earthworks
    monkeypatch.setattr(earthworks,'paint',lambda colour,*args:colour*.9)
    if natural:geometry.natural=np.arange(len(geometry.p),dtype=float)
    data,_=hippo.encoded_glb(owner,geometry.p,geometry.n,geometry.t,geometry.i,'BM_000_Ground')
    old=original('appearance',dict(np=np,source=appearance.source,L=appearance.L,terrain=appearance.terrain,
        forest_weight=appearance.forest_weight,far_palette=appearance.far_palette,
        shorelines=appearance.shorelines,glb_parts=glb_parts,glb_pack=glb_pack))
    path=tmp_path/(owner+'.glb');path.write_bytes(data);old['paint_join'](path,geometry)
    assert appearance.paint_join_data(data,owner,geometry)==path.read_bytes()
