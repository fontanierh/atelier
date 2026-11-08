"""Crater Park's drawn and collision meshes made clean, from build.py's pieces (Blender; docs/CRATERPARK.md "Clean geometry").

clean(loaded) takes build.py's pieces (entry, arrays, kept faces), after the tunnel carve and the added pieces, and
returns what build.py exports:
1. the open space reachable from outside (clean.reachable) and, by rays, the faces seen from it (visibility); a
   foundation face on a riding surface (COVER) and a prism wall shared by two prisms are hidden before any ray;
2. faces lying on a higher-ranked face (ROLES order, piece by piece) have its outline cut out of them exactly
   (clean.subtract): no face lies on another, so nothing flickers and nothing is pushed back;
0. an old mesh an added piece was laid through (CUT_UNDER) loses its parts over the piece's top, cut exactly;
3. T-junctions split, within each mesh and against every other mesh's vertices (clean.fix_tjunctions);
4. the grind lines found on that collision (grind.py), each drawn as the steel coping, Douglas-Peucker'd (COPING_TOL);
5. the baked occlusion on the fine faces (build.ambient_occlusion, the coping included as before);
6. every mesh remeshed (remesh.py): the added pieces as height fields over the ground, the rest by planar patches,
   chains shared, within TOL_H of the fine surface and TOL_AO of its occlusion (and TOL_UV of its UVs).
"""
import hashlib
import json
import math
import resource
import sys
import time
from pathlib import Path

import numpy as np

from craterpark import additions, grind, remesh, visibility
from craterpark import clean as cl
from craterpark import build as B

TOL_H = .003        # metres: a remeshed surface's height off the fine one at every fine vertex, at most
TOL_B = .0015       # metres: a simplified chain (an outline, a crease, a seam) off the fine one
TOL_AO = .02        # the baked occlusion, linear
TOL_UV = .002       # texture tiles, on the textured pieces
COPING_TOL = .0015  # metres: a coping line simplified this close to its lip
WELD = 2e-4         # metres: the library's positions are float32 (0.12 mm apart near x = 1300)
MARGIN = 15.        # metres round a region (box) whose faces are cleaned with it, as its context
TJ = 5e-4           # metres: a vertex this close to another face's edge splits it
# Old meshes an added piece was laid through, whose parts over its top showed through it (a planter's cap as a
# wedge in the plaza kicker's face): cut away exactly (clean.cut_under). Listed, not inferred: a floor a piece runs
# into (the pool landing's run-out under the pool's floor) is ridden over the piece and must stay.
CUT_UNDER = {'add-run-plaza_gap_kicker': ('mesh-0140-000', 'mesh-0179-000')}
COVER = .05         # metres: a foundation face this close on a riding surface is hidden (build.COVER)


def log(t0, *a):
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 30 if sys.platform == 'darwin' else 1 << 20)
    print(f'{time.time() - t0:7.1f}s {peak:5.2f}G clean:', *a, flush=True)


def mesh_rank(entry):
    if entry['id'] == 'add-coping':
        return len(B.ROLES) + 1.
    return B.ROLES.index('bridge_support') + .5 if entry.get('added') else B.ROLES.index(entry['role'])


def heightfield(entry):
    i = entry['id']
    return bool(entry.get('added')) and not i.endswith('-sides') and not i.startswith(('add-solid', 'add-kicker')) and i != 'add-coping'


def compact(P, F, UV):
    used = np.unique(F); rm = np.full(len(P), -1, 'i8'); rm[used] = np.arange(len(used))
    return P[used], rm[F], UV[used]


def weld(P, F, UV):
    """Corners on one position and UV made one vertex; folded faces dropped."""
    key = np.concatenate([np.round(P / WELD), np.round(UV / 1e-5)], 1).astype('i8')
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    F = inv.ravel()[F]
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    return P[first], F, UV[first]


def _key(*arrays):
    """A piece's remesh inputs, hashed: its positions, faces, attributes, fixed vertices, mode and tolerances (each
    already carries its neighbours' effects: clipping, seams, occlusion), with the remesher's own source."""
    h = hashlib.sha256(Path(remesh.__file__).read_bytes())
    for a in arrays:
        h.update(np.ascontiguousarray(np.asarray(a)).tobytes() if not isinstance(a, str) else a.encode())
    return h.hexdigest()[:32]


