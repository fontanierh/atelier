"""Native bodies for unreal.skate_clips (Scripts/skate_ride/import_clips.py and verify_clips.py), one owner per job.

The original functions run from scoped AST reads in each job; their main(), setup(), state files, batching and
directory deletes never run. ``args.action`` selects
- ``rider``: SK_SkateRider and SKEL_SkateRider from the raw glTF import of rider_mesh's GLB, with check_rider;
- ``bone`` / ``curve``: ACL_SkateRideExact and CC_SkateRideExact, the two halves of compression_assets;
- ``mirror``: MDT_SkateRider by mirror_table (refused where the original logs and leaves it out);
- ``clip``: one clip by make_clip from its own member (every key and bone, root lock, curves, both compressions);
- ``verify``: one clip's compressed every-frame pose and curve measurement (sample_poses, measure, check_curves);
- ``still``: a still clip's component-space poses (dump_still's document);
- ``control``: the compression control, an unreal.finish: the finished CONTROL clip duplicated into its own
  store-only /Game/_Raw/SkateRideVerify/ControlDefaultCompression under the engine's default bone compression,
  measured compressed and raw (it must show a compressed error; the exact clip must not);
- ``manifest``: Content/Data/SkateRide/clips.json (setup's head and main's manifest) from the finished assets;
- ``report``: skate-ride/clips-verify.json (main's report) from every clip measurement and the control.
"""
import ast
import json
import math
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
SCRIPTS = 'games/yorimichi/unreal/Scripts/skate_ride'
MEMBERS = 'games/yorimichi/world/skate_clip_members_v2.py'
DEST = '/Game/SkateRide'
IMPORT = ('log', 'enum', 'set_any', 'finish_compilation', 'create', 'check_rider', 'compression_assets', 'curve_keys',
          'round_list', 'set_default_frame_rate', 'make_clip', 'curve_identifier_maker', 'mirror_rows', 'mirror_table')
VERIFY = ('finish_compilation', 'options', 'sample_poses', 'curve_value', 'measure', 'check_curves', 'step_keys')
MANIFEST, REPORT, DATA, CONTROL_DATA = 'data/clips.json', 'data/clips-verify.json', 'data/verify.json', 'data/control.json'
CONTROL_COPY = '/Game/_Raw/SkateRideVerify/ControlDefaultCompression'
KEYS = ('translation_cm', 'rotation_rad', 'scale')


def accepted(measurement, limits):
    """One clip measurement against verify_clips.LIMITS (its rotation already counts Euler-key storage by its distance
    to the stored key, as measure does): finite, within every limit, no missing curve, a finite curve error."""
    problems = [k for k in KEYS if not math.isfinite(measurement[k]) or measurement[k] > limits[k]]
    if not math.isfinite(measurement['curve_error']):
        problems.append('curve_error')
    if measurement['curves_missing']:
        problems.append('curves_missing ' + ','.join(measurement['curves_missing']))
    return problems


def control_accepted(control):
    """The control proves compressed data was measured: actual raw and compressed errors, all finite, and a non-zero
    compressed error under the engine's default compression."""
    if not isinstance(control, dict) or 'error' in control or not all(
            isinstance(control.get(part), dict) and set(KEYS) <= set(control[part]) for part in ('compressed', 'raw')):
        return ['incomplete control']
    values = [control[part][k] for part in ('compressed', 'raw') for k in KEYS]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return ['nonfinite control']
    return [] if max(control['compressed'][k] for k in KEYS) > 0 else ['control shows no compressed error']


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared skate input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Skate native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None, package=None):
    path = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if (asset is None or _path(asset) != path or (cls is not None and not isinstance(asset, cls))
            or (package is not None and path != package)):
        raise ValueError('Declared skate input did not load as expected: ' + path)
    return asset


def _root(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared skate data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Skate data must be a job-local declared input')
    return root


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Skate derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    raise ValueError('Skate roster must be a derived token')


def _start(unreal, context, packages, data=()):
    if sorted(context.outputs) != sorted(packages) or tuple(getattr(context, 'data_outputs', ())) != tuple(data):
        raise ValueError('Skate job owns exactly its declared packages and data')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Skate destination must be fresh: ' + package)


def _code(context, relative):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Skate keyed code is not staged: ' + relative)
    return path


def _members(context):
    import importlib.util
    import sys
    name = 'skate_clip_members_native'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _code(context, MEMBERS))
        module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return sys.modules[name]


