"""The boost zones' look: the owner's Giant sunburst (assets/craterpark/concepts/editor/boost-look-sunrays.jpg).

Every editor piece the owner gave a boost (params.boost > 0, as editor_generate.boost_zones) is painted: a gold sun
disc on its floor, ringed in gold, and alternating hot magenta and warm yellow rays radiating from it across the floor
and up every ridden wall to a gold coping (editor_coping.build). The paint is a glossy lacquer over the ramp's boards
(tools/craterpark_textures.py BOOST_PAINTS: the planks' own painting recoloured, its grain kept faint); the decks, the
sides and every other piece stay as they are.

The rays are cut into the piece's own faces, not painted on a texture: every ray edge is a vertical plane through the
sun's centre, so it runs straight across the floor and straight up a wall, and the sun and its ring are exact circles
in plan. Each region then takes its own material on the boards' UVs (editor_generate.piece_uv / bowl_uv, computed
on the cut mesh), so the edges are as sharp as the geometry at any distance, with no texture resolution to blur and no
seam where a polar map would wrap. The cost is one mesh per paint colour per 64 m render tile the piece touches
(split.py), a few draw calls for the whole park.

Where the sun sits:
- a bowl: the area centroid of its floor; RAYS rays round the full circle, a magenta ray centred on the piece's heading;
- a U-turn (a run with corner: true): the turn's centre (the circle through its stations), on the inside of the turn,
  so the sun rises from the inner edge and the rays fan straight across the floor to the outer wall; an odd number of
  rays as wide as RAYS round a circle fills the turn exactly, magenta at both ends;
- any other boosted run: its middle station, as a bowl.
"""
import math

import numpy as np

MAGENTA = 'material_050'    # hot magenta lacquer over the boards (tools/craterpark_textures.py BOOST_PAINTS)
YELLOW = 'material_051'     # warm yellow lacquer
SUN = 'material_052'        # the sun disc: deeper gold lacquer
GOLD = 'material_053'       # polished gold: the sun's ring and the boost pieces' coping (editor_coping.build)
PAINTS = (MAGENTA, YELLOW, SUN, GOLD)
RAYS = 14                   # rays round a full circle, alternating magenta and yellow (an even number)
BIG_RAYS = 36               # ...round a decal bowl (editor_prado: the Prado), far longer than the others, so its
                            # rays stay a few metres wide up its walls
SUN_RADIUS = 6.5            # metres: the sun disc's radius on a bowl's or a straight run's floor
SUN_REACH = 5.              # metres a U-turn's sun reaches past the turn's inner floor edge
RING = .3                   # metres: the gold ring's width, inside the sun's edge
OUTLINE = 4                 # cut lines per ray width round the sun: its edge is a polygon of RAYS * OUTLINE sides
NEAR = 1.                   # metres past the sun within which its outline lines cut the faces
SNAP = 2e-3                 # metres: a vertex this close to a cut lies on it (no sliver is made)
FLAT = .98                  # a vertex normal this close to up is floor


def boosted(piece):
    """Whether the piece is a boost zone: params.boost > 0 (the editor's own params, editor_generate.main)."""
    return ((piece.metadata.get('params') or {}).get('boost') or 0) > 0 and piece.metadata['type'] not in ('deck', 'rail')


def _circle(points):
    """(centre (2,), radius) of the least-squares circle through plan points (k, 2)."""
    x, z = points[:, 0], points[:, 1]
    A = np.c_[2 * x, 2 * z, np.ones(len(x))]
    (cx, cz, c), *_ = np.linalg.lstsq(A, x * x + z * z, rcond=None)
    return np.array([cx, cz]), math.sqrt(max(c + cx * cx + cz * cz, 0.))


