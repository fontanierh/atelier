"""Production Streets pieces own both visible geometry and complex collision."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(yori.GAME))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import hashlib
import json
from pathlib import Path

import unreal
from atelier.native_membership import retire
from atelier.mesh_geometry import package_inventory
from city_tile_products import STREETS, STREETS_DESTINATION, native_bounds, streets_source, tile_name, streets_source_key, streets_present


def verify(mesh, tile, bindings, editor):
    if not mesh or mesh.get_num_triangles(0) != tile['triangles']:
        raise ValueError('Missing or altered native Streets piece: '+tile['name'])
    slots = list(mesh.static_materials)
    names = [str(slot.get_editor_property('imported_material_slot_name')) for slot in slots]
    if (len(names) != len(bindings) or set(names) != set(bindings)
            or any(not mesh.get_material(i) or mesh.get_material(i).get_path_name() != bindings[name]
                   for i, name in enumerate(names))):
        raise ValueError('Streets piece material bindings changed')
    if not editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'):
        raise ValueError('Streets piece lost full precision UVs')
    body = mesh.get_editor_property('body_setup')
    if not body or body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:
        raise ValueError('Streets piece must own its complex collision')
    if mesh.get_editor_property('complex_collision_mesh') is not None or mesh.get_editor_property('lod_for_collision') != 0:
        raise ValueError('Streets piece collision must use its own LOD0')
    low, high = native_bounds(tile)
    box = mesh.get_bounding_box()
    if any(abs(getattr(box.min, axis)-low[i]) > .2 or abs(getattr(box.max, axis)-high[i]) > .2
           for i, axis in enumerate(('x', 'y', 'z'))):
        raise ValueError('Streets piece bounds changed')


def settings_reader():
    unreal.load_module('StaticMeshEditor')
    reader = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if reader is None:
        reader = unreal.get_default_object(unreal.StaticMeshEditorSubsystem)
    if reader is None:
        raise ValueError('Streets mesh settings subsystem unavailable')
    return reader


def import_streets(out, game, materials, importer):
    """@cc [owner:fontanierh,label:correctness] streets-parent-retirement
    Every current piece MUST bind the original surface materials, retain full precision
    UVs and own complex collision, then validate and save before any old parent retires.
    The complete current roster and external references MUST be checked before deletion.
    Source FBX/query geometry remains owned by its exporter; no native hidden parent MAY
    remain as a collision or preparation fallback. Failures MUST prevent owner success.
    """
    folder = Path(out)/'city_surface_tiles/v1_128m'
    source = streets_source(json.loads((folder/'manifest.json').read_text()))
    bindings = {slot: materials[slot.removeprefix('HDS_')] for slot in source['source_slots']}
    if not all(bindings.values()):
        raise ValueError('Missing current Streets material')
    paths = {slot: material.get_path_name() for slot, material in bindings.items()}
    editor = settings_reader()
    assets = unreal.EditorAssetLibrary
    previous = set()
    for asset in assets.list_assets(STREETS_DESTINATION, recursive=False, include_folder=False):
        package = str(asset).split('.')[0]
        name = package.removeprefix(STREETS_DESTINATION+'/')
        if package == STREETS_DESTINATION+'/'+name and (name == STREETS or tile_name(STREETS, name)):
            previous.add(package)
    for tile in source['tiles']:
        path = folder/(tile['name']+'.fbx')
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != tile['sha256']:
            raise ValueError('Missing or changed Streets piece source')
        mesh = importer(path, STREETS_DESTINATION, tile['name'], fresh_slots=True)
        slots = list(mesh.static_materials)
        if len(slots) != len(bindings):
            raise ValueError('Streets piece lost source slots')
        for index, slot in enumerate(slots):
            name = str(slot.get_editor_property('imported_material_slot_name'))
            if name not in bindings:
                raise ValueError('Unexpected Streets material slot')
            if mesh.get_material(index) != bindings[name]:
                mesh.set_material(index, bindings[name])
        build = editor.get_lod_build_settings(mesh, 0)
        if not build.get_editor_property('use_full_precision_u_vs'):
            build.set_editor_property('use_full_precision_u_vs', True)
            editor.set_lod_build_settings(mesh, 0, build)
        body = mesh.get_editor_property('body_setup')
        if not body:
            raise ValueError('Streets piece has no collision body')
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        if mesh.get_editor_property('complex_collision_mesh') is not None:
            mesh.set_editor_property('complex_collision_mesh', None)
        if mesh.get_editor_property('lod_for_collision') != 0:
            mesh.set_editor_property('lod_for_collision', 0)
        verify(mesh, tile, paths, editor)
        if not assets.save_loaded_asset(mesh):
            raise ValueError('Could not save Streets piece')
        primary = Path(game)/'unreal/Content/Japan/Assets'/(tile['name']+'.uasset')
        if primary.is_symlink() or not primary.is_file():
            raise ValueError('Streets piece has no saved native primary')
    inventory = package_inventory(Path(game)/'unreal/Content',
                                  [STREETS_DESTINATION+'/'+tile['name'] for tile in source['tiles']])
    retire(assets, previous, [tile['name'] for tile in source['tiles']], STREETS_DESTINATION, 'HD_',
           name_check=lambda name: name == STREETS or tile_name(STREETS, name))
    if assets.does_asset_exist(STREETS_DESTINATION+'/'+STREETS):
        raise ValueError('Superseded Streets parent still exists')
    report = dict(source=streets_source_key(source), bindings=paths, files=inventory)
    (Path(out)/'native-city-streets.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    return source


def verified_streets(out):
    """Read the world owner's complete production roster; never import a second copy."""
    out = Path(out)
    source = streets_source(json.loads((out/'city_surface_tiles/v1_128m/manifest.json').read_text()))
    report = json.loads((out/'native-city-streets.json').read_text())
    if not streets_present(out, yori.GAME/'unreal/Content', inventory=package_inventory):
        raise ValueError('Stale production Streets roster')
    editor = settings_reader()
    assets = unreal.EditorAssetLibrary
    if assets.does_asset_exist(STREETS_DESTINATION+'/'+STREETS):
        raise ValueError('Superseded Streets parent remains discoverable')
    result = []
    for tile in source['tiles']:
        package = STREETS_DESTINATION+'/'+tile['name']
        mesh = assets.load_asset(package)
        verify(mesh, tile, report['bindings'], editor)
        result.append(dict(name=tile['name'], asset=package+'.'+tile['name'], triangles=tile['triangles']))
    return result


def main():
    source = streets_source(json.loads((yori.OUT/'city_surface_tiles/v1_128m/manifest.json').read_text()))
    from city_material import load_surface_materials
    from import_village import import_mesh
    import_streets(yori.OUT, yori.GAME, load_surface_materials([name.removeprefix('HDS_') for name in source['source_slots']]), import_mesh)
    unreal.log('CITY STREETS IMPORT COMPLETE')


if __name__ == '__main__':
    main()
