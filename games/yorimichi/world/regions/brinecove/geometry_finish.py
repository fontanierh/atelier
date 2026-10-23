"""Final coastal collar/face finishing consumes explicit data, never exported meshes."""
import math
import numpy as np
from atelier.mesh_partition import face_groups
from terrain_product import load
from brinecove import ground, rocks
from brinecove import layout as L
from brinecove import region as R
from brinecove.geom import Builder, distinct_corners

TILE = 256.0
MIXED_TRIANGLE_LIMIT = 32768
SOFT = ('leaf_', 'palm_', 'waterfall', 'mist', 'spray', 'foam', 'water', 'vine', 'flower', 'grass', 'fern', 'cover_')
SEA_LEVEL = ('water', 'foam', 'spray', 'mist', 'waterfall', 'seabed')
GROUND_REMAP = {'sand': 'terrain', 'jungle_dark': 'terrain'}


def rim(path):
    """FarHills' hole boundary from its final product (world.farhills)."""
    mesh = load(path, owner='FarHills', stage='final', city=True)
    vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles())
    vertices, triangles = ground.weld(vertices, triangles)
    x0, y0, x1, y1 = R.OUTER_WORLD
    near = ((np.abs(vertices[:, 0] - x0) < .05) | (np.abs(vertices[:, 0] - x1) < .05)
            | (np.abs(vertices[:, 1] - y0) < .05) | (np.abs(vertices[:, 1] - y1) < .05))
    near &= (vertices[:, 0] > x0 - .05) & (vertices[:, 0] < x1 + .05) & (vertices[:, 1] > y0 - .05) & (vertices[:, 1] < y1 + .05)
    keep = near[triangles].sum(1) >= 2
    used = np.unique(triangles[keep])
    remap = {int(v): i for i, v in enumerate(used)}
    local = [[remap[int(v)] for v in t] for t in triangles[keep]]
    return R.rim_from_mesh(vertices[used].tolist(), local)


def settle(rim):
    """(x, y) -> (ground change, game ground) across the collar, where ground.py eases the layout into the far-hills
    rim; (0, None) inside INNER. Dressing placed on the layout moves with the ground under it."""
    cache = {}

    def at(x, y):
        key = (round(x, 1), round(y, 1))
        if key not in cache:
            if R.collar_weight(x, y) <= 0.0:
                cache[key] = (0.0, None)
            else:
                g = R.ground(L.ground, rim, x, y)
                cache[key] = (g - L.ground(x, y), g)
        return cache[key]
    return at


def soft(mat):
    return mat.startswith(SOFT)


