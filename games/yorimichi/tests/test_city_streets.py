"""Production city pieces replace the monolith's rendering AND collision."""
import copy
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace as NS

import pytest
from atelier.mesh_geometry import package_inventory


GAME = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('city_tile_products', GAME/'city_tile_products.py')
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)


def manifest():
    tiles = [dict(name='HD_Streets_cell_0_'+str(i), triangles=1, sha256=hashlib.sha256(str(i).encode()).hexdigest(),
                  min=[0., float(i), 0.], max=[1., float(i+1), 1.]) for i in range(2)]
    return dict(complete=True, tag='v1_128m', triangle_limit=32768,
                sources=dict(HD_Terrain={}, HD_Square={}, HD_Streets=dict(
                    source_triangles=2, source_min=[0., 0., 0.], source_max=[1., 2., 1.],
                    source_slots=['HDS_road'], source_collision_boxes=0, tiles=tiles)))


def test_actual_runtime_piece_roster_preserves_all_placements_and_source_queries():
    city = dict(instances=dict(HD_Streets=[[0., 0., 0., 0., 1.], [2., 3., 4., 75., .5]], Other=[[1,2,3,4,5]]),
                roads=[[[1.,2.,3.]]])
    before = copy.deepcopy(city)
    result = P.streets_instances(city, manifest())
    assert city == before
    assert 'HD_Streets' not in result['instances']
    for tile in manifest()['sources']['HD_Streets']['tiles']:
        assert result['instances'][tile['name']] == before['instances']['HD_Streets']
    assert result['instances']['Other'] == before['instances']['Other']
    assert result['roads'] == city['roads']


@pytest.mark.parametrize('change', ['incomplete', 'triangles', 'bounds', 'duplicate', 'collision', 'slots', 'unbounded', 'path'])
def test_invalid_partition_never_publishes_native_runtime_membership(change):
    value = manifest(); source = value['sources']['HD_Streets']
    if change == 'incomplete': value['complete'] = False
    elif change == 'triangles': source['source_triangles'] += 1
    elif change == 'bounds': source['source_max'][2] += .01
    elif change == 'duplicate': source['tiles'][1] = source['tiles'][0]
    elif change == 'collision': source['source_collision_boxes'] = 1
    elif change == 'slots': source['source_slots'] = ['Unknown']
    elif change == 'unbounded': source['tiles'][0]['triangles'] = 32769
    else: source['tiles'][0]['name'] = '../Other'
    with pytest.raises(ValueError): P.streets_source(value)


@pytest.mark.parametrize('placements', [None, [], [[0,0,0,0,False]], [[0,0,0,float('nan'),1]], [[0,0,0,0,0]]])
def test_missing_or_invalid_placements_are_not_replaced_by_identity(placements):
    with pytest.raises(ValueError): P.streets_instances(dict(instances=dict(HD_Streets=placements)), manifest())


class Properties:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value


