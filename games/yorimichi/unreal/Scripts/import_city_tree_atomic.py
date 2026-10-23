"""Receive bounded tree LODs without reopening or recreating monolithic parents."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402
import json
import re
import unreal as U
sys.path.insert(0,str(yori.GAME))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from atelier import mesh_geometry, native_membership  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from city_atomic_products import collision_matches, protected_files, native_bounds  # noqa: E402
from city_tree_atomic_products import read, TREES  # noqa: E402
from import_city_surface_tiles import prepare_collision_import, finish_empty_collision  # noqa: E402
from mesh_import import import_mesh  # noqa: E402

DESTINATION = '/Game/Experiments/CityTrees/v4'


def owned(asset):
    if not isinstance(asset,str): return False
    package,separator,obj = asset.partition('.')
    if separator and obj != package.rsplit('/',1)[-1]: return False
    cell = r'(?:_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?)?'
    return any(re.fullmatch(re.escape(DESTINATION+'/'+parent)+cell+r'_v4', package)
               or re.fullmatch(re.escape(DESTINATION+'/lods/'+parent)+r'_LOD[12]'+cell, package)
               for parent in TREES)


def main():
    editor = U.EditorAssetLibrary
    root = yori.OUT
    content = yori.GAME/'unreal/Content'
    folder = real_directory(content/'Experiments/CityTrees/v4')
    city = json.loads((root/'city_surface_tiles/v1_128m/manifest.json').read_text())
    spec = read(json.loads((root/'city_tree_lods/v4/manifest.json').read_text()), city)
    previous = editor.list_assets(DESTINATION, recursive=True, include_folder=False)
    assert all(owned(asset) for asset in previous), 'Foreign package in exclusive city tree owner'
    original_root = content/'Experiments/CitySurfaces/v1_128m'
    before = protected_files(original_root)
    japan = protected_files(content/'Japan')
    U.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
    U.SystemLibrary.execute_console_command(None,'Editor.AsyncStaticMeshCompilation 0')
    U.load_module('StaticMeshEditor')
    meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    assert meshes is not None
    expected = []
    for pieces in spec['sources'].values():
        for piece in pieces:
            expected.append(DESTINATION+'/'+piece['name']+'_v4')
            expected.extend(DESTINATION+'/lods/'+lod['name'] for lod in piece['lods'])
    existing_files = regular_files(folder) if folder.exists() else set()
    assert {str(path.relative_to(folder)) for path in folder.rglob('*') if path.is_dir()} <= {'lods'}, 'Foreign city tree directory'
    allowed = {asset.split('.')[0].removeprefix(DESTINATION+'/')+suffix
               for asset in [*previous,*expected] for suffix in mesh_geometry.SIDECARS}
    assert existing_files <= allowed, 'Foreign file in exclusive city tree owner'
    report = {}
    for parent,pieces in spec['sources'].items():
        tiles = {row['name']:row for row in city['sources'][parent]['tiles']}
        for piece in pieces:
            name = piece['name']; tile = tiles[name]
            original = editor.load_asset(piece['asset'])
            assert original and original.get_num_lods()==1 and original.get_num_triangles(0)==piece['original_triangles'], name
            assert original.get_num_sections(0)==1 and original.get_editor_property('allow_cpu_access'), name
            path = root/'city_surface_tiles/v1_128m'/parent/(name+'.fbx')
            assert sha(path)==tile['sha256'], name
            target_name = name+'_v4'
            target = import_mesh(path,DESTINATION,target_name,fresh_slots=True,
                before_import=lambda: prepare_collision_import(DESTINATION,target_name,meshes))
            if target.get_num_lods()>1: target.set_num_source_models(1)
            meshes.set_lod_build_settings(target,0,meshes.get_lod_build_settings(original,0))
            material = original.get_material(0)
            assert material and len(target.static_materials)==1, name
            if target.get_material(0)!=material: target.set_material(0,material)
            body = target.get_editor_property('body_setup')
            flag = original.get_editor_property('body_setup').get_editor_property('collision_trace_flag')
            if body.get_editor_property('collision_trace_flag')!=flag: body.set_editor_property('collision_trace_flag',flag)
            finish_empty_collision(target,tile,meshes)
            for lod in piece['lods']:
                source_path = root/lod['file']
                real_directory(source_path.parent)
                assert not source_path.is_symlink() and sha(source_path)==lod['sha256'], lod['name']
                source = import_mesh(source_path,DESTINATION+'/lods',lod['name'],fresh_slots=True,
                    before_import=lambda: prepare_collision_import(DESTINATION+'/lods',lod['name'],meshes))
                assert len(source.static_materials)==1 and source.get_num_triangles(0)==lod['triangles'], lod['name']
                ratio = source.get_bounds().sphere_radius/original.get_bounds().sphere_radius
                assert .85 < ratio < 1.05, (lod['name'],'lower LOD units/bounds',ratio)
                minimum,maximum = native_bounds(dict(min=lod['bounds'][0],max=lod['bounds'][1]))
                box = source.get_bounding_box()
                assert all(abs(getattr(box.min,axis)-minimum[i])<.2 and abs(getattr(box.max,axis)-maximum[i])<.2
                           for i,axis in enumerate(('x','y','z'))), (lod['name'],'current source bounds')
                if source.get_material(0)!=material: source.set_material(0,material)
                settings = meshes.get_lod_build_settings(source,0)
                if not settings.get_editor_property('use_full_precision_u_vs'):
                    settings.set_editor_property('use_full_precision_u_vs',True)
                    meshes.set_lod_build_settings(source,0,settings)
                finish_empty_collision(source,dict(name=lod['name'],collision_hulls=0),meshes)
                assert editor.save_loaded_asset(source,only_if_is_dirty=True), lod['name']
                assert meshes.set_lod_from_static_mesh(target,lod['level'],source,0,True)==lod['level'], lod['name']
                source = None
            target.set_editor_property('lod_for_collision',0)
            if not target.get_editor_property('allow_cpu_access'): target.set_editor_property('allow_cpu_access',True)
            assert target.get_num_lods()==3 and target.get_num_triangles(0)==piece['original_triangles'], name
            assert all(meshes.get_lod_build_settings(target,level).get_editor_property('use_full_precision_u_vs') for level in range(3)), name
            assert all(target.get_num_sections(level)==1 and target.get_material(meshes.get_lod_material_slot(target,level,0))==material for level in range(3)), name
            assert collision_matches(target,city['sources'][parent],tile), (name,'authored hulls')
            assert U.CitySurfaceValidation.validate_collision(target,piece['original_triangles'],bool(city['sources'][parent]['source_collision_hulls'])), name
            for field in ('origin','box_extent'):
                for axis in ('x','y','z'):
                    assert abs(getattr(getattr(target.get_bounds(),field),axis)-getattr(getattr(original.get_bounds(),field),axis))<1., (name,field,axis)
            assert meshes.set_lod_screen_sizes(target,spec['screen_sizes']), name
            assert all(abs(a-b)<1e-5 for a,b in zip(meshes.get_lod_screen_sizes(target),spec['screen_sizes'],strict=True)), name
            assert editor.save_loaded_asset(target,only_if_is_dirty=True), name
            report[name] = dict(asset=target.get_path_name(),original=piece['asset'],
                triangles=[target.get_num_triangles(level) for level in range(3)], screen_sizes=spec['screen_sizes'])
            target = original = body = None
            U.SystemLibrary.collect_garbage()
            U.log('CITY ATOMIC TREE LODS '+name)
    inventory = mesh_geometry.package_inventory(content,expected)
    assert protected_files(original_root)==before and protected_files(content/'Japan')==japan, 'Tree LOD owner changed source packages'
    obsolete = sorted({asset.split('.')[0] for asset in previous}-set(expected))
    native_membership.retire_replaced(editor,{asset:expected for asset in obsolete})
    relative_root = 'Experiments/CityTrees/v4/'
    assert regular_files(folder)=={key.removeprefix(relative_root) for key in inventory}, 'Unretired tree LOD files'
    atomic_json(root/'city_tree_lods/v4/import-report.json',dict(complete=True,pieces=report,files=inventory))
    U.log('CITY ATOMIC TREE LODS IMPORT COMPLETE')


if __name__=='__main__': main()
