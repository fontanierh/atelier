"""Native bodies for Scripts/import_bike.py (unreal.bike), one declared package per job.

``args.action`` selects
- ``part``: /Game/Japan/Assets/<part> as a fresh duplicate of its raw import on M_Bike, with import_bike.receive's
  checks against the part's own construction report (vehicle_bike.report.<part>: triangles, min, max) and export
  receipt (slots, collision hulls, UV channels, triangles; bike_atomic_products.read's ownership checks);
- ``steering``: the four jointly mutated steering packages in one job, each finished as a part, with the complete
  group's true bounds persisted on all four (BikeMeshComponent.PrepareSteeringBounds) before their saves;
- ``record``: bike/import-report.json, the original report, from the finished parts and their construction reports.
The original top level, family inventory and BK_Steer retirement never run.
"""
import json
from pathlib import Path
import re

DEST = '/Game/Japan/Assets/'
RAW = '/Game/_Raw/Bike/'
MATERIAL = '/Game/Japan/Materials/M_Bike'
PART = re.compile(r'BK_[A-Za-z0-9_]+\Z')
STEERING = ('BK_Steer_BasketFoot', 'BK_Steer_BasketRim', 'BK_Steer_BasketShell', 'BK_Steer_Core')
WHEELS = ('BK_WheelFront', 'BK_WheelRear')
RECORD = 'data/import-report.json'
MAX_RECEIPT = 1024 * 1024


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _one(context, slot):
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if slot not in context.inputs or not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Bike input must be exactly one declared package: ' + str(slot))
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _one(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if not isinstance(asset, cls) or _path(asset) != package:
        raise ValueError('Declared Bike input did not load as expected: ' + package)
    return asset


def _json(context, slot, name):
    """One regular job-local data file: <slot>/<name>, or the slot itself when staged as that file."""
    root = context.inputs.get(slot)
    if root is None or context.packages.get(slot) not in ([], (), None):
        raise ValueError('Bike data must be a declared data input: ' + str(slot))
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Bike data must be job-local: ' + slot)
    path = root / name if root.is_dir() else root
    if path.name != name or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RECEIPT:
        raise ValueError(f'Bike data {name} is absent')
    return json.loads(path.read_bytes())


def _report(context, slot):
    """bike_atomic_products.read's construction report checks."""
    import math
    report = _json(context, slot, 'report.json')
    if (set(report) != {'triangles', 'vertices', 'min', 'max'} or type(report['triangles']) is not int
            or report['triangles'] <= 0 or type(report['vertices']) is not int or report['vertices'] <= 0
            or any(not isinstance(report[k], list) or len(report[k]) != 3 for k in ('min', 'max'))
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for k in ('min', 'max') for v in report[k])
            or any(low > high for low, high in zip(report['min'], report['max']))):
        raise ValueError('Bike construction report differs from the original attributes')
    return report


def _roster(value):
    if not isinstance(value, dict) or set(value) != {'derived_items'} or not isinstance(value['derived_items'], dict):
        raise ValueError('Bike derived roster must be a derived token')
    rows = value['derived_items'].get('members')
    if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
        raise ValueError('Bike derived roster is unresolved')
    found = {r['piece']: r['slot'] for r in rows}
    if len(found) != len(rows):
        raise ValueError('Bike derived roster repeats a part')
    return found


def _finish(context, unreal, key, *, raw_slot, export, report_slot, material):
    """One fresh /Game/Japan/Assets/<key> from its raw import with import_bike.receive's finishing and a validator."""
    report = _report(context, report_slot)
    receipt = _json(context, export, 'export.json')
    metadata = receipt.get('metadata') if isinstance(receipt.get('metadata'), dict) else {}
    if (receipt.get('asset') != key or receipt.get('primary') != key + '.fbx' or receipt.get('triangles') != report['triangles']
            or metadata.get('slots') != ['BikePalette'] or metadata.get('collision_hulls') != 0
            or metadata.get('uv_channels') != ['UVMap']):
        raise ValueError('Bike source attributes/ownership differ: ' + key)
    library = unreal.EditorAssetLibrary
    destination = DEST + key
    raw_path = _one(context, raw_slot)
    if raw_path != RAW + key or not isinstance(library.load_asset(raw_path), unreal.StaticMesh):
        raise ValueError('Bike raw input is not its raw StaticMesh: ' + key)
    if library.does_asset_exist(destination):
        raise ValueError('Bike finish destination must be fresh: ' + destination)
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    mesh = library.duplicate_asset(raw_path, destination)
    if not isinstance(mesh, unreal.StaticMesh) or _path(mesh) != destination:
        raise ValueError('Bike raw duplicate failed: ' + destination)
    wheel = key in WHEELS
    if mesh.get_material(0) != material:
        mesh.set_material(0, material)
    if wheel and not mesh.get_editor_property('allow_cpu_access'):
        mesh.set_editor_property('allow_cpu_access', True)

    def validate():
        if mesh.get_num_lods() != 1:
            raise ValueError(f'{key}: original single render LOD')
        slots = mesh.get_editor_property('static_materials')
        if len(slots) != 1 or str(slots[0].get_editor_property('imported_material_slot_name')) != 'BikePalette':
            raise ValueError(f'{key}: original BikePalette slot')
        if mesh.get_material(0) != material:
            raise ValueError(f'{key}: lost M_Bike')
        if bool(mesh.get_editor_property('allow_cpu_access')) != wheel:
            raise ValueError(f'{key}: original wheel CPU support')
        if editor.get_num_uv_channels(mesh, 0) != 1:
            raise ValueError(f'{key}: original single UV channel')
        if editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs'):
            raise ValueError(f'{key}: original UV precision')
        if not unreal.BikeMeshComponent.validate_part(mesh, report['triangles']):
            raise ValueError(f'{key}: current original cooked surface')
        bounds = mesh.get_bounding_box()
        low = (report['min'][0], -report['max'][1], report['min'][2])
        high = (report['max'][0], -report['min'][1], report['max'][2])
        for actual, expected in ((bounds.min, low), (bounds.max, high)):
            if not all(abs(getattr(actual, axis) - target * 100) < .3 for axis, target in zip('xyz', expected)):
                raise ValueError(f'{key}: original axis/scale')
    validate()
    return mesh, validate