def _simulation(context):
    return _members(context).module(_code(context, SCRIPTS + '/simulation.py'), 'skate_ride_simulation')


def _import(context, unreal, **extra):
    """import_clips' scoped functions and constants, with its own globals."""
    M, N = _members(context), _simulation(context)
    path = _code(context, SCRIPTS + '/import_clips.py')
    values = M.constants(path, ('DEST', 'STILLS', 'CONTROL', 'BOARD', 'ACL_ERROR_CM'))
    if values['DEST'] != DEST:
        raise ValueError('import_clips.py DEST differs')
    scope = {'U': unreal, 'N': N, 'json': json, 'math': math, 'E': unreal.EditorAssetLibrary,
             'AT': unreal.AssetToolsHelpers.get_asset_tools(), 'CLIPS': DEST + '/Clips', **values, **extra}
    return M.original(path, IMPORT, scope)


def _verify(context, unreal):
    M, N = _members(context), _simulation(context)
    path = _code(context, SCRIPTS + '/verify_clips.py')
    values = M.constants(path, ('STILLS', 'CONTROL', 'CONTROL_SETTINGS', 'LIMITS', 'STORED_MATCH'))
    scope = {'U': unreal, 'N': N, 'math': math, 'E': unreal.EditorAssetLibrary, 'P': unreal.AnimPoseExtensions, **values}
    return M.original(path, VERIFY, scope)


def _rig(context, slot):
    N = _simulation(context)
    rig = N.Bundle(_root(context, slot)).rig()
    return N, rig, rig.named_pose(0, 'RIG_TPOSE')


def _json(context, slot, relative):
    """A staged JSON Item: the file itself, or <root>/<relative>, or <root>/<basename>."""
    root = _root(context, slot)
    for path in (root, root / relative, root / Path(relative).name):
        if path.is_file() and not path.is_symlink():
            return json.loads(path.read_bytes())
    raise ValueError(f'Skate data {relative} is absent from {slot}')


def _member(context, slot, name=None):
    """(clip, metadata, record): a selected member/ view, or one named member of a whole bank member Item."""
    import base64
    import hashlib
    root = _root(context, slot)
    N = _simulation(context)
    if name is None:
        member = json.loads((root / 'member.json').read_bytes())
        data = (root / 'clip.skate').read_bytes()
    else:
        member = json.loads((root / f'{name}.json').read_bytes())
        data = base64.b64decode(member['clip'], validate=True)
        if member['name'] != name or hashlib.sha256(data).hexdigest() != member['sha256']:
            raise ValueError('Skate bank member differs from its name or checksum')
    clip = N.load_clip(data)
    if clip.name != member['name'] or clip.bank != member['bank']:
        raise ValueError('Skate member differs from its clip')
    return clip, _members(context).clip_metadata(N, member['metadata']), member['record']


def _split(function, target):
    """compression_assets' statements that make one of its two assets: (bone) up to the curve's create, (curve) after."""
    body = [s for s in function.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    cut = [i for i, s in enumerate(body) if isinstance(s, ast.Assign) and getattr(s.targets[0], 'id', None) == 'curve']
    if len(cut) != 1 or not isinstance(body[-1], ast.Return):
        raise ValueError('compression_assets changed shape')
    part = body[:cut[0]] if target == 'bone' else body[cut[0]:-1]
    return ast.Module(body=[*part, ast.Expr(ast.Name(target, ast.Load()))], type_ignores=[])


def rider(context, unreal, args):
    params = context.params
    mesh_package, skeleton_package = params['destination'], params['partners']['skeleton']
    if (mesh_package, skeleton_package) != (DEST + '/SK_SkateRider', DEST + '/SKEL_SkateRider'):
        raise ValueError('The rider owns SK_SkateRider and SKEL_SkateRider')
    _start(unreal, context, [mesh_package, skeleton_package])
    E = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    mesh = E.duplicate_asset(_path(raw), mesh_package)
    skeleton = E.duplicate_asset(_path(raw.get_editor_property('skeleton')), skeleton_package)
    if not isinstance(mesh, unreal.SkeletalMesh) or not isinstance(skeleton, unreal.Skeleton):
        raise ValueError('Skate rider duplicate failed')
    mesh.set_editor_property('skeleton', skeleton); skeleton.set_editor_property('preview_skeletal_mesh', mesh)
    if mesh.skeleton != skeleton:
        raise ValueError('SK_SkateRider is not on SKEL_SkateRider')
    if not E.save_loaded_asset(skeleton, False) or not E.save_loaded_asset(mesh, False):
        raise ValueError('Skate rider save failed')
    _, rig, pose = _rig(context, args['bundle'])
    _import(context, unreal)['check_rider'](rig, pose, mesh, skeleton)
    return mesh


def compression(context, unreal, args):
    target = args['action']
    package = DEST + ('/ACL_SkateRideExact' if target == 'bone' else '/CC_SkateRideExact')
    _start(unreal, context, [package])
    scope = _import(context, unreal)
    tree = ast.parse(_code(context, SCRIPTS + '/import_clips.py').read_bytes())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compression_assets')
    module = _split(function, target)
    *statements, last = module.body
    exec(compile(ast.Module(body=statements, type_ignores=[]), 'compression_assets', 'exec'), scope)
    asset = scope[target]
    if _path(asset) != package:
        raise ValueError('Skate compression asset not authored at its package')
    return asset


def mirror(context, unreal, args):
    package = DEST + '/MDT_SkateRider'
    _start(unreal, context, [package])
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton, DEST + '/SKEL_SkateRider')
    _, rig, _ = _rig(context, args['bundle'])
    path, count, rows, axis = _import(context, unreal)['mirror_table'](rig, skeleton)
    if path != package or count != len(rows) or axis is None:
        raise ValueError(f'MDT_SkateRider was not made completely: {path} {count}/{len(rows)} rows, axis {axis}')
    return unreal.EditorAssetLibrary.load_asset(package)


