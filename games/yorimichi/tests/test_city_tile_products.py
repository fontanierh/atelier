import importlib.util
import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
from atelier import native_membership

import pytest


spec = importlib.util.spec_from_file_location('city_tile_products', Path(__file__).parents[1] / 'city_tile_products.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
ROOT = '/Game/Experiments/CitySurfaces/v1_128m'


def tile(name, root=ROOT):
    return {'name': name, 'asset': root + '/' + name + '.' + name}


def test_only_superseded_owned_packages_retire_after_bounded_transition():
    old = 'HD_Streets_cell_4_1'
    stable = 'HD_Terrain_cell_0_0'
    previous = P.owned_tiles([tile(old)['asset'], tile(stable)['asset'],
                              tile(old, ROOT + '_other')['asset'], ROOT + '/Authored.Authored',
                              '/Game/Japan/Assets/HD_Streets.HD_Streets'], ROOT)
    current = {'HD_Terrain': [tile(stable)], 'HD_Streets': [tile(old+'_Piece0'), tile(old+'_Piece1')]}
    assert P.obsolete_assets(previous, current, ROOT) == [tile(old)['asset']]
    assert P.obsolete_assets(current, current, ROOT) == []


def test_unused_piece_removal_and_negative_cell_coordinates():
    one = tile('HD_Square_cell_-1_2_Piece03')
    two = tile('HD_Square_cell_-1_2_Piece01')
    assert P.obsolete_assets({'HD_Square': [one, two]}, {'HD_Square': [two]}, ROOT) == [one['asset']]


@pytest.mark.parametrize('bad', [
    {'Other': []}, {'HD_Square': 'not a list'}, {'HD_Square': [{}]},
    {'HD_Square': [tile('HD_Streets_cell_1_2')]},
    {'HD_Square': [tile('HD_Square_cell_1_2_Piece8')]},
    {'HD_Square': [tile('HD_Square_cell_1_2', '/Game/Other')]},
    {'HD_Square': [tile('HD_Square_cell_1_2'), tile('HD_Square_cell_1_2')]},
])
def test_invalid_ownership_refuses_before_native_deletion(bad):
    with pytest.raises(ValueError):
        P.obsolete_assets(bad, {}, ROOT)


def test_other_folders_or_nontile_names_never_become_owned():
    names = ['/Game/Japan/HD_Streets_cell_0_0.HD_Streets_cell_0_0',
             ROOT + '/HD_Streets_cell_0_0_extra.HD_Streets_cell_0_0_extra',
             ROOT + '/HD_Streets_cell_0_0/sub.sub']
    assert all(not values for values in P.owned_tiles(names, ROOT).values())


def test_ownership_refuses_mismatched_object_names():
    with pytest.raises(ValueError):
        P.owned_tiles([ROOT + '/HD_Streets_cell_0_0.Other'], ROOT)


def test_other_tag_cannot_be_deletion_destination():
    with pytest.raises(ValueError):
        P.obsolete_assets({}, {}, ROOT + '/../Other')


@pytest.mark.parametrize('failure', [None, 'triangles', 'save', 'bounds', 'empty', 'subset', 'collision'])
def test_real_importer_retires_only_after_complete_current_native_validation(tmp_path, monkeypatch, failure):
    script = Path(__file__).parents[1] / 'unreal/Scripts/import_city_surface_tiles.py'
    main = next(node for node in ast.parse(script.read_text()).body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    folder = tmp_path / 'city_surface_tiles/v1_128m'
    folder.mkdir(parents=True)
    old = 'HD_Streets_cell_4_1'
    sources = {}
    for source in P.SOURCES:
        tiles = []
        names = [old+'_Piece0', old+'_Piece1'] if source == 'HD_Streets' else [source+'_cell_0_0']
        for name in names:
            payload = name.encode()
            (folder / source).mkdir(exist_ok=True)
            (folder / source / (name+'.fbx')).write_bytes(payload)
            tiles.append(dict(name=name, triangles=1 if source=='HD_Streets' else 2,
                              collision_hulls=0, sha256=hashlib.sha256(payload).hexdigest(), min=[1.,2.,3.], max=[2.,4.,5.]))
        sources[source] = dict(source_triangles=2, tiles=tiles, source_collision_hulls=0,
                               source_collision_vertices=[], source_material_slots=['HDS_paving'],
                               source_bounds=dict(min=[1.,2.,3.], max=[2.,4.,5.]))
    if failure == 'empty': sources = {}
    if failure == 'subset': sources = {'HD_Streets': sources['HD_Streets']}
    (folder/'manifest.json').write_text(json.dumps(dict(version=2, triangle_limit=32768, complete=True, tag='v1_128m', sources=sources)))
    monkeypatch.setenv('CITY_SURFACE_TILES_TAG', 'v1_128m')
    events = []
    packages = {'/Game/Japan/Assets/'+name for name in P.SOURCES} | {ROOT+'/'+old}
    material = NS(get_path_name=lambda: '/Game/Japan/Materials/Paving.Paving')
    slot = NS(get_editor_property=lambda key: material if key == 'material_interface' else 'HDS_paving')
    bounds = NS(min=NS(x=100.,y=-400.,z=300.), max=NS(x=200.,y=-200.,z=500.))

    body = NS(get_editor_property=lambda key: 'complex')
    def mesh(name, count):
        return NS(get_editor_property=lambda key: body, get_num_triangles=lambda lod: count, static_materials=[slot], get_material=lambda i: material,
                  set_material=lambda i, value: None, get_bounding_box=lambda: bounds,
                  get_path_name=lambda: ROOT + '/' + name + '.' + name)

    def imported(path, destination, name, **kwargs):
        events.append('import ' + name)
        packages.add(destination+'/'+name)
        result = mesh(name, 7 if failure=='triangles' and name.endswith('Piece1') else
                      1 if name.startswith('HD_Streets') else 2)
        if failure=='bounds':
            result.get_bounding_box=lambda: NS(min=NS(x=100.,y=200.,z=300.),max=NS(x=200.,y=400.,z=500.))
        return result

    def remove(asset):
        events.append('delete '+asset)
        packages.remove(asset)
        return True

    def load_material(path):
        assert '/Materials/' in path, 'Importer must never open a source render parent'
        return material

    editor = NS(load_asset=load_material,
                list_assets=lambda *args, **kwargs: [tile(old)['asset'], ROOT + '/Authored.Authored'],
                save_loaded_asset=lambda value, dirty: events.append('save') or failure!='save',
                does_asset_exist=lambda asset: asset in packages,
                find_package_referencers_for_asset=lambda *args,**kwargs: [],
                delete_asset=remove)
    settings = NS(get_editor_property=lambda key: True)
    unreal = NS(CitySurfaceValidation=NS(validate_collision=lambda *args: failure!='collision'), load_module=lambda name: None, StaticMeshEditorSubsystem=object,
                get_editor_subsystem=lambda cls: NS(get_lod_build_settings=lambda mesh,lod: settings),
                CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
                EditorAssetLibrary=editor, SystemLibrary=NS(execute_console_command=lambda *args: None, collect_garbage=lambda: None),
                log=lambda message: events.append(message))
    namespace = dict(yori=NS(GAME=tmp_path / 'game'), ROOT=tmp_path, unreal=unreal, os=os, json=json,
                     hashlib=hashlib, import_mesh=imported, owned_tiles=P.owned_tiles, obsolete_assets=P.obsolete_assets,
                     production_groups=P.production_groups, native_bounds=P.native_bounds,
                     material_paths=P.material_paths, protected_files=lambda root: {},
                     collision_matches=lambda *args: True,
                     native_membership=native_membership)
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), namespace)
    if failure:
        with pytest.raises(ValueError if failure in ('empty','subset') else AssertionError):
            namespace['main']()
        assert not any(event.startswith('delete ') for event in events)
        assert not (folder / 'import-report.json').exists()
    else:
        namespace['main']()
        assert {event for event in events if event.startswith('delete ')} == {
            'delete '+ROOT+'/'+old, *('delete /Game/Japan/Assets/'+name for name in P.SOURCES)}
        assert events.index('delete ' + ROOT+'/'+old) > events.index('import ' + old + '_Piece1')
        assert (folder / 'import-report.json').is_file()


