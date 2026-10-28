"""Selected native skate data authors and the complete in-memory verifier."""
import importlib.util
import json
import re
from pathlib import Path

RUNTIME = '/Game/SkateRuntime/RuntimeData'
MOTION = '/Game/SkateMotion/MotionData'
SAVE = 'platform/studio/atelier/native_packages.py'
REPORT = 'data/verify.json'


def _json(text):
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out: raise ValueError('Duplicate skate JSON field')
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite skate JSON')))


def _bank(index):
    return f'/Game/SkateMotion/Banks/Bank_{index:03d}'


def _source(context, args):
    root = Path(context.inputs['source'])
    job = Path(context.job_dir).resolve()
    if not root.is_absolute() or root.resolve() != root or not root.is_relative_to(job) or not root.is_dir():
        raise ValueError('Skate source must be the decoded job-local complete package ROOT')
    manifest_path = root / 'package-manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Skate source manifest is missing or linked')
    manifest = _json(manifest_path.read_text())
    clips = manifest.get('clips')
    if (manifest.get('version') != 1 or type(clips) is not int or clips <= 0 or clips != args['clips']
            or (clips + 127) // 128 != args['bank_count'] or not isinstance(manifest.get('files'), dict)
            or clips != sum(name.startswith('animation/clips/') and name.endswith('.skate') for name in manifest['files'])):
        raise ValueError('Skate source ROOT differs from the declared complete clip/bank roster')
    return root


def _load(unreal, package, cls):
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or not isinstance(asset, cls) or asset.get_path_name().split('.', 1)[0] != package:
        raise ValueError('Declared skate native package did not load: ' + package)
    return asset


def _success(result):
    # The existing one-Error-out import wrappers document '' on success, None on failure.
    if type(result) is not str or result:
        raise RuntimeError('Skate native import failed: ' + (result if isinstance(result, str) else 'no successful Error output'))


def run(context):
    """@cc [owner:fontanierh,label:correctness] selected-skate-native-data
    Each author MUST consume the actual decoded complete source ROOT, own exactly
    its fresh declared package and use only its selected native API. MotionData
    and verification MUST bind all exact finished banks. Verification MUST return
    the complete finite native JSON report in memory without file writes, using
    the keyed original configured asset paths with CDO values restored afterward. Native
    saves MUST leave actual primary files; original mains/retirement MUST NOT run.
    """
    import unreal
    params = context.params
    if set(params) != {'args', 'settings', 'input_roots'} or params['settings'] != []:
        raise ValueError('Unsupported skate data parameters')
    args = params['args']
    if (not isinstance(args, dict) or args.get('action') not in ('runtime', 'bank', 'motion', 'verify')
            or type(args.get('clips')) is not int or args['clips'] <= 0
            or type(args.get('bank_count')) is not int or args['bank_count'] != (args['clips'] + 127) // 128):
        raise ValueError('Invalid skate data action/roster')
    action, count = args['action'], args['bank_count']
    expected_args = {'action', 'bank_count', 'clips'} | ({'package'} if action != 'verify' else set()) | ({'bank'} if action == 'bank' else set()) | ({'configured_assets'} if action == 'verify' else set())
    if set(args) != expected_args or set(params['input_roots']) != {'source'}:
        raise ValueError('Skate data arguments differ from the declared action')
    binding = params['input_roots']['source']
    if (not isinstance(binding, dict) or set(binding) != {'archive_member', 'name'} or binding['name'] != 'package'
            or not isinstance(binding['archive_member'], str)
            or re.fullmatch(r'outputs/[0-9]+\.tree\.tar', binding['archive_member']) is None):
        raise ValueError('Skate data must bind the complete producer package ROOT')
    banks = {f'bank{b:03d}': (_bank(b), unreal.SkateMotionBank) for b in range(count)}
    required = banks if action == 'motion' else ({'runtime': (RUNTIME, unreal.SkateRuntimeData),
                'motion': (MOTION, unreal.SkateMotionData), **banks} if action == 'verify' else {})
    if set(context.inputs) != {'source', *required} or set(context.packages) != set(context.inputs) or context.packages['source'] not in ([], ()):
        raise ValueError('Skate native/data input membership differs')
    for slot, (package, cls) in required.items():
        if context.packages[slot] not in (package, [package], (package,)):
            raise ValueError('Skate declared native input differs: ' + slot)
        _load(unreal, package, cls)
    if action == 'verify':
        if list(context.outputs) or tuple(context.data_outputs) != (REPORT,):
            raise ValueError('Skate verifier owns exactly its JsonData report')
    else:
        if action == 'bank' and (type(args['bank']) is not int or not 0 <= args['bank'] < count):
            raise ValueError('Skate bank selection is out of range')
        package = RUNTIME if action == 'runtime' else (MOTION if action == 'motion' else _bank(args['bank']))
        if (args['package'] != package or list(context.outputs) != [package]
                or tuple(getattr(context, 'data_outputs', ())) or unreal.EditorAssetLibrary.does_asset_exist(package)):
            raise ValueError('Skate author owns exactly its fresh selected output')
    source = _source(context, args)
    library = unreal.SkateDataLibrary
    if action == 'verify':
        configured = args['configured_assets']
        if configured != {'motion_data': MOTION + '.MotionData', 'runtime_data': RUNTIME + '.RuntimeData'}:
            raise ValueError('Skate verifier must use its exact declared configured assets')
        settings = unreal.get_default_object(unreal.SkateSettings)
        original = {key: settings.get_editor_property(key) for key in configured}
        try:
            for key, value in configured.items():
                settings.set_editor_property(key, unreal.SoftObjectPath(value))
            result = library.verify_to_json(str(source))
        finally:
            for key, value in original.items():
                settings.set_editor_property(key, value)
        if not isinstance(result, tuple) or len(result) != 2 or any(type(v) is not str for v in result) or result[1]:
            raise RuntimeError('Skate native in-memory verification failed')
        report = _json(result[0])
        expected_banks = [p + '.' + p.rsplit('/', 1)[-1] for p, _ in banks.values()]
        if (not isinstance(report, dict) or report.get('clips') != args['clips'] or report.get('banks') != expected_banks
                or report.get('asset') != MOTION + '.MotionData' or report.get('runtime_asset') != RUNTIME + '.RuntimeData'
                or any(report.get(k) is not True for k in ('exact', 'negative_control', 'runtime_exact', 'runtime_negative_control'))
                or any(report.get(k) != v for k, v in {'replay_cases': 12, 'invalid_record_controls': 3, 'runtime_invalid_record_controls': 3}.items())
                or any(type(report.get(k)) is not int or report[k] <= 0 for k in
                       ('schema', 'runtime_schema', 'clips', 'frames', 'bone_samples', 'replay_steps', 'runtime_files', 'runtime_bytes'))):
            raise ValueError('Skate verification report lacks the original complete exact/replay evidence')
        return {REPORT: report}
    if action == 'runtime':
        result = library.import_runtime(str(source), '/Game/SkateRuntime')
        cls = unreal.SkateRuntimeData
    elif action == 'bank':
        result = library.import_motion_bank(str(source), args['bank'], package)
        cls = unreal.SkateMotionBank
    else:
        result = library.import_motion_index(str(source), package)
        cls = unreal.SkateMotionData
    _success(result)
    asset = _load(unreal, package, cls)
    path = Path(context.job_dir) / SAVE
    if path.resolve() != path or not path.is_file():
        raise ValueError('Skate save helper must be staged keyed code')
    spec = importlib.util.spec_from_file_location('skate_owned_save', path)
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    native.save(asset, unreal.EditorAssetLibrary, context.content_dir)
    return asset
