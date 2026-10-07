"""Hidden riding collision for the community park: the source triangles, welded, with short ramps over joint lips.

The native skate rolls over an edge of at most 12 mm; a taller lip where two separately placed pieces meet stops
the wheels and bails the rider. The rendered pieces keep their exact geometry and stop blocking. This mesh welds
coincident vertices across placements and, wherever a riding edge stands 4 mm to 8 cm proud of the neighbouring
piece's surface, adds a 1:8 wedge from the edge down onto that surface, laid in its plane so bowl walls blend too.
The run is at least 30 cm: a short wedge over a small floor lip can abruptly slow the board.
Closed pieces also carry vertical end caps at their joins: a swept board can hit them through the meeting
riding surfaces. Remove only caps covered on both sides by adjoining pieces at the same riding height. Taller
steps and exposed walls stay, and so do the grind obstacles (ledges, rails), which are meant to be ollied onto.
"""
import numpy as np

LIP = (.004, .08)       # rises that get a wedge; below is flush, above is a ledge
SLOPE = 8.              # wedge run per metre of rise
MIN_RUN = .3           # small floor lips need a gentle change in slope
UP = .5                 # riding surfaces face up at least this much
WELD = .002
ROLLABLE = .012
SEGMENT = .1
PROBE = .02


def _normals(triangles):
    n = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    length = np.linalg.norm(n, axis=1)
    return n/np.maximum(length, 1e-12)[:, None], length/2


