"""Actual immutable island predecessor versus atomic source and serialized corner union."""
import argparse
import ast
from collections import Counter
import gc
import hashlib
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
import yori  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.blender.fbx import export_fbx  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from fbx_face_digests import read as exported  # noqa: E402
from mesh_pieces import capture  # noqa: E402
from mesh_pieces import subset  # noqa: E402
from plan_terrain import construct, OPTIONS, plan_selected, CELL_METRES  # noqa: E402
from terrain_product import load  # noqa: E402
from terrain_sources import ASSETS, project  # noqa: E402
import export_region_piece  # noqa: E402

STAGE = ['input preflight']


def captured(obj):
    data = capture(obj.data)
    data['slots'] = [material.name for material in data['slots']]
    return data


def signature(data):
    def arr(value):
        return (str(value.dtype), value.shape, hashlib.sha256(value.tobytes()).hexdigest())
    value = {key: arr(item) for key, item in data.items() if isinstance(item, np.ndarray)}
    value.update(slots=data['slots'], selection=data['selection'],
                 uvs=[(name, arr(values)) for name, values in data['uvs']],
                 colours=[(name, domain, kind, arr(values)) for name, domain, kind, values in data['colours']])
    return value


def baseline_packets(data, directory, key, matrix, *, options=None, collisions=()):
    """Persist EVERY immutable-original polygon in contiguous bounded source packets.

    Baseline membership does not use the new spatial partitioner. The independent
    cross-region harness reconstructs its complete corner Counter itself.
    """
    directory.mkdir(parents=True)
    groups = []; members = []; triangles = 0
    for face, count in enumerate(data['counts']):
        size = int(count) - 2
        if size > 32768: raise ValueError('Unbounded original source polygon')
        if members and triangles + size > 32768:
            groups.append(members); members = []; triangles = 0
        members.append(face); triangles += size
    if members: groups.append(members)
    rows = []
    for index, members in enumerate(groups):
        name = key + '_Source' + str(index).zfill(4)
        path = directory / (name + '.npz')
        piece = subset(data, members)
        mesh_ir.write(path, mesh_ir.encode(piece, key=name, slots=data['slots'], matrix=matrix,
                                           options=OPTIONS if options is None else options,
                                           collisions=collisions if index == 0 else ()))
        rows.append(dict(path=path.name, sha256=sha(path), triangles=piece['triangles']))
    assert sum(row['triangles'] for row in rows) == int(sum(data['counts'] - 2))
    return rows


