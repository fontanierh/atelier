"""Capture the actual immutable original Village census and per-constructor MT state."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import sys
import threading
import time
import types

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.build_cache import copy_file  # noqa: E402
from atelier.build_inputs import local_imports  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from island_atomic_equivalence import baseline_packets, captured, signature  # noqa: E402
from village import mesh as kernel  # noqa: E402
from village.catalogue import ASSETS  # noqa: E402

STAGE = ['preflight']


class PaletteReads(dict):
    def __init__(self, values):
        super().__init__(values); self.reads = set()

    def __getitem__(self, key):
        self.reads.add(key)
        return super().__getitem__(key)


def original_hull(hull):
    """Independent original-field discovery; shared split capture is deliberately unused."""
    from atelier import mesh_collision
    mesh = hull.data
    positions = np.asarray([tuple(v.co) for v in mesh.vertices], dtype='<f4')
    normals = np.asarray([tuple(value.vector) for value in mesh.corner_normals], dtype='<f4')
    materials = np.asarray([face.material_index for face in mesh.polygons], dtype='<i4')
    smooth = np.asarray([face.use_smooth for face in mesh.polygons], dtype=np.bool_)
    faces = [list(face.vertices) for face in mesh.polygons]
    uvs = [(layer.name, np.asarray([tuple(value.uv) for value in layer.data], dtype='<f4')) for layer in mesh.uv_layers]
    colours = [(layer.name, layer.domain, layer.data_type,
                np.asarray([tuple(value.color) for value in layer.data], dtype='<f4')) for layer in mesh.color_attributes]
    def selected(index):
        return mesh.color_attributes[index].name if 0 <= index < len(mesh.color_attributes) else None
    selection = dict(uv_active=mesh.uv_layers.active.name if mesh.uv_layers.active else None,
        uv_render=next((layer.name for layer in mesh.uv_layers if layer.active_render), None),
        colour_active=selected(mesh.color_attributes.active_color_index),
        colour_render=selected(mesh.color_attributes.render_color_index))
    discovered = [(a.name, a.data_type, a.domain) for a in mesh.attributes if not a.is_internal and not a.name.startswith('.')]
    known = {'position', 'material_index', 'sharp_face', 'sharp_edge', 'custom_normal'} | {n for n, _ in uvs} | {n for n, _, _, _ in colours}
    assert all(name in known for name, _, _ in discovered), 'Original hull has an unrecorded source attribute'
    slots = [slot.name for slot in mesh.materials]
    matrix = [list(row) for row in hull.matrix_world]
    transform = dict(location=list(hull.location), scale=list(hull.scale), rotation_mode=hull.rotation_mode,
        rotation_euler=list(hull.rotation_euler), rotation_quaternion=list(hull.rotation_quaternion),
        rotation_axis_angle=list(hull.rotation_axis_angle))
    piece = dict(positions=positions, normals=normals, materials=materials, smooth=smooth,
                 faces=faces, uvs=uvs, colours=colours, selection=selection)
    encoded = mesh_collision.encode(piece, slots=slots, matrix=matrix, transform=transform)
    roundtrip = mesh_collision.decode(encoded)
    assert roundtrip['faces'] == faces and roundtrip['slots'] == slots and roundtrip['selection'] == selection
    for key in ('positions', 'normals', 'materials', 'smooth'):
        assert roundtrip[key].dtype == piece[key].dtype and roundtrip[key].tobytes() == piece[key].tobytes(), key
    assert [n for n, _ in roundtrip['uvs']] == [n for n, _ in uvs]
    for (_, actual), (_, expected) in zip(roundtrip['uvs'], uvs): assert actual.tobytes() == expected.tobytes()
    assert [(n, d, k) for n, d, k, _ in roundtrip['colours']] == [(n, d, k) for n, d, k, _ in colours]
    for (_, _, _, actual), (_, _, _, expected) in zip(roundtrip['colours'], colours): assert actual.tobytes() == expected.tobytes()
    witness = dict(name=hull.name, positions=positions.tolist(), normals=normals.tolist(), faces=faces,
        materials=materials.tolist(), smooth=smooth.tolist(), material_slots=slots, selection=selection,
        uvs=[(n, v.tolist()) for n, v in uvs], colours=[(n, d, k, v.tolist()) for n, d, k, v in colours],
        matrix=matrix, transform=transform, discovered_attributes=discovered)
    return encoded, witness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    donor = real_directory(args.donor); output = real_directory(args.output)
    if output.exists(): raise ValueError('Village context requires fresh evidence')
    inputs = {name: donor / name for name in ('world.json', 'heightmap.npy')}
    fixture = Path(__file__).with_name('village-predecessor-283329c07.txt')
    original = fixture.read_bytes()
    assert hashlib.sha256(original).hexdigest() == 'a9d4eb65222740c2ad31aa1eef6aa5630ad328bea3c527f8fc94527d16f90409', 'Immutable Village predecessor differs'
    source = GAME / 'world/regions/village/build.py'
    # Geometry constructors and the narrow kernel remain unchanged at this boundary.
    # The immutable snapshot, not current main(), drives the complete original census.
    code = set(local_imports(source, (GAME / 'world', GAME / 'world/regions')))
    code.update((Path(__file__), fixture, Path(__file__).with_name('island_atomic_equivalence.py')))
    def identities():
        values = {}
        for path in sorted(code | set(inputs.values())):
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Nonregular Village proof input')
            st = path.stat()
            values[str(path)] = dict(sha256=sha(path), stat=[st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns])
        return values
    before = identities()
    for key, path in inputs.items():
        target = output / 'data' / key; target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(path, target); assert sha(target) == before[str(path)]['sha256']
    yori.OUT = output / 'data'
    tree = ast.parse(original.decode())
    original_main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    boundary = original.decode().splitlines().index('    # A usable modelling scene: actual layout, separated editable mesh assets.') + 1
    original_main.body = [node for node in original_main.body if node.lineno < boundary]
    tree.body = [node for node in tree.body if not (isinstance(node, ast.If) and node.lineno > boundary)]
    module = types.ModuleType('village_immutable_original')
    module.__file__ = str(fixture); sys.modules[module.__name__] = module
    exec(compile(tree, str(fixture), 'exec'), module.__dict__)
    assert kernel.R.getstate() == random.Random(76).getstate(), 'Original Village did not begin on its fresh seed'
    pending = [json.loads(json.dumps(kernel.R.getstate()))]
    contexts, census, references = {}, {}, {}
    source_palette = dict(kernel.PALETTE)
    palette = PaletteReads(source_palette)
    kernel.PALETTE = module.PALETTE = palette
    original_export = module.export
    from atelier.blender import fbx
    original_fbx = fbx.export_fbx
    captured_hulls, hull_witnesses = [], []
    def observe_fbx(**options):
        pairs = [original_hull(obj) for obj in bpy.context.selected_objects
                 if obj.type == 'MESH' and obj.name.startswith('UCX_')]
        captured_hulls[:] = [row[0] for row in pairs]; hull_witnesses[:] = [row[1] for row in pairs]
        return original_fbx(**options)
    def observe(m, material):
        key = m.name
        assert key in ASSETS and key not in contexts, 'Foreign or duplicate original Village owner'
        STAGE[0] = 'immutable original ' + key
        assert kernel.PALETTE == source_palette, 'Village predecessor changed a sibling palette'
        contexts[key] = dict(state=pending[0], palette_keys=sorted(palette.reads))
        after = kernel.R.getstate()
        obj, info = original_export(m, material)
        assert kernel.R.getstate() == after, 'Original export unexpectedly consumes the geometry RNG'
        pending[0] = json.loads(json.dumps(after))
        data = captured(obj); matrix = [list(row) for row in obj.matrix_world]
        assert len(captured_hulls) == len(m.colliders), 'Original whole hull capture is incomplete'
        packets = baseline_packets(data, output / 'baseline' / key, key, matrix,
            options=dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
                         axis_up='Z', mesh_smooth_type='FACE', use_custom_props=False), collisions=captured_hulls)
        references[key] = dict(signature=signature(data), packets=packets, matrix=matrix)
        atomic_json(output / 'original-hulls' / (key + '.json'), dict(complete=True, hulls=hull_witnesses))
        census[key] = dict(source_triangles=info['triangles'], polygons=len(data['counts']),
                           collision_hulls=len(m.colliders), exported=True)
        print('ORIGINAL VILLAGE CONTEXT ' + key + ' ' + str(info['triangles']), flush=True)
        palette.reads.clear()
        return obj, info
    module.export = observe
    STAGE[0] = 'complete immutable original Village production order'
    fbx.export_fbx = observe_fbx
    try: module.main()
    finally: fbx.export_fbx = original_fbx
    assert tuple(contexts) == ASSETS and set(census) == set(ASSETS)
    assert identities() == before, 'Village source or donor changed during census'
    atomic_json(output / 'contexts.json', dict(schema=1, seed=76, complete=True,
        predecessor_sha256=hashlib.sha256(original).hexdigest(), contexts=contexts,
        provenance=dict(world_sha256=sha(output / 'data/world.json'), heightmap_sha256=sha(output / 'data/heightmap.npy'))))
    atomic_json(output / 'baseline-signatures.json', references)
    atomic_json(output / 'baseline-census.json', dict(complete=True, groups={'village': ['world.village']},
        owners={'world.village': dict(models=list(ASSETS), captures=census)}))
    atomic_json(output / 'result.json', dict(complete=True, sources=before, census=census,
        scope='actual immutable original source/context capture only; current atomic/native equivalence remains separate'))
    print('VILLAGE ORIGINAL CONTEXT COMPLETE', flush=True)


if __name__ == '__main__':
    done = threading.Event(); started = time.monotonic()
    def heartbeat():
        while not done.wait(25): print(f'Village original context {time.monotonic()-started:.0f}s: {STAGE[0]}; no additional completed stage', flush=True)
    thread = threading.Thread(target=heartbeat, daemon=True); thread.start()
    try: main()
    finally: done.set(); thread.join(timeout=1)
