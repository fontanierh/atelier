"""Native bodies for Scripts/import_ride_clips.py (unreal.<k>_bike, unreal.<k>_horse), one declared package per job.

``args.action`` selects
- ``clip``: A_<Clip> in /Game/<Rig><Ride> from its raw import on the character's skeleton: import_ride_clips.fbx's
  finishing (root motion off, the shared compression) and its length check against its own member's duration,
  within 1.5 frames at the export rate;
- ``record``: <ride>/unreal_import.json, the original report, from the export and the finished clips.
The original top level never runs.
"""
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
COMPRESSION_SCRIPT = 'games/yorimichi/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
RECORD = 'data/unreal_import.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _load(unreal, context, slot, cls=None):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared ride input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Ride native input must be exactly one declared package: ' + slot)
    asset = unreal.EditorAssetLibrary.load_asset(packages[0])
    if asset is None or _path(asset) != packages[0] or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared ride input did not load as expected: ' + packages[0])
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared ride data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Ride data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.name != name or path.is_symlink() or not path.is_file():
        raise ValueError(f'Ride data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Ride derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    if not isinstance(value, dict):
        raise ValueError('Ride roster must be a slot map')
    return dict(value)


def clip(context, unreal, args):
    params = context.params
    destination = params['destination']
    if list(context.outputs) != [destination] or unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise ValueError('Ride clip job owns exactly its fresh declared package')
    meta = _data(context, args['meta'], 'meta.json')
    if meta['name'] != args['name'] or meta['fps'] != args['fps']:
        raise ValueError('Ride clip member differs from its declared group')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'])
    settings = _load(unreal, context, args['compression'])
    if _path(settings) != COMPRESSION:
        raise ValueError('Ride clip compression input is not the shared CharacterCompression')
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Ride clip is not on the declared skeleton: ' + destination)
    sequence.set_editor_property('enable_root_motion', False)
    spec = importlib.util.spec_from_file_location('atelier_ride_compression', Path(context.job_dir) / COMPRESSION_SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module._settings = settings   # the declared shared owner: apply_to only assigns it
    module.apply_to(sequence)
    length = sequence.get_play_length()
    # Loops export one frame short of the cycle (the last frame is the first again); one-shots include their last frame.
    if abs(length - meta['duration']) >= 1.5 / meta['fps']:
        raise ValueError(f'{destination}: length {length} differs from {meta["duration"]}')
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Ride clip save failed: ' + destination)
    return sequence


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The ride record job owns only its JsonData output')
    config = _data(context, args['export'], 'export.json')
    finished = {}
    for slot in _roster(args['clips']).values():
        sequence = _load(unreal, context, slot, unreal.AnimSequence)
        finished[_path(sequence).rsplit('/A_', 1)[1]] = sequence
    if set(finished) != set(config['clips']):
        raise ValueError('Ride record clips differ from the export')
    report = {name: {'length': round(finished[name].get_play_length(), 4), 'frames': entry['frames'], 'loop': entry['loop']}
              for name, entry in config['clips'].items()}
    return {RECORD: {'fps': config['fps'], 'source_sha256': config['source_sha256'], 'clips': report}}


ACTIONS = {'clip': clip, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-ride-clip-bodies
    Each job MUST finish exactly its declared ride clip, a fresh duplicate of its raw
    import on the declared character skeleton with the shared compression and the
    original length check from its own member, or write only the ride report from
    the declared export and finished clips. It MUST NOT run the original top level.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported ride action')
    if args['action'] == 'clip':
        if params.get('op') != 'finish' or params.get('kind') != 'animation':
            raise ValueError('A ride clip is finished by unreal.finish(animation)')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected ride author parameters')
    return ACTIONS[args['action']](context, unreal, args)
