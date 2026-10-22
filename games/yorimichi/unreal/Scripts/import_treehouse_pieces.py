"""Current bounded dressing imports, with one complete parent/obsolete retirement preflight."""
import hashlib
import json
import sys
from pathlib import Path

import unreal
from atelier import native_membership
from atelier.mesh_geometry import package_inventory
from mesh_import import import_mesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from treehouse_pieces import DESTINATION, PARENT, NAME, UVS, members, parent_absent, source_files, expected_assets  # noqa: E402


def save_piece(mesh, editor, content):
    """Save dirty current children and require their regular on-disk primary/sidecars."""
    name = mesh.get_name()
    package = DESTINATION + '/' + name
    assert NAME.fullmatch(name) and mesh.get_path_name() == package + '.' + name
    primary = content / (package.removeprefix('/Game/') + '.uasset')
    assert all(not part.is_symlink() for part in (primary, *primary.parents)), 'Linked dressing package'
    assert editor.save_loaded_asset(mesh, only_if_is_dirty=True), 'Dressing package save failed'
    package_inventory(content, [package])


def import_dressing(out, materials, report):
    """Suppress only Message Log UI; preserve diagnostics and every current validation."""
    unreal.load_module('MessageLog')
    system = unreal.SystemLibrary
    key = 'MessageLog.DisablePopup'
    prior = system.get_console_variable_bool_value(key)
    system.execute_console_command(None, key + ' 1')
    assert system.get_console_variable_bool_value(key) is True, 'Message Log UI guard unavailable'
    try:
        _import_dressing(out, materials, report)
    finally:
        system.execute_console_command(None, key + (' 1' if prior else ' 0'))
        assert system.get_console_variable_bool_value(key) == prior, 'Message Log UI guard restore failed'


def _import_dressing(out, materials, report):
    """Validate/save every child before retiring the monolithic parent or obsolete children."""
    root = Path(out)
    manifest = json.loads((root / 'pieces.json').read_text())
    rows = members(manifest)
    files = source_files(root.parent)
    editor = unreal.EditorAssetLibrary
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    assert meshes is not None
    old = set()
    for path in editor.list_assets(DESTINATION, recursive=False, include_folder=False):
        name = path.removeprefix(DESTINATION + '/').split('.')[0]
        if not NAME.fullmatch(name):
            raise RuntimeError('Unexpected package in exclusive dressing owner: ' + path)
        if path != DESTINATION + '/' + name + '.' + name:
            raise RuntimeError('Invalid dressing package path')
        old.add(DESTINATION + '/' + name)
    def collision_free(mesh):
        return meshes.get_simple_collision_count(mesh) == meshes.get_convex_collision_count(mesh) == 0
    current = []
    for row, path in zip(rows, files):
        name = row['name']
        def prepare():
            if editor.does_asset_exist(DESTINATION + '/' + name):
                prior = editor.load_asset(DESTINATION + '/' + name)
                prior.set_num_source_models(1)
                meshes.remove_collisions(prior)
        # Keep the same declared receipt policy as this owner's existing imports.
        # Current geometry, UV, material and collision finishing is checked below.
        mesh = import_mesh(path, DESTINATION, name, fresh_slots=True, before_import=prepare)
        assert mesh.get_num_lods() == 1 and mesh.get_num_triangles(0) == row['triangles'], name
        assert meshes.get_num_uv_channels(mesh, 0) == len(UVS), (name, 'shared fade bake')
        slots = list(mesh.get_editor_property('static_materials'))
        actual = [str(slot.get_editor_property('imported_material_slot_name')) for slot in slots]
        assert (len(set(actual)) == len(actual) and set(row['used_slots']) <= set(actual) <= set(manifest['slots'])), (name, 'source material membership', actual)
        for i, slot in enumerate(actual):
            material = materials.get(slot.removeprefix('TH_'))
            assert material is not None, (name, slot)
            if mesh.get_material(i) != material:
                mesh.set_material(i, material)
            assert mesh.get_material(i) == material, (name, slot, 'material assignment readback')
        assert collision_free(mesh), name
        body = mesh.get_editor_property('body_setup')
        flag = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
        if body.get_editor_property('collision_trace_flag') != flag:
            body.set_editor_property('collision_trace_flag', flag)
        settings = meshes.get_lod_build_settings(mesh, 0)
        if not settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs', True)
            meshes.set_lod_build_settings(mesh, 0, settings)
        assert meshes.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'), name
        assert body.get_editor_property('collision_trace_flag') == flag, name
        assert mesh.get_editor_property('lod_for_collision') == 0, name
        assert mesh.get_editor_property('complex_collision_mesh') is None, name
        box = mesh.get_bounding_box()
        low, high = row['min'], row['max']
        native = ((low[0]*100, -high[1]*100, low[2]*100), (high[0]*100, -low[1]*100, high[2]*100))
        assert all(abs(getattr(point, axis)-want[i]) < .2
                   for point, want in zip((box.min, box.max), native) for i, axis in enumerate(('x','y','z'))), name
        save_piece(mesh, editor, Path(__file__).resolve().parents[1] / 'Content')
        current.append(DESTINATION + '/' + name)
        mesh = body = None
    # These exact bytes are also the complete declared transfer scope. Refuse
    # missing native materials/props/trees before retiring the render parent.
    report['assets'] = expected_assets(root.parent)
    report['files'] = package_inventory(Path(__file__).resolve().parents[1] / 'Content', report['assets'])
    replacements = {'/Game/Japan/Assets/' + PARENT: current}
    replacements.update({package: current for package in old - set(current)})
    native_membership.retire_replaced(editor, replacements)
    content = Path(__file__).resolve().parents[1] / 'Content'
    assert parent_absent(content), 'Superseded dressing parent remains on disk'
    for package in old - set(current):
        folder = content / package.removeprefix('/Game/')
        assert not any(folder.parent.glob(folder.name + '.*')), ('Obsolete dressing package remains', package)
    report['dressing'] = current
    report['pieces_sha256'] = hashlib.sha256((root / 'pieces.json').read_bytes()).hexdigest()
