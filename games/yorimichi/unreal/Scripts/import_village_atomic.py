"""Receive separate bounded Village mesh assets with exact original hull/collision policy."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402,F401
import json
from pathlib import Path
import sys

import unreal

sys.path.insert(0, str(yori.GAME)); sys.path.insert(0, str(Path(__file__).resolve().parent))
from atelier import native_membership  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from mesh_import import import_mesh  # noqa: E402
from village_atomic_products import ASSETS, DESTINATION, MATERIAL, collision_matches, native_bounds, owned, read  # noqa: E402


def inventory(paths):
    result = set()
    for path in paths:
        if not isinstance(path, str) or not path.startswith(DESTINATION + '/'):
            raise ValueError('Village native inventory escaped its exact owner')
        relative = path[len(DESTINATION)+1:]; key = relative.split('.')[0]
        if (relative not in (key, key + '.' + key) or not any(owned(key, parent) for parent in ASSETS)
                or DESTINATION + '/' + key in result):
            raise ValueError('Foreign or duplicate Village native asset')
        result.add(DESTINATION + '/' + key)
    return result


def clear_shapes(mesh, editor):
    if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
        assert editor.remove_collisions(mesh), (mesh.get_path_name(), 'stale hull reset')
    assert editor.get_simple_collision_count(mesh) == editor.get_convex_collision_count(mesh) == 0


def receive(out=None):
    """@cc [owner:fontanierh,label:correctness;performance] receive-current-independent-village
    Admit untouched saved child packages independently. Only a real raw-import miss MAY
    reset previous hulls before authored UCX import. Every hit/miss MUST receive current
    original material, exact full hull geometry, parent collision policy, original half-precision UV,
    render count/bounds/LOD0 cook validation and a checked dirty-only save. Render-only leaves
    of simple-collision parents MUST NOT acquire complex-as-simple blocking behavior.
    No old parent may be loaded as a fallback or retired before the full current set succeeds.
    """
    root = Path(out) if out is not None else yori.OUT
    groups = read(root)
    library = unreal.EditorAssetLibrary
    previous = inventory(library.list_assets(DESTINATION, recursive=True, include_folder=False))
    material = library.load_asset(MATERIAL); assert material is not None, 'Current Village material must be prepared'
    unreal.SystemLibrary.execute_console_command(None, 'Interchange.FeatureFlags.Import.FBX 0')
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem); assert editor is not None
    report = {}
    for parent, group in groups.items():
        source_simple_policy = group['collision'] == 'simple_and_complex'
        expected_trace = (unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX if source_simple_policy
                          else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        current = []
        for index, row in enumerate(group['pieces'], 1):
            key = row['name']
            def before_import(key=key):
                path = DESTINATION + '/' + key
                if library.does_asset_exist(path): clear_shapes(library.load_asset(path), editor)
            mesh = import_mesh(root / 'atomic_regions/village/assets' / (key + '.fbx'), DESTINATION, key,
                fresh_slots=True, before_import=before_import,
                reuse_validator=lambda mesh: collision_matches(mesh, group, row))
            assert mesh.get_path_name().split('.')[0] == DESTINATION + '/' + key
            assert mesh.get_num_triangles(0) == row['triangles'] and mesh.get_num_lods() == 1, (key, 'render geometry')
            assert len(mesh.static_materials) == 1, (key, 'original draw material')
            assert str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) == 'VillagePalette'
            if mesh.get_material(0) != material: mesh.set_material(0, material)
            body = mesh.get_editor_property('body_setup'); assert body is not None
            if body.get_editor_property('collision_trace_flag') != expected_trace:
                body.set_editor_property('collision_trace_flag', expected_trace)
            if row['collision_hulls'] == 0: clear_shapes(mesh, editor)
            assert collision_matches(mesh, group, row), (key, 'complete authored hull geometry')
            settings = editor.get_lod_build_settings(mesh, 0)
            if settings.get_editor_property('use_full_precision_u_vs'):
                settings.set_editor_property('use_full_precision_u_vs', False); editor.set_lod_build_settings(mesh, 0, settings)
            low, high = native_bounds(row); bounds = mesh.get_bounding_box()
            for axis, a, b in zip(('x', 'y', 'z'), low, high):
                assert abs(getattr(bounds.min, axis)-a) < .2 and abs(getattr(bounds.max, axis)-b) < .2, (key, axis, 'bounds')
            assert editor.get_num_uv_channels(mesh, 0) == len(row['uv_channels']) == 1, (key, 'UV count')
            assert not editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
            # This validator's bool selects the expected SimpleAndComplex trace policy;
            # actual hull presence/vertices are independently required above, even at zero.
            assert unreal.CitySurfaceValidation.validate_collision(mesh, row['triangles'], source_simple_policy), (key, 'current cooked surface')
            assert library.save_loaded_asset(mesh, True), (key, 'native save failed')
            current.append(dict(name=key, asset=DESTINATION + '/' + key, triangles=row['triangles']))
            mesh = body = None
            if index % 16 == 0: unreal.SystemLibrary.collect_garbage()
            unreal.log(f'VILLAGE RECEIVE {parent} {index}/{len(group["pieces"])}')
        assert sum(row['triangles'] for row in current) == group['source_triangles']
        report[parent] = current
    return dict(out=root, previous=previous, groups=report)


def retire(received, *, runtime_members):
    """Retire exact old logical parents only after all current saved consumers migrate."""
    library = unreal.EditorAssetLibrary
    current = {parent: [row['asset'] for row in rows] for parent, rows in received['groups'].items()}
    if set(current) != set(ASSETS) or runtime_members != current:
        raise ValueError('Village runtime membership is incomplete or has not migrated')
    all_current = [path for paths in current.values() for path in paths]
    previous = inventory(received['previous'])
    replacements = {'/Game/Japan/Assets/' + parent: paths for parent, paths in current.items()}
    replacements.update({path: all_current for path in previous - set(all_current)})
    retired = native_membership.retire_replaced(library, replacements)
    for package in replacements:
        path = yori.GAME / 'unreal/Content' / package.removeprefix('/Game/')
        real_directory(path.parent)
        assert not list(path.parent.glob(path.name + '.*')), ('Village parent remains on disk', package)
    (Path(received['out']) / 'village/import-report.json').write_text(json.dumps(dict(complete=True,
        parents=received['groups'], retired=retired), indent=2) + '\n')
    unreal.log('VILLAGE ATOMIC IMPORT COMPLETE')
    return retired
