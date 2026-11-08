"""Construct one original coach from its explicit layout/query request and publish bounded source packets."""
import argparse
from dataclasses import fields
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory
from atelier.model_files import regular_files, retain_files

CLASSES = {'Body', 'Coach', 'Room', 'Opening', 'Wall', 'Window', 'Door', 'Box', 'Placement', 'Seat', 'Mount'}


def decode(value, layout):
    if not isinstance(value, dict):
        if value is None or type(value) in (str, bool, int, float): return value
        raise ValueError('Invalid coach constructor scalar')
    kind = value['kind']
    if kind == 'record':
        if value['type'] not in CLASSES: raise ValueError('Foreign coach constructor record')
        cls = getattr(layout, value['type'])
        if set(value['fields']) != {field.name for field in fields(cls)}: raise ValueError('Incomplete coach constructor record')
        return cls(**{key: decode(item, layout) for key, item in value['fields'].items()})
    if kind in ('tuple', 'list'):
        data = [decode(item, layout) for item in value['items']]; return tuple(data) if kind == 'tuple' else data
    if kind == 'map': return {key: decode(item, layout) for key, item in value['items'].items()}
    raise ValueError('Unsupported coach constructor field')


def install_access(value, layout):
    """Selected construction reads published query answers, never the neighbour/character discovery code."""
    if set(value) != {'players', 'locked_gangways', 'locked_doors'} or type(value['locked_doors']) is not bool:
        raise ValueError('Incomplete coach source queries')
    players = decode(value['players'], layout); locks = decode(value['locked_gangways'], layout)
    if not players or any(len(player) != 4 or not all(type(v) in (int, float) and v > 0 for v in player[1:]) for player in players):
        raise ValueError('Invalid player capsule source data')
    module = ModuleType('train.access')
    module.players = lambda: players
    module.tallest = lambda: max(player[3] for player in players)
    module.locked_gangways = lambda: locks
    module.LOCKED_DOORS = value['locked_doors']
    sys.modules['train.access'] = module
    package = importlib.import_module('train'); package.access = module
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True); parser.add_argument('--coach', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--addon', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    real_directory(args.request.parent)
    if args.request.is_symlink() or not args.request.is_file(): raise ValueError('Linked coach request')
    raw = args.request.read_bytes(); value = json.loads(raw); json.dumps(value, allow_nan=False)
    root = real_directory(args.output, create=True)
    before = regular_files(root)
    if before:
        prior = json.loads((root / 'source.json').read_text())
        if (prior.get('schema') != 1 or prior.get('coach') != args.coach or prior.get('complete') is not True
                or before != set(prior['files']) | {'source.json'}
                or any(hashlib.sha256((root / member).read_bytes()).hexdigest() != row['sha256']
                       for member, row in prior['files'].items())):
            raise ValueError('Foreign or corrupt previous carriage source product')
    if value.get('schema') != 1 or value.get('coach') != args.coach: raise ValueError('Foreign selected coach request')
    layout = importlib.import_module('train.layout')
    coach = decode(value['layout'], layout)
    if coach.name != args.coach: raise ValueError('Foreign coach constructor fields')
    access = install_access(value['access'], layout)
    if any(len(pair) != 2 or pair[0] != coach.name for pair in access.locked_gangways()):
        raise ValueError('Foreign adjacent-door source query')
    real_directory(args.addon.parent)
    if args.addon.is_symlink() or not args.addon.is_file(): raise ValueError('Linked source addon identity')
    addon_raw = args.addon.read_bytes(); addon = json.loads(addon_raw)
    if addon.get('schema') != 1 or set(addon['files']) != {'exporter', 'writer'}:
        raise ValueError('Incomplete prepared source addon identity')
    builder = importlib.import_module('train.build')
    source = importlib.import_module('train.carriage_source')
    builder.OUT = root / 'authoring'; builder.TEX = root / 'textures'
    builder.FU.stage(builder.OUT / 'furniture')
    images = builder.make_textures()
    info = builder.build(coach, dict(images), source_sink=source.source_sink(builder, root / 'packets',
        addon=addon['files']))
    if args.request.read_bytes() != raw or args.addon.read_bytes() != addon_raw:
        raise ValueError('Coach request/source addon changed during construction')
    packets = json.loads((root / 'packets/inventory.json').read_text())
    members = {'packets/inventory.json', 'packets/info.json', 'packets/placements.json',
               *(f"packets/{row['source']}" for row in packets['pieces']),
               *(f'authoring/furniture/{asset["id"]}.{suffix}' for asset in layout.contract()['assets'] for suffix in ('glb', 'json')),
               *(f'textures/{name}.{"jpg" if name in builder.T.JPEG else "png"}' for name in images)}
    probes, _ = builder.PT.window_tiles(coach)
    if probes:
        atlas = 'textures/T_BT_' + info['mesh'].removeprefix('SM_BT_') + 'Interior'
        members.update({atlas + '.png', atlas + '.json'})
    if not members <= regular_files(root): raise ValueError('Incomplete selected carriage source output')
    atomic_json(root / 'source.json', dict(schema=1, coach=coach.name, complete=True,
        files={member: dict(bytes=(root / member).stat().st_size, sha256=hashlib.sha256((root / member).read_bytes()).hexdigest())
               for member in sorted(members)}, info=info))
    retain_files(root, [*members, 'source.json'])
    print('SELECTED CARRIAGE SOURCE COMPLETE', coach.name, flush=True)


if __name__ == '__main__': main()