class Surfaces:
    """Plan lookup of upward triangles: which ones lie over a point, and their planes there."""

    def __init__(self, triangles, owner, cell=.5):
        self.triangles, self.owner, self.cell = triangles, owner, cell
        self.normal = _normals(triangles)[0]
        lo = np.floor(triangles[:, :, :2].min(1)/cell).astype(int); hi = np.floor(triangles[:, :, :2].max(1)/cell).astype(int)
        self.index = {}
        for k, (a, b) in enumerate(zip(lo, hi)):
            for i in range(a[0], b[0]+1):
                for j in range(a[1], b[1]+1):
                    self.index.setdefault((i, j), []).append(k)

    def over(self, x, y):
        """Indices of the triangles whose plan contains (x, y)."""
        found = []
        for k in self.index.get((int(np.floor(x/self.cell)), int(np.floor(y/self.cell))), ()):
            a, b, c = self.triangles[k, :, :2]
            d = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(d) < 1e-12: continue
            u = ((x-a[0])*(c[1]-a[1])-(y-a[1])*(c[0]-a[0]))/d; v = ((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/d
            if u >= -1e-9 and v >= -1e-9 and u+v <= 1+1e-9: found.append(k)
        return found

    def crossings(self, a, b):
        """Fractions where a plan segment enters or leaves a triangle, including narrow gaps."""
        a, b = np.asarray(a), np.asarray(b)
        lo_cell = np.floor(np.minimum(a, b)/self.cell).astype(int)
        hi_cell = np.floor(np.maximum(a, b)/self.cell).astype(int)
        candidates = set()
        for i in range(lo_cell[0], hi_cell[0]+1):
            for j in range(lo_cell[1], hi_cell[1]+1):
                candidates.update(self.index.get((i, j), ()))
        if not candidates: return []
        triangles = self.triangles[list(candidates), :, :2]
        origin = triangles[:, 0]; ab = triangles[:, 1]-origin; ac = triangles[:, 2]-origin
        determinant = ab[:, 0]*ac[:, 1]-ab[:, 1]*ac[:, 0]
        valid = abs(determinant) >= 1e-12
        origin, ab, ac, determinant = origin[valid], ab[valid], ac[valid], determinant[valid]
        def weights(point):
            offset = point-origin
            u = (offset[:, 0]*ac[:, 1]-offset[:, 1]*ac[:, 0])/determinant
            v = (ab[:, 0]*offset[:, 1]-ab[:, 1]*offset[:, 0])/determinant
            return np.column_stack((u, v, 1-u-v))
        first = weights(a); change = weights(b)-first
        lo, hi = np.zeros(len(first)), np.ones(len(first))
        for start, delta in zip(first.T, change.T):
            moving = abs(delta) > 1e-12
            crossing = np.divide(-start, delta, out=np.zeros_like(start), where=moving)
            lo = np.where(delta > 1e-12, np.maximum(lo, crossing), lo)
            hi = np.where(delta < -1e-12, np.minimum(hi, crossing), hi)
            hi = np.where(~moving & (start < -1e-9), -1., hi)
        valid = lo <= hi
        return np.concatenate((lo[valid], hi[valid])).tolist()

    def height(self, k, x, y):
        """Height of triangle k's plane at (x, y), so a neighbour that only starts beyond an edge still extends to it."""
        n = self.normal[k]; p = self.triangles[k, 0]
        return float(p[2]-(n[0]*(x-p[0])+n[1]*(y-p[1]))/n[2])

    def rise(self, k, point):
        """Distance of a point above triangle k's plane, measured along its normal."""
        return float((point-self.triangles[k, 0])@self.normal[k])


def _rise(surfaces, point, out, part):
    """How far a riding edge point stands proud of the other pieces' surface just outside it.

    0 when another piece is flush with it or covers it; None for open air or a real step."""
    probe = point[:2]+out*PROBE; lower = []
    for k in surfaces.over(*probe):
        if surfaces.owner[k] == part: continue
        rise = surfaces.rise(k, point)
        if rise < LIP[0]: return 0., k
        # A wedge (negative owner) only ever covers an edge; the step is measured against the pieces themselves.
        if rise <= LIP[1] and surfaces.owner[k] >= 0: lower.append((rise, k))
    return min(lower) if lower else (None, None)


def weld(parts):
    """All non-degenerate triangles of the placed pieces with coincident corners welded: vertices, faces, owner piece."""
    triangles, owner = [], []
    for k, (vertices, faces) in enumerate(parts):
        t = np.asarray(vertices, float)[np.asarray(faces)]; keep = _normals(t)[1] > 1e-10
        triangles.append(t[keep]); owner.append(np.full(keep.sum(), k))
    triangles, owner = np.concatenate(triangles), np.concatenate(owner)
    keys, ids = np.unique(np.round(triangles.reshape(-1, 3)/WELD).astype(np.int64), axis=0, return_inverse=True)
    vertices = np.zeros((len(keys), 3)); vertices[ids.ravel()] = triangles.reshape(-1, 3)
    faces = ids.reshape(-1, 3)
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    keep &= _normals(vertices[faces])[1] > 1e-10
    return vertices, faces[keep], owner[keep]


def _merge(vertices, faces):
    """Weld coincident vertices so consecutive wedges share edges: vertices, faces and the indices of the faces kept."""
    keys, ids = np.unique(np.round(vertices/WELD).astype(np.int64), axis=0, return_inverse=True)
    merged = np.zeros((len(keys), 3)); merged[ids.ravel()] = vertices
    faces = ids.ravel()[faces]
    # Drop what welding collapsed, and repeats, so the importer keeps every remaining triangle.
    keep = np.flatnonzero(_normals(merged[faces])[1] > 1e-6)
    keep = np.sort(keep[np.unique(np.sort(faces[keep], 1), axis=0, return_index=True)[1]])
    return merged, faces[keep], keep


def buried_walls(vertices, faces, owner, obstacles=(), groups=None):
    """Indices of vertical piece faces covered by riding surfaces on both sides.

    Closed ramp pieces bring their end caps to every joint. Although the riding surfaces meet, the skate's
    swept board can hit those buried faces and reverse. Keep exposed walls, tall steps and grind obstacles;
    remove a cap only when another piece meets the same riding height along its boundary and covers its vertical
    span. Existing lip ramps count as coverage. groups identifies material primitives of the same placed piece.
    """
    triangles = vertices[faces]
    normals = _normals(triangles)[0]
    up = normals[:, 2] > 1e-4
    # A lip ramp belongs to the piece whose edge it ramps.
    part = np.where(owner < 0, -1-owner, owner)
    if groups is not None: part = np.asarray(groups)[part]
    surfaces = Surfaces(triangles[up], part[up])
    down = normals[:, 2] < -1e-4
    undersides = Surfaces(triangles[down], part[down])
    removed = []
    for k in np.flatnonzero((abs(normals[:, 2]) < .01) & (owner >= 0)):
        if owner[k] in obstacles: continue
        direction = normals[k, :2]; direction = direction/np.linalg.norm(direction)
        triangle = triangles[k]
        centre = triangle.mean(0)
        samples = [centre]
        # Inset the boundary slightly so adjoining, unrelated outside edges don't defeat a buried joint.
        boundary = triangle*.999+centre*.001
        for a, b in zip(boundary, np.roll(boundary, -1, 0)):
            length = np.linalg.norm(b[:2]-a[:2])
            fractions = np.linspace(0., 1., max(1, int(np.ceil(length/SEGMENT)))+1).tolist()
            # A fixed spacing alone can skip a slot between two neighbours. Split at every plan coverage
            # boundary and check each interval, however narrow, as well as the height samples.
            for lookup, side in ((surfaces, -1), (surfaces, 1), (undersides, 1)):
                fractions.extend(lookup.crossings(a[:2]+side*direction*PROBE, b[:2]+side*direction*PROBE))
            fractions = np.unique(fractions)
            fractions = np.unique(np.r_[fractions, (fractions[:-1]+fractions[1:])/2])
            samples.extend(a+(b-a)*fraction for fraction in fractions)
        covered = True
        for point in samples:
            inside = [surfaces.height(j, *point[:2]) for j in surfaces.over(*(point[:2]-direction*PROBE))
                      if surfaces.owner[j] == part[k]]
            inside = [height for height in inside if height >= point[2]-LIP[1]]
            outside = point[:2]+direction*PROBE
            # Select the neighbour just outside the cap, then extend its plane to the cap itself.
            below = {undersides.owner[j] for j in undersides.over(*outside)
                     if undersides.height(j, *point[:2]) <= point[2]+ROLLABLE+WELD}
            # Use the nearest riding level, and require the neighbour's solid span to cover the wall.
            # Foundation offsets no larger than the rollable edge plus weld tolerance are closed joints;
            # a roof at the same height must not remove the exposed wall of an underpass below it.
            if not inside or not any(surfaces.owner[j] != part[k] and surfaces.owner[j] in below
                                     and surfaces.height(j, *point[:2]) >= point[2]-LIP[1]
                                     and abs(min(inside)-surfaces.height(j, *point[:2])) <= LIP[1]
                                     for j in surfaces.over(*outside)):
                covered = False; break
        if covered: removed.append(k)
    return np.asarray(removed, dtype=int)


def _open_edges(vertices, faces, owner, obstacles=()):
    """Each open edge of the riding surface, sampled every SEGMENT, with its rise over the neighbouring piece.

    Yields (piece, outward plan direction, [(point, rise, neighbour)], surfaces)."""
    up = np.flatnonzero(_normals(vertices[faces])[0][:, 2] > UP)
    surfaces = Surfaces(vertices[faces[up]], owner[up])
    # Edges used by one upward face bound the riding surface.
    edges = np.concatenate([faces[up][:, [i, (i+1) % 3]] for i in range(3)])
    third = np.concatenate([faces[up][:, (i+2) % 3] for i in range(3)])
    piece = np.tile(owner[up], 3)
    _, first, count = np.unique(np.sort(edges, 1), axis=0, return_index=True, return_counts=True)
    for e in first[count == 1]:
        a, b = vertices[edges[e]]; c = vertices[third[e]]; part = piece[e]
        along = b[:2]-a[:2]; length = np.linalg.norm(along)
        if part in obstacles or length < .01: continue
        out = np.array([along[1], -along[0]])/length
        if out@(c[:2]-a[:2]) > 0: out = -out
        points = np.linspace(a, b, max(1, int(np.ceil(length/SEGMENT)))+1)
        samples = [[p, *_rise(surfaces, p, out, part)] for p in points]
        # Where a joint grows past a lip into a step, carry the last lip's neighbour one sample on so its ramp ends
        # at the step rather than a sample short of it.
        for i, j in [(i, j) for i in range(len(samples)) for j in (i-1, i+1) if 0 <= j < len(samples)]:
            if samples[i][1] is None and samples[j][1] is not None and samples[j][1] >= LIP[0]:
                rise = surfaces.rise(samples[j][2], samples[i][0])
                if LIP[0] <= rise <= 2*LIP[1]: samples[i][1:] = [rise, samples[j][2]]
        yield part, out, [tuple(sample) for sample in samples], surfaces


def riding_collision(parts, obstacles=(), groups=None):
    """parts: (vertices, faces) for each placed piece, in park-local metres; obstacles: indices of pieces kept sharp.

    Returns (vertices, faces, owner, report). owner is the piece of each face; a wedge belongs to -1-piece, the
    piece whose edge it ramps, so audits see it as a neighbour. groups optionally gives each part's placed-piece
    identity when materials split one piece into several parts."""
    vertices, faces, owner = weld(parts)
    added, added_owner = [], []
    report = {'welded_vertices': len(vertices), 'wedges': 0, 'max_rise_m': 0., 'wedged_length_m': 0.}
    def slope(point, under, drop, direction):
        """Foot of a 1:SLOPE run from an edge point down onto the neighbour's plane, heading `direction` in plan."""
        n = surfaces.normal[under]; slide = np.array([*direction, 0.]); slide -= (slide@n)*n
        return point-drop*n+slide/np.linalg.norm(slide)*max(SLOPE*drop, MIN_RUN)

    def add(tri, k, part):
        tri = np.asarray(tri)
        # Face the same way as the neighbour the wedge comes down onto.
        if np.cross(tri[1]-tri[0], tri[2]-tri[0])@surfaces.normal[k] < 0: tri = tri[[0, 2, 1]]
        added.append(tri); added_owner.append(-1-part)

    for part, out, samples, surfaces in _open_edges(vertices, faces, owner, obstacles):
        wedged = [r is not None and s is not None and max(r, s) >= LIP[0]
                  for (_, r, _), (_, s, _) in zip(samples, samples[1:])]
        along = samples[-1][0][:2]-samples[0][0][:2]; along /= np.linalg.norm(along)
        for i, ((p, r, k), (q, s, m)) in enumerate(zip(samples, samples[1:])):
            if not wedged[i]: continue
            fp, fq = slope(p, k, r, out), slope(q, m, s, out)
            add([p, q, fq], k, part); add([p, fq, fp], k, part)
            # Where a run stops, taper its side down along the edge too rather than leave a vertical cheek.
            for end, (point, rise, under, foot), sign in ((i == 0 or not wedged[i-1], (p, r, k, fp), -1),
                                                          (i == len(wedged)-1 or not wedged[i+1], (q, s, m, fq), 1)):
                if not end or rise < LIP[0]: continue
                tip = slope(point, under, rise, sign*along)
                if any(surfaces.owner[j] != part for j in surfaces.over(*tip[:2])): add([point, foot, tip], under, part)
            report['wedges'] += 1; report['max_rise_m'] = max(report['max_rise_m'], r, s)
            report['wedged_length_m'] += float(np.linalg.norm(q[:2]-p[:2]))
    if added:
        start = len(vertices)
        vertices = np.vstack([vertices, np.concatenate(added)])
        faces = np.vstack([faces, start+np.arange(3*len(added)).reshape(-1, 3)])
        owner = np.concatenate([owner, added_owner])
    # A floor's top can coincide with a ramp's underside. Keep both piece identities until the cap check;
    # merging repeats first would discard the ramp's foundation and leave a buried cap at that joint.
    buried = buried_walls(vertices, faces, owner, obstacles, groups)
    keep = np.ones(len(faces), bool); keep[buried] = False
    faces, owner = faces[keep], owner[keep]
    if added:
        vertices, faces, keep = _merge(vertices, faces); owner = owner[keep]
    report['buried_wall_triangles'] = len(buried)
    report['triangles'] = len(faces)
    return vertices, faces, owner, report


def steps(vertices, faces, owner, obstacles=(), limit=ROLLABLE):
    """Open riding edges standing more than `limit` (the skate's rollable edge) above a neighbouring piece and no
    more than LIP[1]: (point, rise, piece). Taller steps and the obstacles are deliberate."""
    return [(p, r, part) for part, _, samples, _ in _open_edges(vertices, faces, owner, obstacles)
            for p, r, _ in samples if r is not None and limit < r <= LIP[1]]
