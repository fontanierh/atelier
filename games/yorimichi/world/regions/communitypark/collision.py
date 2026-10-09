"""Hidden riding collision for the community park: the source triangles, welded, with short ramps over joint lips.

The skating simulation rolls over an edge of at most 12 mm; a taller lip where two separately placed pieces meet stops
the wheels and bails the rider. The rendered pieces keep their exact geometry and stop blocking. This mesh welds
coincident vertices across placements and, wherever a riding edge stands 4 mm to 8 cm proud of the neighbouring
piece's surface, adds a 1:8 wedge from the edge down onto that surface, laid in its plane so bowl walls blend too.
Small floor lips use a 30 cm run where the extra length rests on neighbouring riding surfaces: a short wedge can
abruptly slow the board. Short or curved neighbours keep the prior run rather than carry a floating extension.
Closed pieces also carry vertical end caps at their joins: a swept board can hit them through the meeting
riding surfaces. Remove only caps covered on both sides by adjoining pieces at the same riding height. Taller
steps and exposed walls stay, and so do the grind obstacles (ledges, rails), which are meant to be ollied onto.
An angled underside meeting a riding crest can create a speculative contact above the crest. Fill its small
closed pocket down to the neighbouring slab foundation, retaining a flat ceiling and the outside walls. Riding
tops stay exact. Exposed overhangs, steep kicker noses and pockets over other source riding surfaces stay exact.
Horizontal zero-thickness plates keep their tops and gain a 4 mm underside and perimeter. A coincident ceiling
can make the simulation solver treat a riding rim as a 180-degree fold; a closed thin plate retains the real rim.
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

    def supports_segment(self, a, b, part):
        """Every plan coverage interval lies on a neighbouring riding plane, within the weld tolerance."""
        fractions = np.unique([0., 1., *self.crossings(a[:2], b[:2])])
        fractions = np.r_[fractions, (fractions[:-1]+fractions[1:])/2]
        return all(any(self.owner[k] != part and abs(self.rise(k, point)) <= WELD
                       for k in self.over(*point[:2]))
                   for point in (a+(b-a)*t for t in fractions))


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
    def closed_shell(point, direction, neighbour, riding_height, base):
        """The shell closes within the longest lip ramp to this cap triangle's lowest vertex."""
        outside = point[:2]+direction*PROBE
        if not any(undersides.owner[j] == neighbour and
                   abs(undersides.height(j, *point[:2])-riding_height) <= WELD
                   for j in undersides.over(*outside)):
            return False
        # Probe selects the neighbour; coverage must also include the space next to the cap.
        start = point[:2]+direction*WELD
        end = point[:2]+direction*SLOPE*LIP[1]
        fractions = np.unique([0., 1., *undersides.crossings(start, end)])
        fractions = np.sort(np.r_[fractions, (fractions[:-1]+fractions[1:])/2])
        for fraction in fractions:
            xy = start+(end-start)*fraction
            heights = [undersides.height(j, *xy) for j in undersides.over(*xy)
                       if undersides.owner[j] == neighbour]
            if not heights: return False
            if min(heights) <= base+ROLLABLE+WELD: return True
        return False
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
            if not inside or not any(surfaces.owner[j] != part[k]
                                     and surfaces.height(j, *point[:2]) >= point[2]-LIP[1]
                                     and abs(min(inside)-surfaces.height(j, *point[:2])) <= LIP[1]
                                     and (surfaces.owner[j] in below or
                                          closed_shell(point, direction, surfaces.owner[j],
                                                       surfaces.height(j, *point[:2]), triangle[:, 2].min()))
                                     for j in surfaces.over(*outside)):
                covered = False; break
        if covered: removed.append(k)
    return np.asarray(removed, dtype=int)


