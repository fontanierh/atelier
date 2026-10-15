"""Compile the owner's editor park (craterpark-editor/1 park.json) into the existing NPZ/FBX pipeline.

The geometry is the editor's own: the pinned pieces.js (editor/pieces.cjs) meshes every piece through the Node bridge,
exactly as the editor draws it. `--lines` keeps only those lines (by id), plus the pieces they ride into and the decks
they start from. Supports are not built yet (the owner's call), so the geometry is marked an editor playtest instead of
a validated v4 park.

The editor's cut terrain is not a mesh of the park: it is stored as a grid (ground_height, ground_weight) that the
volcano's own terrain follows (craterpark/placement.py terrain), so every surface round the pieces is the volcano's,
with its material, rock and snow, and its collision.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[2]))

import numpy as np  # noqa: E402
from craterpark.v2 import dsl, generate, v4_config  # noqa: E402
from craterpark.v2.editor import frontend  # noqa: E402

GROUND_REACH = 60.     # metres round every kept piece where the volcano takes the editor's cut ground in full
GROUND_FADE = 40.      # metres beyond that over which it eases back to the natural ground
# In a pit a piece cuts (a bowl's), the ground is kept PIT_CLEAR under every piece within PIT_REACH: the volcano samples
# it every 5 m (hidamari/mountains.py STEP), and a 5 m cell's points are all within 7.1 m of its corners, so no
# terrain triangle there rises through the piece.
PIT_REACH = 7.5
PIT_CLEAR = .5
SIDE_COLOURS = ([0.6, 0.58, 0.54], [0.45, 0.43, 0.4])   # pieces.js COL.side, COL.bottom


def select(doc, lines):
    """The pieces of `lines`, the pieces they lead into (a bowl they land in) and the decks of their starts."""
    keep = {p['id'] for p in doc['pieces'] if p['line'] in lines}
    by = {p['id']: p for p in doc['pieces']}
    for pid in list(keep):
        for n in by[pid].get('next') or []:
            if by[n]['type'] in ('bowl', 'deck'):
                keep.add(n)
    # the start decks: decks of the structure line that the kept roll-ins stand on (within 30 m of their top)
    tops = [(p['x'], p['z']) for p in doc['pieces'] if p['id'] in keep and p['type'] == 'rollin']
    for p in doc['pieces']:
        if p['type'] == 'deck' and p['id'] not in keep and any(np.hypot(p['x'] - x, p['z'] - z) < 60 for x, z in tops):
            keep.add(p['id'])
    out = dict(doc)
    out['pieces'] = []
    for p in doc['pieces']:
        if p['id'] in keep:
            q = dict(p)
            q['next'] = [n for n in p.get('next') or [] if n in keep]
            if q.get('attach') and q['attach'] not in keep:
                raise ValueError(f"{p['id']} is attached to {q['attach']}, outside the selected lines")
            out['pieces'].append(q)
    return out


def orient(V, F, N):
    """Faces counter-clockwise from the side their vertex normals face (the editor draws double-sided)."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    flip = (np.cross(b - a, c - a) * (N[F[:, 0]] + N[F[:, 1]] + N[F[:, 2]])).sum(1) < 0
    F = F.copy()
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


def tile_uv(V, N, size=4.):
    """World-projected UVs (4 m tiles) along each vertex normal's dominant axis."""
    ax = np.abs(N).argmax(1)
    uv = np.where(ax[:, None] == 1, V[:, [0, 2]], np.where(ax[:, None] == 0, V[:, [2, 1]], V[:, [0, 1]]))
    return uv / size


def piece_mesh(piece):
    m, meta = piece.mesh, piece.metadata
    V, N, F, col = m.V, m.N, orient(m.V, m.F, m.N), piece.colors
    side = np.zeros(len(F), bool)
    for c in SIDE_COLOURS:
        side |= (np.abs(col[F] - c).max(2) < 0.02).all(1)
    parts = []
    for mask, role, material in ((~side, dsl.RIDING, dsl.DECK if meta['type'] == 'deck' else dsl.CONCRETE),
                                 (side, dsl.SIDE, dsl.SIDE_WALL)):
        if mask.any():
            parts.append(dsl.Mesh.part(V, F[mask], N=N, UV=tile_uv(V, N), role=role, material=material,
                                       feature=meta['id']).subset(np.ones(int(mask.sum()), bool)))
    return parts