@pytest.mark.parametrize('name', ['HD_Streets_cell_01_2', 'HD_Streets_cell_-0_2', 'HD_Streets_cell_١_2',
                                  'HD_Streets_cell_1_2_Piece'+'0'*17])
def test_noncanonical_lookalikes_remain_unknown(name):
    assert all(not values for values in P.owned_tiles([tile(name)['asset']], ROOT).values())


def test_piece_bounds_explicitly_reflect_y_and_convert_metres_to_centimetres():
    assert P.native_bounds({'min':[1.,2.,3.], 'max':[2.,4.,5.]}) == ((100.,-400.,300.),(200.,-200.,500.))


def production_manifest():
    sources = {}
    for source in P.SOURCES:
        sources[source] = dict(source_triangles=2, source_collision_hulls=1,
            source_collision_vertices=[[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]],
            source_material_slots=['HDS_road','HDS_stone'], source_bounds=dict(min=[0,0,0],max=[1,1,1]),
            tiles=[dict(name=source+'_cell_0_0',triangles=1,collision_hulls=1,min=[0,0,0],max=[1,1,1]),
                   dict(name=source+'_cell_0_1',triangles=1,collision_hulls=0,min=[0,0,0],max=[1,1,1])])
    return dict(version=2,complete=True,tag='v1_128m',cell_metres=128,triangle_limit=32768,sources=sources)


def test_complete_piece_union_replaces_all_parents_without_parent_paths():
    groups = P.production_groups(production_manifest())
    assert set(groups) == set(P.SOURCES)
    assert all(len(pieces)==2 and sum(p['collision_hulls'] for p in pieces)==1 for pieces in groups.values())
    assert all(p['asset'].startswith(ROOT+'/') for pieces in groups.values() for p in pieces)
    assert P.material_paths(['HDS_road','HDS_stone']) == {
        'HDS_road':'/Game/Japan/Materials/MI_Road', 'HDS_stone':'/Game/Japan/Hidamari/Materials/MI_HD_stone'}


