"""Compare selected house constructors with the actual original regional authoring order."""
import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import runpy
import sys

import bpy
import numpy as np

GAME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory  # noqa: E402
from mesh_pieces import capture, subset  # noqa: E402


def corner_rows(source, materials, shade):
    obj = source.object(materials, shade)
    value = capture(obj.data)
    piece = subset(value, tuple(range(len(value['counts']))))
    rows = Counter()
    offset = 0
    for index, face in enumerate(piece['faces']):
        corners = []
        for local, vertex in enumerate(face):
            loop = offset + local
            corners.append((tuple(piece['positions'][vertex]), tuple(piece['normals'][loop]),
                tuple((name, tuple(uv[loop])) for name, uv in piece['uvs']),
                tuple((name, domain, kind, tuple(values[vertex if domain == 'POINT' else loop]))
                      for name, domain, kind, values in piece['colours'])))
        slot = value['slots'][int(piece['materials'][index])].name
        rows[(slot, bool(piece['smooth'][index]), tuple(corners))] += 1
        offset += len(face)
    result = dict(rows=rows, matrix=[list(row) for row in obj.matrix_world],
        colliders=[(tuple(c), tuple(s), tuple(rotation)) for c, s, rotation in source.colliders],
        vertices=len(source.vertices), polygons=len(source.faces), triangles=piece['triangles'])
    bpy.data.objects.remove(obj, do_unlink=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', required=True, type=Path)
    parser.add_argument('--heightmap', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = real_directory(args.output)
    if root.exists():
        raise ValueError('House comparison requires a fresh evidence root')
    sources = [GAME / 'world/regions/houses' / name for name in (
        'build.py', 'geometry_mesh.py', 'construction.py', 'house_a.py', 'house_b.py',
        'house_c.py', 'lots.py', 'lot_data.py', 'layout.py')]
    sources += [GAME / 'world/regions/village/mesh.py', GAME / 'world/regions/village/layout.py',
                GAME / 'world/mesh_pieces.py', Path(__file__), args.world, args.heightmap]
    def hashes():
        result = {}
        for path in sources:
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file():
                raise ValueError('House comparison input must be regular and unlinked')
            result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    before = hashes()
    world = json.loads(args.world.read_text())
    heights = np.load(args.heightmap, allow_pickle=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    original = runpy.run_path(str(GAME / 'world/regions/houses/build.py'), run_name='original_house_context')
    kernel = importlib.import_module('houses.geometry_mesh')
    lot_data = importlib.import_module('houses.lot_data')
    materials = [bpy.data.materials.new(label) for label in ('Village', 'Ground')]
    # Count the actual original uniform stream instead of guessing new per-asset seeds.
    draws = [0]
    random = original['R']
    next_random = random.random
    def counted_random():
        draws[0] += 1
        return next_random()
    random.random = counted_random
    references, offsets = {}, {}
    for key, function in [('A', 'house_a'), ('B', 'house_b'), ('C', 'house_c')]:
        name = 'House_' + key
        offsets[name] = draws[0]
        source = original['Mesh'](name)
        original[function](source)
        references[name] = corner_rows(source, materials, original['house_shade'])
    ground = original['Ground'](world, heights)
    for lot in world['houses']['lots']:
        offsets[lot['name']] = draws[0]
        references[lot['name']] = corner_rows(original['lot_mesh'](lot, ground), materials, None)
    assert len(references) == 8 and len(offsets) == 8
    results = {}
    for name, reference in references.items():
        kernel.R.seed(41)
        for _ in range(offsets[name]):
            kernel.R.random()
        if name.startswith('House_'):
            function = 'house_' + name[-1].lower()
            module = importlib.import_module('houses.' + function)
            source = kernel.Mesh(name)
            getattr(module, function)(source)
            shade = kernel.house_shade
        else:
            data = lot_data.project(world, heights, name)
            module = importlib.import_module('houses.lots')
            source = module.lot_mesh(data['lot'], lot_data.Ground(data))
            shade = None
        observed = corner_rows(source, materials, shade)
        assert observed == reference, (name, 'original geometry/corners/UVs/colors/materials/frame/collision changed')
        assert 0 < observed['triangles'] <= 32768
        results[name] = dict(seed=41, prefix_draws=offsets[name], triangles=observed['triangles'],
                             polygons=observed['polygons'], vertices=observed['vertices'])
        print('HOUSE SELECTED CONSERVATION ' + name, results[name], flush=True)
    assert hashes() == before, 'House comparison inputs changed during execution'
    root.mkdir(parents=True)
    (root / 'result.json').write_text(json.dumps(dict(complete=True, assets=results,
        exact_geometry_corner_conservation=True, native_receiving=False, inputs=before), indent=2) + '\n')
    print('HOUSE ATOMIC CONTEXT COMPLETE', flush=True)


if __name__ == '__main__':
    main()
