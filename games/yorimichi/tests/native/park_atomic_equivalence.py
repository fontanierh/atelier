"""Bounded real-source conservation against explicit immutable predecessor scripts.

Run under the ordinary guarded Blender launcher. This does not import Unreal or
claim native package acceptance. The baseline files and donor geometry/font are
explicit inputs, recorded by SHA; no source history is executed by production.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GAME / 'world'), str(GAME / 'world/regions'), str(Path(__file__).resolve().parent)]
import yori  # noqa: E402,F401
from megapark import build as mega, atomic_common, plan_asset as mega_plan  # noqa: E402
from craterpark.v2 import export as crater, atomic_inputs, dsl, plan_asset as crater_plan  # noqa: E402
from craterpark import placement  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from mesh_pieces import capture  # noqa: E402
from region_mesh_parts import plan, validate  # noqa: E402
import export_region_piece  # noqa: E402
import fbx_corners  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def identity(values):
    digest = hashlib.sha256()
    def add(value):
        if value is None:
            digest.update(b'none')
        elif isinstance(value, dict):
            for key in sorted(value):
                add(key); add(value[key])
        elif isinstance(value, str):
            digest.update(value.encode() + b'\0')
        elif isinstance(value, (tuple, list)) and value and isinstance(value[0], str):
            for item in value:
                add(item)
        else:
            a = np.asarray(value)
            digest.update(str(a.dtype).encode() + str(a.shape).encode() + a.tobytes())
    for value in values:
        add(value)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mega-baseline', type=Path, required=True)
    parser.add_argument('--crater-baseline', type=Path, required=True)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    root = args.output.resolve()
    if root.exists() or root.is_symlink():
        raise ValueError('Proof output must be fresh')
    root.mkdir(parents=True)
    watched = [args.mega_baseline, args.crater_baseline, args.geometry, args.font,
               mega.SOURCE / 'map.json', *sorted((mega.SOURCE / 'geometry').glob('*.npz')),
               *sorted((mega.SOURCE / 'collision').glob('*.npz'))]
    baseline_revision = '283329c07'
    baseline_files = {args.mega_baseline: 'games/yorimichi/world/regions/megapark/build.py',
                      args.crater_baseline: 'games/yorimichi/world/regions/craterpark/v2/export.py'}
    for file, relative in baseline_files.items():
        immutable = subprocess.check_output(['git','show',baseline_revision+':'+relative],cwd=GAME.parents[1])
        if file.read_bytes() != immutable:
            raise ValueError('Diagnostic baseline does not match immutable source: '+relative)
    closure = set()
    for script in (Path(mega.__file__), Path(crater.__file__), Path(atomic_inputs.__file__),
                   Path(export_region_piece.__file__), Path(__file__)):
        closure.update(local_imports(script, (GAME/'world',GAME/'world/regions')))
    watched.extend(sorted(closure))
    before = {str(p): dict(sha256=sha(p), size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in watched}
    old = load('immutable_mega_predecessor', args.mega_baseline)
    old.SOURCE = mega.SOURCE; old.OUT = root / 'mega-old'; old.OUT.mkdir()
    font = old.OUT / mega.sign.BLACK; font.parent.mkdir(parents=True); shutil.copyfile(args.font, font)
    mega.OUT = old.OUT
    original_export = old.export_mesh
    old_calls = {}; originals = {}; old_entries = {}
    def collect(name, vertices, faces, materials, face_materials, channels=None, normals=None):
        key = identity((vertices, faces, materials, np.asarray(face_materials, 'i4'), channels, normals))
        old_calls[name] = key
        originals[name] = (np.asarray(vertices).copy(), np.asarray(faces).copy(), materials,
                           np.asarray(face_materials, 'i4'), channels, normals)
        origin = np.round((vertices.min(0).astype('f8') + vertices.max(0))/2/32)*32
        entry = dict(name=name, fbx='fbx/'+name+'.fbx', sha256='diagnostic', native_origin=origin.tolist(),
                    bounds=dict(minimum=vertices.min(0).tolist(), maximum=vertices.max(0).tolist()),
                    vertices=len(vertices), triangles=len(faces), materials=materials)
        old_entries[name] = entry
        return entry
    old.export_mesh = collect
    old.write_island = lambda report: None  # Not a geometry producer; runtime roster is tested separately.
    old.main()
    source = json.loads((mega.SOURCE / 'map.json').read_text())
    letters = old.letters()
    letters_input = root / 'letters-data.npz'
    np.savez(letters_input, **dict(zip(('vertices','faces','normals','uv'),letters)))
    new_calls = {}; model_entries = []
    def compare(*values):
        name = values[0]
        padded = list(values[1:]) + [None] * (6-len(values[1:]))
        padded[3] = np.asarray(padded[3], 'i4')
        actual = identity(tuple(padded))
        if actual != old_calls[name]:
            raise AssertionError(('selected constructor changed source', name))
        new_calls[name] = actual
        return collect(*values)
    report = dict(materials={}, foliage_only=[])
    for model in source['models']:
        entry = mega.model_geometry(source, model, letters, report, entry_mesh=compare)
        if entry:
            model_entries.append(entry)
    for section in source['collision']:
        mega.collision_geometry(section, letters, entry_mesh=compare)
    mega.export_seam(source, report, entry_mesh=compare)
    assert set(new_calls) == set(old_calls) - {'SM_MP_ImportSeed'}
    print('MEGA SOURCE CONSERVATION', len(new_calls), 'logical meshes', flush=True)
    # Compare actual predecessor FBX corners to the complete independent exporter union.
    candidates = [old_entries[key] for key in sorted(old_entries)]
    native_metrics = []
    for entry in candidates:
        key = entry['name']; values = originals[key]
        old.OUT = root / 'controls'; (old.OUT / 'fbx').mkdir(parents=True, exist_ok=True)
        original_export(key, *values)
        planned = root / 'plans' / key
        mega_plan.main(['--asset',key,'--letters',str(letters_input),
                        '--metadata',str(root/'mega-metadata'/(key+'.json')),'--output',str(planned)])
        value = validate(planned)
        combined = dict(render=Counter(), collision=Counter())
        for row in value['pieces']:
            product = root / 'exports' / row['name']
            export_region_piece.main(['--input', str(planned / row['payload']), '--output', str(product)])
            actual = fbx_corners.read(product / (row['name'] + '.fbx'))
            for kind in combined:
                combined[kind].update(actual[kind])
        expected = fbx_corners.read(old.OUT / 'fbx' / (key + '.fbx'))
        assert fbx_corners.polygon_cycles(combined) == fbx_corners.polygon_cycles(expected), key
        native_metrics.append(dict(name=key, triangles=entry['triangles'], pieces=len(value['pieces']),
                                   max_piece=max(r['triangles'] for r in value['pieces'])))
        print('MEGA FBX CORNER CONSERVATION', native_metrics[-1], flush=True)
    old_cp = load('immutable_crater_predecessor', args.crater_baseline)
    # The exact same selected design is required by both original and production admission.
    old_cp.v4_config = crater.v4_config
    with np.load(args.geometry, allow_pickle=False) as geometry:
        old_cp_calls = {}
        def cp_collect(out, name, vertices, faces, materials, face_materials, uvs=None, normals=None, ao=None):
            old_cp_calls[name] = identity((vertices, faces, materials, np.asarray(face_materials,'i4'), uvs, normals, ao))
            return dict(name=name, fbx='fbx/'+name+'.fbx', sha256='diagnostic',
                native_origin=old_cp.origin_of(vertices[np.unique(faces)]).tolist(),
                bounds=dict(minimum=vertices[np.unique(faces)].min(0).tolist(),maximum=vertices[np.unique(faces)].max(0).tolist()),
                vertices=len(vertices), triangles=len(faces), materials=list(materials))
        old_cp.write(root / 'cp-old', placement.SOURCE, geometry, placement, entry_mesh=cp_collect)
    projected = root / 'crater-inputs'
    inventory = atomic_inputs.project(args.geometry, projected)
    render = []
    for row in inventory['assets']:
        if row['kind'] != 'render':
            continue
        with np.load(projected / row['packet']) as data:
            spec = json.loads(str(data['spec'])); mesh = dsl.Mesh.from_arrays(data, 'm_')
            keys = np.unique(mesh.material)
            value = identity((mesh.V, mesh.F, [dsl.MATERIALS[int(m)] for m in keys],
                              np.searchsorted(keys, mesh.material).astype('i4'), mesh.UV, mesh.N, mesh.AO))
            assert value == old_cp_calls[row['name']], row['name']
            render.append((len(mesh.F), row['name']))
    print('CRATER SOURCE CONSERVATION', len(render), sum(r[0] for r in render), flush=True)
    crater_fbx = []
    for count, key in sorted(render, reverse=True):
        with np.load(projected / (key + '.npz')) as packet:
            mesh = dsl.Mesh.from_arrays(packet, 'm_')
            slots = np.unique(mesh.material)
            values = (key, mesh.V, mesh.F, [dsl.MATERIALS[int(m)] for m in slots],
                      np.searchsorted(slots, mesh.material), mesh.UV, mesh.N, mesh.AO)
            control = root / 'cp-controls'; (control / 'fbx').mkdir(parents=True, exist_ok=True)
            old_cp.export_mesh(control, *values)
            planned = root / 'cp-plans' / key
            crater_plan.main(['--input',str(projected/(key+'.npz')),
                              '--metadata',str(root/'cp-metadata'/(key+'.json')),'--output',str(planned)])
            value = validate(planned)
            combined = dict(render=Counter(), collision=Counter())
            for row in value['pieces']:
                product = root / 'cp-exports' / row['name']
                export_region_piece.main(['--input', str(planned / row['payload']), '--output', str(product)])
                decoded = fbx_corners.read(product / (row['name'] + '.fbx'))
                for kind in combined:
                    combined[kind].update(decoded[kind])
            expected = fbx_corners.read(control / 'fbx' / (key + '.fbx'))
            assert fbx_corners.polygon_cycles(combined) == fbx_corners.polygon_cycles(expected), key
            crater_fbx.append(dict(name=key, triangles=count, pieces=len(value['pieces'])))
            print('CRATER FBX CORNER/AO CONSERVATION', crater_fbx[-1], flush=True)
    # Full CP packet/collision face byte equality is verified against original complete outputs.
    with np.load(args.geometry) as original:
        index = json.loads(str(original['index']))
        for i, spec in enumerate(index['collision']):
            chunks = []
            for row in inventory['assets']:
                if row['kind'] == 'collision' and (row['name'] == spec['name'] or row['name'].startswith(spec['name']+'_Piece')):
                    with np.load(projected / row['packet']) as packet:
                        chunks.append(packet['triangles'])
            assert np.array_equal(np.concatenate(chunks), original[f'c{i}'])
    crater_collision_fbx = []
    with np.load(args.geometry) as original:
        index = json.loads(str(original['index']))
        for i,spec in enumerate(index['collision']):
            parent=spec['name']; triangles=np.asarray(original[f'c{i}'],'f8')
            vertices=triangles.reshape(-1,3)
            control=root/'cp-collision-controls';(control/'fbx').mkdir(parents=True,exist_ok=True)
            entry=old_cp.export_mesh(control,parent,vertices,np.arange(len(vertices)).reshape(-1,3),
                                     ['M_Collision'],np.zeros(len(triangles),'i4'))
            combined=dict(render=Counter(),collision=Counter()); children=[]
            for asset in inventory['assets']:
                if asset['kind']!='collision' or not (asset['name']==parent or asset['name'].startswith(parent+'_Piece')):
                    continue
                key=asset['name'];planned=root/'cp-collision-plans'/key
                metadata=root/'cp-collision-metadata'/(key+'.json')
                crater_plan.main(['--input',str(projected/asset['packet']),'--metadata',str(metadata),'--output',str(planned)])
                assert json.loads(metadata.read_text())['entry']['native_origin']==entry['native_origin']
                value=validate(planned)
                for row in value['pieces']:
                    product=root/'cp-collision-exports'/row['name']
                    export_region_piece.main(['--input',str(planned/row['payload']),'--output',str(product)])
                    decoded=fbx_corners.read(product/(row['name']+'.fbx'))
                    for kind in combined:
                        combined[kind].update(decoded[kind])
                    children.append(row['name'])
            expected=fbx_corners.read(control/'fbx'/(parent+'.fbx'))
            assert fbx_corners.polygon_cycles(combined)==fbx_corners.polygon_cycles(expected),parent
            crater_collision_fbx.append(dict(name=parent,triangles=len(triangles),pieces=len(children),children=children))
            print('CRATER COLLISION FBX CORNER CONSERVATION',crater_collision_fbx[-1],flush=True)
    after = {str(p): dict(sha256=sha(p), size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in watched}
    assert before == after, 'Donor source changed during proof'
    result = dict(complete=True, baseline_revision=baseline_revision, baseline_files={str(k):v for k,v in baseline_files.items()}, original_inputs=before, mega_logical=len(new_calls),
                  mega_fbx=native_metrics, crater_fbx=crater_fbx, crater_collision_fbx=crater_collision_fbx, crater_logical=len(render), crater_triangles=sum(n for n,_ in render),
                  crater_max=max(n for n,_ in render), projected_assets=len(inventory['assets']))
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PARK ATOMIC EQUIVALENCE COMPLETE', result['mega_logical'], result['crater_logical'], flush=True)


if __name__ == '__main__':
    main()
