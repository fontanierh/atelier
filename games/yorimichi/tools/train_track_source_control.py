"""Processless immutable-original track/source/serialized-GLB diagnostic.

The outer host freezes original source and inputs. No Git, subprocess, launcher,
source producer stamp or native acceptance runs in this Blender stage.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
import bpy
from atelier.atomic_files import atomic_json
from atelier.gltf import glb_parts
from train import track_sources as selected
import atomic_equivalence as eq


def checked(record):
    path = Path(record['path'])
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Frozen railway authority/input changed')
    return path


def load(label, path, *, filename=None):
    module = types.ModuleType(label); module.__file__ = str(filename or path)
    module.__package__ = label.rpartition('.')[0]; sys.modules[label] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    parent, _, member = label.rpartition('.')
    if parent in sys.modules: setattr(sys.modules[parent], member, module)
    return module


def raw(mesh):
    return hashlib.sha256(json.dumps(dict(vertices=mesh.verts, faces=mesh.faces, materials=mesh.mats),
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    authority = json.loads(args.authority.read_text())
    frozen = {key: checked(value) for key, value in authority['files'].items()}
    fixture = Path(authority['fixture']); yori.OUT = fixture
    # The PRIVATE fixture wraps exact stopped original bytes. This is a reader
    # migration control, never a normal source-producer/cache success claim.
    from belmonte.surface_data import write
    for owner in (() if authority.get('natural_source_producer') else ('SM_BM_NorthCountry', 'SM_BM_NorthApron')):
        data = frozen['input.natural.' + owner].read_bytes(); doc, _ = glb_parts(data)
        triangles = sum(doc['accessors'][primitive['indices']]['count'] // 3 for mesh in doc['meshes'] for primitive in mesh['primitives'])
        entry = dict(name=owner, collision=False, triangles=triangles, sha256=hashlib.sha256(data).hexdigest())
        write(fixture / 'belmonte-natural-source-data' / (owner + '.surface'), entry, data, stage='natural')
    route = json.loads(frozen['input.route.json'].read_text())
    # Current code is loaded before switching the immutable package namespace.
    import train
    import belmonte.source
    from train import plan_track as planner, export_track_piece as exporter
    current_modules = {key: value for key, value in sys.modules.items() if key == 'train' or key.startswith('train.') or key == 'belmonte.source'}
    for key in list(current_modules): sys.modules.pop(key, None)
    package = types.ModuleType('train'); package.__path__ = [str(frozen['original.track.py'].parent)];sys.modules['train'] = package
    old_source = load('belmonte.source', frozen['original.belmonte.source.py'], filename=GAME / 'world/regions/belmonte/source.py')
    old_track = load('train.track', frozen['original.track.py'])
    original_meshes, original_doc = old_track.layout(old_track.Line(route))
    old_factory = load('train.track_build', frozen['original.track_build.py'])
    baseline = {}; paths = {}; render = {}
    baseline_dir = args.output.parent / 'original'; baseline_dir.mkdir(parents=True, exist_ok=True)
    for parent, levels in original_meshes.items():
        for k, mesh in enumerate(levels):
            key = f'{parent}_LOD{k}'
            bpy.ops.wm.read_factory_settings(use_empty=True)
            obj = old_factory.to_object(key, mesh, old_factory.materials())
            path = baseline_dir / (key + '.glb'); old_factory.export_glb(path, obj)
            baseline[key] = dict(raw=raw(mesh), triangles=mesh.triangles)
            paths[key] = path
            render[key] = eq.glb_counter(path.read_bytes())
            print('IMMUTABLE TRACK GLB', key, mesh.triangles, flush=True)
    for key in list(sys.modules):
        if key == 'train' or key.startswith('train.') or key == 'belmonte.source': sys.modules.pop(key, None)
    sys.modules.update(current_modules)
    import belmonte
    belmonte.source = current_modules['belmonte.source']
    current_track = selected.T
    current_track.R._belmonte_surfaces.cache_clear(); current_track.R._square.cache_clear()
    current_meshes, current_doc = selected.requests(current_track.Line(route))
    if current_doc != original_doc or list(current_meshes) != list(original_meshes): raise ValueError('Original railway placement/query census differs')
    projected = dict(selected.inventory(current_track.Line(route)), schema=1)
    rows = []; current_dir = args.output.parent / 'selected'; current_dir.mkdir(parents=True, exist_ok=True)
    for parent, levels in current_meshes.items():
        for k, request in enumerate(levels):
            key = f'{parent}_LOD{k}'; mesh = request.evaluate()
            if raw(mesh) != baseline[key]['raw']: raise ValueError('Original railway ordered source corners/materials differ: ' + key)
            descriptor = selected.descriptor(parent, k, projected)
            packet = selected.from_descriptor(descriptor, line_factory=lambda: current_track.Line(route))
            source = current_dir / (key + '.json'); atomic_json(source, packet)
            plan_root = current_dir / 'plans' / key; materials = current_dir / 'materials' / key
            planner.main(['--source', str(source), '--asset', key, '--output', str(plan_root), '--materials', str(materials)])
            plan = json.loads((plan_root / 'plan.json').read_text())
            actual = dict(render=Counter(), collision=Counter()); count = 0; outputs = []
            for piece in plan['pieces']:
                root = current_dir / 'exports' / piece['name']
                exporter.main(['--input', str(plan_root / piece['payload']), '--materials', str(materials / (piece['name'] + '.json')),
                    '--output', str(root), '--format', '.glb'])
                path = root / (piece['name'] + '.glb'); values, triangles = eq.glb_counter(path.read_bytes())
                for role in actual: actual[role].update(values[role])
                count += triangles; outputs.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            expected, original_count = render[key]
            if actual != expected or count != original_count: raise ValueError('Original complete GLB corner/material/frame fields differ: ' + key)
            rows.append(dict(asset=key, logical=parent, level=k, triangles=count,
                original=dict(path=str(paths[key]), sha256=hashlib.sha256(paths[key].read_bytes()).hexdigest()), selected=outputs,
                ordered_source_sha256=baseline[key]['raw']))
            print('SELECTED TRACK GLB EXACT', len(rows), '/', len(baseline), key, count, flush=True)
    for record in authority['files'].values(): checked(record)
    atomic_json(args.output, dict(schema=1, complete=True, coverage='immutable_source_and_actual_glb_fields_only',
        authority_sha256=hashlib.sha256(args.authority.read_bytes()).hexdigest(), fixture='actual_normal_natural_source_products' if authority.get('natural_source_producer') else 'private_original_natural_reader_migration',
        natural_source_producer=authority.get('natural_source_producer'),
        logical_meshes=len(original_meshes), authored_lods=len(rows), maximum_triangles=max(row['triangles'] for row in rows), rows=rows))
    print('RAILWAY SOURCE/GLB CONTROL COMPLETE', flush=True)


if __name__ == '__main__': main()
