"""Receive independently bounded island meshes; retire the old parent after map migration only."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402,F401
import json
import re
import sys
from pathlib import Path

import unreal

sys.path.insert(0, str(yori.GAME))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from atelier import native_membership  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from island_atomic_products import DESTINATION, PARENTS, material_paths, native_bounds, read  # noqa: E402
from mesh_import import import_mesh  # noqa: E402


def owned_packages(paths):
    """The exclusive native folder admits only canonical current/former island pieces."""
    result = set()
    for path in paths:
        if not isinstance(path, str) or not path.startswith(DESTINATION + '/'):
            raise ValueError('Island native inventory escaped its owned folder')
        relative = path[len(DESTINATION)+1:]
        key = relative.split('.')[0]
        if (relative not in (key, key + '.' + key) or not any(re.fullmatch(
                re.escape(parent) + r'(?:_cell_-?\d+_-?\d+(?:_Piece[A-Za-z0-9]+)?)?', key) for parent in PARENTS)):
            raise ValueError('Foreign package in island native owner')
        package = DESTINATION + '/' + key
        if package in result: raise ValueError('Duplicate island native package')
        result.add(package)
    return result


def _empty_collision(mesh, editor):
    if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
        assert editor.remove_collisions(mesh), ('Island stale collision reset failed', mesh.get_path_name())
    assert editor.get_simple_collision_count(mesh) == editor.get_convex_collision_count(mesh) == 0


def receive(out=None):
    """@cc [owner:fontanierh,label:correctness;performance] receive-independent-island-pieces
    Validate the complete source inventory before native mutation, then admit each bounded
    primary independently on untouched saved packages. A real raw-import miss MAY clear
    only that child's stale hulls before import; current zero-hull finishing MUST also run
    on reuse hits. Bind every original named material and require current render counts,
    bounds, original legacy half-precision UV settings/channel count, LOD0 cooked complex surface and zero simple
    hulls before saving. Never load, join or retire the old combined Terrain here.
    Sea's runtime components MUST remain nonblocking and shadow-free.
    """
    root = Path(out) if out is not None else yori.OUT
    groups = read(root)
    library = unreal.EditorAssetLibrary
    previous = owned_packages(library.list_assets(DESTINATION, recursive=False, include_folder=False))
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert editor is not None
    report = {}
    for parent, group in groups.items():
        materials = {slot: library.load_asset(path) for slot, path in material_paths(parent, group['slots']).items()}
        assert materials and all(materials.values()), (parent, 'missing current island materials')
        current = []
        for index, row in enumerate(group['pieces'], 1):
            def before_import(key=row['name']):
                path = DESTINATION + '/' + key
                if library.does_asset_exist(path):
                    _empty_collision(library.load_asset(path), editor)
            mesh = import_mesh(row['path'], DESTINATION, row['name'], fresh_slots=True, before_import=before_import)
            assert mesh.get_path_name().split('.')[0] == row['asset'], (row['name'], 'native package identity')
            assert mesh.get_num_triangles(0) == row['triangles'] and mesh.get_num_lods() == 1, (row['name'], 'current render geometry')
            actual_slots = []
            for slot, value in enumerate(mesh.static_materials):
                key = str(value.get_editor_property('imported_material_slot_name'))
                assert key in materials and key not in actual_slots, (row['name'], 'slot identity', key)
                actual_slots.append(key)
                if mesh.get_material(slot) != materials[key]: mesh.set_material(slot, materials[key])
            assert set(row['used_slots']) <= set(actual_slots), (row['name'], 'missing consumed material binding')
            settings = editor.get_lod_build_settings(mesh, 0)
            if settings.get_editor_property('use_full_precision_u_vs'):
                settings.set_editor_property('use_full_precision_u_vs', False)
                editor.set_lod_build_settings(mesh, 0, settings)
            body = mesh.get_editor_property('body_setup')
            assert body is not None
            collision = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
            if body.get_editor_property('collision_trace_flag') != collision:
                body.set_editor_property('collision_trace_flag', collision)
            _empty_collision(mesh, editor)
            bounds = mesh.get_bounding_box(); lower, upper = native_bounds(row)
            for axis, low, high in zip(('x', 'y', 'z'), lower, upper):
                assert abs(getattr(bounds.min, axis)-low) < .2 and abs(getattr(bounds.max, axis)-high) < .2, (row['name'], axis, 'bounds')
            assert editor.get_num_uv_channels(mesh, 0) == len(row['uv_channels']) == 1, (row['name'], 'UV channels')
            assert not editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
            assert unreal.CitySurfaceValidation.validate_collision(mesh, row['triangles'], False), (row['name'], 'current cooked LOD0 surface')
            assert library.save_loaded_asset(mesh, True), (row['name'], 'native save failed')
            current.append(dict(name=row['name'], asset=row['asset'], triangles=row['triangles'],
                                materials=[mesh.get_material(i).get_path_name() for i in range(len(mesh.static_materials))]))
            mesh = body = None
            if index % 16 == 0: unreal.SystemLibrary.collect_garbage()
            unreal.log(f'ISLAND RECEIVE {parent} {index}/{len(group["pieces"])}')
        assert sum(row['triangles'] for row in current) == group['source_triangles']
        report[parent] = current
    return dict(out=root, previous=previous, groups=report)


def retire_after_map(received, *, runtime_members, saved_map='/Game/Japan/Maps/Slice'):
    """@cc [owner:fontanierh,label:correctness] island-parent-retirement-after-consumer-migration
    The caller MUST have saved the replacement Slice with separate current components and
    migrated all runtime members before this explicit retirement. Require the exact runtime
    roster, all current native packages and the saved map. The one complete external-reference
    preflight MUST cover both old combined Terrain/Sea and superseded owned children before
    any deletion; physical primary/sidecar absence MUST precede successful report publication.
    """
    library = unreal.EditorAssetLibrary
    groups = received['groups']
    current = {parent: [row['asset'] for row in rows] for parent, rows in groups.items()}
    if runtime_members != current or saved_map != '/Game/Japan/Maps/Slice' or not library.does_asset_exist(saved_map):
        raise ValueError('Island consumers have not migrated to the complete saved current roster')
    all_current = [path for paths in current.values() for path in paths]
    if any(not library.does_asset_exist(path) for path in all_current):
        raise ValueError('Island receiving packages are incomplete')
    previous = owned_packages(received['previous'])
    obsolete = previous - set(all_current)
    replacements = {'/Game/Japan/Terrain': [path for parent, paths in current.items() if parent != 'Sea' for path in paths],
                    '/Game/Japan/Assets/Sea': current['Sea'], **{path: all_current for path in obsolete}}
    retired = native_membership.retire_replaced(library, replacements)
    content = yori.GAME / 'unreal/Content'
    for package in replacements:
        path = content / package.removeprefix('/Game/')
        real_directory(path.parent)
        if any(path.parent.glob(path.name + '.*')):
            raise ValueError('Island superseded package remains physically present: ' + package)
    folder = real_directory(Path(received['out']) / 'terrain')
    (folder / 'island-import-report.json').write_text(json.dumps(dict(complete=True, parents=groups, retired=retired), indent=2) + '\n')
    unreal.log('ISLAND ATOMIC IMPORT COMPLETE')
    return retired
