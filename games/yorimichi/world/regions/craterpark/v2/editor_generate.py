"""Compile the owner's editor park (craterpark-editor/1 park.json) into the existing NPZ/FBX pipeline.

The geometry is the editor's own: the pinned pieces.js (editor/pieces.cjs) meshes every piece through the Node bridge,
exactly as the editor draws it. `--lines` keeps only those lines (by id, or single pieces by id), plus the pieces they
ride into and the decks they start from. The ramps are laid with planks running across them (piece_uv); a bowl named
in DECALS is painted with its own graphic (editor_decal: from above on its floor, laid down its walls, with a tile band
under its brick coping and a concrete deck). Supports (editor_supports: stone viaducts under every ramp) are
generated from the pieces and the cut ground; they are not the v4 validated supports, so the geometry is still marked
an editor playtest instead of a validated v4 park.

The editor's cut terrain is not a mesh of the park: it is stored as a grid (ground_height, ground_weight) that the
volcano's own terrain follows (craterpark/placement.py terrain), so every surface round the pieces is the volcano's,
with its material, rock and snow, and its collision.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from atelier.atomic_files import managed_temporary_parent

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[2]))

import numpy as np  # noqa: E402
from craterpark.v2 import dsl, generate, v4_config  # noqa: E402
from craterpark.v2.editor import frontend  # noqa: E402

WOOD = 'material_030'     # ramp planks, a Sunburst painting on piece_uv (assets/craterpark/materials.json)
PLANKS = 4.             # metres the ramp-plank texture spans each way (eight boards: half-metre boards)
SIDES = 'material_029'    # the ramps' outer sides: the viaducts' masonry (editor_supports.STONE), world-aligned, so the
                          # stone runs up to the planks as in the concept and only the riding faces are wood
# a bowl named with a key here is painted with that decal material (editor_decal), its plan frame decal_frame:
# tools/craterpark_textures.py DECALS paints it onto a plan rendered with the same frame
DECALS = {'Prado': 'material_031'}
KICK_REACH = 30.        # metres of a capped run's end that count as its launch ramp
GROUND_REACH = 60.     # metres round every kept piece where the volcano takes the editor's cut ground in full
GROUND_FADE = 40.      # metres beyond that over which it eases back to the natural ground
# In a pit a piece cuts (a bowl's), the ground is kept PIT_CLEAR under every piece within PIT_REACH: the volcano samples
# it every 5 m (hidamari/mountains.py STEP), and a 5 m cell's points are all within 7.1 m of its corners, so no
# terrain triangle there rises through the piece.
PIT_REACH = 7.5
PIT_CLEAR = .5
# Round a bowl the ground never rises through it: within BOWL_REACH of its rim and deck the ground stays BOWL_CLEAR
# under them, then may climb back BOWL_SLOPE per metre (so a bowl on a slope sits in a gentle cut, not a wall of earth)
BOWL_REACH = 8.     # metres of flat collar outside a deck: wider than the volcano's STEP, so no terrain triangle
                    # spans from the bowl's pit to the collar and leaves a trench or a poke-through at the rim
BOWL_CLEAR = .05
BOWL_SLOPE = .6
BOWL_EASE = 24.
BOWL_SEAL = 1.    # metres the volcano's sampled surface may sit below a deck edge: a deeper trench is a leak
BOWL_POKE = .3     # metres it may sit above the deck
SIDE_COLOURS = ([0.6, 0.58, 0.54], [0.45, 0.43, 0.4])   # pieces.js COL.side, COL.bottom


def select(doc, lines):
    """The pieces of `lines` (line names, or single piece ids), the pieces they lead into (a bowl they land in) and the
    decks of their starts."""
    keep = {p['id'] for p in doc['pieces'] if p['line'] in lines or p['id'] in lines}
    by = {p['id']: p for p in doc['pieces']}
    for pid in list(keep):
        for n in by[pid].get('next') or []:
            if by[n]['type'] in ('bowl', 'deck'):
                keep.add(n)
    # the start decks: decks of the structure line that the kept roll-ins stand on (within 30 m of their top)
    tops = [(p['x'], p['z']) for p in doc['pieces'] if p['id'] in keep and (p['type'] == 'rollin' or p.get('start'))]
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


def piece_uv(V, stations, size=PLANKS):
    """UVs laid along a piece, so its boards run across the ramp the whole way round its curves: v along the piece
    (its stations' distance), u across it, continuing up the walls (lateral offset plus height above the floor)."""
    S = np.array([(s['d'], s['x'], s['z'], s['y'], math.radians(s['h'])) for s in stations])
    uv = np.zeros((len(V), 2))
    for a in range(0, len(V), 4096):
        P = V[a:a + 4096]
        k = (((P[:, None, [0, 2]] - S[None, :, [1, 2]]) ** 2).sum(2)).argmin(1)
        d, x, z, y, h = S[k].T
        dx, dz = P[:, 0] - x, P[:, 2] - z
        along = dx * np.cos(h) + dz * np.sin(h)
        lat = dx * np.sin(h) - dz * np.cos(h)
        rise = np.maximum(P[:, 1] - y, 0.)
        uv[a:a + 4096] = np.stack([lat + np.sign(lat) * rise, d + along], 1)
    return uv / size


def decal_frame(V):
    """The plan frame (x0, z0, width, height) a decal is painted in: the piece's plan bounds, 4% taller, centred in a
    2:3 portrait frame (the painting's 1024x1536); its top is the piece's lowest z."""
    x0, x1, z0, z1 = V[:, 0].min(), V[:, 0].max(), V[:, 2].min(), V[:, 2].max()
    h = (z1 - z0) * 1.04
    w = h / 1.5
    return (x0 + x1 - w) / 2, (z0 + z1 - h) / 2, w, h


def decal_uv(V, frame):
    x0, z0, w, h = frame
    return np.stack([(V[:, 0] - x0) / w, (V[:, 2] - z0) / h], 1)


def bowl_uv(piece, size=PLANKS, V=None):
    """UVs for a wooden bowl, its boards running round it parallel to its lip as the ramps' boards run along them: v the
    distance round the nearest lip, u the distance down from it (across the deck or floor, plus the drop). `V` are the
    vertices to map (the piece's own by default; a boost zone's cut ones, editor_boost)."""
    from craterpark.v2 import editor_coping
    V = np.asarray(piece.mesh.V if V is None else V, 'f8')
    lips = editor_coping._join(editor_coping.piece_lips(piece))
    if not lips:
        return tile_uv(V, np.tile([0., 1., 0.], (len(V), 1)) if len(V) != len(piece.mesh.N) else np.asarray(piece.mesh.N),
                       size)
    pts, run, base = [], [], 0.
    for lip in lips:
        P = np.asarray(lip[0], 'f8')
        d = np.r_[0., np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        pts.append(P)
        run.append(base + d)
        base += d[-1] + 50.
    P, R = np.concatenate(pts), np.concatenate(run)
    uv = np.zeros((len(V), 2))
    for a in range(0, len(V), 2048):
        Q = V[a:a + 2048]
        k = (((Q[:, None, [0, 2]] - P[None, :, [0, 2]]) ** 2).sum(2)).argmin(1)
        flat = np.hypot(Q[:, 0] - P[k, 0], Q[:, 2] - P[k, 2])
        uv[a:a + 2048] = np.stack([flat + np.maximum(P[k, 1] - Q[:, 1], 0.), R[k]], 1)
    return uv / size


DECK_SINK = .03      # a deck lying flush on another piece sinks this much under it; wheels do not feel 3 cm


def settle_decks(pieces):
    """Sink a deck whose top lies flush (within 2 cm) on another piece's surface over an area, so the two never
    z-fight: the tower floor flickered where the owner's deck met the tower deck at the same height. The solid deck
    (the tower) stays, else the earlier piece. Returns the ids sunk."""
    from craterpark.v2 import editor_supports
    plan = editor_supports.Plan(pieces)
    sink = set()
    for k, piece in enumerate(pieces):
        if piece.metadata['type'] != 'deck':
            continue
        V = piece.mesh.V
        top = V[:, 1].max()
        flush = {}
        for x in np.arange(V[:, 0].min() + .25, V[:, 0].max(), .5):
            for z in np.arange(V[:, 2].min() + .25, V[:, 2].max(), .5):
                who, y = plan.heights(x, z)
                if not ((who == k) & (np.abs(y - top) < .005)).any():
                    continue
                for j in set(who[(who != k) & (np.abs(y - top) < .02)].tolist()):
                    flush[j] = flush.get(j, 0) + 1
        for j, count in flush.items():
            if count < 4:
                continue
            other = pieces[j]
            solid = lambda p: bool((p.metadata.get('params') or {}).get('solid'))
            if other.metadata['type'] != 'deck' or solid(other) and not solid(piece) or \
                    solid(other) == solid(piece) and j < k:
                sink.add(k)
            else:
                sink.add(j)
    for k in sink:
        V = pieces[k].mesh.V.copy()
        V[:, 1] -= DECK_SINK
        pieces[k].mesh.V = V
    return sorted(pieces[k].metadata['id'] for k in sink)


def piece_mesh(piece, decal=None, tower=False, sides=SIDES):
    """The piece's riding faces and sides (`sides`: the timber stage's ramps have keyaki sides, as the concept); a tower
    deck (editor_supports.tower) keeps only its top. A boost zone (editor_boost: params.boost > 0) is cut into its
    sunburst, its riding faces painted; a boosted decal bowl (the Prado) drops its painting for editor_prado's graphics,
    cut into its mesh as sharp as the rest."""
    from craterpark.v2 import editor_boost
    m, meta = piece.mesh, piece.metadata
    V, N, F, col = m.V, m.N, orient(m.V, m.F, m.N), piece.colors
    side = np.zeros(len(F), bool)
    for c in SIDE_COLOURS:
        side |= (np.abs(col[F] - c).max(2) < 0.02).all(1)
    paint, prado, box = None, False, None
    if editor_boost.boosted(piece):
        from craterpark.v2 import editor_coping, editor_prado
        ride_faces, _ = editor_coping._classes(piece)
        classes = np.where(side, 2, np.where(ride_faces, 0, 1))
        V, N = np.asarray(V, 'f8'), np.asarray(N, 'f8')
        rays, centre, box = editor_boost.RAYS, None, None
        if decal:
            rays, (centre, box) = editor_boost.BIG_RAYS, editor_prado.plan(V, N, F, classes)
        V, N, F, classes, paint, sun = editor_boost.paint(piece, V, N, F, classes, rays=rays, centre=centre)
        if decal:
            V, N, F, classes, paint = editor_prado.floor(V, N, F, classes, paint, sun, box=box)
            decal, prado = None, True                      # the graphics are cut in: no painting, no tile band
        side = classes == 2
    parts = []
    # wooden ramps (the park's ramp boards) and wooden bowls; a bowl with its own graphic (DECALS) stays poured concrete
    bowl = meta['type'] == 'bowl'
    concrete = bowl and (decal is not None or prado)
    laid = not bowl and meta.get('stations')
    ride, ride_uv = (dsl.CONCRETE if concrete else WOOD), (piece_uv(V, meta['stations']) if laid else None)
    if bowl and not concrete:
        ride_uv = bowl_uv(piece, V=V)
    surfaces = [(~side, dsl.RIDING, ride, ride_uv)]
    if paint is not None:
        surfaces = [(~side & (paint == None), dsl.RIDING, ride, ride_uv)] + [  # noqa: E711 (an object array)
            (paint == p, dsl.RIDING, p, editor_prado.box_uv(V, box) if p == editor_prado.LETTERS and box else ride_uv)
            for p in editor_boost.PAINTS + editor_prado.PAINTS]
    if decal:
        # the painting on the floor and down the walls, a tile band under the coping, a concrete deck (editor_decal)
        from craterpark.v2 import editor_coping, editor_decal
        ride_faces, deck_faces = editor_coping._classes(piece)
        got, _ = editor_decal.parts(piece, decal, ride_faces & ~side, deck_faces & ~side, decal_frame(V), meta['id'])
        parts += got
        surfaces = []
    for mask, role, material, uv in surfaces + [(side, dsl.SIDE, dsl.SIDE_WALL if concrete else sides, None)]:
        uv = tile_uv(V, N) if uv is None else uv
        if tower:
            mask = mask & (V[F][:, :, 1].min(1) > V[:, 1].max() - .05)
        if mask.any():
            parts.append(dsl.Mesh.part(V, F[mask], N=N, UV=uv, role=role, material=material,
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
    from craterpark.v2 import editor_coping
    bowls = []
    for p in getattr(scene, 'pieces', ()):  # the bowls' riding faces and decks: the ground stays under those
        if p.metadata['type'] == 'bowl':
            ride, deck = editor_coping._classes(p)
            V, F = np.asarray(p.mesh.V), np.asarray(p.mesh.F)
            deck_width = float((p.metadata.get('params') or {}).get('deck', 2.))
            rims = []
            for pts, into, _, closed in editor_coping._join(editor_coping.lip_frames(p)):
                # the deck's outer edge: the coping line moved `deck` metres away from the riding side
                outer = np.asarray(pts, 'f8').copy()
                outer[:, 0] -= into[:, 0] * deck_width
                outer[:, 2] -= into[:, 2] * deck_width
                rims.append((outer, closed))
            bowls.append((rims, V[np.unique(F[ride])],
                          not (p.metadata.get('info') or {}).get('through'), deck_width))
    if bowls:
        H = clear_bowls(H, g, bowls, pit)
    return H.astype('f4'), weight.astype('f4')


def _nearest_edge(rims, g, shape, cells):
    """(distance in metres, rim height) of the nearest point on the closed rim polylines, on the cell-centred grid."""
    dist = np.full(shape, np.inf)
    y = np.full(shape, np.nan)
    X = g['x0'] + (np.arange(shape[1]) + .5) * g['G']
    Z = g['z0'] + (np.arange(shape[0]) + .5) * g['G']
    r = (cells + 1) * g['G']
    for points, closed in rims:
        pts = np.asarray(points, 'f8')
        segs = np.stack([pts, np.roll(pts, -1, 0)], 1) if closed else np.stack([pts[:-1], pts[1:]], 1)
        for a, b in segs:
            i0 = max(0, int(np.floor((min(a[0], b[0]) - r - g['x0']) / g['G'])))
            i1 = min(shape[1], int(np.ceil((max(a[0], b[0]) + r - g['x0']) / g['G'])) + 1)
            j0 = max(0, int(np.floor((min(a[2], b[2]) - r - g['z0']) / g['G'])))
            j1 = min(shape[0], int(np.ceil((max(a[2], b[2]) + r - g['z0']) / g['G'])) + 1)
            if i1 <= i0 or j1 <= j0:
                continue
            xx, zz = np.meshgrid(X[i0:i1], Z[j0:j1])
            dx, dz = b[0] - a[0], b[2] - a[2]
            t = np.clip(((xx - a[0]) * dx + (zz - a[2]) * dz) / max(dx * dx + dz * dz, 1e-12), 0, 1)
            d = np.hypot(xx - a[0] - t * dx, zz - a[2] - t * dz)
            h = a[1] + t * (b[1] - a[1])
            sub = dist[j0:j1, i0:i1]
            better = d < sub
            sub[better] = d[better]
            y[j0:j1, i0:i1][better] = h[better]
    return dist, y


def _lowest(points, g, shape, reach):
    """The lowest height among `points` within `reach` cells of each cell."""
    j = np.round((points[:, 2] - g['z0']) / g['G'] - .5).astype(int)
    i = np.round((points[:, 0] - g['x0']) / g['G'] - .5).astype(int)
    on = (j >= 0) & (j < shape[0]) & (i >= 0) & (i < shape[1])
    low = np.full(shape, np.inf)
    np.minimum.at(low, (j[on], i[on]), points[on, 1])
    return np.minimum.reduce([_shifted(low, dy, dx, np.inf) for dy, dx in _shifts(reach)])


def clear_bowls(H, g, bowls, pit):
    """@cc [owner:fontanierh,label:correctness] editor-bowl-rim-seal
    The ground round the bowls, sealed to their decks. Inside the carved pit the ground MUST stay at least BOWL_CLEAR
    below the bowl's riding surface; within BOWL_EASE of a deck edge it MUST stay BOWL_CLEAR below the coping line
    (allowed to climb BOWL_SLOPE per metre beyond BOWL_REACH). Round an in-ground bowl whose carve cut ground (pit
    not None), lower ground outside the pit MUST be lifted to BOWL_CLEAR below the rim, falling BOWL_SLOPE per metre
    beyond BOWL_REACH, so no trench opens under the deck. Ground away from every bowl MUST be left unchanged.

    Inside the carved pit the ground stays BOWL_CLEAR below the bowl's riding surface. Outside it, the ground
    meets the coping line's height at the nearest point (the deck edge) and may climb BOWL_SLOPE per metre away
    from the deck, up to BOWL_EASE. An in-ground bowl also lifts the ground to its rim where the surrounding
    terrain is lower, so no trench is left under the deck and the outer skirt meets the ground all round. `pit`
    marks the cells the bowl's carve lowered, and is None when the park's bowls cut nothing. `bowls` is
    [(rim polylines, riding points, in_ground, deck width)].
    """
    H = np.asarray(H, 'f8')
    shape = H.shape
    reach = max(1, int(np.ceil(BOWL_REACH / g['G'])))
    ease = max(1, int(np.ceil(BOWL_EASE / g['G'])))
    for rims, rides, in_ground, _deck in bowls:
        dist, rim = _nearest_edge(rims, g, shape, ease)
        near = np.isfinite(rim) & (dist < BOWL_EASE)
        step = np.maximum(dist - BOWL_REACH, 0.)
        cap = rim + BOWL_SLOPE * step - BOWL_CLEAR
        if pit is not None:
            H = np.where(pit, np.minimum(H, _lowest(rides, g, shape, reach) - BOWL_CLEAR), H)
        # the deck edge: never above it, and (for an in-ground bowl) never a trench below it either
        H = np.where(near, np.minimum(H, cap), H)
        if in_ground and pit is not None:
            lift = np.minimum(np.maximum(H, rim - BOWL_SLOPE * step - BOWL_CLEAR), cap)
            H = np.where(near & ~pit, lift, H)
    return H


def check_bowl_seal(scene, heights, g, weight):
    """@cc [owner:fontanierh,label:correctness] editor-bowl-seal-check
    Fail when a bowl rim does not meet the volcano surface it stands in. The check MUST sample the ground the player
    rides (the volcano terrain's own STEP-metre nodes, not the finer cut grid), and MUST fail the build when the
    volcano does not take the cut ground in full round the bowls (blend weight below .999), or when at any in-ground
    bowl's deck edge that ground sits more than BOWL_SEAL below the deck or more than BOWL_POKE above it.

    The volcano's terrain samples the cut grid on its own nodes every hidamari.mountains.STEP metres, so the ground a
    player rides is that sampled surface, not the finer cut grid. At every in-ground bowl's deck edge the ground must
    meet the deck within BOWL_SEAL (no trench under the rim) and must not rise through it. The cut grid is
    authoritative there: weight is 1 round the pieces, and the trail and pad carves are hundreds of metres away.
    """
    from hidamari import natural_terrain as mountains
    from craterpark import placement

    bowls = []
    for piece in getattr(scene, 'pieces', ()):
        if piece.metadata['type'] != 'bowl' or (piece.metadata.get('info') or {}).get('through'):
            continue
        V, F = np.asarray(piece.mesh.V, 'f8'), np.asarray(piece.mesh.F)
        col = np.asarray(piece.colors, 'f8')
        side = np.zeros(len(F), bool)
        for c in SIDE_COLOURS:
            side |= (np.abs(col[F] - c).max(2) < .02).all(1)
        sv = V[np.unique(F[side])]
        bottom = float(sv[:, 1].min()) if len(sv) else 0.
        edge = sv[sv[:, 1] > bottom + 1e-3]          # the outer skirt's top: the deck's outer edge
        if len(edge):
            bowls.append((piece.metadata['id'], edge))
    if not bowls:
        return {'bowls': [], 'samples': 0}

    step = float(mountains.STEP)
    isl = placement.native_to_island(np.concatenate([e for _, e in bowls]))
    pad = 3 * step
    x0 = mountains.GRID_ORIGIN[0] + np.ceil((isl[:, 0].min() - pad - mountains.GRID_ORIGIN[0]) / step) * step
    x1 = mountains.GRID_ORIGIN[0] + np.floor((isl[:, 0].max() + pad - mountains.GRID_ORIGIN[0]) / step) * step
    z0 = mountains.GRID_ORIGIN[1] + np.ceil((isl[:, 1].min() - pad - mountains.GRID_ORIGIN[1]) / step) * step
    z1 = mountains.GRID_ORIGIN[1] + np.floor((isl[:, 1].max() + pad - mountains.GRID_ORIGIN[1]) / step) * step
    xs, zs = np.arange(x0, x1 + step, step), np.arange(z0, z1 + step, step)
    IX, IZ = np.meshgrid(np.arange(len(xs)), np.arange(len(zs)))
    nx, nz = placement.island_to_native_xz(xs[IX], zs[IZ])

    def sample(f, x, z):
        fi = (np.asarray(x) - g['x0']) / g['G'] - .5
        fj = (np.asarray(z) - g['z0']) / g['G'] - .5
        i = np.clip(fi.astype(int), 0, g['nx'] - 2)
        j = np.clip(fj.astype(int), 0, g['nz'] - 2)
        u = np.clip(fi - i, 0, 1); v = np.clip(fj - j, 0, 1)
        return (f[j, i] * (1 - u) * (1 - v) + f[j, i + 1] * u * (1 - v)
                + f[j + 1, i] * (1 - u) * v + f[j + 1, i + 1] * u * v)

    Z, W = sample(heights, nx, nz), sample(weight, nx, nz)
    if W.min() < .999:
        raise ValueError('bowl seal: the volcano does not take the cut ground in full round the bowls')

    def surface(x, z):
        """The terrain's surface, sampled as hidamari.mountains._barycentric samples its grid."""
        isl = placement.native_to_island(np.c_[x, np.zeros_like(x), z])
        u = (isl[:, 0] - x0) / step; v = (isl[:, 1] - z0) / step
        i = np.clip(np.floor(u).astype(int), 0, len(xs) - 2)
        j = np.clip(np.floor(v).astype(int), 0, len(zs) - 2)
        a = np.clip(u - i, 0, 1); b = np.clip(v - j, 0, 1)
        z00, z10, z01, z11 = Z[j, i], Z[j, i + 1], Z[j + 1, i], Z[j + 1, i + 1]
        return np.where(a >= b, z00 * (1 - a) + z10 * (a - b) + z11 * b,
                        z00 * (1 - b) + z11 * a + z01 * (b - a))

    out = {'bowls': [name for name, _ in bowls], 'samples': 0, 'worst_gap_m': 0.}
    for name, edge in bowls:
        gap = edge[:, 1] - surface(edge[:, 0], edge[:, 2])
        out['samples'] += len(gap)
        out['worst_gap_m'] = max(out['worst_gap_m'], round(float(gap.max()), 3))
        k = int(np.argmax(gap))
        if gap[k] > BOWL_SEAL:
            raise ValueError(f'{name}: the ground is {gap[k]:.2f} m below the deck edge at native '
                             f'({edge[k, 0]:.1f}, {edge[k, 2]:.1f}); the bowl rim is not sealed')
        k = int(np.argmin(gap))
        if gap[k] < -BOWL_POKE:
            raise ValueError(f'{name}: the ground is {-gap[k]:.2f} m above the deck edge at native '
                             f'({edge[k, 0]:.1f}, {edge[k, 2]:.1f}); terrain rises through the deck')
    return out


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


BOOST_CHUNK = 10.   # m of a boosted run's length per boost box, so a curved run's boxes hug it


def boost_zones(pieces, doc):
    """The bowls and runs the owner gave a pump and powerslide boost (params.boost, a scale; 0 or absent is none):
    the piece's own riding mesh, walls included, as native point sets. A bowl is one set; a run is cut every
    BOOST_CHUNK metres along its stations, so a U-turn's boxes follow its curve. export.py fits a box to each."""
    import numpy as np
    zones, params = [], {p['id']: p.get('params', {}) for p in doc['pieces']}
    for piece in pieces:
        meta = piece.metadata
        boost = params[meta['id']].get('boost') or 0
        if boost <= 0 or meta['type'] not in ('bowl', 'run'):
            continue
        V = np.asarray(piece.mesh.V, 'f8')
        if meta['type'] == 'bowl' or not meta.get('stations'):
            groups = [V]
        else:
            st = meta['stations']
            S = np.asarray([[s['x'], s['z']] for s in st], 'f8')
            d = np.asarray([s['d'] for s in st], 'f8')
            near = np.argmin(((V[:, None, [0, 2]] - S[None]) ** 2).sum(-1), 1)
            chunk = np.floor((d[near] - d[0]) / BOOST_CHUNK).astype(int)
            groups = [V[chunk == k] for k in np.unique(chunk)]
        for k, pts in enumerate(g for g in groups if len(g) >= 3):
            zones.append({'id': f"{meta['id']}_{k}", 'boost': float(boost), 'points': pts.round(3).tolist()})
    return zones


def main(argv=None):
    import yori
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--park', required=True, help="the editor's park.json (its data/ folder beside it)")
    parser.add_argument('--lines', default=v4_config.editor_lines(),
                        help='comma-separated line ids to build (default: L1, orange)')
    parser.add_argument('--out', default=str(yori.OUT / 'craterpark' / 'v2'))
    args = parser.parse_args(argv)
    from craterpark import placement
    from craterpark.v2 import ao, editor_coping, editor_supports, export, spawns
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
        decals = {p['id']: material for p in chosen['pieces'] for key, material in DECALS.items()
                  if p['type'] == 'bowl' and key in (p.get('name') or '')}
        params = {p['id']: p.get('params') or {} for p in chosen['pieces']}
        for piece in scene.pieces:                 # the bridge leaves the params out; the tower needs `solid`
            piece.metadata['params'] = params.get(piece.metadata['id'], {})
        parts, keep = [], np.concatenate([piece.mesh.V for piece in scene.pieces])
        # the editor's chosen terrain layer, before the pieces cut it
        terrain = json.loads((park_path.parent / 'data' / 'terrain.json').read_text())['inner']
        base = np.fromfile(park_path.parent / 'data' / terrain['layers'][doc['terrain']], '<f4')
        heights, weight = ground_grid(scene, keep, base.reshape(terrain['nz'], terrain['nx']).astype('f8'))
        grid = {k: scene.metadata['ground_grid'][k] for k in ('x0', 'z0', 'G', 'nx', 'nz')}
        bowl_seal = check_bowl_seal(scene, heights, grid, weight)
        print(f"CRATERPARK EDITOR bowl seal: {bowl_seal['bowls']}, {bowl_seal['samples']} rim samples, "
              f"worst gap {bowl_seal['worst_gap_m']:.2f} m", flush=True)
        supports, support_summary = editor_supports.build(scene.pieces, heights, grid)
        print(f"CRATERPARK EDITOR supports: stone viaducts, {support_summary['piers']} piers, "
              f"{support_summary['arches']} arches; timber stages, {support_summary['posts']} posts, "
              f"{support_summary['beams']} beams; {support_summary['metres']} m", flush=True)
        parts += supports
        towers = set(support_summary['towers'])
        if towers:
            print(f"CRATERPARK EDITOR towers: {sorted(towers)}", flush=True)
        sunk = settle_decks(scene.pieces)
        if sunk:
            print(f"CRATERPARK EDITOR flush decks sunk {DECK_SINK * 100:.0f} cm: {sunk}", flush=True)
        for piece in scene.pieces:
            parts += piece_mesh(piece, decals.get(piece.metadata['id']), tower=piece.metadata['id'] in towers,
                                sides=editor_supports.KEYAKI if piece.metadata.get('line') in editor_supports.STAGE_LINES
                                else SIDES)
        caps = {p['id']: (p.get('params') or {}).get('vert_assist_max') for p in chosen['pieces']}
        from craterpark.v2 import editor_boost
        boosts = {p.metadata['id'] for p in scene.pieces if editor_boost.boosted(p)}   # a boosted decal bowl too
        if boosts:
            print(f"CRATERPARK EDITOR boost zones painted (sunburst): {sorted(boosts)}", flush=True)
        copings, rails, coping_summary = editor_coping.build(scene.pieces, caps, brick=set(decals) - boosts,
                                                             gold=boosts)
        print(f"CRATERPARK EDITOR coping: {coping_summary['rails']} grind rails, {coping_summary['metres']} m", flush=True)
        parts += copings
    mesh = dsl.Mesh.concat(parts)
    # the riding line: its pieces in order from the roll-in, the centre line, the start on the roll-in's top
    by = {p.metadata['id']: p for p in scene.pieces}
    ride_lines, labels = [], {}
    for line in lines:
        name = next((l['name'] for l in doc['lines'] if l['id'] == line), line)
        # the line's start: its roll-in, or a piece the owner marked as the start (a drop off a deck edge into the void)
        starts = {p['id'] for p in doc['pieces'] if p.get('start')}
        first = next((p for p in scene.pieces if p.metadata['line'] == line and p.metadata['type'] == 'rollin'), None) \
            or next((p for p in scene.pieces if p.metadata['line'] == line and p.metadata['id'] in starts), None)
        if first is None:          # a single piece (or a line without a start): no riding line of its own
            continue
        order, seen, cur = [], set(), first.metadata['id']
        while cur and cur not in seen and cur in by:
            seen.add(cur)
            order.append(cur)
            cur = next(iter(by[cur].metadata['next']), None)
        path = np.concatenate([by[i].centerline for i in order if len(by[i].centerline)])
        if first.metadata['type'] == 'rollin':
            st = first.metadata['stations'][min(3, len(first.metadata['stations']) - 1)]
            spawn = ((st['x'], st['y'], st['z']), float(st['h']))
        else:                      # a start off an edge: on the deck behind it, back from the edge, facing the drop
            st = first.metadata['stations'][0]
            hr = np.radians(float(st['h']))
            spawn = ((st['x'] - 6 * np.cos(hr), st['y'], st['z'] - 6 * np.sin(hr)), float(st['h']))
        ride_lines.append(dsl.RideLine(line, order, path, spawn, path[-1]))
        labels[line] = name
    park = dsl.Park(mesh, rails, ride_lines, [dict(kind='editor_playtest', rev=doc.get('rev'), lines=lines)])
    generate.declare_scenery(park)
    entries = spawns.entries(park.mesh, park.lines, placement, deck_y=None, labels=labels)
    print('CRATERPARK EDITOR baking occlusion', flush=True)
    ao.bake_mesh(park.mesh, drawn=(dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL))
    # the crater floor round the park (editor_floor): rocks, snow, grass and shrubs on the volcano's own ground. Added
    # after the park's bake, with its own baked in plan tiles: in this one the voxel grid would span the whole crater.
    from craterpark.v2 import editor_floor
    floor, floor_summary = editor_floor.build(scene.pieces, heights, grid, editor_floor.site(heights, weight, grid))
    print(f"CRATERPARK EDITOR crater floor: {floor_summary['triangles']} triangles, "
          f"{floor_summary['conifers']} conifers", flush=True)
    park.mesh = dsl.Mesh.concat([park.mesh, *floor])
    # the floor's conifers are instances of the caldera's tree models (trees.py), planted by the park (park.json trees)
    arrays, index = generate.bundle(park, entries, floor_summary['trees'])
    # the cut ground the volcano's terrain follows (v4_placement.ground_grid), instead of a park mesh over it
    arrays.update(ground_height=heights, ground_weight=weight)
    index.update(v4=provenance, editor_playtest={'rev': doc.get('rev'), 'lines': lines, 'pieces': len(chosen['pieces']),
                                                 'pieces_sha256': scene.metadata['pieces_sha256']},
                 ground_grid=dict(grid, reach=GROUND_REACH, fade=GROUND_FADE),
                 bowl_seal=bowl_seal,
                 accepted=False, validation={'ran': False, 'reason': 'editor playtest: generated supports, not v4-validated'},
                 supports={k: v for k, v in support_summary.items() if k != 'pieces'}, coping=coping_summary,
                 bounds_native=[park.mesh.V.min(0).tolist(), park.mesh.V.max(0).tolist()])
    index['assist_zones_native'] = assist_zones(scene.pieces, doc)
    index['boost_zones_native'] = boost_zones(scene.pieces, doc)
    arrays['index'] = np.asarray(json.dumps(index))
    (out / 'lines').mkdir(exist_ok=True)
    for stale in (out / 'lines').glob('*.npz'):
        stale.unlink()
    for line in park.lines:
        export.line_npz(park.mesh, line, out / 'lines' / f'{line.name}.npz')
    rep = generate.report(park, index, time.monotonic() - start)
    rep.update(layout='editor', v4=provenance, editor_playtest=index['editor_playtest'],
               bounds_native=index['bounds_native'], bowl_seal=bowl_seal)
    temporary = managed_temporary_parent(out / 'geometry.tmp.npz') / 'geometry.tmp.npz'
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
