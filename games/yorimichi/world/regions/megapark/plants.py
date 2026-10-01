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

# Island meshes (/Game/Japan/Assets): height and crown radius in metres at scale 1 (world/build_assets.py). All are the detailed leaf-card kind the island uses where the
# player gets close; the painted-card _lo trees are for the far forest.
MESHES = {
    'Tree_Maple_A': (6.5, 3.0), 'Tree_Maple_B': (5.2, 2.3), 'Tree_Ginkgo': (9.0, 2.2), 'Tree_Broad_A': (8.5, 2.3),
    'Tree_Broad_B': (7.0, 1.9), 'Tree_Broad_C': (10., 2.7), 'Tree_Pine_A': (13.0, 2.6), 'Tree_Pine_B': (11.0, 2.4),
    'Tree_Cedar_B': (13.0, 2.2), 'Bush_Ochre_A': (1.5, 1.5),
    'Bush_Ochre_B': (1.1, 1.1), 'Bush_Green_A': (1.4, 1.4), 'Bush_Green_B': (1.0, 1.0), 'Bush_Flower_A': (1.2, 1.2),
}
# Original plant -> (mesh, weight) choices and the scale range. The rock rims get pines, cedars and broadleaves like the
# forest round the park; the groves and canyons get the painted maples and ginkgos; the shrubs become ochre bushes and
# small red maples, the paintovers' undergrowth (the green bushes read pale yellow against the rock). A tree
# TALL metres or more becomes a big conifer or broadleaf, leafy down its trunk rather than a crown on a bare pole.
CHOICES = {
    'longtree': ([('Tree_Pine_B', 3), ('Tree_Cedar_B', 3), ('Tree_Pine_A', 2), ('Tree_Maple_A', 2), ('Tree_Ginkgo', 1),
                  ('Tree_Broad_C', 1)], (.9, 2.2)),
    'poplar': ([('Tree_Maple_A', 4), ('Tree_Maple_B', 2), ('Tree_Ginkgo', 3), ('Tree_Broad_B', 1)], (.8, 2.0)),
    'treewall': ([('Tree_Cedar_B', 2), ('Tree_Pine_B', 1)], (1., 1.4)),
    'birch': ([('Tree_Ginkgo', 1)], (.7, 1.0)),
    'ocotillo': ([('Tree_Maple_B', 3), ('Bush_Ochre_A', 2), ('Tree_Maple_A', 1)], (.7, 1.2)),
    'saguaro': ([('Tree_Maple_B', 2), ('Bush_Ochre_A', 2), ('Bush_Green_A', 1)], (.8, 1.4)),
    'shrub': ([('Bush_Ochre_A', 3), ('Tree_Maple_B', 2), ('Bush_Ochre_B', 1), ('Bush_Green_A', 1), ('Bush_Flower_A', 1)],
              (.8, 1.5)),
    'shrubpot': ([('Bush_Flower_A', 1)], (1.2, 1.6)),
}
TALL = 12.
TALL_CHOICES = ([('Tree_Pine_A', 3), ('Tree_Cedar_B', 3), ('Tree_Pine_B', 2), ('Tree_Broad_C', 1), ('Tree_Maple_A', 2)],
                (.9, 1.6))
# The park's own natural surfaces get plants too, like the paintovers (assets/megapark/concepts/improve-*): shrubs on the
# rock ledges and at the foot of the walls, small wind-shaped trees on the rock rims, forest on the earth hillsides and
# woods on the grass. Diffuse texture -> surface kind.
NATURAL = {'0x2c70170a001d0133': 'rock', '0x2c70170a001d0135': 'rock', '0x2c70170a001d00aa': 'soil',
           '0x2c70170a00040094': 'grass'}
