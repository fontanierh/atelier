"""The Mega Park's plants: the original desert trees, cacti and shrubs, and the island trees that replace them.

Pure NumPy. The original plants are camera-facing cards; the park build leaves their render parts out, and the park
actor plants the island's own trees and bushes where they stood (docs/MEGAPARK.md, "Restyle"). The replacements have
no collision, so the riding surfaces are untouched.
"""
import math
from functools import lru_cache

import numpy as np

from megapark import placement

# Diffuse texture -> the original plant it draws. Trunks belong to the poplar crowns above them.
FOLIAGE = {
    '0x2c70170a001d00b1': 'longtree', '0x2c70170a001d010a': 'poplar', '0x00007dc203e3870a': 'poplar',
    '0x00007dc403e3870a': 'trunk', '0x2c70170a001d00b2': 'shrub', '0x00007e1c03e3870a': 'shrubpot',
    '0x00007e3203e3870a': 'birch', '0x2c70170a00053a88': 'treewall', '0x2c70170a00060004': 'ocotillo',
    '0x2c70170a00060005': 'saguaro', '0x2c70170a00060003': 'saguaro',
}
# Cards of one plant: centres closer than this in plan (metres) with overlapping heights.
LINK = {'longtree': 2.6, 'poplar': 2.0, 'birch': 1.0, 'shrub': 1.2, 'shrubpot': 1.5, 'ocotillo': 1.0, 'saguaro': .8,
        'treewall': 3.0}

# Island meshes (/Game/Japan/Assets): height and crown radius in metres at scale 1 (world/build_assets.py; the tall
# canopy trees are the tree house's, treehouse/trees.py). All are the detailed leaf-card kind the island uses where the
# player gets close; the painted-card _lo trees are for the far forest.
MESHES = {
    'Tree_Maple_A': (6.5, 3.0), 'Tree_Maple_B': (5.2, 2.3), 'Tree_Ginkgo': (9.0, 2.2), 'Tree_Broad_A': (8.5, 2.3),
    'Tree_Broad_B': (7.0, 1.9), 'Tree_Broad_C': (10., 2.7), 'Tree_Pine_A': (13.0, 2.6), 'Tree_Pine_B': (11.0, 2.4),
    'Tree_Cedar_B': (13.0, 2.2), 'Tree_Canopy_Maple': (16.4, 4.5), 'Tree_Canopy_Crimson': (15.2, 4.3),
    'Tree_Canopy_Amber': (17.6, 4.2), 'Tree_Canopy_Ginkgo': (18.5, 3.3), 'Bush_Ochre_A': (1.5, 1.5),
    'Bush_Ochre_B': (1.1, 1.1), 'Bush_Green_A': (1.4, 1.4), 'Bush_Green_B': (1.0, 1.0), 'Bush_Flower_A': (1.2, 1.2),
}
# Original plant -> (mesh, weight) choices and the scale range. The rock rims get pines, cedars and broadleaves like the
# forest round the park; the groves and canyons get the painted maples and ginkgos; the shrubs become bushes. A tree
# TALL metres or more becomes one of the tall canopy trees, or a big conifer.
CHOICES = {
    'longtree': ([('Tree_Pine_B', 3), ('Tree_Cedar_B', 2), ('Tree_Broad_C', 2), ('Tree_Broad_A', 2), ('Tree_Maple_A', 1),
                  ('Tree_Pine_A', 1)], (.9, 2.2)),
    'poplar': ([('Tree_Maple_A', 4), ('Tree_Maple_B', 2), ('Tree_Ginkgo', 3), ('Tree_Broad_A', 1), ('Tree_Broad_B', 1)], (.8, 2.0)),
    'treewall': ([('Tree_Cedar_B', 2), ('Tree_Pine_B', 1)], (1., 1.4)),
    'birch': ([('Tree_Ginkgo', 1)], (.7, 1.0)),
    'ocotillo': ([('Tree_Maple_B', 3), ('Bush_Ochre_A', 2), ('Tree_Maple_A', 1)], (.7, 1.2)),
    'saguaro': ([('Bush_Ochre_A', 2), ('Bush_Green_A', 2), ('Tree_Maple_B', 1)], (.8, 1.6)),
    'shrub': ([('Bush_Ochre_A', 3), ('Bush_Ochre_B', 2), ('Bush_Green_A', 2), ('Bush_Green_B', 1), ('Bush_Flower_A', 1)], (.9, 2.2)),
    'shrubpot': ([('Bush_Flower_A', 1)], (1.2, 1.6)),
}
TALL = 12.
TALL_CHOICES = ([('Tree_Canopy_Maple', 3), ('Tree_Canopy_Crimson', 3), ('Tree_Canopy_Amber', 2), ('Tree_Canopy_Ginkgo', 2),
                 ('Tree_Pine_A', 1), ('Tree_Cedar_B', 1)], (.8, 1.6))
