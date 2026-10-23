"""Current untouched-package admission and exact ownership for ferry ship meshes."""
import json
from pathlib import Path

import unreal

from atelier import native_membership
from atelier.export_manifest import real_directory
from forest_native import hulls_match

DESTINATION = '/Game/Ferry/Ship'


def configure(root, manifest):
    root = Path(root)
    atomic = json.loads((root / 'atomic-manifest.json').read_text())
    current = {row['asset']: row for row in atomic['exports']}
    names = {*manifest['meshes'], 'FY_Collision'}
    if set(current) != names:
        raise ValueError('Native ferry ship roster differs from its complete file assembly')
    proxies = json.loads((root / 'ship-collision-data.json').read_text())
    if (proxies.get('schema') != 1 or proxies.get('asset') != 'FY_Collision'
            or len(proxies['proxies']) != manifest['collision']['convex_hulls']):
        raise ValueError('Native ferry authored proxy closure is incomplete')
    hulls = []
    for proxy in proxies['proxies']:
        # Match the original from_pydata float32 representation before FBX's cm conversion.
        import struct
        def f32(value): return struct.unpack('<f', struct.pack('<f', value))[0]
        vertices = [[f32(x), f32(y), f32(z)] for heights in ('z0', 'z1')
                    for (x, y), z in zip(proxy['poly'], proxy[heights])]
        hulls.append(dict(vertices=vertices, matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]))
    return dict(entries=current, hulls=hulls, previous=inventory(), parents=list(atomic['parents']))


def inventory():
    library = unreal.EditorAssetLibrary
    return native_membership.inventory(library, DESTINATION, 'FY_')


def reusable(mesh, name, state, materials):
    """Read current geometry, whole UCX and material bindings without dirtying candidates."""
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    row = state['entries'][name]
    if (mesh.get_path_name().split('.')[0] != DESTINATION + '/' + name
            or mesh.get_num_lods() != 1 or mesh.get_num_triangles(0) != row['triangles']
            or editor.get_simple_collision_count(mesh) != 0):
        return False
    expected_hulls = state['hulls'] if name == 'FY_Collision' else []
    if editor.get_convex_collision_count(mesh) != len(expected_hulls) or not hulls_match(mesh, expected_hulls):
        return False
    if name == 'FY_Collision':
        body = mesh.get_editor_property('body_setup')
        if body is None or body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX:
            return False
    slots = row['metadata']['slots']
    if len(mesh.static_materials) != len(slots):
        return False
    for index, (slot, expected) in enumerate(zip(mesh.static_materials, slots)):
        actual = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        if actual != expected or expected not in materials or mesh.get_material(index) != materials[expected]:
            return False
    return True


def prepare_source(name):
    """A real import miss alone may reset an old source's collision before raw receiving."""
    library = unreal.EditorAssetLibrary
    if library.does_asset_exist(DESTINATION + '/' + name):
        mesh = library.load_asset(DESTINATION + '/' + name)
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
            if not editor.remove_collisions(mesh):
                raise ValueError('Ferry old authored hull reset failed')


def retire(state):
    names = [*state['entries'], 'FY_Wake']
    obsolete = state['previous'] - {DESTINATION + '/' + key for key in names}
    # The ship owns only its explicit canonical source names and their generated children.
    parents = set(state['entries']) | set(state.get('parents', ()))
    for package in obsolete:
        key = package.rsplit('/', 1)[-1]
        if key not in parents and not any(key.startswith(parent + '_cell_') for parent in parents):
            raise ValueError('Foreign native ferry source prevents retirement: ' + key)
    removed = native_membership.retire(unreal.EditorAssetLibrary, state['previous'], names, DESTINATION, 'FY_')
    content = Path(unreal.Paths.project_content_dir()) / 'Ferry/Ship'
    real_directory(content)
    for package in obsolete:
        key = package.rsplit('/', 1)[-1]
        if list(content.glob(key + '.*')):
            raise ValueError('Retired ferry package remains on disk: ' + key)
    return removed
