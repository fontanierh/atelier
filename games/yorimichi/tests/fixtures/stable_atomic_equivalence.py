"""Actual selected Stable constructors against immutable original packets and complete GLBs."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import threading
import time

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from hidamari_stable import atomic_sources, query_data, plan_asset, query_inputs  # noqa: E402
from hidamari_stable.catalogue import SOURCES, PARTS, selected  # noqa: E402
import export_region_piece  # noqa: E402

STAGE = ['preflight']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--roof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--counter', type=Path, required=True)
    parser.add_argument('--counter-sha', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    root = real_directory(args.output)
    if root.exists(): raise ValueError('Fresh Stable selected-export evidence required')
    old = real_directory(args.baseline) / 'products'
    for witness in (args.baseline, args.roof):
        guard = json.loads((witness / 'guard/memory-health-tree.json').read_text())
        if guard['state'] != 'child_exited' or not guard['cleanup_complete'] or guard['processes'] or guard.get('late_reporters', {}).get('unresolved'):
            raise ValueError('Original Stable witnesses must be positively stopped')
    original = json.loads((old / 'baseline-signatures.json').read_text())
    contexts = GAME / 'assets/hidamari-stable/construction-contexts.json'
    if json.loads(contexts.read_text()) != json.loads((args.roof / 'products/contexts.json').read_text()):
        raise ValueError('Selected states differ from observed original roof/semantic entries')
    paths = set(local_imports(GAME / 'world/regions/hidamari_stable/plan_asset.py', (GAME / 'world', GAME / 'world/regions')))
    paths.update(local_imports(GAME / 'world/regions/hidamari_stable/query_data.py', (GAME / 'world', GAME / 'world/regions')))
    paths.update(query_inputs.committed())
    paths.update((Path(__file__), args.counter, contexts, Path(mesh_ir.__file__), GAME / 'world/export_region_piece.py',
                  GAME / 'world/regions/hidamari/fonts/NotoSansJP.ttf'))
    paths.update(old / 'data' / name for name in query_inputs.generated())
    paths.update(old / 'data/hidamari-stable/glb' / (key + '.glb') for key in original)
    paths.update(old / 'baseline' / key / row['path'] for key, entry in original.items() for row in entry['packets'])
    paths.update((old / 'baseline-signatures.json', old / 'result.json', args.roof / 'products/contexts.json'))
    def bindings():
        result = {}
        for path in sorted(paths):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Nonregular bound Stable proof input')
            st = path.stat(); result[str(path)] = dict(sha256=sha(path), stat=[st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns])
        return result
    before = bindings()
    if sha(args.counter) != args.counter_sha: raise ValueError('Independent counter bytes differ')
    functions = {'require', 'finite', 'canonical', '_digest', '_f32', 'face_counter', 'glb_counter'}
    tree = ast.parse(args.counter.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions
                 or isinstance(node, ast.ClassDef) and node.name == 'EvidenceError']
    if {node.name for node in tree.body} != functions | {'EvidenceError'}: raise ValueError('Independent counter closure differs')
    counter = dict(np=np, Counter=Counter, json=json, hashlib=hashlib, math=math, struct=struct)
    exec(compile(tree, str(args.counter), 'exec'), counter)
    atomic_sources.publish(json.loads(contexts.read_text()), root / 'sources', enabled=True)
    STAGE[0] = 'canonical original selected query data'
    query_data.main(['--source-root', str(old / 'data'), '--road-context', str(root / 'sources/SM_HS_Road.json'),
        '--sign-context', str(root / 'sources/SM_HS_RoadSign.json'), '--output', str(root / 'queries')])
    results = {}; unions = {}
    for key in SOURCES:
        STAGE[0] = 'independent constructor/export ' + key
        argv = ['--asset', key, '--source', str(root / 'sources' / (key+'.json')), '--output', str(root / 'plans' / key)]
        if key in ('SM_HS_Road', 'SM_HS_RoadSign'): argv += ['--queries', str(root / 'queries' / (key+'.json'))]
        plan_asset.main(argv)
        manifest = json.loads((root / 'plans' / key / 'plan.json').read_text())
        parent, lod = selected(key)
        logical = 'SM_HS_Stable_LOD'+str(lod) if parent.removeprefix('SM_HS_') in PARTS else key
        union = unions.setdefault(logical, dict(source=Counter(), glb=dict(render=Counter(), collision=Counter()), triangles=0))
        for row in manifest['pieces']:
            payload = root / 'plans' / key / row['payload']; meta, piece = mesh_ir.decode(payload.read_bytes())
            union['source'].update(counter['face_counter'](meta, piece))
            destination = root / 'exports' / row['name']
            export_region_piece.main(['--input', str(payload), '--output', str(destination), '--format', '.glb'])
            observed, triangles = counter['glb_counter']((destination / (row['name']+'.glb')).read_bytes())
            for kind in observed: union['glb'][kind].update(observed[kind])
            union['triangles'] += triangles
        results[key] = dict(triangles=manifest['source_triangles'], pieces=len(manifest['pieces']),
                            max_triangles=max(row['triangles'] for row in manifest['pieces']))
        print('STABLE ATOMIC EXPORTED '+key+' '+json.dumps(results[key]), flush=True)
    if set(unions) != set(original): raise ValueError('Incomplete original logical union')
    for logical, union in unions.items():
        source = Counter()
        for row in original[logical]['packets']:
            meta, piece = mesh_ir.decode((old / 'baseline' / logical / row['path']).read_bytes())
            source.update(counter['face_counter'](meta, piece))
        if source != union['source']: raise ValueError('Complete original source corner union differs: '+logical)
        serialized, triangles = counter['glb_counter']((old / 'data/hidamari-stable/glb' / (logical+'.glb')).read_bytes())
        if serialized != union['glb'] or triangles != union['triangles']:
            raise ValueError('Complete actual original serialized GLB union differs: '+logical)
        print('STABLE ORIGINAL SOURCE/GLB UNION PASS '+logical, flush=True)
    if bindings() != before: raise ValueError('Bound original/current Stable evidence changed')
    atomic_json(root / 'result.json', dict(complete=True, source_policy_enabled=False,
        source_corner_union=True, numeric_glb_corner_material_union=True, sources=results,
        original_logical_count=len(unions), bindings=before,
        scope='isolated disabled Stable source/export proof; actual saved native GPU/LOD/bounds/collision/query remain separate'))
    print('STABLE ATOMIC EQUIVALENCE COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25): print(f'Stable equivalence {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: main()
    finally: done.set(); thread.join(timeout=1)
