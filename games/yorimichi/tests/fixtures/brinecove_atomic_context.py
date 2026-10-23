"""Compare independent coastal constructors with the original complete authoring order."""
import argparse
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from random_stream import Counted, positioned  # noqa: E402

PHASE = dict(stage='input preflight', completed=0, total=9)


def signature(builder):
    # Every Builder field is compared, including optional anchors/normals and
    # semantic flags. Unsupported values or nonfinite floats refuse JSON encoding.
    data = json.dumps(vars(builder), sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
    return dict(sha256=hashlib.sha256(data).hexdigest(), fields=sorted(vars(builder)),
                vertices=len(builder.verts), polygons=len(builder.faces),
                triangles=sum(len(face) - 2 for face in builder.faces))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root, donor = real_directory(args.output), real_directory(args.donor)
    if os.path.lexists(root):
        raise ValueError('Coastal context requires fresh evidence')
    source = donor / 'terrain/FarHills/final.npz'
    real_directory(source.parent)
    if source.is_symlink() or not source.is_file():
        raise ValueError('Coastal context requires the current final FarHills product')
    regions = GAME / 'world/regions'
    sources = set(local_imports(regions / 'brinecove/build.py', (GAME / 'world', regions)))
    sources.update(p for p in (regions / 'brinecove').rglob('*.py') if '__pycache__' not in p.parts)
    sources.update(GAME / 'assets/brinecove/models' / name for name in (
        'pirate-queen-statue.glb', 'galleon-figurehead.glb', 'ships-wheel.glb',
        'galleon-hull.glb', 'galleon-hull.provenance.json'))
    sources.update((Path(__file__), GAME / 'world/random_stream.py', source))
    def identities():
        return {str(path): sha(path) for path in sorted(sources)}
    before = identities()
    target = root / 'data/terrain/FarHills/final.npz'
    target.parent.mkdir(parents=True)
    copy_file(source, target)
    assert sha(target) == before[str(source)]
    yori.OUT = root / 'data'
    from brinecove import build, modules, rocks
    from brinecove import layout
    from brinecove.geom import Builder
    from brinecove.procedural import geometry_policy, random_state
    PHASE['stage'] = 'final collar query data'
    rim, world = build.rim()
    from brinecove import rim_data
    projection = rim_data.project(target)
    projected, projected_world = rim_data.read(json.loads(json.dumps(projection)))
    assert projected.sides == rim.sides and projected_world == world, 'Final rim data projection changed'
    atomic_json(root / 'rim.json', projection)
    settle = build.settle(rim)
    def final_ground(x, y):
        actual = settle(x, y)[1]
        return layout.ground(x, y) if actual is None else actual
    rocks.FINAL = final_ground
    geometry_policy.FLAT_PAVING.clear()
    geometry_policy._STREET_SLABS.clear()
    contexts, results = {}, {}
    with Counted(modules.RNG) as measured:
        for key, constructor in build.MODULES:
            PHASE['stage'] = 'original constructor ' + key
            context = measured.context(49157)
            original = constructor()
            reference = signature(original)
            del original
            PHASE['stage'] = 'selected constructor ' + key
            random_state.RNG.setstate(positioned(
                context['seed'], context['prefix_words']).getstate())
            function = dict(Rocks='terrain_dressing', Harbor='harbor', TownLower='lower_town',
                Market='market', TownUpper='upper_town', Landmarks='landmarks', Ships='ships',
                Props='props', Understory='vegetation')[key]
            selected = getattr(importlib.import_module('brinecove.procedural.' + function), function)
            actual = selected(Builder('rocks'), hills=False) if key == 'Rocks' else selected()
            assert signature(actual) == reference, (key, 'coastal constructor geometry/UV/material/normal/anchor changed')
            del actual
            contexts[key] = context
            results[key] = reference
            PHASE['completed'] += 1
            gc.collect()
            atomic_json(root / 'progress.json', dict(PHASE))
            print(f'COASTAL CONTEXT {len(results)}/9 {key}: {reference["triangles"]} triangles', flush=True)
    assert geometry_policy.FLAT_PAVING == modules.FLAT_PAVING, 'Complete ground-covering paving rectangles changed'
    from brinecove.procedural.lower_street_slabs import lower_street_slabs
    assert lower_street_slabs() == modules.lower_street_slabs(), 'Terrain-following paving projection changed'
    assert identities() == before, 'Coastal source or donor changed during validation'
    PHASE['stage'] = 'complete'
    atomic_json(root / 'contexts.json', contexts)
    atomic_json(root / 'result.json', dict(complete=True, assets=results, contexts=contexts,
        exact_builder_fields=True, complete_paving_data_equal=True, exact_rim_projection=True, sources=before,
        scope='procedural constructor and paving data only; no mesh export or native receiving acceptance'))
    print('BRINECOVE ATOMIC CONTEXT COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event()
    started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'Coastal context heartbeat {time.monotonic()-started:.0f}s: {PHASE}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        main()
    finally:
        done.set()
        thread.join(timeout=1)