def _settings(unreal, context, args):
    return (_load(unreal, context, args['skeleton'], unreal.Skeleton, DEST + '/SKEL_SkateRider'),
            _load(unreal, context, args['mesh'], unreal.SkeletalMesh, DEST + '/SK_SkateRider'),
            _load(unreal, context, args['bone'], unreal.AnimBoneCompressionSettings, DEST + '/ACL_SkateRideExact'),
            _load(unreal, context, args['curve'], unreal.AnimCurveCompressionSettings, DEST + '/CC_SkateRideExact'))


def clip(context, unreal, args):
    folder = f'{DEST}/Clips/B{args["bank"]}'
    package = f'{folder}/{args["name"]}'
    _start(unreal, context, [package])
    value, meta, _ = _member(context, args['member'])
    if value.name != args['name'] or value.bank != args['bank']:
        raise ValueError('Skate clip member differs from its piece')
    _, rig, pose = _rig(context, args['bundle'])
    skeleton, mesh, bone, curve = _settings(unreal, context, args)
    scope = _import(context, unreal)
    sequence, _, _ = scope['make_clip'](value, meta, rig, pose, skeleton, mesh, bone, curve, scope['curve_identifier_maker']())
    if _path(sequence) != package:
        raise ValueError('Skate clip not authored at its package')
    unreal.EditorAssetLibrary.save_loaded_asset(sequence, False)
    scope['finish_compilation']()
    return sequence


def _measure(scope, unreal, value, rig, pose, sequence, record):
    poses = scope['sample_poses'](sequence, value.fps, value.frame_count)
    worst, where, per_bone, stored = scope['measure'](value, rig, pose, poses)
    curve_error, missing = scope['check_curves'](sequence, value, record, poses)
    return poses, dict(frames=value.frame_count, fps=value.fps, **worst, where=where, curve_error=curve_error,
                       curves_missing=sorted(set(missing)), euler_storage=stored,
                       bones={b: [round(v[0], 7), round(v[1], 8)] for b, v in per_bone.items() if v[0] > 1e-3 or v[1] > 1e-5})


def verify(context, unreal, args):
    _start(unreal, context, [], (DATA,))
    value, _, record = _member(context, args['member'])
    _, rig, pose = _rig(context, args['bundle'])
    sequence = _load(unreal, context, args['sequence'], unreal.AnimSequence, f'{DEST}/Clips/B{value.bank}/{value.name}')
    scope = _verify(context, unreal)
    scope['finish_compilation']()
    measurement = _measure(scope, unreal, value, rig, pose, sequence, record)[1]
    problems = accepted(measurement, scope['LIMITS'])
    if problems:
        raise ValueError(f'{value.name}: compressed pose differs from the simulation: {problems}')
    return {DATA: measurement}