def layout(piece, V, N, F, ride, rays=RAYS, centre=None):
    """The sunburst of a boosted piece: {'centre': (x, z), 'start': angle (rad) of the first ray edge, 'width': a
    ray's angle (rad), 'count': rays (None: round the full circle), 'radius': the sun's radius}. V, N, F, `ride` (face
    mask) are the piece's riding mesh; `centre` (plan) places a bowl's or a run's sun instead (editor_prado.plan)."""
    meta = piece.metadata
    floor = ride & (N[F][:, :, 1] > FLAT).all(1)
    stations = meta.get('stations') or []
    width = 2 * math.pi / rays
    if meta['type'] == 'run' and (meta.get('params') or {}).get('corner') and len(stations) >= 3:
        S = np.array([[s['x'], s['z']] for s in stations])
        centre, _ = _circle(S)
        angles = np.unwrap(np.arctan2(S[:, 1] - centre[1], S[:, 0] - centre[0]))
        turn = angles[-1] - angles[0]
        count = max(1, int(round(abs(turn) / width)))
        count += 1 - count % 2                                       # odd: magenta at both ends
        inner = np.hypot(*(V[np.unique(F[floor])][:, [0, 2]] - centre).T).min() if floor.any() else 0.
        return {'centre': centre, 'start': float(min(angles[0], angles[-1])), 'width': abs(turn) / count,
                'count': count, 'radius': float(inner + SUN_REACH)}
    if centre is not None:
        pass                                                        # placed by the caller
    elif meta['type'] == 'bowl' and floor.any():
        t = V[F[floor]]
        area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        centre = (t.mean(1)[:, [0, 2]] * area[:, None]).sum(0) / area.sum()
    elif stations:
        mid = min(stations, key=lambda s: abs(s['d'] - stations[-1]['d'] / 2))
        centre = np.array([mid['x'], mid['z']])
    else:
        centre = V[:, [0, 2]].mean(0)
    heading = math.radians(stations[0]['h']) if stations else 0.
    return {'centre': np.asarray(centre, 'f8'), 'start': heading - width / 2, 'width': width, 'count': None,
            'radius': SUN_RADIUS, 'rays': rays}


def _cut(V, F, X, parent, field, crossing, faces=None):
    """Split the faces (V, F) where `field` (per vertex) changes sign: a vertex on each crossed edge, at `crossing(a, b)`
    (its t along the edge from a), shared by both faces on the edge; each side fanned in the face's winding. A vertex
    within SNAP of the cut counts as on it. X (per vertex attributes) is interpolated, `parent` (per face) inherited.
    `faces` (mask) limits the faces cut. Returns (V, F, X, parent)."""
    side = np.sign(field)
    side[np.abs(field) < SNAP] = 0
    s = side[F]
    split = (s > 0).any(1) & (s < 0).any(1)
    if faces is not None:
        split &= faces
    if not split.any():
        return V, F, X, parent
    n0 = len(V)
    new_V, new_X = [], []
    made, out, owner = {}, [], []

    def cut(a, b):
        key = (min(a, b), max(a, b))
        if key not in made:
            t = crossing(*key)
            new_V.append(V[key[0]] + t * (V[key[1]] - V[key[0]]))
            new_X.append(X[key[0]] + t * (X[key[1]] - X[key[0]]))
            made[key] = n0 + len(new_V) - 1
        return made[key]

    for f in np.flatnonzero(split):
        tri, st = F[f].tolist(), side[F[f]]
        for keep in (1, -1):
            poly = []
            for i in range(3):
                a, b = tri[i], tri[(i + 1) % 3]
                if st[i] == keep or st[i] == 0:
                    poly.append(a)
                if st[i] * st[(i + 1) % 3] < 0:
                    poly.append(cut(a, b))
            out += [[poly[0], poly[j], poly[j + 1]] for j in range(1, len(poly) - 1)]
            owner += [parent[f]] * (len(poly) - 2)
    if new_V:
        V = np.concatenate([V, np.array(new_V, V.dtype)])
        X = np.concatenate([X, np.array(new_X, X.dtype)])
    F = np.concatenate([F[~split], np.array(out, 'i8').reshape(-1, 3)])
    parent = np.concatenate([parent[~split], np.array(owner, 'i8')])
    return V, F, X, parent


