"""Prototype: regroup Crater Park's geometry per park piece (docs/inventory/craterpark-per-piece.md). Offline, numpy only.

    uv run python games/yorimichi_v2/tools/migrate/craterpark_per_piece.py GEOMETRY.npz [--out build/craterpark-per-piece]

GEOMETRY.npz is the donor generator's output (games/yorimichi/world/regions/craterpark/v2/editor_generate.py --park
games/yorimichi/tools/craterpark_editor/shipped.json). Every face carries a feature name. This script writes, for each
park piece (a piece with its supports, tower and shrine; a coping rail goes to the piece it rides, per
assets/adopted/craterpark/craterpark_ownership.json), and for the crater floor (4 x 4 tile blocks of 64 m):

  <out>/<owner>/render_<role>_<material>[_k].npz   the same faces as today's tile meshes, cut by piece not tile
  <out>/<owner>/collision_<k>.npz                  the same collision triangles as today's z-ordered slices, by piece
  <out>/summary.json                               counts, sizes and the exactness proof

Exactness: the multiset of render triangles (positions, normals, UVs, AO, material, tag) and of collision triangles is
compared with the input; the script exits 1 if they differ by even one triangle. Nothing is committed from --out.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
LEDGER = GAME / 'assets' / 'adopted' / 'craterpark' / 'craterpark_ownership.json'
FLOOR = 'crater_floor'
MAX_TRIANGLES = 30000       # split.MAX_RENDER; the atomic budget is 32768
SECTION = 32768             # atomic_inputs: collision triangles per package
TILE, BLOCK = 64., 4
SUFFIX = re.compile(r'_(?:supports|tower|shrine)$')
RENDER_ROLE = {'riding': 'original', 'side': 'original', 'rail': 'original', 'ground': 'mountain', 'coping': 'coping'}


def z_order(triangles, cell=1., large=8.):
    """split.spatial_order: a z-order curve over the triangle centres, the large triangles last."""
    t = np.asarray(triangles, 'f8')
    if not len(t):
        return np.zeros(0, 'i8')
    centres = t.mean(1)
    big = np.linalg.norm(t.max(1) - t.min(1), axis=1) > large
    q = np.floor((centres - centres.min(0)) / cell).astype('u8') & 0x1fffff
    code = np.zeros(len(q), 'u8')
    for bit in range(21):
        for axis in range(3):
            code |= ((q[:, axis] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(3 * bit + axis)
    return np.lexsort((code, big))


def tri_key(t):
    return np.round(np.asarray(t, 'f8').reshape(len(t), 9) * 1e5).astype('i8')


def digest(rows) -> str:
    rows = np.ascontiguousarray(np.asarray(rows)[np.lexsort(np.asarray(rows).T[::-1])])
    return hashlib.sha256(rows.tobytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('--out', type=Path, default=Path('build/craterpark-per-piece'))
    args = parser.parse_args(argv)
    ledger = json.loads(LEDGER.read_text())
    rides = ledger['coping_rides']
    geometry = np.load(args.geometry)
    index = json.loads(str(geometry['index']))
    renders = index['render']

    def owner_of(name: str) -> str:
        return rides.get(name, SUFFIX.sub('', name))

    # ---- every render face, with its owner and the tile mesh it is in today
    faces = collections.defaultdict(list)           # (owner, role, material) -> list of arrays
    before = []
    today_bytes = 0
    for i, e in enumerate(renders):
        V, F = geometry[f'r{i}_V'], geometry[f'r{i}_F']
        tri = V[F]
        names = np.asarray([owner_of(e['features'][k]) for k in geometry[f'r{i}_feature']])
        material, tag = geometry[f'r{i}_material'], geometry[f'r{i}_tag']
        before.append(np.hstack([tri_key(tri), material[:, None], tag[:, None]]))
        today_bytes += sum(geometry[f'r{i}_{k}'].nbytes for k in ('V', 'F', 'N', 'UV', 'AO', 'material', 'tag'))
        centre = tri.mean(1)
        for owner in np.unique(names):
            sel = names == owner
            if owner == FLOOR:
                bx = np.floor(centre[sel, 0] / TILE / BLOCK).astype('i8')
                bz = np.floor(centre[sel, 2] / TILE / BLOCK).astype('i8')
                groups = [(f'crater-floor-{x}-{z}', np.flatnonzero(sel)[(bx == x) & (bz == z)])
                          for x, z in sorted({(int(a), int(b)) for a, b in zip(bx, bz)})]
            else:
                groups = [(owner, np.flatnonzero(sel))]
            for name, idx in groups:
                for m in np.unique(material[idx]):
                    part = idx[material[idx] == m]
                    faces[(name, e['role'], int(m))].append((i, part))
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    after, summary = [], collections.defaultdict(lambda: {'render': 0, 'render_triangles': 0, 'collision': 0,
                                                          'collision_triangles': 0, 'bytes': 0})
    for (owner, role, material), chunks in sorted(faces.items()):
        arrays = collections.defaultdict(list)
        for i, idx in chunks:
            used = geometry[f'r{i}_F'][idx]
            arrays['V'].append(geometry[f'r{i}_V'][used])
            arrays['N'].append(geometry[f'r{i}_N'][used])
            arrays['UV'].append(geometry[f'r{i}_UV'][used])
            arrays['AO'].append(geometry[f'r{i}_AO'][used])
            arrays['material'].append(geometry[f'r{i}_material'][idx])
            arrays['tag'].append(geometry[f'r{i}_tag'][idx])
        merged = {k: np.concatenate(v) for k, v in arrays.items()}
        order = z_order(merged['V'])
        merged = {k: v[order] for k, v in merged.items()}      # per face: V (n, 3, 3), UV (n, 3, 2), AO (n, 3)
        triangles = merged['V']
        folder = out / owner
        folder.mkdir(exist_ok=True)
        for k in range(0, len(triangles), MAX_TRIANGLES):
            n = len(triangles[k:k + MAX_TRIANGLES])
            part = {key: val[k:k + n] for key, val in merged.items()}
            part = {key: (val.reshape(-1, *val.shape[2:]) if key in ('V', 'N', 'UV', 'AO') else val)
                    for key, val in part.items()}
            part['F'] = np.arange(3 * n).reshape(-1, 3)
            name = f'render_{role}_{material:03d}' + (f'_{k // MAX_TRIANGLES}' if len(triangles) > MAX_TRIANGLES else '')
            np.savez(folder / f'{name}.npz', **part)
            size = (folder / f'{name}.npz').stat().st_size
            after.append(np.hstack([tri_key(part['V'].reshape(-1, 3, 3)), part['material'][:, None], part['tag'][:, None]]))
            s = summary[owner]
            s['render'] += 1; s['render_triangles'] += n; s['bytes'] += size
    # ---- collision: today's triangles, matched back to their render face, regrouped
    lookup = {}
    for i, e in enumerate(renders):
        if e['role'] == 'coping':
            continue
        tri = geometry[f'r{i}_V'][geometry[f'r{i}_F']]
        for key, k in zip(map(bytes, tri_key(tri)), geometry[f'r{i}_feature']):
            lookup[key] = owner_of(e['features'][k])
    groups = collections.defaultdict(list)
    unmatched = 0
    all_collision = []
    for i, e in enumerate(index['collision']):
        t = geometry[f'c{i}']
        all_collision.append(tri_key(t))
        for key, tri in zip(map(bytes, tri_key(t)), t):
            owner = lookup.get(key)
            if owner is None:
                unmatched += 1
                owner = 'unmatched'
            if owner == FLOOR:
                c = tri.mean(0)
                owner = f'crater-floor-{int(np.floor(c[0] / TILE / BLOCK))}-{int(np.floor(c[2] / TILE / BLOCK))}'
            groups[owner].append(tri)
    regrouped = []
    for owner, tris in sorted(groups.items()):
        t = np.asarray(tris, 'f8')
        t = t[z_order(t)]
        regrouped.append(tri_key(t))
        folder = out / owner
        folder.mkdir(exist_ok=True)
        for k in range(0, len(t), SECTION):
            np.savez(folder / f'collision_{k // SECTION}.npz', triangles=t[k:k + SECTION])
            s = summary[owner]
            s['collision'] += 1; s['collision_triangles'] += len(t[k:k + SECTION])
            s['bytes'] += (folder / f'collision_{k // SECTION}.npz').stat().st_size
    # ---- exactness
    before_all, after_all = np.vstack(before), np.vstack(after)
    render_same = len(before_all) == len(after_all) and digest(before_all) == digest(after_all)
    collision_same = digest(np.vstack(all_collision)) == digest(np.vstack(regrouped))
    pieces = {k: v for k, v in summary.items() if not k.startswith('crater-floor-')}
    floor = [v for k, v in summary.items() if k.startswith('crater-floor-')]
    totals = {k: sum(v[k] for v in summary.values()) for k in ('render', 'render_triangles', 'collision',
                                                                  'collision_triangles', 'bytes')}
    result = {'today': {'render': len(renders), 'collision': sum(-(-len(geometry[f"c{i}"]) // SECTION) for i in
                                                                   range(len(index['collision']))),
                        'render_triangles': int(len(before_all)),
                        'collision_triangles': int(sum(len(geometry[f"c{i}"]) for i in range(len(index['collision'])))),
                        'render_array_bytes': today_bytes},
              'per_piece': {'totals': totals, 'pieces': len(pieces), 'floor_blocks': len(floor),
                            'unmatched_collision_triangles': unmatched,
                            'render_exact': bool(render_same), 'collision_exact': bool(collision_same)},
              'owners': dict(sorted(summary.items()))}
    (out / 'summary.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('today', 'per_piece')}, indent=1))
    return 0 if render_same and collision_same and not unmatched else 1


if __name__ == '__main__':
    sys.exit(main())
