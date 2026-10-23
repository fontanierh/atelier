"""Current untouched-package admission and exact ownership for ferry ship meshes."""
import json
import ast
from pathlib import Path

import unreal

from atelier import native_membership
from atelier.export_manifest import real_directory
from forest_native import hulls_match

DESTINATION = '/Game/Ferry/Ship'


def configure(root, manifest):
    from regions.ferry.ship_sources import BUILDERS
    root = Path(root)
    atomic = json.loads((root / 'atomic-manifest.json').read_text())
    if set(atomic['parents']) != set(BUILDERS): raise ValueError('Incomplete native ferry ship logical roster')
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
    return dict(entries=current, hulls=hulls, previous=inventory(), parents=list(atomic['parents']), destination=DESTINATION)


def configure_terminals(root, manifest):
    root = Path(root); destination = '/Game/Ferry/Terminals'
    atomic = json.loads((root / 'atomic-manifest.json').read_text())
    recipe_path = Path(__file__).resolve().parents[2] / 'ferry_terminal_atomic_build.py'
    declaration = next(node for node in ast.parse(recipe_path.read_text()).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'MODELS' for target in node.targets))
    models = ast.literal_eval(declaration.value)
    if set(atomic['parents']) != set(models): raise ValueError('Incomplete native terminal logical roster')
    entries = {row['asset']: row for row in atomic['exports']}
    names = {name for owner in manifest['terminals'].values() for name in owner['meshes']}
    names.update(('FT_HD_Collision', 'FT_BC_Collision'))
    if set(entries) != names: raise ValueError('Native terminal membership differs from complete file assembly')
    hulls = {}
    for name, row in entries.items():
        if name.endswith('_Collision'):
            hulls[name] = row['metadata']['authored_hulls']
        else:
            parent = next((parent for parent, children in atomic['parents'].items() if name in children), None)
            if parent is None: raise ValueError('Foreign native terminal child')
            hulls[name] = next(owner['meshes'][name]['authored_hulls'] for owner in manifest['terminals'].values() if name in owner['meshes'])
        if len(hulls[name]) != row['metadata']['collision_hulls']:
            raise ValueError('Native terminal authored hull closure differs')
    return dict(entries=entries, hulls=hulls, previous=native_membership.inventory(unreal.EditorAssetLibrary, destination, 'FT_'),
                parents=list(atomic['parents']), destination=destination)


def inventory():
    library = unreal.EditorAssetLibrary
    return native_membership.inventory(library, DESTINATION, 'FY_')


def reusable(mesh, name, state, materials):
    """Read current geometry, whole UCX and material bindings without dirtying candidates."""
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    row = state['entries'][name]
    destination = state.get('destination', DESTINATION)
    if (mesh.get_path_name().split('.')[0] != destination + '/' + name
            or mesh.get_num_lods() != 1 or mesh.get_num_triangles(0) != row['triangles']
            or editor.get_simple_collision_count(mesh) != 0):
        return False
    expected_hulls = (state['hulls'].get(name, []) if isinstance(state['hulls'], dict)
                      else state['hulls'] if name == 'FY_Collision' else [])
    if editor.get_convex_collision_count(mesh) != len(expected_hulls) or not hulls_match(mesh, expected_hulls):
        return False
    if name.endswith(('_Collision', '_Brow')):
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


def prepare_source(name, destination=DESTINATION):
    """A real import miss alone may reset an old source's collision before raw receiving."""
    library = unreal.EditorAssetLibrary
    if library.does_asset_exist(destination + '/' + name):
        mesh = library.load_asset(destination + '/' + name)
        editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
            if not editor.remove_collisions(mesh):
                raise ValueError('Ferry old authored hull reset failed')


def retire(state):
    return retire_all((state,))


def retire_all(states):
    """One complete foreign-reference preflight follows every current ship/terminal save."""
    library = unreal.EditorAssetLibrary
    current, obsolete = set(), set()
    for state in states:
        destination = state.get('destination', DESTINATION)
        names = set(state['entries']) | ({'FY_Wake'} if destination == DESTINATION else set())
        packages = {destination + '/' + name for name in names}
        current.update(packages)
        prior = state['previous'] - packages
        parents = set(state['entries']) | set(state.get('parents', ()))
        for package in prior:
            key = package.rsplit('/', 1)[-1]
            if key not in parents and not any(key.startswith(parent + '_cell_') for parent in parents):
                raise ValueError('Foreign native ferry source prevents retirement: ' + key)
        obsolete.update(prior)
    if any(not library.does_asset_exist(package) for package in current):
        raise ValueError('Current ferry native membership is incomplete before retirement')
    removed = native_membership.retire_replaced(library, {package: sorted(current) for package in obsolete}) if obsolete else []
    content = real_directory(Path(unreal.Paths.project_content_dir()))
    for package in obsolete:
        path = content / package.removeprefix('/Game/')
        real_directory(path.parent)
        if list(path.parent.glob(path.name + '.*')):
            raise ValueError('Retired ferry package remains on disk: ' + package)
    return removed
