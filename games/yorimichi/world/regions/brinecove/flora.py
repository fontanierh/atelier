"""Instanced Brinecove foliage: a small library of leaf-card trees, palms and shrubs, scattered thousands of times.

The concept paintings close the headlands and the ridge behind the town with one continuous, rounded canopy. Baking
that many cards into the vegetation mesh would cost tens of millions of triangles, so each species is built once as a
prototype and placed as linked instances (EXT_mesh_gpu_instancing in the viewer). Card normals point away from the
crown centre, as on Hidamari's trees, so a crown shades as one soft mass with lit tops and darker undersides.

Plain Python: the scatter and the triangle budget can be checked without Blender.
"""
import json

from brinecove.foliage_placements import Poisson, _ridge, scatter, groundcover, bloom_spots, COVER_LIMIT

# Model geometry and model definitions are independent of placement changes.
from brinecove import foliage_models, foliage_library


def prototypes():
    return {path.stem: foliage_models.build(json.loads(path.read_text()))
            for path in foliage_library.definitions()}














def triangles(builder):
    return sum(len(f) - 2 for f in builder.faces)


if __name__ == '__main__':
    import time
    started = time.time()
    protos = prototypes()
    built = time.time()
    places = scatter() + bloom_spots(random.Random(5))
    done = time.time()
    tris = {k: triangles(v) for k, v in protos.items()}
    counts = {}
    for p in places:
        counts[p[0]] = counts.get(p[0], 0) + 1
    print('prototypes', len(protos), 'unique tris', sum(tris.values()), f'{built - started:.1f}s')
    print('placements', len(places), 'rendered tris', sum(tris[k] * n for k, n in counts.items()),
          f'{done - built:.1f}s')
    for k in sorted(counts):
        print(f'  {k:12s} {counts[k]:6d} x {tris[k]:5d}')