def _shifts(n):
    return [(dy, dx) for dy in range(-n, n + 1) for dx in range(-n, n + 1) if dy * dy + dx * dx <= n * n]


def _shifted(a, dy, dx, fill):
    """a moved by (dy, dx) cells: out[j, i] = a[j + dy, i + dx], `fill` off the grid."""
    k = max(abs(dy), abs(dx))
    p = np.pad(a, k, constant_values=fill)
    return p[k + dy:k + dy + a.shape[0], k + dx:k + dx + a.shape[1]]


def ground_grid(scene, points, base):
    """The editor's cut ground on its own grid, and how much of it the volcano takes: (heights, weight), (nz, nx) float32.
    `points` are the kept pieces' vertices (native), `base` the editor's terrain layer before the pieces cut it. The
    weight is 1 within GROUND_REACH of the kept pieces, easing to 0 over GROUND_FADE beyond them. Where a piece cut the
    ground below `base` (a pit), the heights stay PIT_CLEAR under the pieces within PIT_REACH."""
    g = scene.metadata['ground_grid']
    shape = (g['nz'], g['nx'])
    H = frontend.read_array(scene.metadata['_dir'], g['heights'], 1).reshape(shape).astype('f8')
    j = np.round((points[:, 2] - g['z0']) / g['G'] - .5).astype(int)
    i = np.round((points[:, 0] - g['x0']) / g['G'] - .5).astype(int)
    on = (j >= 0) & (j < g['nz']) & (i >= 0) & (i < g['nx'])
    j, i, y = j[on], i[on], points[on, 1]
    # metres to the nearest kept point: a chamfer distance (8 neighbours) grown from the cells holding one
    d = np.full(shape, np.inf)
    d[j, i] = 0.
    for _ in range(int(np.ceil((GROUND_REACH + GROUND_FADE) / g['G'])) + 1):
        d = np.minimum.reduce([d] + [_shifted(d, dy, dx, np.inf) + np.hypot(dy, dx) * g['G']
                                     for dy, dx in _shifts(1) if dy or dx])
    t = np.clip((d - GROUND_REACH) / GROUND_FADE, 0, 1)
    weight = 1 - t * t * (3 - 2 * t)
    # the lowest piece over each cell, then over PIT_REACH round it
    low = np.full(shape, np.inf)
    np.minimum.at(low, (j, i), y)
    r = int(np.ceil(PIT_REACH / g['G']))
    low = np.minimum.reduce([_shifted(low, dy, dx, np.inf) for dy, dx in _shifts(r)])
    pit = H < base - PIT_CLEAR
    H = np.where(pit, np.minimum(H, low - PIT_CLEAR), H)
    return H.astype('f4'), weight.astype('f4')