def still_document(source):
    """dump_still without its file write: the document it writes."""
    tree = ast.parse(source)
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dump_still'), None)
    if function is None or ast.unparse(function.body[0]) != 'POSES.mkdir(parents=True, exist_ok=True)' \
            or not ast.unparse(function.body[-1]).startswith("(POSES / f'{name}.json').write_text(json.dumps(dict(clip=name, fps=fps, frames=frames))"):
        raise ValueError('verify_clips.dump_still changed shape')
    function.body = [*function.body[1:-1], ast.parse('return dict(clip=name, fps=fps, frames=frames)').body[0]]
    return ast.Module(body=[function], type_ignores=[])


def still(context, unreal, args):
    _start(unreal, context, [], (DATA,))
    value, _, _ = _member(context, args['members'], args['name'])
    sequence = _load(unreal, context, _roster(args['sequence'])[args['name']], unreal.AnimSequence,
                     f'{DEST}/Clips/B{value.bank}/{value.name}')
    _, rig, _ = _rig(context, args['bundle'])
    scope = _verify(context, unreal)
    exec(compile(still_document(_code(context, SCRIPTS + '/verify_clips.py').read_text()), 'dump_still', 'exec'), scope)
    if value.name != args['name'] or value.name not in scope['STILLS']:
        raise ValueError('Skate still differs from verify_clips.STILLS')
    scope['finish_compilation']()
    return {DATA: scope['dump_still'](value.name, rig, scope['sample_poses'](sequence, value.fps, value.frame_count), value.fps)}


def _source(context):
    """The finish source slot: a declared slot name, or the exact-piece derived token of the finished CONTROL clip."""
    source = context.params['source']
    if isinstance(source, str):
        return source
    rows = _roster(source)
    if len(rows) != 1:
        raise ValueError('The control source must be exactly one finished clip')
    return next(iter(rows.values()))


def control(context, unreal, args):
    params = context.params
    if params['destination'] != CONTROL_COPY:
        raise ValueError('The control owns only ' + CONTROL_COPY)
    _start(unreal, context, [CONTROL_COPY], (CONTROL_DATA,))
    checks = _verify(context, unreal)
    value, _, _ = _member(context, args['members'], checks['CONTROL'])
    _, rig, pose = _rig(context, args['bundle'])
    original = _load(unreal, context, _source(context), unreal.AnimSequence, f'{DEST}/Clips/B{value.bank}/{value.name}')
    # verify_clips.control: a copy of CONTROL under the engine's default bone compression (here its own declared package).
    copy = unreal.EditorAssetLibrary.duplicate_asset(_path(original), CONTROL_COPY)
    if not isinstance(copy, unreal.AnimSequence):
        raise ValueError('control duplicate')
    default = None
    for path in checks['CONTROL_SETTINGS']:     # loaded directly: the commandlet's asset registry does not list engine content
        default = unreal.load_object(None, path)
        if default is not None:
            break
    if default is None:
        raise ValueError('no default bone compression settings')
    copy.set_editor_property('bone_compression_settings', default)
    checks['finish_compilation']()
    compressed = checks['sample_poses'](copy, value.fps, value.frame_count)
    worst, where, _, _ = checks['measure'](value, rig, pose, compressed)
    raw = checks['sample_poses'](copy, value.fps, value.frame_count, unreal.AnimDataEvalType.RAW)
    raw_worst, _, _, _ = checks['measure'](value, rig, pose, raw)
    if not unreal.EditorAssetLibrary.save_loaded_asset(copy, False):
        raise ValueError('control save')
    result = dict(clip=value.name, compression=default.get_path_name(), compressed=worst, compressed_where=where, raw=raw_worst)
    problems = control_accepted(result)
    if problems:
        raise ValueError(f'compression control: {problems}')
    return {CONTROL_DATA: result}


def _statements(source, function, names):
    """The named assignments (and, for 'reference', its filling loop) of an original function body, in order."""
    tree = ast.parse(source)
    body = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function).body
    picked = []
    def walk(statements):
        for s in statements:
            if isinstance(s, ast.Assign) and getattr(s.targets[0], 'id', None) in names:
                picked.append(s)
            elif isinstance(s, ast.For) and 'reference' in names and 'reference.append' in ast.unparse(s):
                picked.append(s)
            elif isinstance(s, ast.If):
                walk(s.body)
    walk(body)
    return ast.Module(body=picked, type_ignores=[])


def _records(context, slots):
    rows = {}
    for slot in slots:
        for path in sorted(_root(context, slot).iterdir()):
            member = json.loads(path.read_bytes())
            if path.name != member['name'] + '.json' or member['name'] in rows:
                raise ValueError('Skate member records are not one per clip')
            rows[member['name']] = member
    return rows


