"""Plan one original railway authored LOD from its complete selected source data."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
import bpy
import numpy as np
from atelier.atomic_files import atomic_json
from atelier.model_files import regular_files, retain_files
from region_mesh_parts import plan
from atelier.export_manifest import real_directory, sha


def construct(value):
    """Restore the original flat-shaded mesh, planar UVs and consumed material graphs."""
    namespace = dict(bpy=bpy, np=np, T=SimpleNamespace(MATERIALS=value['palette']))
    exec(compile(value['material_factory'] + '\n' + value['to_object'],
                 '<selected-original-railway-conversion>', 'exec'), namespace)
    materials = namespace['materials']()
    mesh = SimpleNamespace(verts=value['vertices'], faces=value['faces'], mats=value['materials'])
    return namespace['to_object'](value['asset'], mesh, materials)


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness] track-plan-consumed-source
    A complete railway plan MUST bind the exact consumed source bytes and each
    geometry/material packet digest. Changed inputs MUST refuse publication of
    that binding; equal triangle counts MUST NOT substitute for source identity.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--materials', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file(): raise ValueError('Railway source must be a regular file')
    source_bytes = args.source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    value = json.loads(source_bytes)
    if value.get('schema') != 1 or value.get('asset') != args.asset: raise ValueError('Foreign railway source')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = construct(value)
    result = plan(obj, args.output, options=dict(export_apply=True), partition='whole')
    palette_root = real_directory(args.materials, create=True)
    expected = {row['name'] + '.json' for row in result['pieces']}
    previous = palette_root / 'manifest.json'
    owned = set(json.loads(previous.read_text())['files']) if previous.exists() else set()
    if regular_files(palette_root) - expected - owned - {'manifest.json'}: raise ValueError('Foreign railway material packets')
    for row in result['pieces']:
        palette = palette_root / (row['name'] + '.json')
        atomic_json(palette, dict(schema=1, asset=row['name'],
            palette={slot: value['palette'][slot] for slot in row['slots']},
            material_factory=value['material_factory'], export_glb=value['export_glb']))
        row['material_sha256'] = sha(palette)
    atomic_json(previous, dict(schema=1, files=sorted(expected)))
    retain_files(palette_root, ['manifest.json', *expected])
    if result['source_triangles'] != value['triangles']: raise ValueError('Railway source triangle loss')
    if args.source.read_bytes() != source_bytes: raise ValueError('Railway source changed during planning')
    result['source_sha256'] = source_sha256
    atomic_json(args.output / 'plan.json', result)
    print('RAILWAY LOGICAL PLAN COMPLETE', value['asset'], len(result['pieces']), flush=True)


if __name__ == '__main__': main()
