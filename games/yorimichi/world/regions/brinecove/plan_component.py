"""Construct one coastal component, then publish its individually bounded final mesh inputs."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import name, real_directory  # noqa: E402
from random_stream import positioned  # noqa: E402
from brinecove.piece_inputs import finish_parts  # noqa: E402


def read_context(path, asset):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Coastal source parameters must be regular and unlinked')
    value = json.loads(path.read_text())
    if (set(value) != {'schema', 'asset', 'seed', 'prefix_words'} or type(value['schema']) is not int
            or value['schema'] != 1 or value['asset'] != asset or type(value['seed']) is not int
            or type(value['prefix_words']) is not int or not 0 <= value['prefix_words'] <= 1_000_000):
        raise ValueError('Invalid coastal constructor parameters')
    return value




def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--builder', required=True)
    parser.add_argument('--context', required=True, type=Path)
    parser.add_argument('--rim', required=True, type=Path)
    parser.add_argument('--paving-output', required=True, type=Path)
    parser.add_argument('--query-output', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name(args.asset); name(args.builder)
    context = read_context(args.context, args.asset)
    for path in (args.rim,):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing final coastal boundary data')
    real_directory(args.output); real_directory(args.paving_output.parent)
    from brinecove.rim_schema import read
    rim, _ = read(json.loads(args.rim.read_text()))
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from brinecove import geometry_finish, layout, rocks
    from brinecove.geom import Builder
    from brinecove.procedural import geometry_policy, random_state
    constructor = getattr(importlib.import_module('brinecove.procedural.' + args.builder), args.builder)
    geometry_policy.FLAT_PAVING.clear(); geometry_policy._STREET_SLABS.clear()
    random_state.RNG.setstate(positioned(context['seed'], context['prefix_words']).getstate())
    settled = geometry_finish.settle(rim)
    def final_ground(x, y):
        current = settled(x, y)[1]
        return layout.ground(x, y) if current is None else current
    rocks.FINAL = final_ground
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'Coastal {args.asset} constructing/planning after {time.monotonic()-started:.0f}s; no complete product yet', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try:
        builder = constructor(Builder('rocks'), hills=False) if args.asset == 'Rocks' else constructor()
        value, counts, _ = finish_parts(builder, args.asset, rim, args.output, query_output=args.query_output)
        # Geometry changes that leave these rectangles unchanged stop before ground.
        atomic_json(args.paving_output, dict(schema=1, owner=args.asset, rectangles=geometry_policy.FLAT_PAVING))
    finally:
        done.set(); thread.join(timeout=1)
    print('COASTAL COMPONENT PLAN COMPLETE', args.asset, len(value['pieces']), counts, flush=True)


if __name__ == '__main__':
    main()
