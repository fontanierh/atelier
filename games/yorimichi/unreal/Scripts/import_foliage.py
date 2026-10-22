"""Own one tree/bush/grass package and its LOD source packages, at stable runtime paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))

import json
import os
import unreal as U

import yori
from asset_catalog import FOLIAGE
from import_foliage_lods import apply_lods, crown_path
from mesh_import import import_mesh
from foliage_package_repair import require_valid_or_missing


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
    import_trunk = data['import_trunk_collision']
    if type(import_trunk) is not bool or (import_trunk and not data['trunk_collision']):
        raise ValueError('Invalid authored trunk collision policy: ' + name)
    interface = json.loads((yori.OUT / 'materials/foliage-interface.json').read_text())
    editor = U.EditorAssetLibrary
    U.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    U.load_module('StaticMeshEditor')
    meshes = U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    if meshes is None:
        raise RuntimeError('StaticMeshEditor subsystem is unavailable')
    path = '/Game/Japan/Assets/' + name
    folder = '/Game/Japan/FoliageLODs/' + name
    expected = {folder + f'/{name}_LOD{i}' for i in range(1, len(data['screen_sizes']))}
    # The far crown's material lives with the LODs; it is retired only when the manifest drops the crown.
    if data.get('crown'):
        expected.add(crown_path(data['crown'], folder))
    require_valid_or_missing(yori.GAME / 'unreal/Content', name)
    def prepare_import():
        if editor.does_asset_exist(path):
            previous = editor.load_asset(path)
            if previous is not None:
                # Reimport must remove deleted LODs/hulls, after saved-byte admission misses.
                previous.set_num_source_models(1)
                meshes.remove_collisions(previous)
    def reusable_collision(mesh):
        return mesh.get_name() != name or not import_trunk or (meshes.get_simple_collision_count(mesh) == 0
                                    and meshes.get_convex_collision_count(mesh) == 1)
    seed = source / (name + '_Seed.fbx')
    mesh = import_mesh(source / (name + '.fbx'), '/Game/Japan/Assets', name, seed=seed,
                       fresh_slots=True, before_import=prepare_import, reuse_validator=reusable_collision)
    # A saved base may still contain the previous longer assembled chain.
    # Trim it only after admission, then build and validate the current manifest.
    mesh.set_num_source_models(1)
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
    # The legacy imported catalogue has no simple shapes, even where the FBX contains UCX.
    # Keep that runtime policy explicit rather than adding colliders during this migration.
    if not import_trunk and not meshes.remove_collisions(mesh):
        raise RuntimeError('Could not clear disabled trunk collision: ' + name)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise RuntimeError('Missing body setup: ' + name)
    flag = {'complex': U.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE, 'default': U.CollisionTraceFlag.CTF_USE_DEFAULT}
    body.set_editor_property('collision_trace_flag', flag[data['collision']])
    report = apply_lods(mesh, data, source, meshes, seed=seed, folder=folder, interface=interface,
                        reuse_validator=reusable_collision)
    report['triangles'] = [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())]
    assert report['triangles'] == data['triangles'], (name, 'triangles', report['triangles'], data['triangles'])
    verify_bounds(mesh, data['bounds'])
    report['collision'] = data['collision']
    report['import_trunk_collision'] = import_trunk
    report['simple_collisions'] = meshes.get_simple_collision_count(mesh)
    report['convex_collisions'] = meshes.get_convex_collision_count(mesh)
    # UE counts boxes, spheres and capsules separately from authored UCX convex hulls.
    assert report['simple_collisions'] == 0, (name, 'unexpected collision primitives', report)
    assert report['convex_collisions'] == int(import_trunk), (name, 'collision hulls', report)
    assert meshes.get_collision_complexity(mesh) == flag[data['collision']], (name, 'collision policy', report)
    # Fresh FBX packages default to 64; the legacy catalogue uses resolution 4 and UV0.
    # Apply this after LOD assembly so repairs do not inherit a factory or previous-package default.
    for key, value in (('light_map_resolution', 4), ('light_map_coordinate_index', 0)):
        mesh.set_editor_property(key, value)
        assert mesh.get_editor_property(key) == value, (name, key, value)
    if not editor.save_loaded_asset(mesh, False):
        raise RuntimeError('Could not save foliage package: ' + path)
    # Only now, with the replacement chain validated and saved, retire this tree's obsolete LODs and dropped crown
    # material, and only when nothing outside that obsolete set still uses them.
    stale = [asset for asset in editor.list_assets(folder, recursive=True) if asset.split('.')[0] not in expected]
    obsolete = {asset.split('.')[0] for asset in stale}
    for asset in stale:
        users = set(editor.find_package_referencers_for_asset(asset, False)) - obsolete
        if users:
            raise RuntimeError('Obsolete owned LOD still referenced: ' + asset + ' by ' + ', '.join(sorted(users)))
    for asset in stale:
        if not editor.delete_asset(asset):
            raise RuntimeError('Cannot retire owned LOD: ' + asset)
    report_path = yori.OUT / 'imports/foliage' / (name + '.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    U.log('FOLIAGE IMPORT COMPLETE ' + name + ': ' + json.dumps(report))


if __name__ == '__main__':
    main()
