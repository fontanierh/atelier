"""Receive independent Stable semantics/LODs with unchanged AABB and door policy."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori  # noqa: E402
sys.path.insert(0, str(yori.GAME)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import json
import unreal

from atelier import native_membership
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from atelier.interchange_mesh import import_static_mesh
from atelier.native_protocol import native_context
from atelier.unreal_mesh_reuse import MeshReuse
from hidamari_stable.catalogue import PARENTS, PARTS, LOD_PARENTS
from hidamari_stable import layout
import glb_mesh_validation
from stable_atomic_products import DESTINATION, read

MATERIAL = '/Game/Japan/Materials/M_Arcade'
CITY = '/Game/Japan/Hidamari/Materials'


def cm_bounds(bounds):
    low, high = bounds
    return [low[0]*100, -high[1]*100, low[2]*100], [high[0]*100, -low[1]*100, high[2]*100]


def raw_import(source, folder, key):
    return import_static_mesh(source, folder, key)


def validate_raw(mesh, source, row, out):
    """Saved byte/source/options proof plus exact raw geometry before current finishing."""
    return (glb_mesh_validation.validate_mesh(mesh, source, dict(triangles=row['triangles'], bounds_m=row['bounds']),
                len(row['slots']), out=out, tolerance_cm=.2)
            and mesh.get_num_triangles(0) == row['triangles']
            and mesh.get_num_lods() in ((1, 3) if row['name'].endswith('_LOD0') else (1,))
            and [str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
                 for slot in mesh.get_editor_property('static_materials')] == row['slots'])


def donor_row(report, key):
    for group in report.get('parents', {}).values():
        for row in group.get('levels', []):
            if row.get('name') == key: return row
    return None


def boxes_match(mesh, boxes):
    body = mesh.get_editor_property('body_setup')
    if body is None: return False
    aggregate = body.get_editor_property('agg_geom')
    if any(len(aggregate.get_editor_property(key)) for key in ('sphere_elems', 'sphyl_elems', 'convex_elems', 'tapered_capsule_elems')):
        return False
    shapes = list(aggregate.get_editor_property('box_elems'))
    if len(shapes) != len(boxes): return False
    for shape, values in zip(shapes, boxes):
        low, high = cm_bounds([values[:3], values[3:]])
        center, rotation = shape.get_editor_property('center'), shape.get_editor_property('rotation')
        if any(abs(v) > .001 for v in (rotation.pitch, rotation.yaw, rotation.roll)): return False
        if any(abs(getattr(center, axis)-(a+b)/2) > .001 for axis, a, b in zip(('x', 'y', 'z'), low, high)): return False
        if any(abs(shape.get_editor_property(axis)-(b-a)) > .001 for axis, a, b in zip(('x', 'y', 'z'), low, high)): return False
    return True


def box(values):
    low, high = cm_bounds([values[:3], values[3:]])
    result = unreal.Box(); result.min = unreal.Vector(*low); result.max = unreal.Vector(*high); result.is_valid = True
    return result


def finish(mesh, group, editor):
    library = unreal.EditorAssetLibrary
    slots = group['levels'][0]['slots']
    for index, slot in enumerate(slots):
        path = CITY + '/MI_HD_' + slot.removeprefix('HDS_') if slot.startswith('HDS_') else MATERIAL
        material = library.load_asset(path); assert material is not None, path
        if mesh.get_material(index) != material: mesh.set_material(index, material)
        assert mesh.get_material(index) == material
    simple = group['collision'] == 'simple_as_complex'
    body = mesh.get_editor_property('body_setup'); assert body is not None
    trace = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX if simple else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    if simple:
        if not boxes_match(mesh, group['boxes']):
            assert unreal.BelmonteTrainImportLibrary.set_simple_boxes(mesh, [box(values) for values in group['boxes']]) == len(group['boxes'])
        assert boxes_match(mesh, group['boxes']), 'Complete original Stable AABB collision differs'
    elif editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
        assert editor.remove_collisions(mesh)
    if body.get_editor_property('collision_trace_flag') != trace: body.set_editor_property('collision_trace_flag', trace)
    if mesh.get_editor_property('lod_for_collision') != 0: mesh.set_editor_property('lod_for_collision', 0)
    assert mesh.get_editor_property('complex_collision_mesh') is None
    for level, row in enumerate(group['levels']):
        assert mesh.get_num_triangles(level) == row['triangles'], (row['name'], 'current LOD geometry')
        settings = editor.get_lod_build_settings(mesh, level)
        if group['uv_precision'] == 'full' and not settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs', True); editor.set_lod_build_settings(mesh, level, settings)
        assert editor.get_num_uv_channels(mesh, level) == len(row['uv_channels']) == 1
        if group['uv_precision'] == 'full':
            assert editor.get_lod_build_settings(mesh, level).get_editor_property('use_full_precision_u_vs')
    bounds = mesh.get_bounding_box(); low, high = cm_bounds(group['levels'][0]['bounds'])
    for axis, a, b in zip(('x', 'y', 'z'), low, high):
        assert abs(getattr(bounds.min, axis)-a) < .2 and abs(getattr(bounds.max, axis)-b) < .2
    if simple:
        assert unreal.CitySurfaceValidation.validate_simple_boxes(mesh, len(group['boxes']))
    else:
        assert unreal.CitySurfaceValidation.validate_collision(mesh, group['levels'][0]['triangles'], False)
    assert library.save_loaded_asset(mesh, True), 'Stable saved receiving package failed'


def receive(out=None):
    """Admit each raw LOD independently, then apply unchanged current LOD/collision finishing."""
    root = Path(out) if out is not None else yori.OUT
    groups = read(root); library = unreal.EditorAssetLibrary
    previous = set(library.list_assets(DESTINATION, recursive=True, include_folder=False))
    allowed = {DESTINATION + '/' + parent for parent in PARENTS}
    allowed.update(DESTINATION + '/Source/' + parent + '_LOD' + str(lod)
                   for parent in LOD_PARENTS for lod in (1, 2))
    normalized = set()
    for path in previous:
        package = path.split('.')[0]
        if package not in allowed or path not in (package, package + '.' + package.rsplit('/', 1)[1]):
            raise ValueError('Foreign Stable native member')
        if package in normalized: raise ValueError('Duplicate Stable native member')
        normalized.add(package)
    unreal.SystemLibrary.execute_console_command(None, 'Editor.AsyncStaticMeshCompilation 0')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem); assert editor is not None
    reuse = MeshReuse(native_context(yori.GAME.name), 'unreal.hidamari_stable', __file__, ('raw_import',),
        report_member='generated/hidamari-stable/atomic-manifest.json', validation_functions=('validate_raw',))
    received = {}
    for parent in PARENTS:
        group = groups[parent]; levels = []
        for index, row in enumerate(group['levels']):
            key = row['name']; folder = DESTINATION if index == 0 else DESTINATION + '/Source'
            name = parent if index == 0 else key; target = folder + '/' + name
            source = root / 'atomic_regions/hidamari_stable/assets' / (key + '.glb')
            mesh = reuse.acquire(key, target, geometry=row, donor_geometry=lambda old, key=key: donor_row(old, key),
                sources=[(target, source, row['sha256'])],
                validator=lambda mesh, source=source, row=row: validate_raw(mesh, source, row, root))
            if mesh is None: mesh = raw_import(source, folder, name); reuse.imported(key)
            assert validate_raw(mesh, source, row, root), (key, 'current raw admission')
            levels.append(mesh)
        mesh = levels[0]
        for level, source in enumerate(levels[1:], 1):
            assert editor.set_lod_from_static_mesh(mesh, level, source, 0, True) == level
        if len(levels) > 1:
            assert editor.set_lod_screen_sizes(mesh, group['lod_screen_sizes'])
            assert all(abs(a-b) < 1e-6 for a, b in zip(editor.get_lod_screen_sizes(mesh), group['lod_screen_sizes']))
        assert mesh.get_num_lods() == len(levels)
        finish(mesh, group, editor)
        for row, source in zip(group['levels'], levels):
            assert library.save_loaded_asset(source, True)
            reuse.validated(row['name'])
        received[parent] = DESTINATION + '/' + parent
        unreal.log('STABLE ATOMIC RECEIVE ' + parent)
    reuse.finish()
    return dict(out=root, received=received, previous=normalized, allowed=allowed)


def main():
    assert layout.is_enabled(), 'Hidamari Stable remains disabled in committed production policy'
    root = yori.OUT
    runtime = json.loads((root / 'hidamari-stable/placements.json').read_text())
    assert runtime['atomic'] is True and runtime['asset_root'] == DESTINATION
    assert set(runtime['expected_assets']) == set(PARENTS)
    result = receive(root); library = unreal.EditorAssetLibrary
    current = list(result['received'].values())
    levels = []
    for level in (0, 1, 2):
        paths = [DESTINATION + ('/SM_HS_' + part if level == 0 else '/Source/SM_HS_' + part + '_LOD' + str(level))
                 for part in PARTS]
        meshes = [library.load_asset(path) for path in paths]
        assert all(mesh is not None for mesh in meshes), 'Complete coordinated Stable native bounds sources required'
        levels.append(meshes)
    measured = unreal.HidamariStableMeshComponent.measure_logical_bounds(*levels)
    assert measured, 'Exact original coordinated Stable native bound is unavailable'
    runtime['logical_stable_bounds_cm'] = json.loads(measured)
    data = yori.GAME / 'unreal/Content/Data/hidamari_stable/stable.json'
    real_directory(data.parent, create=True)
    if data.is_symlink() or (data.exists() and not data.is_file()): raise ValueError('Linked or nonregular Stable runtime data')
    # Current data consumers migrate only after all current packages were saved,
    # and before the combined old-package retirement preflight can delete anything.
    atomic_json(data, runtime)
    # Retire only explicit historical generated packages after every new consumer exists.
    replacements = {'/Game/HidamariStable/' + name: current for name in
        ('SM_HS_Stable', 'SM_HS_StallDoor', 'SM_HS_RoomDoor', 'SM_HS_Ground', 'SM_HS_Road', 'SM_HS_RoadSign')}
    for name in ('Stable', 'StallDoor', 'RoomDoor'):
        for level in (0, 1, 2):
            key = 'SM_HS_' + name
            replacements['/Game/HidamariStable/Source/' + key + '/' + key + '_LOD' + str(level)] = current
    replacements.update({path: current for path in result['previous'] - result['allowed']})
    retired = native_membership.retire_replaced(library, replacements)
    for package in replacements:
        path = yori.GAME / 'unreal/Content' / package.removeprefix('/Game/')
        assert not list(path.parent.glob(path.name + '.*')), ('Old Stable physical package remains', package)
    atomic_json(root / 'hidamari-stable/import-report.json', dict(complete=True, assets=result['received'], retired=retired))
    unreal.log('HIDAMARI STABLE IMPORT COMPLETE')


if __name__ == '__main__': main()
