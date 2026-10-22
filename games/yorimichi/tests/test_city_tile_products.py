import importlib.util
import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

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


@pytest.mark.parametrize('failure', [None, 'triangles', 'save', 'bounds', 'empty', 'subset'])
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
            (folder / (name+'.fbx')).write_bytes(payload)
            tiles.append(dict(name=name, triangles=1 if source=='HD_Streets' else 2,
                              sha256=hashlib.sha256(payload).hexdigest(), min=[1.,2.,3.], max=[2.,4.,5.]))
        sources[source] = dict(source_triangles=2, tiles=tiles)
    if failure == 'empty': sources = {}
    if failure == 'subset': sources = {'HD_Streets': sources['HD_Streets']}
    (folder/'manifest.json').write_text(json.dumps(dict(complete=True, tag='v1_128m', sources=sources)))
    monkeypatch.setenv('CITY_SURFACE_TILES_TAG', 'v1_128m')
    events = []
    material = NS(get_path_name=lambda: '/Game/Japan/Materials/Paving.Paving')
    slot = NS(get_editor_property=lambda key: material if key == 'material_interface' else 'Paving')
    bounds = NS(min=NS(x=100.,y=-400.,z=300.), max=NS(x=200.,y=-200.,z=500.))

    def mesh(name, count):
        return NS(get_num_triangles=lambda lod: count, static_materials=[slot], get_material=lambda i: material,
                  set_material=lambda i, value: None, get_bounding_box=lambda: bounds,
                  get_path_name=lambda: ROOT + '/' + name + '.' + name)

    def imported(path, destination, name, **kwargs):
        events.append('import ' + name)
        result = mesh(name, 7 if failure=='triangles' and name.endswith('Piece1') else
                      1 if name.startswith('HD_Streets') else 2)
        if failure=='bounds':
            result.get_bounding_box=lambda: NS(min=NS(x=100.,y=200.,z=300.),max=NS(x=200.,y=400.,z=500.))
        return result

    editor = NS(load_asset=lambda path: mesh('original', 2),
                list_assets=lambda *args, **kwargs: [tile(old)['asset'], ROOT + '/Authored.Authored'],
                save_loaded_asset=lambda value: events.append('save') or failure!='save',
                does_asset_exist=lambda asset: True,
                delete_asset=lambda asset: events.append('delete ' + asset) or True)
    unreal = NS(EditorAssetLibrary=editor, SystemLibrary=NS(execute_console_command=lambda *args: None),
                log=lambda message: events.append(message))
    namespace = dict(yori=NS(GAME=tmp_path / 'game'), ROOT=tmp_path, unreal=unreal, os=os, json=json,
                     hashlib=hashlib, import_mesh=imported, owned_tiles=P.owned_tiles, obsolete_assets=P.obsolete_assets,
                     require_sources=P.require_sources, native_bounds=P.native_bounds)
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), namespace)
    if failure:
        with pytest.raises(ValueError if failure in ('empty','subset') else AssertionError):
            namespace['main']()
        assert not any(event.startswith('delete ') for event in events)
        assert not (folder / 'import-report.json').exists()
    else:
        namespace['main']()
        assert [event for event in events if event.startswith('delete ')] == ['delete ' + tile(old)['asset']]
        assert events.index('delete ' + tile(old)['asset']) > events.index('import ' + old + '_Piece1')
        assert (folder / 'import-report.json').is_file()


@pytest.mark.parametrize('name', ['HD_Streets_cell_01_2', 'HD_Streets_cell_-0_2', 'HD_Streets_cell_١_2',
                                  'HD_Streets_cell_1_2_Piece'+'0'*17])
def test_noncanonical_lookalikes_remain_unknown(name):
    assert all(not values for values in P.owned_tiles([tile(name)['asset']], ROOT).values())


def test_piece_bounds_explicitly_reflect_y_and_convert_metres_to_centimetres():
    assert P.native_bounds({'min':[1.,2.,3.], 'max':[2.,4.,5.]}) == ((100.,-400.,300.),(200.,-200.,500.))
