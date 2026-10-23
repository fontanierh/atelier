"""Observe the immutable Stable source in a clearly isolated disabled-owner fixture.

Only the original main entry's enable refusal is removed. The committed runtime switch
is untouched; this diagnostic is not acceptance of an enabled world or normal task.
"""
import argparse
import ast
import hashlib
import json
import random
from pathlib import Path
import sys
import threading
import time
import types

import bpy

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from island_atomic_equivalence import baseline_packets, captured, signature  # noqa: E402
from village import mesh as kernel  # noqa: E402

STAGE = ['preflight']
PARTS = ('barn', 'gate', 'yard', 'paddock')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    output = real_directory(args.output)
    if output.exists(): raise ValueError('Fresh original Stable fixture required')
    fixture = Path(__file__).with_name('stable-predecessor-283329c07.txt')
    original = fixture.read_text(); source = GAME / 'world/regions/hidamari_stable/build.py'
    assert sha(fixture) == sha(source), 'Original Stable constructor source changed before census'
    paths = set(local_imports(source, (GAME / 'world', GAME / 'world/regions')))
    paths.update((Path(__file__), fixture, Path(__file__).with_name('island_atomic_equivalence.py')))
    paths.add(GAME / 'world/regions/hidamari/fonts/NotoSansJP.ttf')
    before = {str(path): sha(path) for path in sorted(paths)}
    yori.OUT = output / 'data'
    tree = ast.parse(original)
    entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    refusal = entry.body[0]
    assert isinstance(refusal, ast.If) and ast.unparse(refusal.test) == 'not L.is_enabled()'
    assert len(refusal.body) == 1 and isinstance(refusal.body[0], ast.Raise)
    entry.body = entry.body[1:]
    tree.body = [n for n in tree.body if not (isinstance(n, ast.If) and n.lineno > entry.lineno)]
    scope = types.ModuleType('stable_immutable_original'); scope.__file__ = str(fixture)
    sys.modules[scope.__name__] = scope
    exec(compile(tree, str(fixture), 'exec'), scope.__dict__)
    if scope.L.is_enabled(): raise ValueError('Diagnostic must retain the committed disabled source policy')
    assert kernel.R.getstate() == random.Random(76).getstate(), 'Original Stable must retain its untouched fresh RNG'
    contexts, ranges, references = {}, {}, {}
    for part in PARTS:
        original_part = getattr(scope, part)
        def observed(m, lod, part=part, original_part=original_part):
            STAGE[0] = f'original {part} LOD{lod}'
            key = part + '_LOD' + str(lod)
            contexts[key] = json.loads(json.dumps(kernel.R.getstate()))
            start = len(m.faces)
            original_part(m, lod)
            ranges[key] = [start, len(m.faces)]
            print('STABLE ORIGINAL PART ' + key + ' ' + str(sum(len(f)-2 for f in m.faces[start:])), flush=True)
        setattr(scope, part, observed)
    for part in ('stall_door', 'room_door', 'ground', 'road', 'road_sign'):
        original_part = getattr(scope, part)
        def observed(*values, part=part, original_part=original_part):
            key = part + ('_LOD' + str(values[0]) if part.endswith('door') else '')
            contexts[key] = json.loads(json.dumps(kernel.R.getstate()))
            return original_part(*values)
        setattr(scope, part, observed)
    original_export = scope.export_glb
    def export(path, objects):
        STAGE[0] = 'original GLB ' + path.stem
        if not path.stem.endswith('_Collision'):
            assert len(objects) == 1
            obj = objects[0]; data = captured(obj)
            references[path.stem] = dict(signature=signature(data),
                matrix=[list(row) for row in obj.matrix_world],
                packets=baseline_packets(data, output / 'baseline' / path.stem, path.stem,
                    [list(row) for row in obj.matrix_world], options=dict(export_apply=True)))
        result = original_export(path, objects)
        print('STABLE ORIGINAL GLB COMPLETE ' + path.stem, flush=True)
        return result
    scope.export_glb = export
    scope.main()
    if {str(path): sha(path) for path in sorted(paths)} != before:
        raise ValueError('Stable source changed during immutable census')
    atomic_json(output / 'contexts.json', dict(schema=1, seed=76, complete=True, contexts=contexts,
        semantic_face_ranges=ranges, predecessor_sha256=hashlib.sha256(original.encode()).hexdigest(),
        source_policy_enabled=False, scope='isolated original disabled-owner fixture; production switch unchanged'))
    atomic_json(output / 'baseline-signatures.json', references)
    atomic_json(output / 'result.json', dict(complete=True, baseline_sources=before, contexts=list(contexts),
        source_policy_enabled=False, scope='actual immutable original Stable constructors and GLB only; no native or enabled-world acceptance'))
    print('STABLE ORIGINAL CONTEXT COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25): print(f'Stable original context {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: main()
    finally: done.set(); thread.join(timeout=1)