SINK = .3           # metres the trunk base goes under the original card base, so slopes never show a gap


def is_foliage(part):
    return part.get('retail_texture_ids', {}).get('diffuse') in FOLIAGE


def _components(v, f):
    """Connected card groups of one mesh part (vertices welded at 1 cm): a list of vertex index arrays."""
    key = np.round(v / .01).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    parent = np.arange(weld.max() + 1)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for a, b, c in weld[f]:
        ra = find(a); parent[find(b)] = ra; parent[find(c)] = ra
    root = np.array([find(i) for i in weld])
    face_root = root[f[:, 0]]
    return [np.unique(f[face_root == r]) for r in np.unique(face_root)]


@lru_cache(maxsize=1)
def plants():
    """The original plants of the kept park: dicts with kind, base (native x, y, z of the trunk foot), height and
    radius (metres). Card groups of one kind are joined when close in plan with overlapping heights."""
    models, _ = placement.kept()
    groups = []
    for model in models:
        with np.load(placement.SOURCE / model['npz'], allow_pickle=False) as arrays:
            for part in model['meshes']:
                kind = FOLIAGE.get(part.get('retail_texture_ids', {}).get('diffuse'))
                if kind is None or kind == 'trunk':
                    continue
                i = part['index']; v = arrays[f'vertices_{i}'].astype('f8'); f = arrays[f'faces_{i}']
                if not len(f):
                    continue
                for sel in _components(v, f):
                    q = v[sel]
                    low = q[:, 1].min()
                    foot = q[q[:, 1] < low + .6]
                    groups.append({'kind': kind, 'lo': low, 'hi': q[:, 1].max(), 'foot': foot[:, [0, 2]].mean(0),
                                   'centre': q[:, [0, 2]].mean(0),
                                   'r': float(np.linalg.norm(q[:, [0, 2]] - q[:, [0, 2]].mean(0), axis=1).max())})
    result = []
    for kind in sorted(LINK):
        G = [g for g in groups if g['kind'] == kind]
        if not G:
            continue
        n = len(G); C = np.array([g['centre'] for g in G]); lo = np.array([g['lo'] for g in G]); hi = np.array([g['hi'] for g in G])
        parent = np.arange(n)

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]; i = parent[i]
            return i
        d = np.linalg.norm(C[:, None] - C[None], axis=-1)
        overlap = np.minimum(hi[:, None], hi[None]) - np.maximum(lo[:, None], lo[None]) > -3
        for a, b in zip(*np.nonzero(np.triu((d < LINK[kind]) & overlap, 1))):
            parent[find(b)] = find(a)
        root = np.array([find(i) for i in range(n)])
        for r in np.unique(root):
            members = [G[i] for i in np.flatnonzero(root == r)]
            low = min(g['lo'] for g in members)
            foot = np.mean([g['foot'] for g in members if g['lo'] < low + 1.], 0)
            centre = np.mean([g['centre'] for g in members], 0)
            result.append({'kind': kind, 'base': [float(foot[0]), float(low), float(foot[1])],
                           'height': float(max(g['hi'] for g in members) - low),
                           'radius': float(max(np.linalg.norm(g['centre'] - centre) + g['r'] for g in members))})
    return result


def trees(seed=11):
    """The replacements: {mesh: [[x, y, z, yaw, scale], ...]} with x, y, z the native trunk foot in metres (y up)."""
    rng = np.random.default_rng(seed)
    out = {}
    for plant in plants():
        options, (smin, smax) = TALL_CHOICES if plant['kind'] in ('longtree', 'poplar') and plant['height'] >= TALL \
            else CHOICES[plant['kind']]
        names = [n for n, _ in options]; weights = np.array([w for _, w in options], 'f8')
        name = names[rng.choice(len(names), p=weights / weights.sum())]
        height, crown = MESHES[name]
        # Match the original height, but keep the crown within the original plant's reach (plus a little).
        scale = min(max(plant['height'] / height, smin), smax, max((plant['radius'] + 1.5) / crown, smin))
        scale *= rng.uniform(.92, 1.08)
        x, y, z = plant['base']
        out.setdefault(name, []).append([round(x, 3), round(y - SINK, 3), round(z, 3),
                                         round(float(rng.uniform(0, 360)), 1), round(float(scale), 3)])
    return out


def summary():
    t = trees()
    kinds = {}
    for p in plants():
        kinds[p['kind']] = kinds.get(p['kind'], 0) + 1
    return {'plants': kinds, 'trees': {k: len(v) for k, v in sorted(t.items())}}


if __name__ == '__main__':
    import json
    print(json.dumps(summary(), indent=1))