@pytest.mark.parametrize('negative', [False, True])
@pytest.mark.parametrize('failure', [None, 'triangles', 'bounds', 'save', 'primary', 'linked-sidecar', 'foreign-reference', 'delete'])
def test_real_native_owner_saves_all_collision_pieces_before_parent_retirement(tmp_path, monkeypatch, failure, negative):
    value = manifest(); out = tmp_path/'out'; game = tmp_path/'game'
    if negative:
        for tile in value['sources']['HD_Streets']['tiles']:
            tile['name'] = tile['name'].replace('_cell_0_', '_cell_-2_')
    folder = out/'city_surface_tiles/v1_128m'; folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps(value))
    for i, tile in enumerate(value['sources']['HD_Streets']['tiles']):
        (folder/(tile['name']+'.fbx')).write_bytes(str(i).encode())
    material = NS(get_path_name=lambda: '/Game/Materials/Road.Road')
    old = '/Game/Japan/Assets/HD_Streets'
    assets = {old: NS()}; events = []
    class Editor:
        def list_assets(self, *args, **kwargs): return [p+'.'+p.rsplit('/',1)[-1] for p in assets]
        def does_asset_exist(self, path): return path in assets
        def save_loaded_asset(self, mesh): events.append('save '+mesh.name); return failure != 'save'
        def find_package_referencers_for_asset(self, path, **kwargs):
            events.append('references '+path)
            return ['/Game/Foreign'] if failure == 'foreign-reference' else []
        def delete_asset(self, path):
            events.append('delete '+path)
            if failure == 'delete': return False
            del assets[path]; return True
    settings = NS(get_lod_build_settings=lambda mesh, lod: mesh.build,
                  set_lod_build_settings=lambda mesh, lod, build: None)
    unreal = NS(EditorAssetLibrary=Editor(), CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
                load_module=lambda name: None, StaticMeshEditorSubsystem=object(),
                get_editor_subsystem=lambda cls: settings)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.setitem(sys.modules, 'city_tile_products', P)
    spec = importlib.util.spec_from_file_location('production_streets', GAME/'unreal/Scripts/import_city_streets.py')
    owner = importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
    monkeypatch.setattr(owner, 'yori', NS(GAME=game, OUT=out))
    def importer(path, destination, name, **kwargs):
        tile = next(t for t in value['sources']['HD_Streets']['tiles'] if t['name'] == name)
        low, high = P.native_bounds(tile)
        mesh = NS(name=name, static_materials=[Properties(imported_material_slot_name='HDS_road')],
                  build=Properties(use_full_precision_u_vs=False), body=Properties(collision_trace_flag=None))
        mesh.get_num_triangles=lambda lod: 7 if failure == 'triangles' else 1
        mesh.get_material=lambda index: material
        properties = dict(body_setup=mesh.body, complex_collision_mesh=object(), lod_for_collision=2)
        mesh.get_editor_property=lambda key: properties[key]
        mesh.set_editor_property=lambda key, val: properties.__setitem__(key, val)
        mesh.get_bounding_box=lambda: NS(min=NS(**dict(zip('xyz', low))),
                                        max=NS(**dict(zip('xyz', [999.,999.,999.] if failure == 'bounds' else high))))
        assets[destination+'/'+name] = mesh
        primary = game/'unreal/Content/Japan/Assets'/(name+'.uasset')
        primary.parent.mkdir(parents=True, exist_ok=True)
        if failure != 'primary': primary.write_bytes(b'native piece')
        if failure == 'linked-sidecar': primary.with_suffix('.ubulk').symlink_to(primary)
        events.append('import '+name)
        return mesh
    if failure:
        with pytest.raises(ValueError): owner.import_streets(out, game, {'road':material}, importer)
        assert old in assets
        assert not (out/'native-city-streets.json').exists()
        if failure != 'delete': assert not any(e.startswith('delete ') for e in events)
    else:
        owner.import_streets(out, game, {'road':material}, importer)
        assert old not in assets
        assert events.index('delete '+old) > max(i for i,e in enumerate(events) if e.startswith('save '))
        assert all(mesh.body.values['collision_trace_flag']=='complex' for mesh in assets.values())
        assert all(mesh.get_editor_property('complex_collision_mesh') is None and
                   mesh.get_editor_property('lod_for_collision') == 0 for mesh in assets.values())
        unreal.EditorAssetLibrary.load_asset=lambda path: assets.get(path)
        assert len(owner.verified_streets(out)) == 2
        assert not any('HD_Streets.HD_Streets' in e for e in events if e.startswith('import '))
        assert P.streets_present(out, game/'unreal/Content', inventory=package_inventory)
        primary = game/'unreal/Content/Japan/Assets'/(source_name := value['sources']['HD_Streets']['tiles'][0]['name']+'.uasset')
        primary.unlink()
        assert not P.streets_present(out, game/'unreal/Content', inventory=package_inventory), source_name


def test_real_data_staging_publishes_piece_instances_and_keeps_offline_city_whole(tmp_path, monkeypatch):
    from atelier import build
    data = build.load_recipe('yorimichi').runtime_data
    out = tmp_path/'out'; (out/'hidamari').mkdir(parents=True)
    city = dict(instances=dict(HD_Streets=[[0,0,0,0,1]]), roads=[])
    (out/'hidamari/city.json').write_text(json.dumps(city))
    folder = out/'city_surface_tiles/v1_128m'; folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps(manifest()))
    monkeypatch.setattr(data, 'staged', lambda out: ['hidamari/city.json'])
    monkeypatch.setattr(data.courses, 'load', lambda *args: None)
    monkeypatch.setattr(data.paths, 'content_data', lambda game: tmp_path/'Data')
    data.stage_data(NS(out=out, game='yorimichi'), io.StringIO())
    actual = json.loads((tmp_path/'Data/hidamari/city.json').read_text())
    assert actual == P.streets_instances(city, manifest())
    assert json.loads((out/'hidamari/city.json').read_text()) == city


