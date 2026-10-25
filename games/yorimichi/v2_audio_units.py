"""Author C3 SoundWave RawImport and Finish units from exact audio producer rows.

One shared constructor covers the fixed sound roster that ``unreal.sounds`` imports
(footsteps, combat, skate, bike, transport, driving). Each producer owns one folder
product ROOT whose WAV membership is generated (sliced or synthesised), so the per-file
roster MUST arrive as keyed group members; this module never scans a generated folder.
Without keyed members a producer refuses with ``DynamicMembership``.
"""
from pathlib import PurePosixPath
import re

from v2_texture_units import OPS, SIDECARS, Unsupported, _code, _path

GAME = 'games/yorimichi'
AUDIO = GAME + '/assets/audio'
# producer -> (product ROOT, generator script, destination folder, per-surface folders,
# loop rule, fixed finish properties). Rules mirror Scripts/import_<name>.py exactly.
ROSTER = {
    'audio.footsteps': ('footsteps', AUDIO + '/footsteps/slice.py', '/Game/Japan/Audio/Footsteps', True, 'never',
                        {'looping': False, 'streaming': False}),
    'audio.combat': ('combat', AUDIO + '/combat/slice.py', '/Game/Audio/Combat', False, 'ambience', {}),
    'audio.skate': ('skate', AUDIO + '/skate/make.py', '/Game/Audio/Skate', False, 'manifest', {}),
    'audio.bike': ('bike', AUDIO + '/bike/make.py', '/Game/Audio/Bike', False, 'manifest', {}),
    'audio.transport': ('transport', AUDIO + '/transport/make.py', '/Game/Audio/Transport', False, 'manifest', {}),
    'audio.kart': ('kart', AUDIO + '/kart/make.py', '/Game/Audio/Driving', False, 'manifest', {}),
}
# Assets import_footsteps.py builds beside the waves that raw_import/finish cannot author.
GAPS = ({'producer': 'audio.footsteps', 'package': '/Game/Japan/Audio/A_Footstep', 'class': 'SoundAttenuation',
         'reason': 'authored attenuation asset: no C3 create op'},
        {'producer': 'audio.footsteps', 'package': '/Game/Japan/Audio/DA_Footsteps', 'class': 'JapanFootstepSet',
         'reason': 'data asset over every surface wave: needs a C3 aggregate op consuming the finished waves'},
        {'producer': 'audio.music', 'package': '/Game/Audio/Music', 'class': 'SoundWave',
         'reason': 'explicit optional library: names and library.json come from the generated selection manifest'})
_NAME = re.compile(r'[A-Za-z0-9_]+\Z')


class DynamicMembership(Unsupported):
    """A producer's WAV roster is generated and no keyed group membership was supplied."""


def _output(package, *, raw):
    stem = package.removeprefix('/Game/')
    files = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not raw:
            row['install_path'] = GAME + '/unreal/Content/' + stem + suffix
        files.append(row)
    return {'id': 'raw_sound' if raw else 'sound', 'logical_path': package,
            'class': 'RawSound' if raw else 'Sound', 'destination': 'store' if raw else 'checkout', 'files': files}


def _check(row):
    root, script = ROSTER[row['id']][:2]
    source = f'build/yorimichi/audio/{root}'
    products = row['products']
    if (len(products) != 1 or products[0]['id'] != row['id'] or products[0]['paths'] != [source]
            or products[0]['optional_paths'] or row['outputs'] != [source + '/manifest.json']):
        raise Unsupported(f'{row["id"]}: producer must own exactly its audio folder ROOT and manifest')
    commands = row['commands']
    if (len(commands) != 1 or commands[0].get('kind') != 'python'
            or commands[0].get('script') != {'path': script} or commands[0].get('args')):
        raise Unsupported(f'{row["id"]}: producer command differs from the original declared body')


def _member(value):
    path = _path(value)
    parts = PurePosixPath(path).parts
    if (len(parts) != 2 or not path.endswith('.wav') or parts[0] == 'preview'
            or not _NAME.fullmatch(parts[0]) or not _NAME.fullmatch(PurePosixPath(path).stem)):
        raise Unsupported(f'noncanonical audio member {value!r}')
    return parts[0], PurePosixPath(path).stem


