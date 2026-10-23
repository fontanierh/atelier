"""Actual independent Village constructors versus frozen immutable-original source and FBX."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import threading
import time

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(GAME / 'tests/native'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402
from atelier import mesh_ir, mesh_collision  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from fbx_face_digests import read as exported  # noqa: E402
from island_atomic_equivalence import captured, signature, verify_piece  # noqa: E402
from region_mesh_parts import capture_colliders, plan  # noqa: E402
from village.atomic_sources import ASSETS, HEIGHTS, contexts, project  # noqa: E402
from village.logical import construct  # noqa: E402
from village.plan_asset import OPTIONS  # noqa: E402
import export_region_piece  # noqa: E402

STAGE = ['preflight']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    baseline = real_directory(args.baseline)
    root = real_directory(args.output)
    if root.exists(): raise ValueError('Fresh complete Village export proof required')
    receipt = json.loads((baseline / 'guard/memory-health-tree.json').read_text())
    if (receipt['state'] != 'child_exited' or not receipt['cleanup_complete'] or receipt['processes']
            or receipt.get('late_reporters', {}).get('unresolved')):
        raise ValueError('Original Village census is not positively stopped')
    old = baseline / 'products'
    witness = json.loads((old / 'result.json').read_text())
    if not witness['complete'] or set(witness['census']) != set(ASSETS):
        raise ValueError('Incomplete immutable-original Village census')
    code = set(local_imports(GAME / 'world/regions/village/plan_asset.py', (GAME / 'world', GAME / 'world/regions')))
    code.update((Path(__file__), GAME / 'world/export_region_piece.py', GAME / 'tests/native/fbx_face_digests.py',
                 GAME / 'tests/native/fbx_corners.py', Path(__file__).with_name('island_atomic_equivalence.py'),
                 GAME / 'assets/village/construction-contexts.json', Path(mesh_ir.__file__), Path(mesh_collision.__file__)))
    inputs = {old / 'data/world.json', old / 'data/heightmap.npy', old / 'contexts.json',
              old / 'baseline-signatures.json', old / 'result.json', baseline / 'guard/memory-health-tree.json'}
    inputs.update(old / 'data/village/assets' / (key + '.fbx') for key in ASSETS)
    inputs.update(old / 'original-hulls' / (key + '.json') for key in ASSETS)
    references = json.loads((old / 'baseline-signatures.json').read_text())
    inputs.update(old / 'baseline' / key / row['path'] for key in ASSETS for row in references[key]['packets'])
    def identities(paths):
        result = {}
        for path in sorted(paths):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Nonregular bounded Village proof input')
            st = path.stat()
            result[str(path)] = dict(sha256=sha(path), stat=[st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns])
        return result
    before, sources = identities(inputs), identities(code)
    recorded = json.loads((old / 'contexts.json').read_text())
    if json.loads((GAME / 'assets/village/construction-contexts.json').read_text()) != recorded:
        raise ValueError('Current independent construction states differ from actual predecessor')
    selected = project(json.loads((old / 'data/world.json').read_text()), contexts())
    h = np.load(old / 'data/heightmap.npy', allow_pickle=False)
    result = {}
    for key in ASSETS:
        STAGE[0] = 'independent original constructor ' + key
        bpy.ops.wm.read_factory_settings(use_empty=True)
        m = construct(key, selected[key], h if key in HEIGHTS else None)
        obj = m.object(bpy.data.materials.new('VillagePalette'))
        data = captured(obj)
        if json.loads(json.dumps(signature(data))) != references[key]['signature']:
            raise ValueError('Ordered original Village source channels differ: ' + key)
        if [list(row) for row in obj.matrix_world] != references[key]['matrix']:
            raise ValueError('Village authored frame changed: ' + key)
        hulls = capture_colliders(m.colliders)
        # Expected discovery was independent enumeration of actual original old-export hulls.
        expected_meta, _ = mesh_ir.decode((old / 'baseline' / key / references[key]['packets'][0]['path']).read_bytes())
        if hulls != expected_meta['collisions']:
            raise ValueError('Complete original Village collision channels/transform changed: ' + key)
        value = plan(obj, root / 'plans' / key, partition='spatial' if key == 'Village_Planting' else 'whole', collisions=hulls, options=OPTIONS)
        original = exported(old / 'data/village/assets' / (key + '.fbx'))
        observed = dict(render=Counter(), collision=Counter())
        for index, row in enumerate(value['pieces'], 1):
            STAGE[0] = f'atomic {key} {index}/{len(value["pieces"])}'
            payload = root / 'plans' / key / row['payload']
            _, piece = mesh_ir.decode(payload.read_bytes())
            verify_piece(data, row, piece)
            output = root / 'exports' / row['name']
            export_region_piece.main(['--input', str(payload), '--output', str(output)])
            for kind, counts in exported(output / (row['name'] + '.fbx')).items(): observed[kind].update(counts)
        if observed != original:
            raise ValueError('Complete serialized render/collision corner union changed: ' + key)
        result[key] = dict(triangles=value['source_triangles'], polygons=value['source_polygons'],
            hulls=value['source_collision_hulls'], pieces=len(value['pieces']),
            max_triangles=max(row['triangles'] for row in value['pieces']))
        print('VILLAGE ATOMIC CONSERVATION ' + key + ' ' + json.dumps(result[key]), flush=True)
    if identities(inputs) != before or identities(code) != sources:
        raise ValueError('Bound Village proof source or original artifacts changed')
    atomic_json(root / 'result.json', dict(complete=True, source_channels=True, collision_channels=True,
        numeric_exported_polygon_union=True, assets=result, baseline_inputs=before, actual_sources=sources,
        scope='all12 actual Village source/serialized exports; native cook/query/seams remain separate'))
    print('VILLAGE ATOMIC EQUIVALENCE COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25): print(f'Village equivalence {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: main()
    finally: done.set(); thread.join(timeout=1)