def manifest(context, unreal, args):
    _start(unreal, context, [], (MANIFEST,))
    N, rig, pose = _rig(context, args['bundle'])
    skeleton, mesh, bone, curve = _settings(unreal, context, args)
    table = _load(unreal, context, args['mirror'], unreal.MirrorDataTable, DEST + '/MDT_SkateRider')
    scope = _import(context, unreal)
    unreal_order, ref_t, ref_r = scope['check_rider'](rig, pose, mesh, skeleton)
    axis = table.get_editor_property('mirror_axis')
    members = _records(context, args['members'])
    finished = {}
    for token in args['clips']:
        finished.update(_roster(token))
    if sorted(finished) != sorted(members):
        raise ValueError('Finished skate clips differ from the committed roster')
    stats = json.loads((_root(context, args['bundle']) / 'stats.json').read_bytes())
    source = _code(context, SCRIPTS + '/import_clips.py').read_text()
    scope.update(rig=rig, pose=pose, skeleton=skeleton, mesh=mesh, bone_settings=bone, curve_settings=curve,
                 mirror_path=_path(table), mirror_ok=len(table.get_row_names()), mirror_axis=getattr(axis, 'name', str(axis)),
                 unreal_order=unreal_order, ref_t=ref_t, ref_r=ref_r, mesh_stats=stats, partial=False)
    exec(compile(_statements(source, 'setup', ('reference', 'head')), 'setup', 'exec'), scope)
    head, clips = scope['head'], {}
    for name, member in sorted(members.items(), key=lambda row: (row[1]['bank'], row[0] + '.skate')):
        asset = _load(unreal, context, finished[name], unreal.AnimSequence, f'{DEST}/Clips/B{member["bank"]}/{name}')
        record = dict(member['record'])
        record['mirror'] = dict(table=head['mirror_table'], **record['mirror'])
        clips[name] = dict(asset=_path(asset), **record)
    scope['clips'] = clips
    exec(compile(_statements(source, 'main', ('manifest',)), 'main', 'exec'), scope)
    return {MANIFEST: scope['manifest']}


def report(context, unreal, args):
    _start(unreal, context, [], (REPORT,))
    _, rig, _ = _rig(context, args['bundle'])
    measured = {}
    for token in args['verify']:
        for name, slot in _roster(token).items():
            measured[name] = _json(context, slot, DATA)
    control_value = _json(context, args['control'], CONTROL_DATA)
    path = _code(context, SCRIPTS + '/verify_clips.py')
    scope = {'LIMITS': _members(context).constants(path, ('LIMITS',))['LIMITS'], 'rig': rig,
             'state': {'clips': measured, 'control': control_value}, 'manifest': {'partial': False}}
    exec(compile(_statements(path.read_text(), 'main', ('clips', 'overall', 'worst_clip', 'over', 'stored_all', 'report')),
                 'main', 'exec'), scope)
    result = scope['report']
    if result['clips'] != args['count']:
        raise ValueError('The skate clip verification is not over the complete roster')
    problems = [f'{n}: {p}' for n, m in sorted(measured.items()) for p in accepted(m, scope['LIMITS'])]
    problems += control_accepted(result['control'])
    if result['passed'] is not True or problems or result['curves_missing'] or not math.isfinite(result['curve_max_error']):
        raise ValueError(f"The skate clips do not pass their verification: passed={result['passed']} {problems[:20]}")
    return {REPORT: result}


ACTIONS = {'rider': rider, 'bone': compression, 'curve': compression, 'mirror': mirror, 'clip': clip, 'verify': verify,
           'still': still, 'control': control, 'manifest': manifest, 'report': report}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-skate-clip-native-bodies
    Each job MUST author or finish exactly its declared /Game/SkateRide owner or its
    one JSON document from declared inputs, by the original import_clips and
    verify_clips functions: the rider with check_rider, both compressions, the
    mirror table, every clip key and curve, every-frame compressed measurement
    refused beyond the original LIMITS or with missing curves, the private control
    copy that must show a compressed error, and the complete manifest and a report
    that MUST pass. It MUST NOT run the originals' main, setup, state, batching or
    directory deletes.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported skate clip action')
    finishes = {'rider': 'skeletal_mesh', 'control': 'animation'}
    if args['action'] in finishes:
        if params.get('op') != 'finish' or params.get('kind') != finishes[args['action']]:
            raise ValueError(f"The {args['action']} is finished by unreal.finish({finishes[args['action']]})")
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected skate author parameters')
    return ACTIONS[args['action']](context, unreal, args)
