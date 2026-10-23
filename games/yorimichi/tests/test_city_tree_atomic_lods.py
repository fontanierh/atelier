"""Tree outline LODs preserve exact original base polygon ownership."""
import ast
import importlib
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]


def test_outline_reducer_remains_identical_to_existing_production_policy():
    def function(path):
        return ast.dump(next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)
                             and n.name == 'simplified'), include_attributes=False)
    assert function(GAME / 'world/city_tree_lods.py') == function(GAME / 'world/regions/hidamari/tree_outline.py')


def test_lod_parts_follow_the_same_complete_face_groups_as_base(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    monkeypatch.syspath_prepend(str(GAME / 'world/regions'))
    module = importlib.import_module('hidamari.plan_tree_lod')
    parent = 'HD_ArcadeTree'
    base = dict(parent=parent, source_polygons=3, source_collision_hulls=2, pieces=[
        dict(name=parent+'_cell_-1_0', source_faces=[0,2], polygons=2),
        dict(name=parent+'_cell_0_0', source_faces=[1], polygons=1)])
    assert module.groups(base,parent,2,3) == [
        (parent+'_LOD2_cell_-1_0',[0,2]), (parent+'_LOD2_cell_0_0',[1])]
    del base['pieces'][1]['source_faces']
    with pytest.raises(ValueError, match='membership'): module.groups(base,parent,2,3)


def test_normal_tree_graph_declares_selected_source_data_and_atomic_exports(tmp_path):
    import importlib.util
    from types import SimpleNamespace
    from atelier.build import check_modules
    path = GAME / 'hidamari_tree_build.py'
    spec = importlib.util.spec_from_file_location('tree_lod_graph_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    steps = module.steps(SimpleNamespace(out=tmp_path.resolve()))
    planners = [s for s in steps if '.geometry.' in s.name]
    assert len(planners) == 6
    for step in planners:
        asset = step.commands[0].args[1]
        assert step.reads == ['hidamari.geometry.' + asset]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert GAME / 'world/regions/hidamari/logical' / (asset+'.py') in step.inputs
        assert all(p.suffix not in ('.fbx','.glb') for p in step.inputs)
    assembly = steps[-1]
    assert assembly.name == 'world.city_trees' and assembly.cache
    assert 'city_tree_lods.atomic' in assembly.reads and 'city.atomic_manifest' in assembly.reads
    check_modules(steps)


def test_lod_manifest_requires_both_levels_for_every_current_tree_child(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME))
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    owner = importlib.import_module('city_tree_atomic_products')
    city_owner = importlib.import_module('city_atomic_products')
    sources = {key: dict(source_triangles=2, source_collision_hulls=0, source_collision_vertices=[],
        source_material_slots=['Palette'], source_bounds=dict(min=[0,0,0],max=[1,1,1]),
        tiles=[dict(name=key,triangles=2,collision_hulls=0,min=[0,0,0],max=[1,1,1])]) for key in city_owner.SOURCES}
    city = dict(version=3,complete=True,tag='v1_128m',triangle_limit=32768,sources=sources)
    spec = dict(version=3,complete=True,tag='v4',screen_sizes=[1.,.18,.07],sources={})
    for key in owner.TREES:
        spec['sources'][key] = [dict(name=key,asset=owner.DESTINATION+'/'+key+'.'+key,original_triangles=2,
            lods=[dict(name=key+'_LOD'+str(level),level=level,triangles=1,sha256='a'*64,bounds=[[0,0,0],[1,1,1]],
                file='atomic_regions/city_tree_lods/assets/'+key+'_LOD'+str(level)+'.fbx') for level in (1,2)])]
    assert owner.read(spec,city) == spec
    spec['sources']['HD_ArcadeTree'][0]['lods'][0]['sha256'] = 'z'*64
    with pytest.raises(ValueError): owner.read(spec,city)
    spec['sources']['HD_ArcadeTree'][0]['lods'].pop()
    with pytest.raises(ValueError): owner.read(spec,city)


def test_native_tree_retirement_owns_only_exact_generated_package_names():
    script = GAME / 'unreal/Scripts/import_city_tree_atomic.py'
    function = next(node for node in ast.parse(script.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='owned')
    import re
    namespace = dict(re=re,DESTINATION='/Game/Experiments/CityTrees/v4',
                     TREES=('HD_ArcadeTree','HD_PlazaTreeGold','HD_PlazaTreeOrange'))
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(script),'exec'),namespace)
    valid = ['/Game/Experiments/CityTrees/v4/HD_ArcadeTree_cell_-1_0_Piece03_v4',
             '/Game/Experiments/CityTrees/v4/lods/HD_PlazaTreeGold_LOD1_cell_0_0']
    assert all(namespace['owned'](value) for value in valid)
    assert namespace['owned'](valid[0]+'.'+valid[0].rsplit('/',1)[-1])
    assert not any(namespace['owned'](value) for value in [valid[0]+'.Foreign',valid[0].replace('v4/','Other/'),
        valid[0].replace('cell_-1','cell_-0'),'/Game/Experiments/CityTrees/v4/Foreign_v4'])
