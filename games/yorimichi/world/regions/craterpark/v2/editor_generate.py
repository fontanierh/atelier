"""Compile the owner's editor park (craterpark-editor/1 park.json) into the existing NPZ/FBX pipeline.

The geometry is the editor's own: the pinned pieces.js (editor/pieces.cjs) meshes every piece through the Node bridge,
exactly as the editor draws it, and the ground is the editor's cut terrain. `--lines` keeps only those lines (by id),
plus the pieces they ride into and the decks they start from. Supports are not built yet (the owner's call), so the
geometry is marked an editor playtest instead of a validated v4 park.
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

WOOD = 'material_016'     # ramp boards (assets/craterpark/materials.json)
KICK_REACH = 30.        # metres of a capped run's end that count as its launch ramp
GROUND_REACH = 60.     # metres of cut ground kept round every kept piece
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
    # wooden ramps (the park's ramp boards) everywhere but the bowls, which stay poured concrete
    concrete = meta['type'] == 'bowl'
    for mask, role, material in ((~side, dsl.RIDING, dsl.CONCRETE if concrete else WOOD),
                                 (side, dsl.SIDE, dsl.SIDE_WALL if concrete else WOOD)):
        if mask.any():
            parts.append(dsl.Mesh.part(V, F[mask], N=N, UV=tile_uv(V, N), role=role, material=material,
                                       feature=meta['id']).subset(np.ones(int(mask.sum()), bool)))
    return parts


def ground_mesh(scene, keep_xz):
    """The editor's cut ground, full resolution, only within GROUND_REACH of the kept pieces."""
    g = scene.metadata['ground_grid']
    spec = g['heights']
    H = frontend.read_array(scene.metadata['_dir'], spec, 1).reshape(g['nz'], g['nx']).astype('f8')
    x = g['x0'] + (np.arange(g['nx']) + .5) * g['G']
    z = g['z0'] + (np.arange(g['nz']) + .5) * g['G']
    # cells near any kept point, by a distance transform on the grid
    near = np.zeros((g['nz'], g['nx']), bool)
    r = int(np.ceil(GROUND_REACH / g['G']))
    idx = np.unique(np.c_[np.round((keep_xz[:, 1] - g['z0']) / g['G'] - .5), np.round((keep_xz[:, 0] - g['x0']) / g['G'] - .5)].astype(int), axis=0)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disk = (xx * xx + yy * yy) <= r * r
    for j, i in idx:
        j0, j1, i0, i1 = max(0, j - r), min(g['nz'], j + r + 1), max(0, i - r), min(g['nx'], i + r + 1)
        if j0 < j1 and i0 < i1:
            near[j0:j1, i0:i1] |= disk[j0 - j + r:j1 - j + r, i0 - i + r:i1 - i + r]
    cell = near[:-1, :-1] & near[1:, :-1] & near[:-1, 1:] & near[1:, 1:]
    X, Z = np.meshgrid(x, z)
    V = np.c_[X.ravel(), H.ravel(), Z.ravel()]
    jj, ii = np.nonzero(cell)
    a = jj * g['nx'] + ii
    b, c, d = a + 1, a + g['nx'], a + g['nx'] + 1
    F = np.concatenate([np.c_[a, c, b], np.c_[b, c, d]])
    used = np.unique(F)
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    V, F = V[used], remap[F]
    m = dsl.Mesh.part(V, F, role=dsl.GROUND, material=dsl.GROUND_MAT, feature='ground')
    m.F = orient(m.V, m.F, np.tile([0., 1., 0.], (len(m.V), 1)))
    m.UV = V[:, [0, 2]] / 8.
    return m


def assist_zones(pieces, doc):
    """The launch ramps the owner capped (params.vert_assist_max): a jump's kicker up to its lip, or the last
    KICK_REACH metres of a run, as native points with the ramp's half width. export.py turns them into boxes."""
    zones, params = [], {p['id']: p.get('params', {}) for p in doc['pieces']}
    for piece in pieces:
        meta = piece.metadata
        cap = params[meta['id']].get('vert_assist_max')
        if cap is None:
            continue
        st = meta['stations']
        if meta['type'] == 'jump':
            st = st[:meta['info']['lip']['i'] + 1]
        else:
            st = [s for s in st if s['d'] >= st[-1]['d'] - KICK_REACH]
        width = params[meta['id']].get('width', 12)
        zones.append({'id': meta['id'], 'vert_assist_max': float(cap), 'half_width': width / 2,
                      'points': [[s['x'], s['y'], s['z']] for s in st]})
    return zones


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
            keep.append(piece.mesh.V[:, [0, 2]])
        keep = np.concatenate(keep)
        ground = ground_mesh(scene, keep[::4])
    mesh = dsl.Mesh.concat(parts + [ground])
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
    ao.bake_mesh(park.mesh, drawn=(dsl.RIDING, dsl.SIDE, dsl.GROUND, dsl.COPING, dsl.RAIL))
    arrays, index = generate.bundle(park, entries, {})
    index.update(v4=provenance, editor_playtest={'rev': doc.get('rev'), 'lines': lines, 'pieces': len(chosen['pieces']),
                                                 'pieces_sha256': scene.metadata['pieces_sha256']},
                 accepted=False, validation={'ran': False, 'reason': 'editor playtest: supports not built (owner)'},
                 bounds_native=[park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()])
    index['assist_zones_native'] = assist_zones(scene.pieces, doc)
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