def main(argv=None):
    import yori
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--park', required=True, help="the editor's park.json (its data/ folder beside it)")
    parser.add_argument('--lines', default=os.environ.get('ATELIER_CRATERPARK_EDITOR_LINES', 'L1'),
                        help='comma-separated line ids to build (default: L1, orange)')
    parser.add_argument('--out', default=str(yori.OUT / 'craterpark' / 'v2'))
    args = parser.parse_args(argv)
    from craterpark import placement
    from craterpark.v2 import ao, export, spawns
    start = time.monotonic()
    park_path = Path(args.park).expanduser().resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ('geometry.npz', 'geometry-report.json'):
        (out / name).unlink(missing_ok=True)
    provenance = v4_config.provenance(park_path)
    doc = json.loads(park_path.read_text())
    lines = [s for s in args.lines.split(',') if s]
    chosen = select(doc, set(lines))
    print(f'CRATERPARK EDITOR rev {doc.get("rev")}: lines {lines}, {len(chosen["pieces"])} of {len(doc["pieces"])} pieces', flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'src').mkdir()
        (tmp / 'src' / 'park.json').write_text(json.dumps(chosen))
        snap = frontend.snapshot(tmp / 'src' / 'park.json', tmp / 'snap', terrain_dir=park_path.parent / 'data')
        scene = frontend.compile_snapshot(snap, tmp / 'mesh', timeout=600)
        scene.metadata['_dir'] = str(tmp / 'mesh')
        parts, keep = [], []
        for piece in scene.pieces:
            parts += piece_mesh(piece)
            keep.append(piece.mesh.V)
        keep = np.concatenate(keep)
        # the editor's chosen terrain layer, before the pieces cut it
        terrain = json.loads((park_path.parent / 'data' / 'terrain.json').read_text())['inner']
        base = np.fromfile(park_path.parent / 'data' / terrain['layers'][doc['terrain']], '<f4')
        heights, weight = ground_grid(scene, keep, base.reshape(terrain['nz'], terrain['nx']).astype('f8'))
        grid = {k: scene.metadata['ground_grid'][k] for k in ('x0', 'z0', 'G', 'nx', 'nz')}
    mesh = dsl.Mesh.concat(parts)
    # the riding line: its pieces in order from the roll-in, the centre line, the start on the roll-in's top
    by = {p.metadata['id']: p for p in scene.pieces}
    ride_lines, labels = [], {}
    for line in lines:
        name = next((l['name'] for l in doc['lines'] if l['id'] == line), line)
        first = next(p for p in scene.pieces if p.metadata['line'] == line and p.metadata['type'] == 'rollin')
        order, seen, cur = [], set(), first.metadata['id']
        while cur and cur not in seen and cur in by:
            seen.add(cur)
            order.append(cur)
            cur = next(iter(by[cur].metadata['next']), None)
        path = np.concatenate([by[i].centerline for i in order if len(by[i].centerline)])
        st = first.metadata['stations'][min(3, len(first.metadata['stations']) - 1)]
        spawn = ((st['x'], st['y'], st['z']), float(st['h']))
        ride_lines.append(dsl.RideLine(line, order, path, spawn, path[-1]))
        labels[line] = name
    park = dsl.Park(mesh, [], ride_lines, [dict(kind='editor_playtest', rev=doc.get('rev'), lines=lines)])
    generate.declare_scenery(park)
    entries = spawns.entries(park.mesh, park.lines, placement, deck_y=None, labels=labels)
    print('CRATERPARK EDITOR baking occlusion', flush=True)
    ao.bake_mesh(park.mesh, drawn=(dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL))
    arrays, index = generate.bundle(park, entries, {})
    # the cut ground the volcano's terrain follows (v4_placement.ground_grid), instead of a park mesh over it
    arrays.update(ground_height=heights, ground_weight=weight)
    index.update(v4=provenance, editor_playtest={'rev': doc.get('rev'), 'lines': lines, 'pieces': len(chosen['pieces']),
                                                 'pieces_sha256': scene.metadata['pieces_sha256']},
                 ground_grid=dict(grid, reach=GROUND_REACH, fade=GROUND_FADE),
                 accepted=False, validation={'ran': False, 'reason': 'editor playtest: supports not built (owner)'},
                 bounds_native=[park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()])
    arrays['index'] = np.asarray(json.dumps(index))
    (out / 'lines').mkdir(exist_ok=True)
    for stale in (out / 'lines').glob('*.npz'):
        stale.unlink()
    for line in park.lines:
        export.line_npz(park.mesh, line, out / 'lines' / f'{line.name}.npz')
    rep = generate.report(park, index, time.monotonic() - start)
    rep.update(layout='editor', v4=provenance, editor_playtest=index['editor_playtest'],
               bounds_native=index['bounds_native'])
    temporary = out / 'geometry.tmp.npz'
    np.savez(temporary, **arrays)
    rep['geometry_sha256'] = hashlib.sha256(temporary.read_bytes()).hexdigest()
    if v4_config.provenance(park_path) != provenance:
        temporary.unlink(missing_ok=True)
        raise ValueError('the editor park changed while compiling; rerun (ship from a frozen copy)')
    (out / 'geometry-report.json').write_text(json.dumps(rep, indent=1) + '\n')
    temporary.replace(out / 'geometry.npz')
    print('CRATERPARK EDITOR GEOMETRY COMPLETE', rep['render_triangles'], 'render',
          rep['collision_triangles'], 'collision', f'{time.monotonic() - start:.0f}s', flush=True)


if __name__ == '__main__':
    main()