# kind -> (tree choices, scale range, trees per square metre in a clump, the least up component of a planted face's
# normal, the share of the surface left open). Earth is planted up to steep slopes, as a forest covers a hillside.
LEDGE_TREES = {
    'rock': ([('Tree_Pine_B', 4), ('Tree_Maple_B', 3), ('Tree_Maple_A', 2), ('Tree_Cedar_B', 2), ('Tree_Ginkgo', 1)],
             (.55, 1.), 1 / 25., .7, -.1),
    'soil': ([('Tree_Pine_B', 3), ('Tree_Cedar_B', 3), ('Tree_Pine_A', 2), ('Tree_Maple_A', 3), ('Tree_Maple_B', 1),
              ('Tree_Ginkgo', 2)], (.9, 1.45), 1 / 7., .45, -.6),
    'grass': ([('Tree_Maple_A', 3), ('Tree_Ginkgo', 2), ('Tree_Pine_B', 2), ('Tree_Cedar_B', 2)], (.9, 1.4), 1 / 9.,
              .82, -.1),
}
LEDGE_SHRUBS = ([('Tree_Maple_B', 5), ('Tree_Pine_B', 2), ('Bush_Ochre_A', 1), ('Bush_Ochre_B', 1), ('Bush_Flower_A', 1)],
                (.7, 1.5), 1 / 6., .7)
# A maple or pine this small is a shrub: red and dark green ones like the paintovers' ledges, where the island's bushes
# read pale yellow against the rock.
SHRUB_SCALE = {'Tree_Maple_B': (.3, .45), 'Tree_Pine_B': (.18, .28)}
BUILT_CLEAR = (6., 1.4)         # metres from any built surface (concrete, wood, paint, metal) for a tree, a shrub
# The seam's rocks (seam()): meshes, scale range, rocks per square metre tried, the least gap between two, and the band
# of distance from the concrete they lie in (metres).
SEAM_ROCKS = (('Rock_A', 'Rock_B', 'Rock_C'), (.55, 1.1), 1 / 18., 3.5, (1.2, 6.))
# The rock is ridden too, so the plants on it keep off the lines: the grind rails and copings (the source's rail
# splines) and the roll-in from the deck spawn (native x, z; the points tools/review_megapark.py probes). Metres in
# plan, and the height band a rail clears.
ROLL_IN = ((330, -710), (322, -700), (320, -690), (320, -675), (318, -650), (305, -630), (310, -610), (320, -590),
           (300, -560), (340, -550), (375, -655))
LINE_CLEAR = {'roll_in': 5., 'rail': 2., 'band': 3.}
# The original plants keep their places except on the roll-in proper, its first DROP points from the deck start to the
# bottom: the cacti and shrubs on a ledge under it and at its foot, whose trees and bushes would poke through it in the
# way of every run from the start.
DROP = 5
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


def trees():
    """Every plant of the park: the replacements, the ledge plants and the seam's, {mesh: [[x, y, z, yaw, scale], ...]}."""
    out = {name: list(rows) for name, rows in replacements().items()}
    for group in (ledges(), seam()):
        for name, rows in group.items():
            out.setdefault(name, []).extend(rows)
    return out


def replacements(seed=11):
    """One island plant for each original but those on the roll-in (DROP): {mesh: [[x, y, z, yaw, scale], ...]} with
    x, y, z the native trunk foot in metres (y up)."""
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
        if _to_line(np.array(ROLL_IN[:DROP], 'f8'), np.array([x, z])) < 2.5 + crown * scale:
            continue
        out.setdefault(name, []).append([round(x, 3), round(y - SINK, 3), round(z, 3),
                                         round(float(rng.uniform(0, 360)), 1), round(float(scale), 3)])
    return out


