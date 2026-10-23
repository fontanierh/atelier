"""The lake's terrain/RNG source data precedes individual logical export tasks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(GAME/'world'),str(GAME/'world/regions')]
from forest_lake.query_data import publish  # noqa: E402
from forest_lake.scatter import rng_after_cabin  # noqa: E402


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def test_shared_draw_prefix_is_exact_without_constructing_other_meshes():
    import random
    baseline=random.Random(719)
    for _ in range(2*len(np.arange(-3.4,3.5,.25))):
        for _ in range(3):baseline.uniform(.9,1.1)
    for _ in range(len(np.arange(-13,-4.3,.22))):
        for _ in range(3):baseline.uniform(.91,1.09)
    assert rng_after_cabin().getstate()==baseline.getstate()


def test_final_query_packets_ignore_unconsumed_world_metadata_and_refuse_links(tmp_path):
    root=tmp_path.resolve();height=root/'heightmap.npy';np.save(height,np.full((65,65),75.,dtype='f4'))
    world=root/'world.json';doc={'forest_lake':{'trail':[[0,200,75],[2,202,75],[4,204,75]]},'other':'old'}
    world.write_text(json.dumps(doc));output=root/'queries'
    programs=publish(height,world,output)
    assert set(programs)=={'Lake_Trail','Lake_Shore','Lake_Plants'}
    before={p.name:p.read_bytes() for p in output.glob('Lake_*.json')}
    doc['other']='changed';world.write_text(json.dumps(doc));publish(height,world,output)
    assert before=={p.name:p.read_bytes() for p in output.glob('Lake_*.json')}
    external=root/'external';external.write_text('private')
    (output/'Lake_Shore.json').unlink();(output/'Lake_Shore.json').symlink_to(external)
    with pytest.raises(ValueError):publish(height,world,output)
    assert external.read_text()=='private'


def test_lake_owns_five_selected_constructors_and_has_no_export_edges(tmp_path):
    helper=module('lake_atomic_recipe',GAME/'lake_atomic_build.py')
    steps=helper.steps(SimpleNamespace(out=tmp_path.resolve()))
    selected=[s for s in steps if s.name.startswith('world.lake.geometry.')]
    assert len(selected)==5 and {s.name.rsplit('.',1)[-1] for s in selected}==set(helper.OWNERS)
    for step in selected:
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads==3
        assert '--asset' in step.commands[0].args and not step.reads
        assert not any('exports' in p.parts for p in step.inputs if isinstance(p,Path))
    query=next(s for s in steps if s.name=='world.lake.query_data')
    assert query.needs==['world.layout'] and len(query.products)==4


def test_lake_native_has_no_terrain_receiver_or_hardcoded_parent_import():
    text=(GAME/'unreal/Scripts/import_forest_lake.py').read_text()
    assert 'terrain.fbx' not in text and "'/Game/Japan','Terrain'" not in text
    assert "value['parents']" in text and "value['assets'][name]" in text
    native=module('lake_native_test',GAME/'unreal/Scripts/lake_native.py')
    assert native.owned('Lake_Cabin_cell_-1_2') and native.owned('Lake_Water')
    assert not native.owned('Lake_Unknown') and not native.owned('Lake_Cabin/escape')
