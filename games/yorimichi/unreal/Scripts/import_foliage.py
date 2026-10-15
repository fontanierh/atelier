"""Own one tree/bush/grass package and its LOD source packages, at stable runtime paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import json
import os
import unreal as U

import yori
from asset_catalog import FOLIAGE
from import_foliage_lods import apply_lods
from mesh_import import import_mesh


def verify_bounds(mesh, authored):
    """Compare authored metres with Unreal centimetres, independent of the Y-axis flip."""
    bounds = mesh.get_bounding_box()
    extents = [getattr(bounds.max, axis) - getattr(bounds.min, axis) for axis in ('x', 'y', 'z')]
    expected = [(b - a) * 100 for a, b in zip(*authored)]
    assert all(abs(a - b) < .1 for a, b in zip(extents, expected)), (mesh.get_name(), 'bounds', extents, expected)


def main():
    """@cc [owner:fontanierh,label:correctness] complete-foliage-package-owner
    One action MUST import and validate its LOD0, LOD chain, slots, collision and runtime flags.
    It MUST preserve stable package paths, save its final packages and never modify shared materials.
    """
    name = os.environ['ATELIER_FOLIAGE']
    if name not in FOLIAGE:
        raise ValueError('Unknown foliage owner: ' + name)
    source = yori.OUT / 'foliage' / name
    data = json.loads((source / 'manifest.json').read_text())
    interface = json.loads((yori.OUT / 'materials/foliage-interface.json').read_text())
    editor = U.EditorAssetLibrary
    U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    U.load_module('StaticMeshEditor')
    meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    if meshes is None:
        raise RuntimeError('StaticMeshEditor subsystem is unavailable')
    path = '/Game/Japan/Assets/' + name
    if editor.does_asset_exist(path):
        previous = editor.load_asset(path)
        # Reimport must also remove a deleted LOD or a collision hull, not just add new data.
        previous.set_num_source_models(1)
        meshes.remove_collisions(previous)
    seed = source / (name + '_Seed.fbx')
    mesh = import_mesh(source / (name + '.fbx'), '/Game/Japan/Assets', name, seed=seed, fresh_slots=True)
    verify_bounds(mesh, data['bounds'])
    palette = []
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        material = editor.load_asset('/Game/Japan/Materials/MI_' + key)
        if not material:
            raise RuntimeError('Missing shared material: ' + key)
        mesh.set_material(index, material)
        palette.append(key)
    assert sorted(palette) == sorted(data['materials']), (name, 'material slots', palette)
    mesh.set_editor_property('allow_cpu_access', False)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise RuntimeError('Missing body setup: ' + name)
    flag = {'complex': U.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, 'default': U.CollisionTraceFlag.CTF_USE_DEFAULT}
    body.set_editor_property('collision_trace_flag', flag[data['collision']])
    folder = '/Game/Japan/FoliageLODs/' + name
    expected = {folder + f'/{name}_LOD{i}' for i in range(1, len(data['screen_sizes']))}
    for asset in editor.list_assets(folder, recursive=True):
        package = asset.split('.')[0]
        if package not in expected and not editor.delete_asset(asset):
            raise RuntimeError('Cannot retire owned LOD: ' + asset)
    report = apply_lods(mesh, data, source, meshes, seed=seed, folder=folder, interface=interface)
    report['triangles'] = [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())]
    assert report['triangles'] == data['triangles'], (name, 'triangles', report['triangles'], data['triangles'])
    verify_bounds(mesh, data['bounds'])
    report['collision'] = data['collision']
    report['simple_collisions'] = meshes.get_simple_collision_count(mesh)
    report['convex_collisions'] = meshes.get_convex_collision_count(mesh)
    # UE counts boxes, spheres and capsules separately from authored UCX convex hulls.
    assert report['simple_collisions'] == 0, (name, 'unexpected collision primitives', report)
    assert report['convex_collisions'] == (1 if data['trunk_collision'] else 0), (name, 'collision hulls', report)
    assert meshes.get_collision_complexity(mesh) == flag[data['collision']], (name, 'collision policy', report)
    if not editor.save_loaded_asset(mesh, False):
        raise RuntimeError('Could not save foliage package: ' + path)
    report_path = yori.OUT / 'imports/foliage' / (name + '.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    U.log('FOLIAGE IMPORT COMPLETE ' + name + ': ' + json.dumps(report))


if __name__ == '__main__':
    main()