def _line(V, F, X, parent, centre, angle, faces=None):
    """Cut along the vertical plane through `centre` (plan) at `angle`: exact, the field is linear in plan."""
    d = np.array([math.cos(angle), math.sin(angle)])
    field = (V[:, 0] - centre[0]) * d[1] - (V[:, 2] - centre[1]) * d[0]

    def crossing(a, b):
        return field[a] / (field[a] - field[b])
    return _cut(V, F, X, parent, field, crossing, faces)


def _ring(V, F, X, parent, centre, radius):
    """Cut along the vertical cylinder of `radius` round `centre`: each crossing exactly on the circle in plan."""
    P = V[:, [0, 2]] - centre
    field = np.linalg.norm(P, axis=1) - radius

    def crossing(a, b):
        p, q = P[a], P[b] - P[a]
        A, B, C = q @ q, 2 * p @ q, p @ p - radius * radius
        roots = (-B + np.array([-1., 1.]) * math.sqrt(max(B * B - 4 * A * C, 0.))) / (2 * A)
        ok = roots[(roots >= -1e-9) & (roots <= 1 + 1e-9)]
        return float(np.clip(ok[0] if len(ok) else field[a] / (field[a] - field[b]), 0., 1.))
    return _cut(V, F, X, parent, field, crossing)


def _angles(sun):
    """The ray edges' angles (rad) and the sun outline's extra cut angles."""
    w, start = sun['width'], sun['start']
    if sun['count'] is None:
        half = sun.get('rays', RAYS) // 2
        rays = [start + k * w for k in range(half)]                  # a line through the centre cuts both halves
        fine = [start + (k + j / OUTLINE) * w for k in range(half) for j in range(1, OUTLINE)]
    else:
        rays = [start + k * w for k in range(sun['count'] + 1)]
        fine = [start + (k + j / OUTLINE) * w for k in range(sun['count']) for j in range(1, OUTLINE)]
    return rays, fine


def paint(piece, V, N, F, classes, ride=0, rays=RAYS, centre=None):
    """The boosted piece's faces cut into its sunburst: (V, N, F, cls, material, sun). `classes` (per original face,
    small ints: the riding faces `ride`, the decks, the sides) comes back per new face as `cls`; `material` (per face) is
    the paint of a riding face and None elsewhere (decks and sides keep theirs). Every face of the piece is cut, so the
    piece keeps conforming within itself; the sun's outline lines cut only near the sun, and the T-junctions they leave
    where they stop are split (tjunction.fix_tjunctions)."""
    from .tjunction import fix_tjunctions
    classes = np.asarray(classes)
    sun = layout(piece, V, N, F, classes == ride, rays, centre)
    centre, radius = sun['centre'], sun['radius']
    parent = np.arange(len(F))
    rays, fine = _angles(sun)
    for a in rays:
        V, F, N, parent = _line(V, F, N, parent, centre, a)
    r2_limit = (radius + NEAR) ** 2
    for a in fine:
        dx = V[:, 0] - centre[0]
        dz = V[:, 2] - centre[1]
        v_near = (dx * dx + dz * dz) < r2_limit
        near = v_near[F[:, 0]] | v_near[F[:, 1]] | v_near[F[:, 2]]
        V, F, N, parent = _line(V, F, N, parent, centre, a, near)
    for r in (radius - RING, radius):
        V, F, N, parent = _ring(V, F, N, parent, centre, r)
    # split per class, so each face keeps its original's class
    out, cls = [], []
    for c in np.unique(classes):
        mask = classes[parent] == c
        V, Fc, _, N = fix_tjunctions(V, F[mask], attrs=N)
        out.append(Fc)
        cls.append(np.full(len(Fc), c))
    F, cls = np.concatenate(out), np.concatenate(cls)
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    c = V[F].mean(1)[:, [0, 2]] - centre
    r = np.linalg.norm(c, axis=1)
    k = np.floor(((np.arctan2(c[:, 1], c[:, 0]) - sun['start']) % (2 * math.pi)) / sun['width']).astype(int)
    material = np.where(r < radius - RING, SUN, np.where(r < radius, GOLD, np.where(k % 2 == 0, MAGENTA, YELLOW)))
    material = np.where(cls == ride, material, None)
    return V, N, F, cls, material, sun