def _material(unreal, context, slot):
    material = _load(unreal, context, slot, unreal.MaterialInterface)
    if _path(material) != MATERIAL:
        raise ValueError('Bike finish needs the declared M_Bike')
    return material


def part(context, unreal, args):
    """One ordinary (non-steering) part: unreal.finish(static_mesh) of exactly its package."""
    params = context.params
    key = args.get('part')
    if not PART.fullmatch(str(key)) or key in STEERING or args.get('piece') != key:
        raise ValueError('Bike export child is not its ordinary part: ' + str(args.get('piece')))
    destination = DEST + key
    if params.get('destination') != destination or list(context.outputs) != [destination]:
        raise ValueError('Bike finish must own exactly ' + destination)
    if set(context.inputs) != {'raw', args['export'], args['report'], args['material']}:
        raise ValueError('Bike finish inputs differ from its declaration')
    mesh, validate = _finish(context, unreal, key, raw_slot='raw', export=args['export'], report_slot=args['report'],
                             material=_material(unreal, context, args['material']))
    if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, False):
        raise ValueError('Bike native save failed: ' + destination)
    validate()
    return mesh


def steering(context, unreal, args):
    """The four jointly mutated steering packages: each finished as an ordinary part, then the complete group's true
    bounds persisted on all four (BikeMeshComponent.PrepareSteeringBounds), then each saved and re-read."""
    raws, exports, reports = _roster(args['raws']), _roster(args['exports']), args.get('reports')
    if (sorted(raws) != sorted(STEERING) or sorted(exports) != sorted(STEERING) or not isinstance(reports, dict)
            or sorted(reports) != sorted(STEERING)):
        raise ValueError('Bike steering owner needs the complete four-part group')
    if sorted(context.outputs) != sorted(DEST + key for key in STEERING):
        raise ValueError('Bike steering owner must own exactly the four steering packages')
    if set(context.inputs) != {*raws.values(), *exports.values(), *reports.values(), args['material']}:
        raise ValueError('Bike steering inputs differ from its declaration')
    material = _material(unreal, context, args['material'])
    finished = {key: _finish(context, unreal, key, raw_slot=raws[key], export=exports[key], report_slot=reports[key],
                             material=material) for key in STEERING}
    group = [finished[key][0] for key in STEERING]
    if not unreal.BikeMeshComponent.prepare_steering_bounds(group):
        raise ValueError('Incomplete actual steering bounds')
    for key, (mesh, validate) in finished.items():
        if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, False):
            raise ValueError('Bike native save failed: ' + DEST + key)
        validate()
    if not unreal.BikeMeshComponent.steering_bounds(group):
        raise ValueError('Bike steering parts carry no complete saved group bounds')
    return group


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The Bike record job owns only its JsonData output')
    finished = {**_roster(args['parts']), **(args.get('steering') or {})}
    reports = args.get('reports')
    if not isinstance(reports, dict) or sorted(reports) != sorted(finished):
        raise ValueError('Bike record reports differ from the finished parts')
    if set(context.inputs) != {*finished.values(), *reports.values()}:
        raise ValueError('Bike record inputs differ from its declaration')
    meshes, parts = {}, {}
    for key, slot in finished.items():
        mesh = _load(unreal, context, slot, unreal.StaticMesh)
        if _path(mesh) != DEST + key:
            raise ValueError('Bike record part is not its finished package: ' + key)
        entry = _report(context, reports[key])
        bounds = mesh.get_bounding_box()
        meshes[key] = mesh
        parts[key] = {'source_triangles': entry['triangles'], 'triangles': mesh.get_num_triangles(0),
                      'min': [bounds.min.x, bounds.min.y, bounds.min.z], 'max': [bounds.max.x, bounds.max.y, bounds.max.z]}
    if not set(STEERING) <= set(meshes):
        raise ValueError('Bike record needs the complete steering group')
    steering = unreal.BikeMeshComponent.steering_bounds([meshes[key] for key in STEERING])
    if not steering:
        raise ValueError('Bike steering parts carry no complete saved group bounds')
    return {RECORD: {'complete': True, 'parts': parts, 'steering_bounds': json.loads(steering), 'retired': []}}


ACTIONS = {'part': part, 'steering': steering, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-bike-part-bodies
    Each job MUST finish exactly its declared Bike part, a fresh duplicate of its
    raw import on the declared M_Bike with import_bike.py's checks against its own
    construction report and receipt before and after its save; the steering owner
    MUST finish exactly the four steering packages and persist the complete group's
    true bounds on all four before saving. The record MUST write only the report from the
    declared finished parts. It MUST NOT run the original top level or retirement.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported Bike action')
    if args['action'] == 'part':
        if (params.get('op') != 'finish' or params.get('kind') != 'static_mesh' or params.get('source') != 'raw'
                or set(params) - {'op', 'kind', 'source', 'destination', 'args', 'input_roots', 'settings'}):
            raise ValueError('A Bike part is finished by unreal.finish(static_mesh)')
    elif set(params) - {'args', 'settings', 'input_roots'}:  # steering and record are unreal.author jobs
        raise ValueError('Unexpected Bike author parameters')
    return ACTIONS[args['action']](context, unreal, args)