def clean(loaded, cache=None, box=None):
    """build.py's pieces -> (pieces with p['out'] = (P, F, UV, AO), grind lines, stats). `cache`: a directory of
    remeshed faces, one file per piece keyed by its inputs (_key), reused while they are unchanged. `box` (x0, z0, x1,
    z1): a region only (checks within the small memory slot): the open space and the rays see every face, the rest
    runs on the faces within MARGIN of the box, and only the faces whose centroid lies in it come out."""
    t0 = time.time(); stats = {}; diag = {}
    if cache is not None:
        cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    pieces = []
    for entry, a, keep in loaded:
        F = a['triangles'][keep].astype('i8')
        if not len(F):
            continue
        P, F, UV = compact(a['positions'].astype('f8'), F, a['uvs'].astype('f8'))
        pieces.append({'entry': entry, 'P': P, 'F': F, 'UV': UV})
    stats['fine_faces'] = int(sum(len(p['F']) for p in pieces))
    # 0. old meshes an added piece was laid through (CUT_UNDER): their parts over its top cut away, exactly
    byid = {p['entry']['id']: p for p in pieces}
    for piece, olds in CUT_UNDER.items():
        if piece not in byid:
            continue
        t = byid[piece]['P'][byid[piece]['F']]
        skin = t[remesh.face_normals(t.reshape(-1, 3), np.arange(3 * len(t)).reshape(-1, 3))[0][:, 1] > .05]
        for o in olds:
            if o not in byid:
                continue
            q = byid[o]; T0 = q['P'][q['F']]
            lo, hi = skin.reshape(-1, 3).min(0), skin.reshape(-1, 3).max(0)
            near = np.flatnonzero((T0.max(1) >= lo).all(1) & (T0.min(1) <= hi).all(1))
            keep = np.ones(len(T0), bool); add_P, add_UV = [], []
            for f in near.tolist():
                parts = cl.cut_under(T0[f], skin)
                if len(parts) == 1 and np.allclose(parts[0], T0[f]):
                    continue
                keep[f] = False
                if len(parts):
                    tri = q['F'][f]
                    bc = np.linalg.lstsq(np.stack([T0[f][1] - T0[f][0], T0[f][2] - T0[f][0]], 1),
                                         (parts.reshape(-1, 3) - T0[f][0]).T, rcond=None)[0].T
                    bc = np.stack([1 - bc[:, 0] - bc[:, 1], bc[:, 0], bc[:, 1]], 1)
                    add_P.append(parts.reshape(-1, 3)); add_UV.append(bc @ q['UV'][tri])
            if (~keep).any():
                base = len(q['P'])
                P = np.concatenate([q['P']] + add_P); UV = np.concatenate([q['UV']] + add_UV)
                F = np.concatenate([q['F'][keep], base + np.arange(sum(len(x) for x in add_P)).reshape(-1, 3)])
                q['P'], q['F'], q['UV'] = weld(*compact(P, F, UV))
                stats.setdefault('cut_under', {})[o] = int((~keep).sum())
                log(t0, f'{o}: {int((~keep).sum())} faces cut under {piece}')
    T = np.concatenate([p['P'][p['F']] for p in pieces])
    owner = np.repeat(np.arange(len(pieces)), [len(p['F']) for p in pieces])
    ctx = np.ones(len(T), bool)
    if box is not None:
        c = T.mean(1)
        ctx = (c[:, 0] >= box[0] - MARGIN) & (c[:, 0] <= box[2] + MARGIN) & (c[:, 2] >= box[1] - MARGIN) & (c[:, 2] <= box[3] + MARGIN)
    # 1. visibility
    reach = cl.reachable(T, log=lambda m: log(t0, m))
    pre = np.zeros(len(T), bool)
    role = np.array([p['entry']['role'] for p in pieces])[owner]
    found = (role == 'foundation') & ctx
    ride = (role == 'original')
    two = np.array([bool(p['entry'].get('doubleSided')) for p in pieces])[owner]
    if found.any():
        f = np.flatnonzero(found)
        near = ride & ctx
        pre[f[cl.covered(T[f], T[near], eps=COVER)]] = True
        pre[f[cl.inner_walls(T[f], np.zeros(len(f), 'i8'))]] = True
    log(t0, 'hidden before rays (foundation on riding, shared prism walls):', int(pre.sum()))
    tree = visibility.bvh(T)
    seen = visibility.seen_faces(tree, T, two, reach, test=~pre & ctx) & ~pre & ctx
    del tree
    # failed rays are evidence, not proof: a riding top (n_y > .2) stays unless the exact pre-pass hid it
    top = ride & ctx & (remesh.face_normals(T.reshape(-1, 3), np.arange(3 * len(T)).reshape(-1, 3))[0][:, 1] > .2)
    stats['riding_tops_kept_unwitnessed'] = int((top & ~seen & ~pre).sum())
    seen |= top & ~pre
    stats['hidden'] = int((~seen).sum())
    log(t0, 'faces seen:', int(seen.sum()), 'of', len(T))
    # 2. overlaps clipped by rank (piece by piece within a mesh)
    order = sorted(range(len(pieces)), key=lambda k: (mesh_rank(pieces[k]['entry']), pieces[k]['entry']['id']))
    mrank = np.empty(len(pieces), 'i8'); mrank[order] = np.arange(len(pieces))
    rank = np.concatenate([mrank[k] * (1 << 24) + B.pieces(p['F']) for k, p in enumerate(pieces)])
    vis = np.flatnonzero(seen)
    pairs = cl.overlap_pairs(T[vis], rank[vis])
    stats['overlap_pairs'] = int(len(pairs))
    removed = np.zeros(len(T), bool); parts = {}
    if len(pairs):
        pairs = vis[pairs]
        srt = pairs[np.argsort(pairs[:, 0], kind='stable')]
        starts = np.flatnonzero(np.r_[True, srt[1:, 0] != srt[:-1, 0]]); ends = np.r_[starts[1:], len(srt)]
        for s, e in zip(starts, ends):
            f = srt[s, 0]
            removed[f] = True
            kept = cl.subtract(T[f], T[srt[s:e, 1]])
            if len(kept):
                parts[f] = kept
    stats['clipped'] = int(removed.sum())
    log(t0, 'overlapping faces clipped:', int(removed.sum()), 'parts kept:', sum(len(v) for v in parts.values()))
    start = np.r_[0, np.cumsum([len(p['F']) for p in pieces])]
    for k, p in enumerate(pieces):
        g = np.arange(start[k], start[k + 1])
        F = p['F'][(seen & ~removed)[g]]
        P, UV = p['P'], p['UV']
        nP, nUV, nF = [P], [UV], [F]; base = len(P)
        for gi in g[removed[g]]:
            if gi not in parts:
                continue
            q = parts[gi]; tri = p['F'][gi - start[k]]; T3 = P[tri]
            sol = np.linalg.lstsq(np.stack([T3[1] - T3[0], T3[2] - T3[0]], 1), (q.reshape(-1, 3) - T3[0]).T, rcond=None)[0].T
            bc = np.stack([1 - sol[:, 0] - sol[:, 1], sol[:, 0], sol[:, 1]], 1)
            nP.append(q.reshape(-1, 3)); nUV.append(bc @ UV[tri]); nF.append(base + np.arange(3 * len(q)).reshape(-1, 3)); base += 3 * len(q)
        P, F, UV = np.concatenate(nP), np.concatenate(nF), np.concatenate(nUV)
        p['P'], p['F'], p['UV'] = weld(*compact(P, F, UV)) if len(F) else (P[:0], F, UV[:0])
    pieces = [p for p in pieces if len(p['F'])]
    # 3. T-junctions
    allP = np.concatenate([x['P'] for x in pieces]); whose = np.repeat(np.arange(len(pieces)), [len(x['P']) for x in pieces])
    for k, p in enumerate(pieces):
        lo, hi = p['P'].min(0) - 1, p['P'].max(0) + 1
        others = allP[((allP >= lo) & (allP <= hi)).all(1) & (whose != k)]     # positions as they were before this pass
        P, F, added, p['UV'] = cl.fix_tjunctions(p['P'], p['F'], others, tol=TJ, attrs=p['UV'])   # UVs along the split edge
        p['P'], p['F'] = P, F
    log(t0, 'T-junctions split')
    # 4. grind lines on the fine collision, and the coping along them
    above, final = collision(pieces)
    lines = grind.grind_lines(final['original'], np.concatenate([x for r, x in final.items() if r != 'original']))
    log(t0, 'grind lines:', len(lines))
    # the rails keep every point (park.json); the tube needs only the points off a straight run
    tube = additions.coping([l[remesh.dp_chain(np.arange(len(l)), l, None, COPING_TOL, None)] for l in lines])
    if tube is not None:
        v, f, uv = tube
        cop = v.astype('f8')[f]
        tree = visibility.bvh(np.concatenate([np.concatenate([p['P'][p['F']] for p in pieces]), cop]))
        keep = visibility.seen_faces(tree, cop, False, reach)
        del tree
        P, F, UV = compact(v.astype('f8'), f[keep].astype('i8'), uv.astype('f8'))
        pieces.append({'entry': {'id': 'add-coping', 'role': 'coping', 'material': additions.COPING_MATERIAL,
                                 'doubleSided': False, 'added': True}, 'P': P, 'F': F, 'UV': UV})
        stats['coping'] = {'faces': int(len(f)), 'seen': int(keep.sum())}
    # 5. occlusion on the fine faces
    for p, ao in zip(pieces, occlusion([(p['P'], p['F']) for p in pieces])):
        p['AO'] = ao
    log(t0, 'occlusion baked')
    if box is not None:
        for p in pieces:
            c = p['P'][p['F']].mean(1)
            m = (c[:, 0] >= box[0]) & (c[:, 0] <= box[2]) & (c[:, 2] >= box[1]) & (c[:, 2] <= box[3])
            cut = np.zeros(len(p['P']), bool)                          # on the box's cut: kept exactly (tiles meet)
            cut[np.intersect1d(p['F'][m].ravel(), p['F'][~m].ravel())] = True
            F = p['F'][m]; used = np.unique(F); rm = np.full(len(p['P']), -1, 'i8'); rm[used] = np.arange(len(used))
            p['P'], p['F'], p['UV'], p['AO'] = p['P'][used], rm[F], p['UV'][used], p['AO'][used]
            p['cut'] = cut[used]
        pieces = [p for p in pieces if len(p['F'])]
    # 6. remesh
    keys = np.concatenate([np.round(p['P'] / WELD).astype('i8') for p in pieces])
    who = np.repeat(np.arange(len(pieces)), [len(p['P']) for p in pieces])
    u, inv = np.unique(keys, axis=0, return_inverse=True); inv = inv.ravel()
    # a position used by more than one piece is a seam between meshes: it stays
    pairs_ = np.unique(np.stack([inv, who], 1), axis=0)
    shared = np.bincount(pairs_[:, 0], minlength=len(u)) > 1
    off = np.r_[0, np.cumsum([len(p['P']) for p in pieces])]
    for k, p in enumerate(pieces):
        e = p['entry']; P, F, UV, AO = p['P'], p['F'], p['UV'], p['AO']
        mine = inv[off[k]:off[k + 1]]
        cnt = np.bincount(mine, minlength=len(u))
        fixed_v = shared[mine] | (cnt[mine] > 1)                       # seams with other meshes, UV seams within
        if 'cut' in p:
            fixed_v = fixed_v | p['cut']
        textured = e['role'] not in B.PLAIN and e['id'] != 'add-coping'
        A = np.stack([AO] + ([UV[:, 0], UV[:, 1]] if textured else []), 1)
        tolA = np.array([TOL_AO] + ([TOL_UV, TOL_UV] if textured else []))
        mode = 'coping' if e['id'] == 'add-coping' else 'height' if heightfield(e) and (remesh.face_normals(P, F)[0][:, 1] > .05).any() else 'planar'
        key = _key(P, F, A, fixed_v, mode, tolA, np.array([TOL_H, TOL_B]))
        hit = cache / (key + '.npy') if cache is not None else None
        if hit is not None and hit.exists():
            Tn = np.load(hit)
        elif mode == 'coping':
            Tn = F
        elif mode == 'height':
            up = remesh.face_normals(P, F)[0][:, 1] > .05
            lab = np.unique(np.where(up, 0, 1 + np.arange(len(F))), return_inverse=True)[1].ravel()
            Tn = remesh.remesh_mesh(P, F, A, TOL_H, tolA, lab, normal_of=lambda l: np.array([0., 1., 0.]), tol_b=TOL_B,
                                    fixed=set(range(1, int(lab.max()) + 1)), fixed_vertex=fixed_v, diag=diag)
        else:
            Tn = remesh.remesh_mesh(P, F, A, TOL_H, tolA, remesh.planar_patches(P, F), tol_b=TOL_B, fixed_vertex=fixed_v,
                                    diag=diag)
        if hit is not None and not hit.exists():
            np.save(hit, Tn)
        used = np.unique(Tn); rm = np.full(len(P), -1, 'i8'); rm[used] = np.arange(len(used))
        p['out'] = (P[used], rm[Tn], UV[used], AO[used])
        p['fine_faces'] = int(len(F))
    stats['remesh_fallback'] = diag
    log(t0, 'remeshed', diag)
    return pieces, lines, stats


