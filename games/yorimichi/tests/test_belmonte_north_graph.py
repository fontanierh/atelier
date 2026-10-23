"""Normal northern declarations consume narrow data instead of global region exports."""
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from atelier.build import Step,check_modules,order

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return importlib.import_module('belmonte.north_context'),importlib.import_module('hidamari.layout')


def inputs(tmp_path):
    np.save(tmp_path/'heightmap.npy',np.arange(96**2,dtype=float).reshape(96,96)*.001)
    np.save(tmp_path/'farhills.npy',np.arange(96**2,dtype=float).reshape(96,96)*.01)
    world=tmp_path/'world.json';world.write_text(json.dumps(dict(road=[[200.,10.,2.],[250.,20.,3.]],unread=['first'])))
    return world,tmp_path/'heightmap.npy',tmp_path/'farhills.npy'


def test_northern_context_stops_unread_world_changes_but_retains_consumed_anchor(tmp_path,modules):
    context,_=modules;world,heightmap,farhills=inputs(tmp_path)
    first=context.project(world,heightmap,farhills)
    value=json.loads(world.read_text());value['unread']=['second'];world.write_text(json.dumps(value))
    assert context.project(world,heightmap,farhills)==first
    value['road'][1][1]+=1;world.write_text(json.dumps(value))
    assert context.project(world,heightmap,farhills)!=first


def test_bound_context_matches_original_lazy_array_and_anchor_consumers(tmp_path,modules,monkeypatch):
    context,layout=modules;world,heightmap,farhills=inputs(tmp_path)
    monkeypatch.setattr(layout.yori,'OUT',tmp_path)
    monkeypatch.setattr(layout,'H',None);monkeypatch.setattr(layout,'BACKDROP',None)
    monkeypatch.setattr(layout.street_height,'start',None,raising=False);delattr(layout.street_height,'start')
    x=np.array([300.,335.,500.,700.]);y=np.array([10.,85.,140.,250.])
    heights=layout.street_height(x,y);backdrop=layout.backdrop_grid().copy()
    selected=tmp_path/'context.json';selected.write_text(json.dumps(context.project(world,heightmap,farhills)))
    world.write_text('This unread metadata is deliberately unavailable after projection')
    context.apply(selected,heightmap,farhills)
    assert layout.street_height(x,y).tobytes()==heights.tobytes()
    assert layout.backdrop_grid().tobytes()==backdrop.tobytes()


def test_stale_context_refuses_before_altering_lazy_terrain_caches(tmp_path,modules,monkeypatch):
    context,layout=modules;world,heightmap,farhills=inputs(tmp_path)
    monkeypatch.setattr(layout.yori,'OUT',tmp_path)
    marker=object();monkeypatch.setattr(layout,'H',marker)
    selected=tmp_path/'context.json';selected.write_text(json.dumps(context.project(world,heightmap,farhills)))
    np.save(heightmap,np.zeros((96,96)))
    with pytest.raises(ValueError,match='Stale'):context.apply(selected,heightmap,farhills)
    assert layout.H is marker


def test_northern_graph_has_independent_raw_owners_and_two_consumed_boundary_stages(tmp_path):
    spec=importlib.util.spec_from_file_location('belmonte_north_graph_test',GAME/'belmonte_north_build.py')
    graph=importlib.util.module_from_spec(spec);spec.loader.exec_module(graph)
    ctx=SimpleNamespace(out=tmp_path.resolve());steps=graph.steps(ctx);check_modules(steps)
    raw=[step for step in steps if '.north.raw.' in step.name]
    assert len(raw)==2 and len({step.commands[0].script for step in raw})==2
    for step in raw:
        assert not step.needs and ctx.out/'world.json' not in step.inputs
        assert 'belmonte.north_context' in step.reads
        assert '--context' in step.commands[0].args
    assert 'belmonte.valley_natural' in raw[0].reads and 'belmonte.valley_natural' not in raw[1].reads
    boundaries=[step for step in steps if step.name.endswith('_boundaries')]
    assert len(boundaries)==2 and all(len(step.products)==2 for step in boundaries)
    final=[step for step in steps if '.north.final.' in step.name]
    assert len(final)==2
    for step in final:
        owner=step.name.rsplit('.',1)[1]
        assert step.reads==['belmonte.north.carve.'+owner,'belmonte.north.final_seam.'+owner,'belmonte.valley_colours']
        assert not any(path.suffix=='.glb' for path in step.inputs)
    queries=graph.query_steps(ctx);check_modules(queries)
    natural=next(step for step in queries if step.name.endswith('valley_natural'))
    colours=next(step for step in queries if step.name.endswith('valley_colours'))
    final_query=next(step for step in queries if step.name.endswith('valley_final'))
    assert len(natural.reads)==56 and colours.reads==['belmonte.valley_palette'] and len(final_query.reads)==56
    assert not any(path.suffix=='.glb' for path in final_query.inputs)


def test_complete_model_valley_and_north_source_graph_is_acyclic_before_exports(tmp_path):
    def load(label,path):
        spec=importlib.util.spec_from_file_location(label,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    north=load('belmonte_complete_north_graph',GAME/'belmonte_north_build.py')
    models=load('belmonte_complete_model_graph',GAME/'belmonte_atomic_build.py')
    ctx=SimpleNamespace(out=tmp_path.resolve())
    steps=[Step('world.layout',[]),*models.model_steps(ctx),*models.ground_steps(ctx),
           *north.query_steps(ctx),*north.steps(ctx)]
    wanted=['world.belmonte_models.assembled','world.belmonte_ground.assembled',
            'world.belmonte_north.assembled','world.belmonte.valley_final']
    selected=order(steps,wanted);names=[step.name for step in selected]
    assert len(names)==len(set(names))
    assert names.index('world.belmonte.valley_natural')<names.index('world.belmonte.north.raw.SM_BM_NorthApron')
    assert names.index('world.belmonte.north.natural_boundaries')<names.index('world.belmonte.north.carve.SM_BM_NorthApron')
    assert names.index('world.belmonte.north.final_boundaries')<names.index('world.belmonte_north.assembled')