def crest_pockets(vertices, faces, owner, obstacles=(), groups=None, evidence=None):
    """Ceiling patches enclosing a small knife-edge pocket beside a riding slab.

    The riding top and the underside share the crest edge. On the other side, another piece's riding top
    meets it and its foundation bounds the pocket. Require continuous underside coverage from the crest to
    that foundation, within the longest lip-ramp reach; a real overhang or underpass must stay collidable.
    Inspect the unmerged source so both material identities and the neighbouring foundations are available.
    """
    triangles = vertices[faces]; normals = _normals(triangles)[0]
    part = np.where(owner < 0, -1-owner, owner)
    if groups is not None: part = np.asarray(groups)[part]
    up = normals[:, 2] > UP
    down = normals[:, 2] < -1e-4
    riding = normals[:, 2] > 1e-4
    floors = Surfaces(triangles[riding], part[riding])
    floor_indices = np.flatnonzero(riding)
    tops = Surfaces(triangles[up], part[up])
    bottoms = Surfaces(triangles[down], part[down])
    edge_faces = {}
    for k, face in enumerate(faces):
        for a, b in zip(face, np.roll(face, -1)):
            edge_faces.setdefault(tuple(sorted((int(a), int(b)))), []).append(k)
    candidates = set(np.flatnonzero((normals[:, 2] <= -UP) & (owner >= 0) & ~np.isin(owner, list(obstacles))).tolist())
    removed = []
    reach = SLOPE*LIP[1]
    def riding_space(patch):
        """Keep any patch over a lower riding surface, except a closed, rollable seam.

        Intersect plan triangles, rather than cast a sparse grid that could miss a narrow lower platform.
        Height differences are linear on each intersection, so its vertices bound every point inside it.
        A closer floor may hide a lower one; retaining the underside in that case is deliberate.
        """
        maximum = None; lower = {}
        for triangle in patch:
            lo = np.floor(triangle[:, :2].min(0)/floors.cell).astype(int)
            hi = np.floor(triangle[:, :2].max(0)/floors.cell).astype(int)
            candidates = set()
            for x in range(lo[0], hi[0]+1):
                for y in range(lo[1], hi[1]+1):
                    candidates.update(floors.index.get((x, y), ()))
            normal = _normals(triangle[None])[0][0]
            for k in candidates:
                polygon = triangle[:, :2].copy()
                boundary = floors.triangles[k, :, :2]
                for a, b in zip(boundary, np.roll(boundary, -1, 0)):
                    if not len(polygon): break
                    direction = b-a
                    side = (direction[0]*(polygon[:, 1]-a[1])-direction[1]*(polygon[:, 0]-a[0]))
                    clipped = []
                    for i in range(len(polygon)):
                        j = (i+1) % len(polygon)
                        if side[i] >= -1e-9: clipped.append(polygon[i])
                        if (side[i] < 0) != (side[j] < 0):
                            clipped.append(polygon[i]+(polygon[j]-polygon[i])*side[i]/(side[i]-side[j]))
                    polygon = np.asarray(clipped).reshape(-1, 2)
                if len(polygon) < 3: continue
                shifted = polygon-polygon[0]
                following = np.roll(shifted, -1, 0)
                area = abs(np.sum(shifted[:, 0]*following[:, 1]-shifted[:, 1]*following[:, 0]))/2
                if area <= 1e-10: continue
                under = triangle[0, 2]-((polygon-triangle[0, :2])@normal[:2])/normal[2]
                floor = np.asarray([floors.height(k, *xy) for xy in polygon])
                gaps = under-floor; gap = float(gaps.max())
                maximum = gap if maximum is None else max(maximum, gap)
                if gap > WELD:
                    index = int(floor_indices[k])
                    lower[index] = {'face': index, 'part': int(floors.owner[k]),
                                     'minimum_gap_m': float(gaps.min()), 'maximum_gap_m': gap}
        return maximum is not None and maximum > ROLLABLE+WELD, maximum, list(lower.values())
    while candidates:
        first = candidates.pop(); patch = {first}; pending = [first]
        # Classify both halves of a planar quad together, without spreading around a facet crease.
        while pending:
            k = pending.pop()
            for a, b in zip(faces[k], np.roll(faces[k], -1)):
                for j in edge_faces[tuple(sorted((int(a), int(b))))]:
                    if j not in candidates or part[j] != part[first]: continue
                    if normals[j]@normals[first] < 1-1e-6: continue
                    if abs((triangles[j, 0]-triangles[first, 0])@normals[first]) > WELD: continue
                    candidates.remove(j); patch.add(j); pending.append(j)
        lookup = Surfaces(triangles[sorted(patch)], np.full(len(patch), part[first]))
        points = triangles[sorted(patch)].reshape(-1, 3)
        boundary = {tuple(sorted((int(a), int(b)))) for k in patch
                    for a, b in zip(faces[k], np.roll(faces[k], -1))}
        receipt = {'faces': sorted(patch), 'filled': False, 'covering_parts': [],
                   'maximum_floor_clearance_m': None}
        for a, b in sorted(boundary):
            neighbours = edge_faces[a, b]
            if not any(k in patch for k in neighbours): continue
            if not any(up[k] and part[k] == part[first] for k in neighbours): continue
            start, end = vertices[[a, b]]
            # A horizontal crest bounds the pocket's highest edge. Sloping exposed side edges don't qualify.
            if abs(start[2]-end[2]) > WELD or points[:, 2].max() > min(start[2], end[2])+WELD: continue
            along = end[:2]-start[:2]; length = np.linalg.norm(along)
            if length <= 2*WELD: continue
            along /= length
            out = np.array([along[1], -along[0]])
            if out@(points[:, :2].mean(0)-start[:2]) < 0: out = -out
            distances = (points[:, :2]-start[:2])@out
            if distances.min() < -WELD or distances.max() > reach+WELD: continue
            inset_start = start[:2]+along*WELD; inset_end = end[:2]-along*WELD
            fractions = [0., 1.]
            for surface in (tops, bottoms):
                fractions.extend(surface.crossings(inset_start-out*PROBE, inset_end-out*PROBE))
            fractions = np.unique(fractions)
            fractions = np.r_[fractions, (fractions[:-1]+fractions[1:])/2]
            closed = True
            covering = []; bases = []
            for fraction in fractions:
                xy = inset_start+(inset_end-inset_start)*fraction
                crest = (start[2]+end[2])/2
                inside = xy-out*PROBE
                neighbours = [j for j in tops.over(*inside) if tops.owner[j] != part[first]
                              and abs(tops.height(j, *xy)-crest) <= WELD]
                foundations = [bottoms.height(k, *xy) for j in neighbours for k in bottoms.over(*inside)
                               if bottoms.owner[k] == tops.owner[j]
                               and WELD < crest-bottoms.height(k, *xy) <= reach]
                # No matching slab foundation means an exposed overhang, rather than a closed little pocket.
                if not foundations: closed = False; break
                covering.append({'fraction': float(fraction),
                                 'parts': sorted({int(tops.owner[j]) for j in neighbours})})
                base = max(foundations); bases.append(base)
                ray_start = xy+out*WELD; ray_end = xy+out*reach
                crossings = np.unique([0., 1., *lookup.crossings(ray_start, ray_end)])
                crossings = np.sort(np.r_[crossings, (crossings[:-1]+crossings[1:])/2])
                closure = False
                for t in crossings:
                    point = ray_start+(ray_end-ray_start)*t
                    heights = [lookup.height(j, *point) for j in lookup.over(*point)]
                    if not heights: break
                    if min(heights) <= base+ROLLABLE+WELD: closure = True; break
                if not closure: closed = False; break
            if closed:
                usable, maximum, lower_rows = riding_space(triangles[sorted(patch)])
                receipt.update(covering_parts=covering, maximum_floor_clearance_m=maximum,
                               upward_faces_below=lower_rows, usable_riding_space_below=usable)
                if not usable and max(bases)-min(bases) <= WELD:
                    # A plane that stays below the neighbouring riding top cannot create the crest ghost.
                    behind = inset_start-out*PROBE
                    if lookup.height(0, *behind) > (start[2]+end[2])/2+WELD:
                        removed.extend(patch); receipt.update(filled=True, ceiling_z=min(bases))
                break
        if evidence is not None: evidence.append(receipt)
    return np.asarray(sorted(removed), dtype=int)


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
    def slope(point, under, drop, direction, extend=True):
        """Extend the prior run only when its added length stays on existing neighbouring riding planes."""
        n = surfaces.normal[under]; slide = np.array([*direction, 0.]); slide -= (slide@n)*n
        slide /= np.linalg.norm(slide)
        length = max(SLOPE*drop, .1)
        foot = point-drop*n+slide*length
        if not extend or length >= MIN_RUN: return foot
        extended = point-drop*n+slide*MIN_RUN
        return extended if surfaces.supports_segment(foot, extended, part) else foot

    def add(tri, k, part):
        tri = np.asarray(tri)
        # Face the same way as the neighbour the wedge comes down onto.
        if np.cross(tri[1]-tri[0], tri[2]-tri[0])@surfaces.normal[k] < 0: tri = tri[[0, 2, 1]]
        added.append(tri); added_owner.append(-1-part)

    for part, out, samples, surfaces in _open_edges(vertices, faces, owner, obstacles):
        wedged = [r is not None and s is not None and max(r, s) >= LIP[0]
                  for (_, r, _), (_, s, _) in zip(samples, samples[1:])]
        along = samples[-1][0][:2]-samples[0][0][:2]; along /= np.linalg.norm(along)
        short = [None if k is None else slope(p, k, r, out, False) for p, r, k in samples]
        feet = [None if k is None else slope(p, k, r, out) for p, r, k in samples]
        tips, short_tips = {}, {}
        for i, (p, r, k) in enumerate(samples):
            if r is None or r < LIP[0]: continue
            for sign, end in ((-1, i < len(wedged) and wedged[i] and (i == 0 or not wedged[i-1])),
                              (1, i > 0 and wedged[i-1] and (i == len(wedged) or not wedged[i]))):
                if end:
                    tips[i, sign] = slope(p, k, r, sign*along)
                    short_tips[i, sign] = slope(p, k, r, sign*along, False)
        # A shortened endpoint is shared by both adjacent ramp segments. Recheck their foot edges until
        # none of the added length cuts across a neighbour's boundary, including the end taper.
        changed = True
        while changed:
            changed = False
            for i, use in enumerate(wedged):
                if not use or all(np.array_equal(feet[j], short[j]) for j in (i, i+1)): continue
                if not surfaces.supports_segment(feet[i], feet[i+1], part):
                    feet[i], feet[i+1] = short[i], short[i+1]; changed = True
            for key, tip in list(tips.items()):
                i, _ = key
                if np.array_equal(feet[i], short[i]) and np.array_equal(tip, short_tips[key]): continue
                if any(surfaces.owner[j] != part for j in surfaces.over(*tip[:2])) and not surfaces.supports_segment(feet[i], tip, part):
                    feet[i], tips[key] = short[i], short_tips[key]; changed = True
        for i, ((p, r, k), (q, s, m)) in enumerate(zip(samples, samples[1:])):
            if not wedged[i]: continue
            fp, fq = feet[i], feet[i+1]
            add([p, q, fq], k, part); add([p, fq, fp], k, part)
            # Where a run stops, taper its side down along the edge too rather than leave a vertical cheek.
            for end, (point, rise, under, foot), sign in ((i == 0 or not wedged[i-1], (p, r, k, fp), -1),
                                                          (i == len(wedged)-1 or not wedged[i+1], (q, s, m, fq), 1)):
                if not end or rise < LIP[0]: continue
                tip = tips[(i if sign < 0 else i+1), sign]
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
    pockets = []
    undersides = crest_pockets(vertices, faces, owner, obstacles, groups, pockets)
    added_faces, added_parts = [], []
    for pocket in pockets:
        if not pocket['filled']: continue
        indices = pocket['faces']; level = pocket['ceiling_z']
        boundary = {}
        for k in indices:
            flat = vertices[faces[k]].copy(); flat[:, 2] = level
            added_faces.append(flat); added_parts.append(owner[k])
            for a, b in zip(faces[k], np.roll(faces[k], -1)):
                key = tuple(sorted((int(a), int(b))))
                if key in boundary: boundary.pop(key)
                else: boundary[key] = (int(a), int(b))
        highest = vertices[faces[indices], 2].max()
        for a, b in boundary.values():
            a, b = vertices[[a, b]]
            # The crest is internal to the adjoining solid slab. A cap here would recreate its riding snag.
            if min(a[2], b[2]) >= highest-WELD: continue
            fa, fb = a.copy(), b.copy(); fa[2] = fb[2] = level
            for triangle in (np.array([a, b, fb]), np.array([a, fb, fa])):
                if _normals(triangle[None])[1][0] <= 1e-10: continue
                added_faces.append(triangle); added_parts.append(owner[indices[0]])
    keep = np.ones(len(faces), bool); keep[np.r_[buried, undersides]] = False
    faces, owner = faces[keep], owner[keep]
    if added_faces:
        start = len(vertices)
        vertices = np.vstack([vertices, np.concatenate(added_faces)])
        faces = np.vstack([faces, start+np.arange(3*len(added_faces)).reshape(-1, 3)])
        owner = np.r_[owner, added_parts]
    report['filled_crest_pockets'] = sum(p['filled'] for p in pockets)
    report['filled_underside_triangles'] = len(undersides)
    report['fill_skirt_triangles'] = len(added_faces)-len(undersides)
    if added or added_faces:
        vertices, faces, keep = _merge(vertices, faces); owner = owner[keep]
    vertices, faces, owner, sheet_report = solid_sheet_undersides(vertices, faces, owner, obstacles, groups)
    report.update(sheet_report)
    report['buried_wall_triangles'] = len(buried)
    report['triangles'] = len(faces)
    return vertices, faces, owner, report


