"""Actual native owner control flow validates inputs, saves the map, then retires parents."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from atelier import native_packages
from atelier.export_manifest import real_directory

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def owner(tmp_path,monkeypatch):
    script=GAME/'unreal/Scripts/import_island_world.py'
    code=ast.parse(script.read_text())
    functions=[node for node in code.body if isinstance(node,ast.FunctionDef)]
    spec=importlib.util.spec_from_file_location('island_world_policy_test',GAME/'island_native_policy.py')
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    events=[];state=SimpleNamespace(receive_fails=False,map_fails=False,missing=None,change_runtime=False)
    groups={key:dict(pieces=[dict(asset='/Game/Current/'+key,name=key)]) for key in ('Terrain','Sea')}
    runtime=dict(schema=1,complete=True,origin=[0.,0.,0.],parents={key:dict(meshes=value['pieces']) for key,value in groups.items()})
    (tmp_path/'terrain').mkdir();path=tmp_path/'terrain/island.json';path.write_text(json.dumps(runtime))
    (tmp_path/'world.json').write_text(json.dumps(dict(player_start=[1.,2.,3.,4.])))
    def load(path):return None if path==state.missing else path
    unreal=SimpleNamespace(EditorAssetLibrary=SimpleNamespace(load_asset=load),
        SystemLibrary=SimpleNamespace(collect_garbage=lambda:events.append('gc')))
    def operation(name):
        def run(*args):events.append(name);return name
        return run
    monkeypatch.setitem(sys.modules,'import_southwest',SimpleNamespace(sand_material=operation('sand'),sea_material=operation('sea')))
    monkeypatch.setitem(sys.modules,'forest_ground',SimpleNamespace(material=operation('forest'),
        coast_instance=operation('coast'),coast_rock_instance=operation('coastrock')))
    monkeypatch.setitem(sys.modules,'material_assets',SimpleNamespace(instance=operation('instance')))
    monkeypatch.setattr(native_packages,'save',lambda *args:events.append('save_material'))
    def receive():
        events.append('receive')
        if state.receive_fails:raise RuntimeError('receiving failed')
        state.received=dict(groups={key:value['pieces'] for key,value in groups.items()})
        return state.received
    def build(meshes,world,materials):
        events.append('map')
        assert meshes=={key:[(key,'/Game/Current/'+key)] for key in groups}
        assert world['player_start']==[1.,2.,3.,4.] and materials=={'_painterly':'/Game/Shared/Painterly'}
        if state.map_fails:raise RuntimeError('map failed')
        if state.change_runtime:path.write_text('{}')
    def retire(received,*,runtime_members):
        assert received is state.received
        assert runtime_members=={key:['/Game/Current/'+key] for key in groups}
        assert events.index('receive')<events.index('map')
        events.append('retire')
    scope=dict(yori=SimpleNamespace(OUT=tmp_path,GAME=tmp_path/'game'),real_directory=real_directory,
        json=json,math=__import__('math'),unreal=unreal,native_packages=native_packages,
        MATERIAL_PACKAGES=policy.MATERIAL_PACKAGES,read=lambda out:groups,
        receive=receive,retire_after_map=retire,build_level=build,
        material_bindings=lambda:dict(_painterly='/Game/Shared/Painterly'))
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(script),'exec'),scope)
    state.run=scope['main'];state.root=tmp_path;state.events=events;state.runtime=path
    return state


def test_complete_owner_saves_separate_map_before_combined_retirement(owner):
    owner.run()
    assert owner.events.count('receive')==owner.events.count('map')==owner.events.count('retire')==1
    assert owner.events.index('sea')<owner.events.index('receive')<owner.events.index('map')<owner.events.index('retire')
    assert owner.events.count('save_material')==8


@pytest.mark.parametrize('fault',['missing_runtime','runtime_link','wrong_membership','invalid_start','missing_shared'])
def test_input_refusal_precedes_native_material_or_mesh_mutation(owner,tmp_path,fault):
    if fault=='missing_runtime':owner.runtime.unlink()
    elif fault=='runtime_link':
        outside=tmp_path/'external';outside.write_bytes(owner.runtime.read_bytes());owner.runtime.unlink();owner.runtime.symlink_to(outside)
    elif fault=='wrong_membership':
        value=json.loads(owner.runtime.read_text());value['parents']['Sea']['meshes']=[];owner.runtime.write_text(json.dumps(value))
    elif fault=='invalid_start':(owner.root/'world.json').write_text(json.dumps(dict(player_start=[True,2,3,4])))
    elif fault=='missing_shared':owner.missing='/Game/Shared/Painterly'
    with pytest.raises((ValueError,RuntimeError,FileNotFoundError)):
        owner.run()
    assert owner.events==[]


@pytest.mark.parametrize('fault',['receive','map','runtime_change','missing_child'])
def test_failed_receiving_or_map_never_retires_original_packages(owner,fault):
    if fault=='receive':owner.receive_fails=True
    elif fault=='map':owner.map_fails=True
    elif fault=='runtime_change':owner.change_runtime=True
    elif fault=='missing_child':owner.missing='/Game/Current/Terrain'
    with pytest.raises((ValueError,RuntimeError)):
        owner.run()
    assert 'retire' not in owner.events