def _surfaces(seam=False):
    """(natural, built): natural up-facing triangles as (kind, triangle, up) lists, and points on every other opaque
    surface, all native metres (y up). The natural ones are the kept park's, or with `seam` the seam's
    (placement.SEAM); the built ones are both's, so either keeps clear of the other's walls and roads."""
    natural, built = [], []
    for model in placement.source()['models']:
        own = placement.SEAM.get(model['asset_id'], ())
        if not (own or placement.is_park_model(model)):
            continue
        with np.load(placement.SOURCE / model['npz'], allow_pickle=False) as arrays:
            for part in model['meshes']:
                tid = part.get('retail_texture_ids', {}).get('diffuse')
                i = part['index']; f = arrays[f'faces_{i}']
                if tid in FOLIAGE or not len(f) or (own and i not in own):
                    continue
                v = arrays[f'vertices_{i}'].astype('f8'); t = v[f]
                if tid in NATURAL and bool(own) == seam:
                    n = arrays[f'normals_{i}'][f].astype('f8').mean(1)
                    up = n[:, 1] / np.maximum(np.linalg.norm(n, axis=1), 1e-9)
                    kind = NATURAL[tid]
                    keep = up > min(LEDGE_TREES[kind][3], LEDGE_SHRUBS[3])
                    natural += [(kind, q, u) for q, u in zip(t[keep], up[keep])]
                elif tid not in NATURAL and part.get('alpha_mode', 0) == 0:
                    built.append(t)
    built = placement.surface_samples(np.concatenate(built), 1.2) if built else np.zeros((0, 3))
    return natural, built


@lru_cache(maxsize=1)
def lines():
    """(roll-in polyline (n, 2) in native plan x, z; rail samples (m, 3) native x, y, z every half metre or so)."""
    import json, struct
    source = json.loads((placement.SOURCE / 'map.json').read_text())
    rails = []
    for rail in source['rails']:
        for raw in rail['native_segment_payloads']:
            v = np.asarray(struct.unpack('>30f', bytes.fromhex(raw)), 'f8')
            a, b, c, d = (v[o:o + 3] for o in (0, 4, 8, 12))
            n = max(2, int(np.linalg.norm(a + b + c) / .5) + 1)
            t = np.linspace(0, 1, n)[:, None]
            rails.append(d + c * t + b * t * t + a * t ** 3)
    return np.array(ROLL_IN, 'f8'), np.concatenate(rails)


def _to_line(line, q):
    """Metres from plan point q to the polyline `line` (n, 2)."""
    a, b = line[:-1], line[1:]; d = b - a
    u = np.clip(((q - a) * d).sum(1) / (d * d).sum(1), 0, 1)
    return float(np.hypot(*(a + d * u[:, None] - q).T).min())


def _ridden(q, margin):
    """Whether native point q is within `margin` metres (plus the line's own clearance) of a line skaters ride."""
    roll, rails = lines()
    if _to_line(roll, q[[0, 2]]) < LINE_CLEAR['roll_in'] + margin:
        return True
    near = np.abs(rails[:, 1] - q[1]) < LINE_CLEAR['band']
    return bool(near.any() and np.hypot(rails[near, 0] - q[0], rails[near, 2] - q[2]).min() < LINE_CLEAR['rail'] + margin)


@lru_cache(maxsize=1)
def ledges(seed=12):
    """Plants on the park's own rock, earth and grass: {mesh: [[x, y, z, yaw, scale], ...]} native metres (y up)."""
    natural, built = _surfaces()
    return _plant(natural, built, np.random.default_rng(seed), [(np.array(p['base'])[[0, 2]], 2.) for p in plants()])


@lru_cache(maxsize=1)
def seam(seed=13):
    """Plants on the seam's earth (placement.SEAM) by the same rules, clear of the park's own plants: the hillside
    between the gate's rock and the air station's footbridge gets its forest, shrubs at the wall's foot and bare
    patches (assets/megapark/concepts/seam-gate). {mesh: [[x, y, z, yaw, scale], ...]} native metres (y up)."""
    natural, built = _surfaces(seam=True)
    taken = [(np.array(p['base'])[[0, 2]], 2.) for p in plants()]
    for rows in ledges().values():
        taken += [(np.array(r)[[0, 2]], 1.3) for r in rows]
    rng = np.random.default_rng(seed)
    out = _plant(natural, built, rng, taken)
    # Rocks where the earth meets the concrete, as in the concept: between the shrubs' and the trees' clearances.
    clear = _clearance(built)
    names, (lo, hi), per, gap, near = SEAM_ROCKS
    rocks = []
    for kind, (a, b, c), up in natural:
        want = np.linalg.norm(np.cross(b - a, c - a)) / 2 * per
        for _ in range(int(want) + (rng.random() < want % 1)):
            u, v = rng.random(2)
            if u + v > 1: u, v = 1 - u, 1 - v
            q = a + u * (b - a) + v * (c - a)
            if not near[0] < clear(q) < near[1] or any(np.hypot(*(q - o)[[0, 2]]) < gap for o in rocks):
                continue
            rocks.append(q)
            size = rng.uniform(lo, hi)
            out.setdefault(names[rng.integers(len(names))], []).append(
                [round(float(q[0]), 3), round(float(q[1]) - .3 * size, 3), round(float(q[2]), 3),
                 round(float(rng.uniform(0, 360)), 1), round(float(size), 3)])
    return out