def occlusion(meshes):
    """build.ambient_occlusion, the same rays, reach and smoothing, with its voxel grid filled by clean.mark at the
    same sample spacing (voxel/2), which costs a face its edges' lengths, not its longest edge squared."""
    voxel, reach = B.AO_VOXEL, B.AO_REACH
    tris = np.concatenate([v[f] for v, f in meshes]).astype('f8')
    verts = np.concatenate([v for v, _ in meshes]).astype('f8')
    lo = verts.min(0) - reach - voxel; hi = verts.max(0) + reach + voxel
    lo[1] = max(lo[1], np.percentile(verts[:, 1], 1) - reach)
    grid = np.zeros(np.ceil((hi - lo) / voxel).astype(int), bool)
    cl.mark(grid, tris, lo, voxel, step=voxel / 2, cheapest=False)
    del tris
    return _rays(meshes, grid, lo)


def _rays(meshes, grid, lo):
    """build.ambient_occlusion's rays and smoothing over a given grid (origin lo, voxel AO_VOXEL)."""
    voxel, reach = B.AO_VOXEL, B.AO_REACH
    shape = np.array(grid.shape)
    local = B.ao_directions()
    distances = np.geomspace(1.5 * voxel, reach, B.AO_STEPS)
    result = []
    for vertices, faces in meshes:
        v = vertices.astype('f8'); n = B.vertex_normals(vertices, faces)
        side = np.where(np.abs(n[:, :1]) < .9, [[1., 0., 0.]], [[0., 0., 1.]])
        tu = np.cross(n, side); tu /= np.linalg.norm(tu, axis=1, keepdims=True); tv = np.cross(n, tu)
        ao = np.ones(len(v))
        for s in range(0, len(v), B.CHUNK):
            d = (local[None, :, :1] * tu[s:s + B.CHUNK, None] + local[None, :, 1:2] * tv[s:s + B.CHUNK, None]
                 + local[None, :, 2:] * n[s:s + B.CHUNK, None])
            origin = v[s:s + B.CHUNK, None, None] + 1.2 * voxel * n[s:s + B.CHUNK, None, None]
            p = origin + d[:, :, None] * distances[None, None, :, None]
            c = np.floor((p - lo) / voxel).astype(int)
            inside = ((c >= 0) & (c < shape)).all(-1)
            c = np.where(inside[..., None], c, 0)
            blocked = grid[c[..., 0], c[..., 1], c[..., 2]] & inside
            first = np.where(blocked.any(-1), distances[blocked.argmax(-1)], reach)
            ao[s:s + B.CHUNK] = 1 - (1 - first / reach).mean(1)
        edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        for _ in range(2):
            total = np.zeros(len(v)); count = np.zeros(len(v))
            np.add.at(total, edges[:, 0], ao[edges[:, 1]]); np.add.at(count, edges[:, 0], 1)
            np.add.at(total, edges[:, 1], ao[edges[:, 0]]); np.add.at(count, edges[:, 1], 1)
            ao = np.where(count > 0, .5 * ao + .5 * total / np.maximum(count, 1), ao)
        result.append(np.clip(ao, 0, 1))
    return result


def collision(pieces):
    """Per role, the faces the board rides, as build.py: riding faces as they are, the others with every corner
    inside the solid sunk; faces whose top edge is inside the solid left out. Returns (riding_above, {role: (n,3,3)})."""
    parts = {}
    for p in pieces:
        r = p['entry']['role']
        if r == 'coping':
            continue
        parts.setdefault(r, []).append(p['P'][p['F']])
    ride = np.concatenate(parts['original']).astype('f8')
    above = B.riding_above(ride[B.unit_normals(ride)[:, 1] > .2])
    final = {}
    for r, x in parts.items():
        t = np.concatenate(x).astype('f8')
        t = t[~B.hidden_walls(t, above)]
        if r != 'original':
            t, _ = B.sink_inside(t, above)
        final[r] = t
    return above, final
