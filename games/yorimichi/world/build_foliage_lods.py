"""Export one complete foliage asset: LOD0, authored LODs and its import manifest.

Run through ``atelier build yorimichi world.foliage.<asset>``. Each specification owns one
folder; editing another tree's seed, silhouette or distances does not change this action.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import math

import bpy
from mathutils import Vector

import asset_mesh as A
import far_crown
import foliage_geometry as F
from asset_catalog import FOLIAGE, SPEC_ROOT
from material_specs import MATERIALS
import yori


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def lod_mesh_type(original, generate, minimum, maximum, level, strides):
    """Keep the original random sequence and palette while thinning cards and small branches."""
    stride = strides[level - 1]
    roadside = generate in (F.tree_broad, F.tree_maple, F.tree_ginkgo)
    conifer = generate in (F.tree_pine, F.tree_cedar)
    tree = roadside or conifer

    class LodMesh(original):
        def __init__(self, *args):
            super().__init__(*args)
            self.card_number = 0

        def card(self, center, size, yaw, tilt, m, cell, normal, roll=0., col=1.,
                 col_bottom=None, crop=(0., 0., 1., 1.)):
            self.card_number += 1
            # The caller still draws every random value, including for dropped cards.
            if (self.card_number - 1) % stride:
                return
            cap = 3.6 if tree and level == 4 else 3.0 if roadside or (conifer and level == 3) else 2.2
            scale = min(math.sqrt(stride), cap)
            super().card(center, (size[0] * scale, size[1] * scale), yaw, tilt, m, cell, normal,
                         roll, col, col_bottom, crop)

        def quad(self, points, *args, **kwargs):
            points = [Vector(tuple(max(minimum[i], min(maximum[i], p[i])) for i in range(3))) for p in points]
            super().quad(points, *args, **kwargs)

        def tube(self, *args, **kwargs):
            if tree:
                n = kwargs.get('n', 8)
                if (level == 1 and n == 5) or (level >= 2 and n in (5, 6)) or (level == 4 and n == 8):
                    return
            kwargs['n'] = min(kwargs.get('n', 8), 5 if level == 1 else 3)
            super().tube(*args, **kwargs)

    return LodMesh


def build(name):
    spec = json.loads((SPEC_ROOT / (name + '.json')).read_text())
    import_trunk = spec['import_trunk_collision']
    if type(import_trunk) is not bool:
        raise ValueError(f'{name}: import_trunk_collision must be a boolean')
    sizes = spec['screen_sizes']
    grass = spec['generator'] == 'grass_tuft'
    if not (len(sizes) >= 2 and sizes[0] == 1 and all(a > b > 0 for a, b in zip(sizes, sizes[1:]))):
        raise ValueError(f'{name}: expected strictly decreasing screen sizes starting at 1')
    if not grass and len(spec['strides']) != len(sizes) - 1:
        raise ValueError(f'{name}: one stride is required for each distant LOD')
    crown = spec.get('far_crown')
    if crown is not None and (set(crown) != {'shape', 'screen_size'} or crown['shape'] != 'flat12'
                              or not 0 < crown['screen_size'] < sizes[-1]):
        raise ValueError(f'{name}: far_crown is {{"shape": "flat12", "screen_size": s}} with s below the last LOD')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    A.MATS.clear()
    A.LEAF_CROPS.clear()
    A.materials(spec['materials'])
    output = yori.OUT / 'foliage' / name
    output.mkdir(parents=True, exist_ok=True)
    # The folder is exclusively ours. Retire old levels when the specification gets shorter.
    for path in output.glob('*.fbx'):
        path.unlink()
    A.OUTDIR = str(output)
    original = A.Mesh
    generate = getattr(F, spec['generator'])
    base = generate(name, *spec['arguments'])
    if import_trunk and 'trunk_collision' not in base:
        raise ValueError(f'{name}: trunk collision requested without authored trunk geometry')
    minimum = Vector(tuple(min(v.co[i] for v in base.data.vertices) for i in range(3)))
    maximum = Vector(tuple(max(v.co[i] for v in base.data.vertices) for i in range(3)))
    palette = [m.name for m in base.data.materials]
    assert set(palette) == set(spec['materials']), (name, 'undeclared material', palette)
    if crown is not None:
        leaves = [m for m in palette if MATERIALS[m].get('alpha')]
        if len(leaves) != 1:
            raise ValueError(f'{name}: a far crown needs exactly one leaf material, not {palette}')
        crown_material = A.mat(far_crown.slot(name), color=(1., 1., 1.))
    report = {'triangles': [triangles(base)], 'screen_sizes': sizes + ([crown['screen_size']] if crown else []),
              'materials': palette,
              'bounds': [list(minimum), list(maximum)], 'collision': spec['collision'],
              'import_trunk_collision': import_trunk,
              'trunk_collision': list(base['trunk_collision']) if 'trunk_collision' in base else None}
    A.export(base, name, portable=True)
    try:
        for level in range(1, len(sizes)):
            lod_name = f'{name}_LOD{level}'
            if grass:
                obj = generate(lod_name, *spec['arguments'], lod=level)
            else:
                A.Mesh = lod_mesh_type(original, generate, minimum, maximum, level, spec['strides'])
                obj = generate(lod_name, *spec['arguments'])
            # The far crown is one more level past the authored chain, made from the last level's cards; every
            # authored level is unchanged. import_foliage_lods gives its slot an opaque instance and checks it.
            for crowned in ((False, True) if crown is not None and level == len(sizes) - 1 else (False,)):
                if crowned:
                    lod_name = f'{name}_LOD{level + 1}'
                    obj = generate(lod_name, *spec['arguments'])
                    report['crown'] = far_crown.replace(obj, A.MATS[leaves[0]], crown_material, (maximum - minimum).length,
                                                        far_crown.LEAF_TINTS.get(leaves[0], (1., 1., 1.)))
                count = triangles(obj)
                assert count < report['triangles'][-1], (name, lod_name, count)
                assert all(math.isfinite(c) for v in obj.data.vertices for c in v.co)
                expected = {crown_material.name} if crowned else set(palette)
                assert {m.name for m in obj.data.materials} == expected, ('LOD palette changed', name, lod_name)
                report['triangles'].append(count)
                A.export(obj, lod_name, portable=True)
                bpy.data.objects.remove(obj, do_unlink=True)
    finally:
        A.Mesh = original
    # UE's legacy FBX importer needs a first import before reimport applies all settings. Give
    # this asset its own tiny seed instead of borrowing a mesh generated by another region.
    seed = A.Mesh(name + '_Seed')
    seed.box((0, 0, .5), (1, 1, 1), A.MATS[palette[0]])
    obj = seed.build()
    A.export(obj, obj.name, portable=True)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'FOLIAGE EXPORT COMPLETE {name}: {report["triangles"]}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', choices=FOLIAGE)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    build(args.name)


if __name__ == '__main__':
    main()
