"""Actual atomic graph ownership and complete lake inputs/combined legacy retirement."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from atelier import build

GAME=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def test_actual_cold_recipe_has_selected_forest_lake_and_complete_native_products(tmp_path):
    ctx=SimpleNamespace(game='yorimichi',out=tmp_path.resolve(),logs=tmp_path/'logs',stamps=tmp_path/'stamps',uproject=None)
    steps=build.load_recipe('yorimichi').steps(ctx);by_name={s.name:s for s in steps}
    selected=build.order(steps,['unreal.forest','unreal.lake','data.stage'])
    assert len([s for s in selected if s.name.startswith('world.forest.geometry.')])==40
    assert len([s for s in selected if s.name.startswith('world.lake.geometry.')])==5
    build.check_modules([by_name[name] for name in ('world.forest','world.lake','world.forest_textures')])
    assert by_name['world.forest_textures'].cache
    assert {'forest.library','forest.textures'}<=set(by_name['unreal.forest'].reads)
    assert by_name['unreal.lake'].reads==['lake.library']
    assert 'lake.library' in by_name['data.stage'].reads
    roots={p for product in by_name['unreal.forest'].products for p in product.paths}
    species=[p.stem for p in (GAME/'assets/forest/export-parameters').glob('*.json')]
    for name in species:
        assert GAME/f'unreal/Content/Japan/Assets/{name}.uasset' in roots
        assert GAME/f'unreal/Content/Japan/FoliageLODs/MI_{name}_Crown.uasset' in roots
        assert all(GAME/f'unreal/Content/Japan/FoliageLODs/{name}_LOD{i}.uasset' in roots for i in range(1,5))
        assert all(GAME/f'unreal/Content/Japan/Textures/T_{name}_{kind}.uasset' in roots for kind in ('colour','normal'))
    lake_roots={p for product in by_name['unreal.lake'].products for p in product.paths}
    assert GAME/'unreal/Content/Japan/Lake/Pieces' in lake_roots
    assert GAME/'unreal/Content/Japan/Materials/M_ForestLakeWater.uasset' in lake_roots
    assert all(getattr(command,'script',None) not in (GAME/'world/build_forest.py',GAME/'world/regions/forest_lake/build.py')
               for step in steps for command in step.commands)


@pytest.fixture
def lake(tmp_path):
    native=load('lake_native_owner_integration',GAME/'unreal/Scripts/lake_native.py')
    root=tmp_path.resolve();(root/'assets').mkdir()
    value=dict(schema=2,complete=True,parents={},assets={})
    for parent in native.OWNERS:
        name=parent+'_cell_-1_0';payload=name.encode();(root/'assets'/(name+'.fbx')).write_bytes(payload)
        value['parents'][parent]=[name]
        value['assets'][name]=dict(parent=parent,fbx='assets/'+name+'.fbx',triangles=12,collision_boxes=0,
            min=[-2.,-1.,0.],max=[2.,1.,3.],sha256=hashlib.sha256(payload).hexdigest())
    (root/'manifest.json').write_text(json.dumps(value))
    return native,root,value


def test_complete_lake_source_membership_is_preflighted(lake):
    native,root,value=lake
    assert native.read(root)==value


@pytest.mark.parametrize('fault',['missing_parent','foreign_asset','duplicate','unbounded','wrong_owner','payload','link','hull','bounds'])
def test_any_invalid_lake_piece_refuses_complete_receiving(lake,fault):
    native,root,original=lake;value=copy.deepcopy(original);name=value['parents']['Lake_Cabin'][0];row=value['assets'][name]
    if fault=='missing_parent':del value['parents']['Lake_Plants']
    elif fault=='foreign_asset':value['assets']['Foreign']=copy.deepcopy(row)
    elif fault=='duplicate':value['parents']['Lake_Cabin'].append(name)
    elif fault=='unbounded':row['triangles']=32769
    elif fault=='wrong_owner':row['parent']='Lake_Water'
    elif fault=='payload':(root/row['fbx']).write_bytes(b'changed')
    elif fault=='link':
        target=root/'outside';target.write_bytes((root/row['fbx']).read_bytes());(root/row['fbx']).unlink();(root/row['fbx']).symlink_to(target)
    elif fault=='hull':row['collision_boxes']=1
    elif fault=='bounds':row['min'][1]=2.
    (root/'manifest.json').write_text(json.dumps(value))
    with pytest.raises(ValueError):native.read(root)


def test_legacy_and_current_obsolete_lake_packages_share_one_retirement_preflight(lake):
    native,root,value=lake;content=root/'Content';current=[name for names in value['parents'].values() for name in names]
    previous={native.LEGACY+'/Lake_Cabin',native.DEST+'/Lake_Shore_cell_9_9'}
    for package in previous|{native.DEST+'/'+name for name in current}:
        path=content/(package[6:]+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'owned')
    events=[]
    editor=SimpleNamespace(does_asset_exist=lambda p:True)
    original=native.native_membership
    def refuse(editor,replacements):events.append(replacements);raise ValueError('Foreign reference')
    native.native_membership=SimpleNamespace(retire_replaced=refuse)
    try:
        with pytest.raises(ValueError,match='Foreign reference'):native.retire(editor,previous,current,content)
    finally:native.native_membership=original
    assert len(events)==1 and set(events[0])==previous
    assert all(set(replacements)=={native.DEST+'/'+name for name in current} for replacements in events[0].values())
    assert all((content/(package[6:]+'.uasset')).is_file() for package in previous)
