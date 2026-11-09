"""Plan and prove the split of Brine Cove's fused tile meshes into one mesh per object (docs/inventory/brinecove-split.md).

Pure Python: reads a donor GLB (`build/yorimichi/brinecove/glb/SM_BC_<Feature>_<tx>_<ty>.glb`), welds vertices by
position, groups triangles into connected components, assigns each component to the object whose box (Unreal-axis
free GLB metres, the donor's own frame) holds the component's centre, and reports per-object triangle counts, bounds
and materials. It never writes a mesh: the controller step that does (Blender export of each object's faces) must pass
`verify_partition`, which proves the parts are exactly the source's triangles.

    python3 games/yorimichi_v2/tools/migrate/brinecove_split.py plan GLB_DIR
    python3 games/yorimichi_v2/tools/migrate/brinecove_split.py components GLB [--min-tris N]

The GLB frame is the donor's (glTF Y up, metres); V2 placements already carry the matching transform, so a part keeps
its source vertices unchanged and its placement keeps the tile's transform (identity pivot), which is what makes the
split lossless.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

QUANT = 1e-4   # vertex weld tolerance, metres


def read_glb(path: Path) -> dict:
    """{'materials': [name], 'prims': [{'material': int, 'positions': [(x,y,z)], 'indices': [int]}]} of a binary glTF."""
    data = Path(path).read_bytes()
    if data[:4] != b'glTF':
        raise ValueError(f'{path}: not a binary glTF (an LFS pointer?)')
    json_len = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + json_len])
    bin_start = 20 + json_len + 8
    blob = data[bin_start:]
    sizes = {5126: ('f', 4), 5123: ('H', 2), 5125: ('I', 4), 5121: ('B', 1)}
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}

    def accessor(index):
        acc = doc['accessors'][index]
        view = doc['bufferViews'][acc['bufferView']]
        fmt, size = sizes[acc['componentType']]
        n = width[acc['type']]
        start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
        stride = view.get('byteStride') or size * n
        out = []
        for i in range(acc['count']):
            out.append(struct.unpack_from('<' + fmt * n, blob, start + i * stride))
        return out

    prims = []
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            pos = accessor(prim['attributes']['POSITION'])
            idx = [v[0] for v in accessor(prim['indices'])] if 'indices' in prim else list(range(len(pos)))
            extra = {k: accessor(prim['attributes'][k]) for k in ('NORMAL', 'TEXCOORD_0') if k in prim['attributes']}
            prims.append({'material': prim.get('material', -1), 'positions': pos, 'indices': idx, **extra})
    return {'materials': [m.get('name', '') for m in doc.get('materials', [])], 'prims': prims,
            'material_docs': doc.get('materials', [])}


def triangles(model: dict):
    """Yield (material name, (p0, p1, p2)) for every triangle, in the order write_subset and merge_models count them."""
    for prim in model['prims']:
        name = model['materials'][prim['material']] if prim['material'] >= 0 else ''
        pos, idx = prim['positions'], prim['indices']
        for i in range(0, len(idx) - 2, 3):
            yield name, (pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]])


def _key(p):
    return (round(p[0] / QUANT), round(p[1] / QUANT), round(p[2] / QUANT))


def components(tris: list) -> list[list[int]]:
    """Connected components of triangles that share a welded vertex; each a list of triangle indices, largest first."""
    parent = list(range(len(tris)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    seen: dict = {}
    for t, (_, corners) in enumerate(tris):
        for p in corners:
            k = _key(p)
            if k in seen:
                ra, rb = find(t), find(seen[k])
                if ra != rb:
                    parent[ra] = rb
            else:
                seen[k] = t
    groups = defaultdict(list)
    for t in range(len(tris)):
        groups[find(t)].append(t)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def bounds(tris: list, members: list[int]) -> tuple[tuple, tuple]:
    xs = [c for t in members for p in tris[t][1] for c in (p[0],)]
    ys = [p[1] for t in members for p in tris[t][1]]
    zs = [p[2] for t in members for p in tris[t][1]]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def centre(box) -> tuple:
    lo, hi = box
    return tuple((a + b) / 2 for a, b in zip(lo, hi))


def inside(point, region) -> bool:
    """region = [xmin, xmax, zmin, zmax] in GLB axes (x, z are the ground plane; y is up). None bounds are open."""
    xmin, xmax, zmin, zmax = region
    x, _, z = point
    return (xmin is None or x >= xmin) and (xmax is None or x < xmax) and (zmin is None or z >= zmin) and (zmax is None or z < zmax)


def assign(tris: list, comps: list[list[int]], objects: dict[str, list]) -> dict[str, list[int]]:
    """Give each component to the first object whose region holds its centre; unassigned go to '' (the remainder)."""
    out: dict[str, list[int]] = {name: [] for name in objects}
    out[''] = []
    for comp in comps:
        c = centre(bounds(tris, comp))
        for name, region in objects.items():
            if inside(c, region):
                out[name].extend(comp)
                break
        else:
            out[''].extend(comp)
    return out


def extent(box) -> float:
    """Longest ground-plane side of a (min, max) box."""
    lo, hi = box
    return max(hi[0] - lo[0], hi[2] - lo[2])


def assign_anchored(tris: list, comps: list[list[int]], anchors: dict[str, dict]) -> dict[str, list[int]]:
    """Give each component to the nearest anchored object it lies within.

    anchors[name] = {'x', 'y': layout metres (the generator's frame; the GLB ground plane is (x, -y)),
    'radius': metres, 'max_extent': longest allowed component side (a quay, floor or terrain slab is longer and is
    never an object part), 'min_height': lowest vertex a part may start at (the slab it stands on is lower),
    'exclude_materials': material names the object never uses (the floor's setts and kerbs),
    'exclude_zones': [(x, y, radius)] layout points of neighbouring things (a palm: planter, trunk and fronds) whose
    components never belong to this object, whatever their material, even when they lie inside its radius}.
    A component that no anchor claims stays in the remainder ''. Ties go to the nearer anchor, then the name."""
    out: dict[str, list[int]] = {name: [] for name in anchors}
    out[''] = []
    for comp in comps:
        box = bounds(tris, comp)
        cx, cy, cz = centre(box)
        best = None
        for name, a in sorted(anchors.items()):
            if extent(box) > a.get('max_extent', 30.0) or box[0][1] < a.get('min_height', -1e9):
                continue
            if a.get('exclude_materials') and any(tris[t][0] in a['exclude_materials'] for t in comp):
                continue
            if any(((cx - zx) ** 2 + (cz + zy) ** 2) ** 0.5 <= zr for zx, zy, zr in a.get('exclude_zones', ())):
                continue
            d = ((cx - a['x']) ** 2 + (cz + a['y']) ** 2) ** 0.5
            if d <= a['radius'] and (best is None or d < best[0]):
                best = (d, name)
        out[best[1] if best else ''].extend(comp)
    return out


def merge_models(parts: list[tuple[dict, list[int]]]) -> dict:
    """One model from triangles of several tile models (each `(model, ordinals)`), materials joined by name, so an object
    that spans tiles becomes a single mesh in the shared tile frame. Vertices are copied unchanged."""
    names, docs, prims = [], [], {}
    for model, members in parts:
        chosen, n = set(members), 0
        for prim in model['prims']:
            name = model['materials'][prim['material']] if prim['material'] >= 0 else ''
            for k in range(0, len(prim['indices']) - 2, 3):
                if n in chosen:
                    if name not in names:
                        names.append(name)
                        docs.append(model.get('material_docs', [{}] * len(model['materials']))[prim['material']]
                                    if prim['material'] >= 0 else {'name': name})
                    out = prims.setdefault(name, {'positions': [], 'indices': [], 'NORMAL': [], 'TEXCOORD_0': []})
                    for j in range(3):
                        i = prim['indices'][k + j]
                        out['indices'].append(len(out['positions']))
                        out['positions'].append(prim['positions'][i])
                        for key in ('NORMAL', 'TEXCOORD_0'):
                            if key in prim:
                                out[key].append(prim[key][i])
                n += 1
    merged = []
    for name in names:
        prim = {'material': names.index(name), **prims[name]}
        for key in ('NORMAL', 'TEXCOORD_0'):
            if not prim[key]:
                del prim[key]
        merged.append(prim)
    return {'materials': names, 'material_docs': docs, 'prims': merged}


def write_subset(model: dict, members, path: Path) -> list[str]:
    """Write the triangles with these ordinals (the order `triangles` yields them) as a binary glTF that keeps every
    source vertex position, normal and UV unchanged. The material list is the used materials in first-use order (what the
    Unreal import turns into slots); the names are returned in that order. Vertices are not shared between triangles."""
    chosen = set(members)
    refs, n = [], 0
    for pi, prim in enumerate(model['prims']):
        for k in range(0, len(prim['indices']) - 2, 3):
            if n in chosen:
                refs.append((pi, k))
            n += 1
    blob, views, accessors, primitives = b'', [], [], []

    def add(values, fmt, ctype, kind, minmax=False):
        nonlocal blob
        data = b''.join(struct.pack('<' + fmt * len(v), *v) for v in values)
        data += b'\0' * (-len(data) % 4)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(data)})
        acc = {'bufferView': len(views) - 1, 'componentType': ctype, 'count': len(values), 'type': kind}
        if minmax and values:
            acc['min'] = [min(v[i] for v in values) for i in range(3)]
            acc['max'] = [max(v[i] for v in values) for i in range(3)]
        accessors.append(acc)
        blob += data
        return len(accessors) - 1

    by_prim: dict = defaultdict(list)
    for pi, k in refs:
        by_prim[pi].append(k)
    used: list[int] = []        # source material indices in first-use order
    docs = model.get('material_docs') or [{'name': m} for m in model['materials']]
    for pi in sorted(by_prim):
        prim = model['prims'][pi]
        order = [prim['indices'][k + j] for k in by_prim[pi] for j in range(3)]
        attrs = {'POSITION': add([prim['positions'][i] for i in order], 'f', 5126, 'VEC3', True)}
        if 'NORMAL' in prim:
            attrs['NORMAL'] = add([prim['NORMAL'][i] for i in order], 'f', 5126, 'VEC3')
        if 'TEXCOORD_0' in prim:
            attrs['TEXCOORD_0'] = add([prim['TEXCOORD_0'][i] for i in order], 'f', 5126, 'VEC2')
        index = add([(i,) for i in range(len(order))], 'I', 5125, 'SCALAR')
        if prim['material'] not in used:
            used.append(prim['material'])
        primitives.append({'attributes': attrs, 'indices': index, 'material': used.index(prim['material'])})
    doc = {'asset': {'version': '2.0', 'generator': 'brinecove_split'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'mesh': 0, 'name': Path(path).stem}], 'meshes': [{'name': Path(path).stem, 'primitives': primitives}],
           'materials': [docs[m] for m in used],
           'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(blob)}]}
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(blob), 0x004E4942) + blob
    Path(path).write_bytes(b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body)
    return [model['materials'][m] for m in used]


def signature(tris: list, members) -> dict:
    """Order-free fingerprint: triangle count, per-material counts and the sorted welded triangles' hash."""
    import hashlib
    per = defaultdict(int)
    items = []
    for t in members:
        m, corners = tris[t]
        per[m] += 1
        items.append((m, tuple(sorted(_key(p) for p in corners))))
    items.sort()
    return {'triangles': len(items), 'by_material': dict(sorted(per.items())),
            'sha256': hashlib.sha256(repr(items).encode()).hexdigest()}


def verify_partition(source_tris: list, parts: list[list]) -> list[str]:
    """Problems proving the parts (each a list of (material, corners)) are exactly the source's triangles."""
    src = signature(source_tris, range(len(source_tris)))
    merged = [tri for part in parts for tri in part]
    got = signature(merged, range(len(merged)))
    problems = []
    if src['triangles'] != got['triangles']:
        problems.append(f"triangles: source {src['triangles']}, parts {got['triangles']}")
    if src['by_material'] != got['by_material']:
        problems.append('material split differs')
    if src['sha256'] != got['sha256']:
        problems.append('triangle set differs (vertex positions, winding aside)')
    return problems


def report(glb: Path, objects: dict[str, list] | None = None, min_tris: int = 1) -> dict:
    model = read_glb(glb)
    tris = list(triangles(model))
    comps = components(tris)
    rows = []
    for comp in comps:
        if len(comp) < min_tris:
            continue
        lo, hi = bounds(tris, comp)
        rows.append({'triangles': len(comp), 'min': [round(v, 3) for v in lo], 'max': [round(v, 3) for v in hi],
                     'materials': sorted({tris[t][0] for t in comp})})
    out = {'glb': glb.name, 'triangles': len(tris), 'components': len(comps), 'top': rows}
    if objects:
        owned = assign(tris, comps, objects)
        out['objects'] = {name: {'triangles': len(m), **({'min': [round(v, 3) for v in bounds(tris, m)[0]],
                                                          'max': [round(v, 3) for v in bounds(tris, m)[1]]} if m else {})}
                          for name, m in owned.items()}
        parts = [[tris[t] for t in m] for m in owned.values()]
        out['partition_problems'] = verify_partition(tris, parts)
    return out


# The first batch: 13 objects the generator places at fixed positions (no RNG jitter), read from
# games/yorimichi/world/regions/brinecove/{layout,landmarks}.py and procedural/{ships,harbor,props,market}.py.
# x, y are layout metres; `tiles` are the donor GLB stems (without SM_BC_) that can hold the object.
FLOOR_MATERIALS = ('BC_cobble', 'BC_cobble_dark', 'BC_stone_light')
OBJECTS: dict[str, dict] = {
    'galleon-nightjar': dict(x=40, y=-132, radius=110, max_extent=120, min_height=-50,
                             tiles=('Ships_4_2', 'Ships_4_3')),
    'sloop-east': dict(x=252, y=-72, radius=40, max_extent=120, min_height=-50, tiles=('Ships_4_3', 'Ships_5_3')),
    'shipyard-yard': dict(x=376, y=78, radius=36, max_extent=40, min_height=-5,
                          exclude_materials=('BC_stone', 'BC_stone_dark', 'BC_stone_light'),
                          tiles=('Harbor_5_3', 'Harbor_5_3_Soft', 'Harbor_5_4')),
    # harbor.py builds a palm in a stone planter at (-330, 72) and (300, 72) (lines 97-103); the crane stands at (-334, 84)
    # and the shed at (305, 86), so those palms (trunk, planter, fronds: all within 5 m of the base) stay in the tile.
    'crane-west': dict(x=-326, y=83, radius=14, max_extent=25, min_height=4.5, exclude_zones=((-330, 72, 5.0),),
                       tiles=('Harbor_2_3', 'Harbor_2_3_Soft')),
    'crane-east': dict(x=418, y=127, radius=14, max_extent=25, min_height=4.5, tiles=('Harbor_5_4',)),
    'fish-shed': dict(x=305, y=86, radius=21, max_extent=40, min_height=4.9, exclude_zones=((300, 72, 5.0),),
                      tiles=('Harbor_5_3', 'Harbor_5_3_Soft')),
    'net-rack-west': dict(x=274, y=70, radius=5.5, max_extent=12, min_height=4.5, tiles=('Props_5_3',)),
    'net-rack-east': dict(x=286, y=70, radius=5.5, max_extent=12, min_height=4.5, tiles=('Props_5_3',)),
    'cannon-west': dict(x=-206, y=88, radius=8, max_extent=12, min_height=4.5, tiles=('Props_3_3',)),
    'cannon-east': dict(x=210, y=88, radius=8, max_extent=12, min_height=4.5, tiles=('Props_4_3',)),
    'quay-anchor': dict(x=-292, y=90, radius=6, max_extent=12, min_height=4.5, tiles=('Props_2_3',)),
    'market-well': dict(x=47, y=137, radius=4.5, max_extent=8, min_height=4.5,
                        exclude_materials=FLOOR_MATERIALS, tiles=('Market_',)),
    'market-auction-block': dict(x=-44, y=188, radius=7, max_extent=14, min_height=4.5,
                                 exclude_materials=FLOOR_MATERIALS, tiles=('Market_',)),
}


def is_soft(stem: str) -> bool:
    return stem.endswith('_Soft')


def wanted_tiles(glb_dir: Path, objects: dict[str, dict]) -> list[str]:
    stems = sorted({p.stem[len('SM_BC_'):] for p in Path(glb_dir).glob('SM_BC_*.glb')})
    return [s for s in stems if any(s.startswith(t) if t.endswith('_') else s == t
                                    for o in objects.values() for t in o['tiles'])]


def compute(glb_dir: Path, objects: dict[str, dict] | None = None, assigner=None) -> dict:
    """Split every donor tile the batch touches: {'models': {tile: model}, 'tris': {tile: [triangles]},
    'owned': {tile: {object or '': [ordinals]}}, 'problems': [...]}. The remainder ('') plus the parts is each tile's triangles.
    `assigner(stem, tris, components, allowed)` replaces the anchored (radius) assignment, e.g. brinecove_ships.py's
    generator-boundary assignment; it returns the same {object or '': [ordinals]}."""
    objects = objects or OBJECTS
    out = {'models': {}, 'tris': {}, 'owned': {}, 'problems': []}
    for stem in wanted_tiles(glb_dir, objects):
        model = read_glb(Path(glb_dir) / f'SM_BC_{stem}.glb')
        tris = list(triangles(model))
        allowed = {n: {k: v for k, v in o.items() if k != 'tiles'} for n, o in objects.items()
                   if any(stem.startswith(t) if t.endswith('_') else stem == t for t in o['tiles'])}
        comps = components(tris)
        owned = assigner(stem, tris, comps, allowed) if assigner else assign_anchored(tris, comps, allowed)
        out['problems'] += [f'{stem}: {p}' for p in verify_partition(tris, [[tris[t] for t in m] for m in owned.values()])]
        out['models'][stem], out['tris'][stem], out['owned'][stem] = model, tris, owned
    return out


def plan_batch(glb_dir: Path, objects: dict[str, dict] | None = None, out_dir: Path | None = None) -> dict:
    """Per object triangles, bounds, source tiles and materials, plus the partition check of each tile. With `out_dir`
    also writes `<object>/<tile>.glb` and `_rest/<tile>.glb` (per-tile pieces; apply joins an object's tiles)."""
    objects = objects or OBJECTS
    done = compute(glb_dir, objects)
    result = {name: {'triangles': 0, 'tiles': {}, 'materials': set(), 'min': None, 'max': None} for name in objects}
    for stem, owned in done['owned'].items():
        tris, model = done['tris'][stem], done['models'][stem]
        if out_dir is not None and owned.get(''):
            (Path(out_dir) / '_rest').mkdir(parents=True, exist_ok=True)
            write_subset(model, owned[''], Path(out_dir) / '_rest' / f'SM_BC_{stem}.glb')
        for name, members in owned.items():
            if not name or not members:
                continue
            lo, hi = bounds(tris, members)
            r = result[name]
            r['triangles'] += len(members)
            if out_dir is not None:
                (Path(out_dir) / name).mkdir(parents=True, exist_ok=True)
                write_subset(model, members, Path(out_dir) / name / f'SM_BC_{stem}.glb')
            r['tiles'][stem] = len(members)
            r['materials'] |= {tris[t][0] for t in members}
            r['min'] = lo if r['min'] is None else tuple(min(a, b) for a, b in zip(r['min'], lo))
            r['max'] = hi if r['max'] is None else tuple(max(a, b) for a, b in zip(r['max'], hi))
    for r in result.values():
        r['materials'] = sorted(r['materials'])
    return {'objects': result, 'problems': done['problems']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    comp = sub.add_parser('components', help='list the connected components of one GLB')
    comp.add_argument('glb', type=Path)
    comp.add_argument('--min-tris', type=int, default=20)
    plan = sub.add_parser('plan', help='split the donor tiles the first batch touches and check each tile\'s partition')
    plan.add_argument('glb_dir', type=Path, help='build/yorimichi/brinecove/glb of the donor')
    plan.add_argument('--out', type=Path, help='also write each object\'s parts and the tiles\' remainders here (a new directory)')
    args = parser.parse_args(argv)
    if args.command == 'components':
        print(json.dumps(report(args.glb, min_tris=args.min_tris), indent=1))
    else:
        print(json.dumps(plan_batch(args.glb_dir, out_dir=args.out), indent=1, default=list))
    return 0


if __name__ == '__main__':
    sys.exit(main())