def solid_sheet_undersides(vertices, faces, owner, obstacles=(), groups=None):
    """Give horizontal, coincident top/back plates thickness without moving their riding faces.

    Only backs with a surviving reversed rim against the same piece's coplanar top form a patch. An adjoining
    back beneath a curved top stays authored. Lower the selected backs by two weld cells, and skirt free edges
    whose sole reverse partner was the mirror. Unpaired T-edges and rims joined to non-mirror faces do not gain
    a contact partner. Flush neighbours include sloped riding aprons; partly joined patches stay authored.
    Fully joined patches change only when a whole rim meets a horizontal slab, the measured floor-seam case.
    Patches connected only through sloped aprons stay authored.
    Patches with every mirrored riding rim covered by another top within 3 cm also stay unchanged.
    Existing solid slabs, tilted shells and obstacles retain their original geometry and collision.
    """
    triangles = vertices[faces]; normals = _normals(triangles)[0]
    part = np.where(owner < 0, -1-owner, owner)
    if groups is not None: part = np.asarray(groups)[part]
    down = set(np.flatnonzero((normals[:, 2] < -.99999) & (owner >= 0)
                             & ~np.isin(owner, list(obstacles))).tolist())
    edges = {}
    for k, face in enumerate(faces):
        for a, b in zip(face, np.roll(face, -1)):
            edges.setdefault(tuple(sorted((int(a), int(b)))), []).append((k, int(a), int(b)))
    seeds = set()
    for k in down:
        for a, b in zip(faces[k], np.roll(faces[k], -1)):
            if any(j != k and x == b and y == a and part[j] == part[k]
                   and normals[j, 2] > .99999
                   and np.max(abs((triangles[j]-triangles[k, 0])@normals[k])) <= .0001
                   for j, x, y in edges[tuple(sorted((int(a), int(b))))]):
                seeds.add(k)
    down.intersection_update(seeds)
    tops = Surfaces(triangles[normals[:, 2] > 0], part[normals[:, 2] > 0])
    riding = Surfaces(triangles[normals[:, 2] > 0], part[normals[:, 2] > 0])
    selected, visited, extra, extra_owner, patches, partial, covered = set(), set(), [], [], 0, 0, 0
    for seed in sorted(seeds):
        if seed in visited: continue
        patch, pending = set(), [seed]
        while pending:
            k = pending.pop()
            if k in patch: continue
            patch.add(k)
            for a, b in zip(faces[k], np.roll(faces[k], -1)):
                for j, _, _ in edges[tuple(sorted((int(a), int(b))))]:
                    if (j in down and j not in patch and part[j] == part[seed]
                            and np.max(abs((triangles[j]-triangles[seed, 0])@normals[seed])) <= .0001):
                        pending.append(j)
        visited.update(patch)
        boundary = {}
        for k in sorted(patch):
            for a, b in zip(faces[k], np.roll(faces[k], -1)):
                key = tuple(sorted((int(a), int(b))))
                if key in boundary: boundary.pop(key)
                else: boundary[key] = (k, int(a), int(b))
        skirt = []; partly_joined = False; exposed = False; flat_join = False
        for k, a, b in boundary.values():
            partners = [j for j, x, y in edges[tuple(sorted((a, b)))]
                        if j not in patch and x == b and y == a]
            if not partners or any(normals[j]@normals[k] >= -.99
                                   or np.max(abs((triangles[j]-triangles[k, 0])@normals[k])) > .0001
                                   for j in partners):
                continue
            a, b = vertices[[a, b]]
            fractions = np.unique([0., 1., *riding.crossings(a[:2], b[:2])])
            for fraction in (fractions[:-1]+fractions[1:])/2:
                point = a+(b-a)*fraction
                if not any(riding.owner[j] != part[seed]
                           and -WELD <= riding.height(j, *point[:2])-point[2] <= .03
                           for j in riding.over(*point[:2])):
                    exposed = True; break
            direction = b[:2]-a[:2]; out = np.array([-direction[1], direction[0]])/np.linalg.norm(direction)
            # A flush neighbour can meet a long rim through a T-junction, with no equal edge key.
            # Check every plan interval on both probes; a partial join keeps the original patch rather
            # than split its riding rim into more unmatched edges.
            fractions = np.unique([0., 1., *tops.crossings(a[:2]+out*WELD, b[:2]+out*WELD),
                                   *tops.crossings(a[:2]+out*2*WELD, b[:2]+out*2*WELD)])
            joined = []; flat = []
            for fraction in (fractions[:-1]+fractions[1:])/2:
                point = a+(b-a)*fraction
                # Probe coverage outside the rim, but compare the neighbouring plane at the rim itself:
                # a flush sloped apron drops slightly at the probe and must not gain an internal wall.
                joined.append(all(any(abs(tops.height(j, *point[:2])-point[2]) <= .0001
                                      for j in tops.over(*xy))
                                  for xy in (point[:2]+out*WELD, point[:2]+out*2*WELD)))
                flat.append(all(any(tops.normal[j, 2] > .99999
                                    and abs(tops.height(j, *point[:2])-point[2]) <= .0001
                                    for j in tops.over(*xy))
                                for xy in (point[:2]+out*WELD, point[:2]+out*2*WELD)))
            if any(joined):
                if not all(joined): partly_joined = True; break
                flat_join |= all(flat)
                continue
            skirt.append((a, b))
        if partly_joined:
            partial += 1; continue
        if not exposed or (not skirt and not flat_join):
            covered += 1; continue
        for k in sorted(patch):
            lowered = triangles[k].copy(); lowered[:, 2] -= 2*WELD
            extra.append(lowered); extra_owner.append(owner[k])
        for a, b in skirt:
            fa, fb = a.copy(), b.copy()
            fa[2] -= 2*WELD; fb[2] -= 2*WELD
            extra.extend((np.array([a, b, fb]), np.array([a, fb, fa])))
            extra_owner.extend((owner[seed], owner[seed]))
        selected.update(patch); patches += 1
    report = {'solid_sheet_patches': patches, 'partial_sheet_patches_kept': partial,
              'covered_sheet_patches_kept': covered,
              'lowered_sheet_triangles': len(selected),
              'sheet_skirt_triangles': len(extra)-len(selected)}
    if not selected: return vertices, faces, owner, report
    keep = np.ones(len(faces), bool); keep[list(selected)] = False
    start = len(vertices)
    vertices = np.vstack([vertices, np.concatenate(extra)])
    faces = np.vstack([faces[keep], start+np.arange(3*len(extra)).reshape(-1, 3)])
    owner = np.r_[owner[keep], extra_owner]
    vertices, faces, keep = _merge(vertices, faces)
    return vertices, faces, owner[keep], report


def steps(vertices, faces, owner, obstacles=(), limit=ROLLABLE):
    """Open riding edges standing more than `limit` (the skate's rollable edge) above a neighbouring piece and no
    more than LIP[1]: (point, rise, piece). Taller steps and the obstacles are deliberate."""
    return [(p, r, part) for part, _, samples, _ in _open_edges(vertices, faces, owner, obstacles)
            for p, r, _ in samples if r is not None and limit < r <= LIP[1]]