@pytest.mark.parametrize('bad', ['missing','sum','budget','duplicate','hull','hull_vertices','slots','bounds'])
def test_incomplete_or_changed_geometry_collision_membership_refuses(bad):
    manifest = production_manifest()
    source = manifest['sources']['HD_Streets']
    if bad=='missing': del manifest['sources']['HD_Square']
    if bad=='sum': source['source_triangles'] += 1
    if bad=='budget': source['tiles'][0]['triangles'] = 32769
    if bad=='duplicate': source['tiles'][1]['name'] = source['tiles'][0]['name']
    if bad=='hull': source['tiles'][1]['collision_hulls'] = 1
    if bad=='hull_vertices': source['source_collision_vertices'][0].pop()
    if bad=='slots': source['source_material_slots'][0] = '../road'
    if bad=='bounds': source['source_bounds']['min'][0] = float('nan')
    with pytest.raises(ValueError): P.production_groups(manifest)


def test_source_assembly_reuses_completed_siblings_and_refuses_partial_publication(tmp_path):
    report = production_manifest()
    before = {}
    for source,row in report['sources'].items():
        folder = tmp_path/source
        folder.mkdir()
        value = {**report, 'sources':{source:row}}
        (folder/'manifest.json').write_text(json.dumps(value))
        for tile in row['tiles']:
            (folder/(tile['name']+'.fbx')).write_bytes(b'current source')
        before[source] = (folder/'manifest.json').read_bytes()
    old = tmp_path/'HD_Streets_cell_99_1.fbx'
    old.write_bytes(b'superseded flat export')
    foreign = tmp_path/'Authored.fbx'
    foreign.write_bytes(b'not owned')
    P.assemble(tmp_path, lambda message: None)
    assert not old.exists() and foreign.read_bytes()==b'not owned'
    assert json.loads((tmp_path/'manifest.json').read_text()) == report
    assert all((tmp_path/name/'manifest.json').read_bytes()==data for name,data in before.items())
    (tmp_path/'HD_Square/manifest.json').write_text('{}')
    with pytest.raises(ValueError): P.assemble(tmp_path, lambda message: None)
    assert json.loads((tmp_path/'manifest.json').read_text()) == report


def test_actual_collision_hulls_require_complete_transformed_vertex_identity():
    points = [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    hulls = [list(reversed(points))]
    mesh = object()
    read = lambda _: json.dumps(hulls)
    row = {'source_collision_vertices':[[list(point) for point in points]]}
    assert P.collision_matches(mesh,row,{'collision_hulls':1},read_vertices=read)
    row['source_collision_vertices'][0][1][0] += .02
    assert not P.collision_matches(mesh,row,{'collision_hulls':1},read_vertices=read)
    hulls.clear()
    assert not P.collision_matches(mesh,row,{'collision_hulls':1},read_vertices=read)
    assert P.collision_matches(mesh,row,{'collision_hulls':0},read_vertices=read)


@pytest.mark.parametrize('invalid', ['', '{}', '[[]]', '[[[0,0,0],[1,0,0],[0,1,0],[0,0,NaN]]]'])
def test_unsupported_native_collision_readback_refuses(invalid):
    assert not P.collision_matches(object(),{'source_collision_vertices':[]},
                                   {'collision_hulls':0},read_vertices=lambda _:invalid)


def test_parent_absence_is_a_receiving_postcondition_including_orphan_sidecars(tmp_path):
    root = tmp_path/'Japan/Assets'
    root.mkdir(parents=True)
    (root/'Other.uasset').write_bytes(b'foreign')
    assert P.parents_retired(tmp_path)
    for extension in ('.uasset','.uexp','.ubulk','.uptnl','.m.ubulk','.upayload'):
        path = root/('HD_Streets'+extension)
        path.write_bytes(b'old parent')
        assert not P.parents_retired(tmp_path)
        path.unlink()
    assert P.parents_retired(tmp_path)


def test_assembly_never_publishes_without_every_current_fbx(tmp_path):
    report = production_manifest()
    for source,row in report['sources'].items():
        folder = tmp_path/source
        folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({**report,'sources':{source:row}}))
    old = tmp_path/'HD_Streets_cell_0_0.fbx'
    old.write_bytes(b'old')
    with pytest.raises(ValueError, match='Missing completed'):
        P.assemble(tmp_path, lambda message: None)
    assert not (tmp_path/'manifest.json').exists() and old.read_bytes()==b'old'


@pytest.mark.parametrize('source', ['HD_CivicGardens', 'HD_Park'])
def test_added_family_is_mandatory_and_its_parent_sidecars_must_retire(tmp_path, source):
    manifest = production_manifest()
    assert source in P.production_groups(manifest)
    del manifest['sources'][source]
    with pytest.raises(ValueError, match='all five'):
        P.production_groups(manifest)
    root = tmp_path/'Japan/Assets'
    root.mkdir(parents=True)
    (root/(source+'.ubulk')).write_bytes(b'old whole parent bulk')
    assert not P.parents_retired(tmp_path)