def verify_piece(reference, row, piece):
    members = np.asarray(row['source_faces'])
    starts, counts = reference['starts'][members], reference['counts'][members]
    loops = np.concatenate([np.arange(a, a+n) for a, n in zip(starts, counts)])
    expected_vertices = reference['vertex_indices'][loops]
    actual_vertices = np.asarray([i for face in piece['faces'] for i in face])
    assert np.array_equal(reference['positions'][expected_vertices], piece['positions'][actual_vertices])
    assert np.array_equal(reference['normals'][loops], piece['normals'])
    assert np.array_equal(counts, [len(f) for f in piece['faces']])
    assert np.array_equal(reference['materials'][members], piece['materials'])
    assert np.array_equal(reference['smooth'][members], piece['smooth'])
    assert reference['selection'] == piece['selection'] and reference['slots'] == piece['slots']
    assert [name for name, _ in reference['uvs']] == [name for name, _ in piece['uvs']]
    for (_, expected), (_, current) in zip(reference['uvs'], piece['uvs']):
        assert np.array_equal(expected[loops], current)
    assert [(n, d, k) for n, d, k, _ in reference['colours']] == [(n, d, k) for n, d, k, _ in piece['colours']]
    for (_, domain, _, expected), (_, _, _, current) in zip(reference['colours'], piece['colours']):
        assert np.array_equal(expected[expected_vertices if domain == 'POINT' else loops],
                              current[actual_vertices] if domain == 'POINT' else current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--assets', nargs='+', choices=ASSETS, default=list(ASSETS))
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    donor = real_directory(args.donor)
    root = real_directory(args.output)
    if root.exists(): raise ValueError('Equivalence evidence requires a fresh root')
    paths = ('world.json', 'heightmap.npy', 'terrain/FarHills/final.npz', 'terrain/FarHills/natural.npz',
             'terrain/FarHills/manifest.json', 'hidamari/city.json',
             'textures/T_ground.jpg', 'textures/T_road.jpg', 'textures/T_water.jpg')
    originals = [donor / name for name in paths]
    def identities():
        result = {}
        for path in originals:
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Nonregular donor input')
            st = path.stat()
            result[str(path)] = dict(sha256=sha(path), stat=[st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns])
        return result
    before = identities()
    code = set(local_imports(GAME / 'world/plan_terrain.py', (GAME / 'world', GAME / 'world/regions')))
    code.update((Path(__file__), GAME / 'tests/native/fbx_face_digests.py',
                 GAME / 'tests/native/fbx_corners.py', Path(mesh_ir.__file__),
                 GAME / 'world/export_region_piece.py', GAME / 'assets/vehicles/belmonte-train/line.json',
                 GAME / 'tests/fixtures/island-terrain-predecessor-283329c07.txt'))
    source_hashes = {str(path): sha(path) for path in sorted(code)}
    for name in paths:
        target = root / 'data' / name; target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(donor / name, target)
        assert sha(target) == before[str(donor / name)]['sha256']
    yori.OUT = root / 'data'; yori.TEXTURES = yori.OUT / 'textures'
    fixture = GAME / 'tests/fixtures/island-terrain-predecessor-283329c07.txt'
    text = fixture.read_text()
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == 'c00634b7dadc6ff98fe87ee4759f3a471dbe24cdf4c0c3d935fa835f6f9d6108'
    tree = ast.parse(text)
    main_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    boundary = text.splitlines().index('    # export terrain fbx') + 1
    # Retain the immutable complete construction statements, excluding only actual exports.
    sea = [n for n in main_fn.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'sea' for t in n.targets)]
    sea_data = [n for n in main_fn.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Tuple) and any(isinstance(x, ast.Name) and x.id == 'sea_vertices' for x in t.elts)
        for t in n.targets)]
    main_fn.body = [n for n in main_fn.body if n.lineno < boundary] + sea_data + sea
    scope = dict(__file__=str(fixture), __name__='island_immutable_predecessor')
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Name) and n.value.func.id == 'main')]
    STAGE[0] = 'immutable original complete island construction'
    exec(compile(tree, str(fixture), 'exec'), scope)
    scope['main']()
    references, controls, frames, baseline = {}, {}, {}, {}
    for key in args.assets:
        STAGE[0] = 'original capture and FBX ' + key
        obj = bpy.data.objects[key]
        references[key] = captured(obj)
        frames[key] = [list(row) for row in obj.matrix_world]
        baseline[key] = baseline_packets(references[key], root / 'baseline' / key, key, frames[key])
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        path = root / (key + '-whole-control.fbx')
        export_fbx(filepath=str(path), use_selection=True, object_types={'MESH'}, bake_anim=False, **OPTIONS)
        controls[key] = exported(path)
        print('ISLAND ORIGINAL CONTROL ' + key, flush=True)
    source = project(json.loads((yori.OUT / 'world.json').read_text()), city=True)
    heightmap = np.load(yori.OUT / 'heightmap.npy', allow_pickle=False)
    final = load(yori.OUT / 'terrain/FarHills/final.npz', owner='FarHills', stage='final', city=True)
    results = {}
    for key in args.assets:
        STAGE[0] = 'selected original constructor ' + key
        obj = construct(key, source[key], heightmap=heightmap if key in ('Terrain', 'Lane') else None,
                        final=final if key == 'FarHills' else None)
        actual = captured(obj)
        assert [list(row) for row in obj.matrix_world] == frames[key], (key, 'authored frame changed')
        assert signature(actual) == signature(references[key]), (key, 'ordered source channels differ')
        del actual
        value = plan_selected(obj, root / 'plans' / key)
        observed = dict(render=Counter(), collision=Counter())
        for index, row in enumerate(value['pieces'], 1):
            STAGE[0] = f'atomic {key} {index}/{len(value["pieces"])}'
            payload = root / 'plans' / key / row['payload']
            _, piece = mesh_ir.decode(payload.read_bytes())
            verify_piece(references[key], row, piece)
            output = root / 'exports' / row['name']
            export_region_piece.main(['--input', str(payload), '--output', str(output)])
            for kind, rows in exported(output / (row['name'] + '.fbx')).items(): observed[kind].update(rows)
            del piece
            print(f'ISLAND ATOMIC {key} {index}/{len(value["pieces"])}', flush=True)
        assert observed == controls[key], (key, 'serialized complete corner/material/UV/color/frame union changed')
        results[key] = dict(triangles=value['source_triangles'], polygons=value['source_polygons'],
                            pieces=len(value['pieces']), max_triangles=max(r['triangles'] for r in value['pieces']),
                            baseline_packets=baseline[key], actual_packets=[dict(path=row['payload'], sha256=row['sha256'])
                                for row in value['pieces']])
        del references[key], controls[key], observed
        gc.collect()
    assert identities() == before, 'Donor source identity changed during canary'
    assert {str(path): sha(path) for path in sorted(code)} == source_hashes, 'Canary source changed during execution'
    atomic_json(root / 'baseline-census.json', dict(complete=set(args.assets) == set(ASSETS),
        groups={'island': ['world.terrain']}, owners={'world.terrain': dict(models=args.assets,
            captures={key: dict(source_triangles=row['triangles'], exported=True) for key, row in results.items()})}))
    atomic_json(root / 'result.json', dict(complete=True, predecessor_sha256=sha(fixture), inputs=before,
        source_hashes=source_hashes, cells={key: CELL_METRES.get(key, 128.) for key in args.assets},
        assets=results, exact_source_channels=True, exact_piece_channel_union=True,
        numeric_exported_polygon_union=True,
        scope='original island and canonical final FarHills source/export parity; native seam/traversal not exercised'))
    print('ISLAND ATOMIC EQUIVALENCE COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25):
            print(f'Island equivalence {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: main()
    finally: done.set(); thread.join(timeout=1)