def split(builder, prefix, settle, remap=None, *, ceiling=None):
    """Tiles of TILE metres, and per tile a solid part and a soft part (foliage cards, water, spray).

    Faces in the collar follow the eased ground (settle); water, foam and spray stay at sea level, and plant cards
    whose ground went under the sea are dropped. The ground itself is already eased: settle is None for it.
    Faces with a collapsed corner (a cone's apex quad) lose the repeat, and faces with no area are dropped:
    Unreal drops them on import, and the import checks every tile's triangle count against this report."""
    if remap and not callable(ceiling):
        raise ValueError('Ground finishing requires its complete explicit paving query')
    parts, outside, drowned, degenerate = {}, 0, 0, 0
    ox0, oy0, ox1, oy1 = R.OUTER
    anchors = builder.anchors or ()
    for n, (f, mat) in enumerate(zip(builder.faces, builder.mats)):
        pts = [builder.verts[i] for i in f]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        if not (ox0 <= cx <= ox1 and oy0 <= cy <= oy1):
            outside += 1
            continue
        anchor = anchors[n] if n < len(anchors) else None
        if settle is not None and not mat.startswith(SEA_LEVEL):
            # A rigid object (a rock, a prop) moves by its anchor's change as one piece; loose faces follow the
            # ground under each vertex. Moving a rock's vertices apart sheared it into overlapping slabs.
            if anchor == rocks.FIXED:
                moves = [(0.0, None)] * len(pts)  # placed on the final ground already
            elif anchor is not None:
                moves = [settle(*anchor)] * len(pts)
            else:
                moves = [settle(p[0], p[1]) for p in pts]
            if soft(mat) and any(g is not None and g < 0.2 for _, g in moves):
                drowned += 1
                continue
            pts = [(p[0], p[1], p[2] + d) for p, (d, _) in zip(pts, moves)]
        if remap:
            mat = remap.get(mat, mat)
            pts = [(p[0], p[1], min(p[2], ceiling(p[0], p[1]))) for p in pts]
            # A seabed face is chosen by its average height, so on a steep shore one corner can stand above the sea:
            # a flat untextured teal wedge on the beach. The blended terrain layer turns to sand at the waterline.
            if mat == 'seabed' and max(p[2] for p in pts) > -0.05:
                mat = 'terrain'
        corners = distinct_corners(pts)
        if corners is None:
            degenerate += 1
            continue
        key = (int((cx - ox0) // TILE), int((cy - oy0) // TILE), soft(mat))
        part = parts.get(key)
        if part is None:
            part = parts[key] = Builder(f'SM_BC_{prefix}_{key[0]}_{key[1]}' + ('_Soft' if key[2] else ''))
            part.spatial_centers = []
        normals = [builder.normals[f[k]] for k in corners] if builder.normals is not None else None
        part.face([pts[k] for k in corners], mat, [builder.uvs[f[k]] for k in corners], normals)
        part.spatial_centers.append((cx, cy))
    return bounded_parts(parts, prefix), outside, drowned, degenerate


def bounded_parts(parts, prefix):
    """Keep bounded existing tiles/models intact; partition every oversized final mesh.

    Complete faces keep the same positions, UVs, normals, materials and role labels.
    Each piece keeps the parent's identity transform and solid/soft policy. Fixed
    child-cell names stay stable while their ancestor subdivision decisions stay the same.
    """
    result = {}
    for key, part in parts.items():
        x, y, is_soft = key
        if sum(len(face) - 2 for face in part.faces) <= MIXED_TRIANGLE_LIMIT:
            result[(*key, '')] = part
            continue
        x0, y0 = R.OUTER[0] + x * TILE, R.OUTER[1] + y * TILE
        groups = face_groups(part.verts, part.faces, (x0, y0, x0 + TILE, y0 + TILE),
                             triangle_limit=MIXED_TRIANGLE_LIMIT, locations=getattr(part, 'spatial_centers', None))
        parent_water = all(mat.startswith(('water', 'mist', 'spray', 'foam', 'waterfall')) for mat in part.mats)
        roles = getattr(part, 'foliage_roles', {})
        for suffix, indices in groups:
            piece = Builder(part.name + '_Piece' + suffix)
            # Splitting a mixed water/foliage parent must not change its shadow policy.
            piece.parent_water = parent_water
            for index in indices:
                face = part.faces[index]
                piece.anchor = part.anchors[index] if part.anchors is not None else None
                normals = [part.normals[i] for i in face] if part.normals is not None else None
                piece.face([part.verts[i] for i in face], part.mats[index], [part.uvs[i] for i in face], normals)
                if index in roles:
                    if not hasattr(piece, 'foliage_roles'):
                        piece.foliage_roles = {}
                    piece.foliage_roles[len(piece.faces) - 1] = roles[index]
            result[(*key, suffix)] = piece
    return result


def collar_normals(builder, rim, normals, h=1.0):
    """Collar vertices take the eased ground's own gradient: the zipper's long fan triangles to the far-hills rim
    averaged only among themselves and shaded as bands (2026-10-19 capture, note 5)."""
    ox0, oy0, ox1, oy1 = R.OUTER
    memo = {}
    out = list(normals)
    for i, p in enumerate(builder.verts):
        x, y = p[0], p[1]
        if R.collar_weight(x, y) <= 0.0:
            continue
        key = (round(x, 2), round(y, 2))
        if key not in memo:
            xa, xb = max(ox0, x - h), min(ox1, x + h)
            ya, yb = max(oy0, y - h), min(oy1, y + h)
            gx = (R.ground(L.ground, rim, xb, y) - R.ground(L.ground, rim, xa, y)) / max(1e-3, xb - xa)
            gy = (R.ground(L.ground, rim, x, yb) - R.ground(L.ground, rim, x, ya)) / max(1e-3, yb - ya)
            m = math.sqrt(gx * gx + gy * gy + 1.0)
            memo[key] = (-gx / m, -gy / m, 1.0 / m)
        out[i] = memo[key]
    return out


def smooth_normals(builder, crease=0.5):
    """Per-vertex normals for a builder whose faces own their vertices: each corner averages the area-weighted
    normals of the faces meeting at its position that bend less than ~60 degrees from its own face.

    Without them the ground shades flat per triangle: the meadow slopes read as lit facets (playtest note 5)."""
    faces = []
    meet = {}
    for f in builder.faces:
        pts = [builder.verts[i] for i in f]
        nx = ny = nz = 0.0
        for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:] + pts[:1]):
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        if nz < 0:  # a heightfield: every normal points up, whatever a face's winding
            nx, ny, nz = -nx, -ny, -nz
        faces.append((nx, ny, nz))
        for p in pts:
            meet.setdefault((round(p[0], 3), round(p[1], 3), round(p[2], 3)), []).append((nx, ny, nz))
    normals = [None] * len(builder.verts)
    for f, (nx, ny, nz) in zip(builder.faces, faces):
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        own = (nx / length, ny / length, nz / length)
        for i in f:
            p = builder.verts[i]
            sx = sy = sz = 0.0
            for mx, my, mz in meet[(round(p[0], 3), round(p[1], 3), round(p[2], 3))]:
                m = math.sqrt(mx * mx + my * my + mz * mz) or 1.0
                if (mx * own[0] + my * own[1] + mz * own[2]) / m >= crease:
                    sx, sy, sz = sx + mx, sy + my, sz + mz
            s = math.sqrt(sx * sx + sy * sy + sz * sz)
            normals[i] = (sx / s, sy / s, sz / s) if s > 0 else own
    return normals


def area(points):
    """A planar polygon's area from its Newell normal."""
    points = list(points)
    nx = ny = nz = 0.0
    for (x0, y0, z0), (x1, y1, z1) in zip(points, points[1:] + points[:1]):
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return math.sqrt(nx * nx + ny * ny + nz * nz) / 2


def paving_limit(rectangles):
    """@cc [owner:fontanierh,label:correctness] coastal-explicit-final-paving-data
    Use the complete current separately owned flat-paving rectangle inventory. Every
    covered final ground point MUST remain five centimetres below the lowest slab
    underside. No exported sibling mesh or implicit mutable module registry may be
    read to recover this input. Unsupported or nonfinite rectangles MUST refuse.
    """
    rows = tuple(tuple(row) for row in rectangles)
    if any(len(row) != 5 or not all(math.isfinite(v) for v in row)
           or row[1] < row[0] or row[3] < row[2] for row in rows):
        raise ValueError("Invalid final paving rectangle data")
    def ceiling(x, y):
        return min((bottom - .05 for x0, x1, y0, y1, bottom in rows
                    if x0 <= x <= x1 and y0 <= y <= y1), default=math.inf)
    return ceiling