def test_normal_graph_has_an_independent_complete_streets_owner(tmp_path):
    from atelier import build
    recipe = build.load_recipe('yorimichi')
    steps = {step.name:step for step in recipe.steps(NS(out=tmp_path, uproject=None))}
    owner = steps['unreal.city_streets']
    assert owner.commands[0].script == GAME/'unreal/Scripts/import_city_streets.py'
    assert owner.commands[0].script in owner.inputs
    assert GAME/'city_tile_products.py' in owner.inputs
    assert GAME/'unreal/Scripts/city_material.py' in owner.inputs
    assert set(owner.needs) == {'unreal.world', 'world.city_tiles.meshes'}
    assert 'unreal.city_streets' in steps['unreal.desktop'].needs
    assert steps['unreal.city_streets'].verify is not None
    assert not owner.verify()
    assert 'world.city_tiles.meshes' not in steps['unreal.world'].needs
    assert GAME/'city_tile_products.py' in steps['data.stage'].inputs


def test_streets_entrypoint_bootstraps_local_helpers_without_editable_site_or_pythonpath(tmp_path):
    script = GAME/'unreal/Scripts/import_city_streets.py'
    code = '''import importlib.util,sys,types
from pathlib import Path
sys.modules['unreal']=types.ModuleType('unreal')
path=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('isolated_streets_owner',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for name in ('city_material','import_village'):
    assert Path(importlib.util.find_spec(name).origin).parent==path.parent
assert callable(module.main)
'''
    subprocess.run([sys.executable, '-I', '-S', '-c', code, str(script)], cwd=tmp_path,
                   check=True, capture_output=True, timeout=15)


def test_normal_build_repairs_a_missing_piece_without_running_the_world(tmp_path, monkeypatch):
    from atelier import build
    from atelier.mesh_geometry import package_inventory
    recipe = build.load_recipe('yorimichi')
    out, game = tmp_path/'out', tmp_path/'game'
    content = game/'unreal/Content'
    folder = out/'city_surface_tiles/v1_128m'; folder.mkdir(parents=True)
    value = manifest(); (folder/'manifest.json').write_text(json.dumps(value))
    source = value['sources']['HD_Streets']
    ctx = NS(game='yorimichi', out=out, logs=out/'logs', stamps=out/'stamps', uproject=None)
    actual = next(step for step in recipe.steps(ctx) if step.name == 'unreal.city_streets')
    runs = []
    packages = [P.STREETS_DESTINATION+'/'+tile['name'] for tile in source['tiles']]
    def repair(ctx, log):
        runs.append(True)
        for package in packages:
            target = content/(package.removeprefix('/Game/')+'.uasset')
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b'verified piece')
        (out/'native-city-streets.json').write_text(json.dumps(dict(
            source=P.streets_source_key(source), bindings={'HDS_road':'/Game/Materials/Road.Road'},
            files=package_inventory(content, packages))))
    code = tmp_path/'owner.py'; code.write_text('same source')
    bounded = replace(actual, commands=[build.Call('repair Streets fixture', repair)], needs=[], after=[],
                      inputs=[code], candidate_scope=None)
    monkeypatch.setattr(recipe, 'GAME', game)  # The actual recipe verify closes over this native root.
    monkeypatch.setattr(build, 'Context', lambda name: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda name: NS(steps=lambda ctx:[bounded]))
    assert build.build('yorimichi', echo=lambda line:None) == 0
    assert build.build('yorimichi', echo=lambda line:None) == 0 and len(runs) == 1
    missing = content/(packages[0].removeprefix('/Game/')+'.uasset')
    missing.unlink()
    assert build.build('yorimichi', echo=lambda line:None) == 0 and len(runs) == 2
    assert missing.is_file()