def _source(entry, producer):
    """The member's exact existing InputSource: a D2 group member or a fixed one-WAV Item.

    A legacy ``item`` {unit, item} means only an explicitly fixed published Item. No
    per-member item id is ever invented here.
    """
    if 'item' in entry:
        value = entry['item']
        if not isinstance(value, dict) or set(value) != {'unit', 'item'}:
            raise Unsupported(f'{producer}: fixed member item is {{unit, item}}')
        value = {'kind': 'item', **value}
    else:
        value = entry['source']
    shapes = {'item': {'kind', 'unit', 'item'}, 'group_member': {'kind', 'unit', 'group', 'piece'}}
    if (not isinstance(value, dict) or value.get('kind') not in shapes or set(value) != shapes[value['kind']]
            or not all(isinstance(value[key], str) and value[key] for key in value)):
        raise Unsupported(f'{producer}: member source must be an exact item or group_member InputSource')
    if value['unit'] == producer and value['kind'] == 'item':
        raise Unsupported(f'{producer}: the producer publishes one multi-WAV ROOT, not a per-file Item')
    return dict(value)


def audio_units(rows, *, checkout, members=None):
    """@cc [owner:fontanierh,label:correctness] authored-c3-audio-units
    Each selected audio producer MUST match its exact original row, folder product ROOT
    and command. Its per-file roster MUST be supplied as keyed group members (each a
    canonical <cue>/<name>.wav with its exact existing InputSource: a D2 group_member or
    an explicitly fixed one-WAV item, preserved unchanged as the raw input); the generated
    folder is never scanned and an absent roster refuses with DynamicMembership. The
    current producers publish one multi-WAV ROOT, so the dynamic group adaptation is open. RawImport MUST stay
    store-only without properties; Finish MUST consume its actual raw Item, apply only
    the original import script's looping/streaming settings and own its runtime package
    with the permitted sidecars. Native worker source membership MUST be keyed code.
    """
    members = members or {}
    selected = [row for row in rows if row['id'] in ROSTER]
    for row in selected:
        _check(row)
    if len({row['id'] for row in selected}) != len(selected):
        raise Unsupported('duplicate audio producer')
    missing = sorted(row['id'] for row in selected if row['id'] not in members)
    if missing:
        raise DynamicMembership('generated WAV rosters need keyed group members: ' + ', '.join(missing))
    if set(members) - {row['id'] for row in selected}:
        raise Unsupported('audio members name an unselected producer')
    code = _code(checkout) if selected else []
    units, staged, slots, packages = [], {}, {}, {}
    for row in selected:
        _, _, folder, surfaces, rule, fixed = ROSTER[row['id']]
        roster = members[row['id']]
        if not isinstance(roster, dict) or set(roster) - {'files', 'loops'} or 'files' not in roster:
            raise Unsupported(f'{row["id"]}: members must be {{files, loops}}')
        loops = roster.get('loops')
        if (rule == 'manifest') != isinstance(loops, list):
            raise Unsupported(f'{row["id"]}: loop cues are required exactly for manifest-looped rosters')
        if not roster['files']:
            raise Unsupported(f'{row["id"]}: empty audio roster')
        for entry in roster['files']:
            if not isinstance(entry, dict) or len(entry) != 2 or 'path' not in entry or not (
                    set(entry) & {'source', 'item'}):
                raise Unsupported(f'{row["id"]}: each member is {{path, source}}')
            source = _source(entry, row['id'])
            group, name = _member(entry['path'])
            package = f'{folder}/{group}/{name}' if surfaces else f'{folder}/{name}'
            if package in packages:
                raise Unsupported(f'duplicate audio package {package}')
            looping = {'never': False, 'ambience': name.startswith('ambience_'),
                       'manifest': name.rsplit('_', 1)[0] in (loops or ())}[rule]
            properties = dict(fixed) if fixed else {'looping': looping}
            key = row['id'].removeprefix('audio.') + '.' + (group + '.' if surfaces else '') + name
            raw_id, finish_id = 'unreal.sound.raw.' + key, 'unreal.sound.finish.' + key
            raw_package = '/Game/_Raw/' + package.removeprefix('/Game/')
            for unit_id, op, params, input_name, unit_source, raw in (
                (raw_id, 'unreal.raw_import',
                 {'op': 'raw_import', 'kind': 'sound', 'source': 'source', 'destination': raw_package},
                 'source', source, True),
                (finish_id, 'unreal.finish',
                 {'op': 'finish', 'kind': 'sound', 'source': 'raw', 'destination': package,
                  'package_sources': {'raw': raw_package}, 'properties': properties},
                 'raw', {'kind': 'item', 'unit': raw_id, 'item': 'raw_sound'}, False)):
                units.append({'id': unit_id, 'op': {'kind': op, 'version': '1'}, 'script': OPS, 'code': list(code),
                              'inputs': [{'role': 'content', 'name': input_name, 'source': unit_source}],
                              'params': params, 'outputs': [_output(raw_package if raw else package, raw=raw)]})
                staged[unit_id] = {input_name: 'inputs/' + input_name}
                slots[input_name] = False
            packages[package] = {'unit': finish_id, 'item': 'sound', 'package': package}
    return {'units': units, 'staged': staged, 'slots': slots, 'packages': packages, 'gaps': list(GAPS)}