def _clearance(built):
    """clear(q): metres from native point q to the nearest `built` point, 99 beyond 6 m or so."""
    grid = {}
    for q in built:
        grid.setdefault(tuple(np.floor(q / 6.).astype(int)), []).append(q)
    def clear(q):
        k = np.floor(q / 6.).astype(int)
        near = [o for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                for o in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ())]
        return float(np.linalg.norm(np.asarray(near) - q, axis=1).min()) if near else 99.
    return clear


def _plant(natural, built, rng, taken):
    """Plant `natural` [(kind, triangle, up)] clear of the `built` points and of `taken` [(plan point, gap)]."""
    clear = _clearance(built)
    placed = ({}, {})              # trees, shrubs: plan cell -> [(point, gap)]
    out = {}
    def free(q, gap, tree):
        # Trees keep their spacing from trees, shrubs theirs from shrubs and a metre from any trunk.
        k = (math.floor(q[0] / 4), math.floor(q[2] / 4))
        near = lambda cells, g0: all(np.hypot(*(q[[0, 2]] - o)) >= g0(g) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                                     for o, g in cells.get((k[0] + dx, k[1] + dy), ()))
        return (near(placed[0], lambda g: max(gap, g)) if tree else
                near(placed[1], lambda g: max(gap, g)) and near(placed[0], lambda g: 1.)) and \
            all(np.hypot(*(q[[0, 2]] - o)) >= g for o, g in taken)
    def put(name, q, scale, gap, sink, tree):
        out.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]) - sink, 3), round(float(q[2]), 3),
                                         round(float(rng.uniform(0, 360)), 1), round(float(scale), 3)])
        placed[0 if tree else 1].setdefault((math.floor(q[0] / 4), math.floor(q[2] / 4)), []).append((q[[0, 2]], gap))
    def pick(options):
        names = [n for n, _ in options]; w = np.array([w for _, w in options], 'f8')
        return names[rng.choice(len(names), p=w / w.sum())]
    shrubs, (slo, shi), sper, shrub_up = LEDGE_SHRUBS
    for tree in (True, False):
        for kind, tri, up in natural:
            a, b, c = tri
            trees, (lo, hi), per, tree_up, open_ = LEDGE_TREES[kind]
            want = np.linalg.norm(np.cross(b - a, c - a)) * (per * (up > tree_up) if tree else sper * (up > shrub_up))
            for _ in range(int(want) + (rng.random() < want % 1)):
                u, v = rng.random(2)
                if u + v > 1: u, v = 1 - u, 1 - v
                q = a + u * (b - a) + v * (c - a)
                # Clumps: part of the surface is bare rock or open ground, the rest takes twice the mean density.
                clump = np.sin(q[0] * .11 + np.sin(q[2] * .09) * 2.) * np.sin(q[2] * .1 + np.sin(q[0] * .07) * 1.6)
                if clump < (open_ if tree else -.35) or rng.random() < .5 or clear(q) < BUILT_CLEAR[0 if tree else 1]:
                    continue
                if tree:
                    scale = rng.uniform(lo, hi); name = pick(trees)
                    if free(q, 2.8 * scale, True) and not _ridden(q, MESHES[name][1] * scale):
                        put(name, q, scale, 2.8 * scale, SINK, True)
                elif free(q, 1.3, False) and not _ridden(q, .7):
                    name = pick(shrubs)
                    put(name, q, rng.uniform(*SHRUB_SCALE.get(name, (slo, shi))), 1.3, .15, False)
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
