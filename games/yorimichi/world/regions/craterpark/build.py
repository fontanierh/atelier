"""Build Crater Park's Unreal interchange files from the committed library arrays (docs/CRATERPARK.md).

Run with Blender. Every mesh except the helpers is kept, with no simplification:
- render: one mesh per source mesh, without the faces its `render_skip` hides (coplanar flicker), smoothed only
  across edges under SMOOTH degrees; the PLAIN roles, drawn with world-aligned materials, are simplified (simplify);
  foundation faces lying on a drawn riding surface are left out (covered); every drawn vertex carries its baked
  ambient occlusion in its vertex colour (ambient_occlusion);
- collision: what is drawn, as Mega Park's riding collision (megapark/build.py): the riding surfaces exactly, never
  simplified, and the other roles simplified; no face lying on a riding surface (a foundation's top, a coincident
  duplicate facing the other way), which the board met as a second contact millimetres off the ramp and bailed on;
  no face inside the solid under the ramps (hidden_walls, sink_inside); sections of at most SECTION triangles.
park.json places them on the caldera floor for ASuperUltraMegaPark::Spawn (placement.py).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori
from craterpark import additions, grind, placement, tunnel

import bpy
import bmesh
import hashlib
import json
import math
import numpy as np

SOURCE = placement.SOURCE
OUT = yori.OUT / 'craterpark'
MESH_ROOT = '/Game/CraterPark/Meshes'
SMOOTH = 35.0           # degrees: sharper edges keep their crease
SECTION = 200000        # collision triangles per mesh
# Roles drawn with world-aligned materials (import_craterpark.py): their UVs are unused, so their flat faces are merged.
PLAIN = {'foundation', 'mountain', 'access_bridge', 'bridge_support', 'boundary'}
# Where two meshes' faces lie on each other, the earlier role's is drawn: the riding pieces, then the built walls and
# blocks, the added pieces (after the bridges), the hillside last (its dark rock showed in patches on the perimeter walls).
ROLES = ('original', 'boundary', 'foundation', 'access_bridge', 'bridge_support', 'mountain')
FLAT = .5              # degrees: faces this close to coplanar are merged (a shape-preserving simplification)
COVER = .05             # metres: foundation faces this close to a drawn riding surface, and parallel to it, are not drawn
TWIN = .01              # metres: a riding face this close to another facing the opposite way is its double-sided twin
FLICKER = .03           # metres: drawn faces of two meshes this close and parallel z-fight; one of them is drawn
RECEDE = .005           # metres a drawn face lying in part on a higher-ranked mesh's face moves back (recede)
CHUNK = 20000           # points or vertices per vectorised batch (covered, ambient_occlusion): bounds the memory
PAIRS = 2_000_000       # point-face candidate pairs per batch at most (covered): about 0.6 GB
CELLS = 4_000_000       # surface cell entries indexed at once at most (covered): about 0.7 GB while indexing
HIDE = 1.              # metres: a steep face's top edge this far under riding faces on both sides is inside the solid
WALL_SIDE = .02         # metres either side of a steep face's top edge (across it) that hidden_walls probes for a riding face
EDGE = 1e-9             # barycentric slack: a probe on the shared edge of two riding faces lies over them
WALL_STEP = .03         # metres: a riding face this far below the top edge at a probe still covers it (a slope, not a riser)
WALL_FLUSH = .005       # metres a riding face lies above a steep face's top edge at least, for the edge to be inside the solid
LARGE = 8.              # metres across: a collision face this large is stored with the other large ones (spatial_order)
SINK = .25              # metres the collision's corners inside the solid move down, out of the board's reach
# Baked ambient occlusion, per drawn vertex (ambient_occlusion): voxel size and reach in metres, rays and steps per ray.
AO_VOXEL = .5
AO_REACH = 12.
AO_RAYS = 16
AO_STEPS = 10


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_to_blender(values):
    result = np.asarray(values)[:, [0, 2, 1]].copy()
    result[:, 1] *= -1
    return result


def ue(point):
    return [point[0] * 100., point[2] * 100., point[1] * 100.]


def export_mesh(name, vertices, faces, materials, face_materials, uvs=None, smooth=None, ao=None):
    """As megapark/build.py export_mesh: an FBX about a local origin on a 32 m grid, native units, Y up. Its smoothing
    groups go with the normals: without them the FBX import warns, which crashes a windowless (null RHI) editor. `ao`
    (per vertex, linear) goes in the vertex colour, sRGB-encoded in the FBX (import_craterpark.py decodes it)."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    origin = np.round((vertices.min(axis=0).astype('f8') + vertices.max(axis=0)) / 2 / 32) * 32
    data = bpy.data.meshes.new(name)
    data.from_pydata(native_to_blender(vertices.astype('f8') - origin).tolist(), [], faces.tolist())
    data.update()
    for key in materials:
        data.materials.append(bpy.data.materials.get(key) or bpy.data.materials.new(key))
    data.polygons.foreach_set('material_index', np.asarray(face_materials, dtype='i4'))
    if uvs is not None:
        loops = np.empty(len(data.loops), dtype='i4')
        data.loops.foreach_get('vertex_index', loops)
        uv = uvs.copy(); uv[:, 1] = 1 - uv[:, 1]
        data.uv_layers.new(name='UVMap').data.foreach_set('uv', uv[loops].ravel())
    if ao is not None:
        colour = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        rgba = np.repeat(np.asarray(ao, 'f4')[:, None], 4, 1); rgba[:, 3] = 1.
        colour.data.foreach_set('color', rgba.ravel())
    if (uvs is not None) if smooth is None else smooth:
        data.shade_smooth()
        data.set_sharp_from_angle(angle=math.radians(SMOOTH))
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = OUT / 'fbx' / f'{name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
        axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='FACE',
        use_tspace=uvs is not None, bake_anim=False, add_leaf_bones=False, path_mode='STRIP', colors_type='SRGB')
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    result = {'name': name, 'fbx': f'fbx/{name}.fbx', 'sha256': sha(path), 'native_origin': origin.tolist(),
              'bounds': {'minimum': lo.tolist(), 'maximum': hi.tolist()}, 'vertices': len(vertices), 'triangles': len(faces),
              'materials': materials}
    bpy.data.meshes.remove(data, do_unlink=True)
    return result


def simplify(vertices, faces):
    """The same surface with fewer triangles: shared corners welded and nearly coplanar faces (FLAT) merged, then
    triangulated again. Returns (vertices, faces)."""
    data = bpy.data.meshes.new('simplify')
    data.from_pydata(vertices.astype('f8').tolist(), [], np.asarray(faces).tolist())
    bm = bmesh.new(); bm.from_mesh(data); bpy.data.meshes.remove(data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(FLAT), verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table(); bm.verts.index_update()
    v = np.array([p.co[:] for p in bm.verts], 'f4')
    f = np.array([[p.index for p in face.verts] for face in bm.faces], 'i8').reshape(-1, 3)
    bm.free()
    return v, f[valid(v, f)]


def spatial_order(triangles, cell=1.):
    """The order of the `triangles` (n, 3, 3) along a Z-order curve of their centres over CELL-metre cells, those over
    LARGE metres across last. The skate simulation groups a snapshot's triangles 64 at a time in their stored order and
    tests each group's box: stored in this order, a group is a few metres across instead of the whole park (the
    simplified foundations' groups spanned 433 m, so every query met all of them and a step took up to 186 ms), and the
    few large faces share their own groups."""
    t = triangles.astype('f8'); centres = t.mean(1)
    large = np.linalg.norm(t.max(1) - t.min(1), axis=1) > LARGE
    q = np.floor((centres - centres.min(0)) / cell).astype('u8') & 0x1fffff
    code = np.zeros(len(q), 'u8')
    for bit in range(21):
        for axis in range(3):
            code |= ((q[:, axis] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(3 * bit + axis)
    return np.lexsort((code, large))


def valid(positions, triangles):
    t = positions[triangles].astype('f8')
    return np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-12


def unit_normals(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)


def cell_keys(cells):
    """Integer cells (..., 3) packed into one int64 key each."""
    c = cells.astype('i8') + (1 << 20)
    return (c[..., 0] << 42) | (c[..., 1] << 21) | c[..., 2]


def covered(triangles, surfaces, two_sided, eps=COVER, cell=1., ranks=None):
    """Mask of `triangles` (n, 3, 3) that lie on the drawn riding `surfaces` (m, 3, 3): the centroid and the three corners
    are each within eps of the plane of a surface triangle facing the same way (either way where `two_sided`), and inside
    it, or within eps of its edges. Drawn under the riding surface they only flicker through it. With `ranks` (the
    triangles', the surfaces'), only a surface of a lower rank counts."""
    t = triangles.astype('f8'); nt = unit_normals(t)
    points = np.concatenate([t.mean(1, keepdims=True), t], 1).reshape(-1, 3)
    on = lying_on(points, np.repeat(nt, 4, 0), surfaces, two_sided, eps, eps, cell,
                  None if ranks is None else (np.repeat(ranks[0], 4), ranks[1]))
    return on.reshape(-1, 4).all(1)


def lying_on(points, normals, surfaces, two_sided, eps, margin, cell=1., ranks=None, pairs=False):
    """Mask of the `points` (k, 3), each on a face with unit normal `normals` (k, 3), that lie within eps of the plane of
    a surface triangle (m, 3, 3) facing the same way (either way where `two_sided`), inside it or within `margin` of its
    edges. With `ranks` (the points', the surfaces'), only a surface of a lower rank counts. With `pairs`, the (point,
    surface) index pairs instead."""
    s = surfaces.astype('f8'); ns = unit_normals(s)
    lo = np.floor((s.min(1) - eps) / cell).astype('i8'); hi = np.floor((s.max(1) + eps) / cell).astype('i8')
    size = hi - lo + 1; count = size.prod(1); total = np.cumsum(count)
    k = cell_keys(np.floor(points / cell))
    on = np.zeros(len(points), bool); found = []
    # The surfaces are indexed in batches of at most CELLS cell entries: a large face spans thousands of cells.
    bounds = np.unique(np.concatenate([[0], np.searchsorted(total, np.arange(CELLS, total[-1] if len(s) else 0, CELLS)), [len(s)]]))
    for s0, s1 in zip(bounds[:-1], bounds[1:]):
        c = count[s0:s1]
        owner = s0 + np.repeat(np.arange(s1 - s0), c)
        local = np.arange(c.sum()) - np.repeat(np.cumsum(c) - c, c)
        sx, sy = size[owner, 0], size[owner, 1]
        keys = cell_keys(lo[owner] + np.stack([local % sx, (local // sx) % sy, local // (sx * sy)], -1))
        del local, sx, sy
        order = np.argsort(keys, kind='stable'); keys, owner = keys[order], owner[order]
        first = np.searchsorted(keys, k, 'left'); pairs_ = np.cumsum(np.searchsorted(keys, k, 'right') - first)
        # Batches of points bounded by their candidate pairs, not their count: a dense cell holds thousands of faces.
        cuts = np.unique(np.concatenate([np.arange(0, len(points), CHUNK), np.searchsorted(pairs_, np.arange(PAIRS, pairs_[-1] if len(pairs_) else 0, PAIRS)), [len(points)]]))
        for start, end in zip(cuts[:-1], cuts[1:]):
            p = points[start:end]; n = normals[start:end]
            a = first[start:end]; reps = np.diff(pairs_[start:end], prepend=pairs_[start - 1] if start else 0)
            which = np.repeat(np.arange(len(p)), reps)
            cand = owner[np.repeat(a, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
            q = p[which]; v = s[cand]; m = ns[cand]
            facing = (n[which] * m).sum(1)
            ok = (np.abs(((q - v[:, 0]) * m).sum(1)) < eps) & ((facing > .98) | (two_sided[cand] & (facing < -.98)))
            for i in range(3):
                e = v[:, (i + 1) % 3] - v[:, i]
                inward = (np.cross(e, q - v[:, i]) * m).sum(1) / np.maximum(np.linalg.norm(e, axis=1), 1e-12)
                ok &= inward > -margin
            if ranks is not None:
                ok &= ranks[1][cand] < ranks[0][start + which]
            on[start + which[ok]] = True
            if pairs:
                found.append(np.stack([start + which[ok], cand[ok]], 1))
    if pairs:
        return np.concatenate(found) if found else np.zeros((0, 2), 'i8')
    return on


def recede(meshes, ranks, two_sided, eps=FLICKER, depth=RECEDE):
    """The drawn `meshes` [(vertices, faces)] with every face lying on a face of a lower-ranked mesh in part moved back
    `depth` along its normal. Faces lying on one wholly are left out before (covered); a face only partly on another (a
    foundation wall behind the side of a riding piece, the hillside against a block's wall) stays, and the two exactly
    coplanar faces z-fight, worst far away. A few millimetres behind, the depth test always draws the higher-ranked one.
    Its corners move, still shared with the neighbouring faces, so nothing cracks. `ranks` and `two_sided` are per mesh.
    Returns the new vertices of each mesh and the number of faces moved."""
    t = [v[f].astype('f8') for v, f in meshes]; owner = np.repeat(np.arange(len(t)), [len(x) for x in t])
    every = np.concatenate(t); n = unit_normals(every); r = np.asarray(ranks)[owner]
    points = np.concatenate([every.mean(1, keepdims=True), every], 1).reshape(-1, 3); pn = np.repeat(n, 4, 0)
    pr = np.repeat(r, 4)
    lies = lying_on(points, pn, every, np.asarray(two_sided)[owner], eps, eps, ranks=(pr, r)).reshape(-1, 4).any(1)
    # A lower-ranked face inside a larger one: a corner of it lies on the larger face.
    lies[lying_on(points, pn, every, np.ones(len(every), bool), eps, eps, ranks=(-pr, -r), pairs=True)[:, 1]] = True
    out, start = [], 0
    for (v, f), x in zip(meshes, t):
        back = lies[start:start + len(x)]; start += len(x)
        push = np.zeros((len(v), 3)); np.add.at(push, f[back].ravel(), np.repeat(n[start - len(x):start][back], 3, 0))
        length = np.linalg.norm(push, axis=1, keepdims=True); moved = length[:, 0] > 1e-9
        v = v.copy(); v[moved] = v[moved] - (depth * push[moved] / length[moved]).astype(v.dtype)
        out.append((v, int(back.sum())))
    return out


def riding_above(riding, cell=2.):
    """A test over the upward riding faces `riding` (m, 3, 3): above(points, low, high) is the mask of the points (k, 3)
    with a riding face over them, between low and high (k,) in height."""
    s = riding.astype('f8')
    lo = np.floor(s.min(1)[:, [0, 2]] / cell).astype('i8'); hi = np.floor(s.max(1)[:, [0, 2]] / cell).astype('i8')
    size = hi - lo + 1; count = size.prod(1)
    owner = np.repeat(np.arange(len(s)), count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    cells = lo[owner] + np.stack([local % size[owner, 0], local // size[owner, 0]], -1)
    keys = (cells[:, 0] + (1 << 20)) << 21 | (cells[:, 1] + (1 << 20))
    order = np.argsort(keys, kind='stable'); keys, owner = keys[order], owner[order]

    def above(points, low, high):
        c = np.floor(points[:, [0, 2]] / cell).astype('i8'); k = (c[:, 0] + (1 << 20)) << 21 | (c[:, 1] + (1 << 20))
        start = np.searchsorted(keys, k, 'left'); pairs = np.cumsum(np.searchsorted(keys, k, 'right') - start)
        found = np.zeros(len(points), bool)
        cuts = np.unique(np.concatenate([np.arange(0, len(points), CHUNK), np.searchsorted(pairs, np.arange(PAIRS, pairs[-1] if len(pairs) else 0, PAIRS)), [len(points)]]))
        for i0, i1 in zip(cuts[:-1], cuts[1:]):
            reps = np.diff(pairs[i0:i1], prepend=pairs[i0 - 1] if i0 else 0)
            which = np.repeat(np.arange(i0, i1), reps)
            cand = owner[np.repeat(start[i0:i1], reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
            p = points[which]; v = s[cand]
            d = (v[:, 1, 2] - v[:, 2, 2]) * (v[:, 0, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (v[:, 0, 2] - v[:, 2, 2])
            ok = np.abs(d) > 1e-12; d = np.where(ok, d, 1.)
            l1 = ((v[:, 1, 2] - v[:, 2, 2]) * (p[:, 0] - v[:, 2, 0]) + (v[:, 2, 0] - v[:, 1, 0]) * (p[:, 2] - v[:, 2, 2])) / d
            l2 = ((v[:, 2, 2] - v[:, 0, 2]) * (p[:, 0] - v[:, 2, 0]) + (v[:, 0, 0] - v[:, 2, 0]) * (p[:, 2] - v[:, 2, 2])) / d
            l3 = 1 - l1 - l2
            y = l1 * v[:, 0, 1] + l2 * v[:, 1, 1] + l3 * v[:, 2, 1]
            hit = ok & (l1 >= -EDGE) & (l2 >= -EDGE) & (l3 >= -EDGE) & (y >= low[which]) & (y <= high[which])
            found[which[hit]] = True
        return found
    return above


def inside(points, above, across=None):
    """Mask of the points (k, 3) inside the park's solid: a riding face lies over the point (WALL_FLUSH to HIDE above it)
    and over its neighbours WALL_SIDE away (from WALL_STEP below, where a slope falls away, to HIDE above): on both sides
    along `across` (k, 3), a wall's horizontal normal, or else in all four directions."""
    if across is None:
        side = np.broadcast_to(WALL_SIDE * np.array([[0, 0, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]]), (len(points), 5, 3))
    else:
        side = WALL_SIDE * across[:, None] * np.array([0, 1, -1])[None, :, None]
    probes = (points[:, None] + side).reshape(-1, 3); m = side.shape[1]
    y = np.repeat(points[:, 1], m)
    low = y - np.tile([-WALL_FLUSH] + [WALL_STEP] * (m - 1), len(points))
    return above(probes, low, y + HIDE).reshape(-1, m).all(1)


def hidden_walls(triangles, above):
    """Mask of the steep `triangles` (n, 3, 3) whose top edge lies inside the park's solid (inside, at three points along
    it). Inside, the foundations' shared walls and the pieces' sides run up to a few centimetres under the ramps; the
    board's contacts met them head-on there and threw the rider off at speed (a runout). A riser of WALL_STEP or more, or
    an outer wall, with a drop on one side, keeps its face. The probes go across the wall only: a cross wall's top
    corner at a ramp's outer edge is still inside."""
    t = triangles.astype('f8'); n = unit_normals(t)
    steep = np.flatnonzero(np.abs(n[:, 1]) < .7)
    mask = np.zeros(len(t), bool)
    if not len(steep):
        return mask
    # The top edge: the edge with the highest corners, level or slanting along a slope; or, for a wall's lower half
    # (one corner at the top, a diagonal down), that top corner alone.
    w = t[steep]; rows = np.arange(len(w))
    first = np.argmax(np.stack([w[:, i, 1] + w[:, (i + 1) % 3, 1] for i in range(3)], 1), 1)
    a = w[rows, first]; b = w[rows, (first + 1) % 3]
    along = np.stack([a + (b - a) * f for f in (.1, .5, .9)], 1).reshape(-1, 3)
    corner = w[rows, np.argmax(w[:, :, 1], 1)]
    inward = (w.mean(1) - corner) * [1, 0, 1]                          # along the wall, off a ramp's outer corner
    corner = corner + WALL_SIDE / 2 * inward / np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 1e-9)
    across = n[steep] * [1, 0, 1]; across /= np.linalg.norm(across, axis=1, keepdims=True)
    probes = inside(np.concatenate([along, corner]), above, np.concatenate([np.repeat(across, 3, 0), across]))
    mask[steep] = probes[:len(along)].reshape(-1, 3).all(1) | probes[len(along):]
    return mask


def sink_inside(triangles, above):
    """The collision `triangles` (n, 3, 3) with every corner inside the park's solid moved SINK down: a wall partly
    inside (an outer corner showing) keeps its shape outside and drops its hidden top out of the board's reach."""
    t = triangles.copy(); corners = t.reshape(-1, 3)
    hidden = inside(corners.astype('f8'), above)
    corners[hidden, 1] -= SINK
    return t, int(hidden.sum())


def ao_directions(rays=AO_RAYS):
    """Cosine-weighted directions over the hemisphere about +z, a fixed spiral (deterministic builds)."""
    i = np.arange(rays) + .5
    r = np.sqrt(i / rays); phi = i * math.pi * (3 - math.sqrt(5))
    return np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - r * r)], -1)


def vertex_normals(vertices, faces):
    t = vertices[faces].astype('f8')
    face = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])          # area-weighted
    n = np.zeros((len(vertices), 3))
    for i in range(3): np.add.at(n, faces[:, i], face)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(length > 1e-12, n / np.maximum(length, 1e-12), [0., 1., 0.])


def ambient_occlusion(meshes, voxel=AO_VOXEL, reach=AO_REACH):
    """Per-vertex ambient occlusion (1 open, 0 closed) of the drawn park, native frame (y up): `meshes` is a list of
    (vertices, faces). The drawn triangles fill a voxel grid; from each vertex AO_RAYS cosine-weighted rays march out
    to `reach`, and each one blocked at distance d occludes by 1 - d / reach."""
    tris = np.concatenate([v[f] for v, f in meshes]).astype('f8')
    verts = np.concatenate([v for v, _ in meshes]).astype('f8')
    # The grid spans the drawn park and `reach` round it, but not the block's buried sides, far below its surfaces.
    lo = verts.min(0) - reach - voxel; hi = verts.max(0) + reach + voxel
    lo[1] = max(lo[1], np.percentile(verts[:, 1], 1) - reach)
    shape = np.ceil((hi - lo) / voxel).astype(int)
    grid = np.zeros(shape, bool)
    edge = np.linalg.norm(tris - np.roll(tris, 1, 1), axis=2).max(1)
    steps = np.clip(np.ceil(edge / (voxel / 2)), 1, 400).astype(int)
    for k in np.unique(steps):
        g = np.linspace(0, 1, k + 1); a, b = np.meshgrid(g, g); m = a + b <= 1 + 1e-9; a, b = a[m], b[m]
        for chunk in np.array_split(np.flatnonzero(steps == k), max(1, (steps == k).sum() * len(a) // 4000000 + 1)):
            t = tris[chunk]
            p = t[:, None, 0] + a[None, :, None] * (t[:, None, 1] - t[:, None, 0]) + b[None, :, None] * (t[:, None, 2] - t[:, None, 0])
            c = np.floor((p.reshape(-1, 3) - lo) / voxel).astype(int)
            c = c[((c >= 0) & (c < shape)).all(1)]
            grid[c[:, 0], c[:, 1], c[:, 2]] = True
    local = ao_directions()
    distances = np.geomspace(1.5 * voxel, reach, AO_STEPS)
    result = []
    for vertices, faces in meshes:
        v = vertices.astype('f8'); n = vertex_normals(vertices, faces)
        side = np.where(np.abs(n[:, :1]) < .9, [[1., 0., 0.]], [[0., 0., 1.]])
        tu = np.cross(n, side); tu /= np.linalg.norm(tu, axis=1, keepdims=True); tv = np.cross(n, tu)
        ao = np.ones(len(v))
        for s in range(0, len(v), CHUNK):
            d = (local[None, :, :1] * tu[s:s + CHUNK, None] + local[None, :, 1:2] * tv[s:s + CHUNK, None]
                 + local[None, :, 2:] * n[s:s + CHUNK, None])                                     # (V, rays, 3)
            origin = v[s:s + CHUNK, None, None] + 1.2 * voxel * n[s:s + CHUNK, None, None]   # clear of its own voxels
            p = origin + d[:, :, None] * distances[None, None, :, None]                         # (V, rays, steps, 3)
            c = np.floor((p - lo) / voxel).astype(int)
            inside = ((c >= 0) & (c < shape)).all(-1)
            c = np.where(inside[..., None], c, 0)
            blocked = grid[c[..., 0], c[..., 1], c[..., 2]] & inside
            first = np.where(blocked.any(-1), distances[blocked.argmax(-1)], reach)
            ao[s:s + CHUNK] = 1 - (1 - first / reach).mean(1)
        # Two passes of neighbour averaging take out the voxel grid's step noise between neighbouring vertices.
        edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        for _ in range(2):
            total = np.zeros(len(v)); count = np.zeros(len(v))
            np.add.at(total, edges[:, 0], ao[edges[:, 1]]); np.add.at(count, edges[:, 0], 1)
            np.add.at(total, edges[:, 1], ao[edges[:, 0]]); np.add.at(count, edges[:, 1], 1)
            ao = np.where(count > 0, .5 * ao + .5 * total / np.maximum(count, 1), ao)
        result.append(np.clip(ao, 0, 1))
    return result


def main():
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    scene = placement.scene()
    report = {'scene_sha256': sha(SOURCE / 'scene.json'), 'render': [], 'collision': []}
    sections = {}
    loaded = []
    for entry in placement.meshes():
        assert sha(SOURCE / entry['npz']) == entry['sha256'], entry['npz']
        a = placement.arrays(entry)
        keep = valid(a['positions'], a['triangles'])
        keep[a['render_skip']] = False
        loaded.append((entry, a, keep))
    # The riding surfaces as drawn; foundation faces lying on them are left out of the render and the collision.
    surfaces = [(a['positions'][a['triangles'][keep]], entry['doubleSided']) for entry, a, keep in loaded
                if entry['role'] == 'original']
    riding = np.concatenate([t for t, _ in surfaces])
    two_sided = np.concatenate([np.full(len(t), d) for t, d in surfaces])
    # A double-sided piece modelled with both windings: drop the face turned down where an upward one lies on it. Its
    # material draws both sides, so the pair only flickered, and the board met the downward one as a ceiling.
    up = unit_normals(riding)[:, 1] > .5        # native frame: y up
    for entry, a, keep in loaded:
        if entry['role'] != 'original':
            continue
        index = np.flatnonzero(keep); t = a['positions'][a['triangles'][index]]
        down = unit_normals(t.astype('f8'))[:, 1] < -.5
        if down.any():
            twin = covered(t[down], riding[up], np.ones(int(up.sum()), bool), eps=TWIN)
            keep[index[np.flatnonzero(down)[twin]]] = False
            print('Riding', entry['id'], 'downward twins left out:', int(twin.sum()), flush=True)
    # The solid filling a tunnel's bore is left out of the render and the collision.
    bores = tunnel.tunnels([a['positions'][a['triangles'][keep]].astype('f8') for entry, a, keep in loaded
                             if entry['role'] == 'original'])
    print('Pieces closing round a tunnel:', len(bores), flush=True)
    for entry, a, keep in loaded:
        if entry['role'] in ('original', 'mountain'):
            continue
        index = np.flatnonzero(keep)
        bore = tunnel.inside_tubes(a['positions'][a['triangles'][index]], bores)
        keep[index[bore]] = False
        if bore.any():
            print('Mesh', entry['id'], entry['role'], 'faces in a tunnel left out:', int(bore.sum()), flush=True)
    # The added riding pieces (additions.py): snake channels in the east bowls' slots, and caps and walls closing the
    # sheets that ended in the air. They come after the park's own pieces: where one lies on a piece, the piece is drawn.
    riding_now = np.concatenate([a['positions'][a['triangles'][keep]] for entry, a, keep in loaded
                                 if entry['role'] == 'original']).astype('f8')
    solid_now = np.concatenate([a['positions'][a['triangles'][keep]] for entry, a, keep in loaded
                                if entry['role'] != 'original']).astype('f8')
    added = []
    for name, (box, floor, deep, depth, feet) in additions.SNAKES.items():
        made = additions.snake_channels(riding_now, solid_now, box, floor, deep, depth, feet) or {}
        for part, mesh in made.items():
            material = additions.SNAKE_MATERIAL if part == 'channels' else additions.FEET_MATERIAL
            added.append(({'id': f'add-{part}-{name}', 'role': 'original', 'material': material,
                           'doubleSided': False, 'added': True}, mesh))
    around = np.concatenate([riding_now, solid_now]); heights = grind.heights(around)
    for name, (box, joins) in additions.BANKS.items():
        made = additions.bank(riding_now, solid_now, box, joins)
        if made is None:
            continue
        added.append(({'id': f'add-bank-{name}', 'role': 'original', 'material': additions.SNAKE_MATERIAL,
                       'doubleSided': False, 'added': True}, made))
        sides = additions.solidify(made[0][made[1]].astype('f8'), heights, around)
        if sides is not None:
            added.append(({'id': f'add-bank-{name}-sides', 'role': 'original', 'material': additions.SNAKE_MATERIAL,
                           'doubleSided': False, 'added': True}, sides))
    for entry, a, keep in loaded:
        if entry['role'] != 'original':
            continue
        made = additions.solidify(a['positions'][a['triangles'][keep]], heights, around,
                                  additions.tile_metres(a['positions'], a['uvs'], a['triangles'][keep]))
        if made is not None:
            added.append(({'id': 'add-solid-' + entry['id'][5:9], 'role': 'original', 'material': entry['material'],
                           'doubleSided': False, 'added': True}, made))
    del riding_now, solid_now, heights, around
    for entry, (vertices, faces, uvs) in added:
        loaded.append((entry, {'positions': vertices.astype('f4'), 'triangles': faces.astype('i8'),
                               'uvs': uvs.astype('f4'), 'render_skip': np.zeros(0, 'i8')}, np.ones(len(faces), bool)))
        print('Added', entry['id'], 'faces:', len(faces), flush=True)
    # Faces of different meshes lying on each other z-fight (the foundations' shared walls and tops, a riding piece on the
    # block): each face lying on one of an earlier mesh, in ROLES order, is left out of the render and collision.
    # The added pieces rank after the bridges: a bridge over a snake channel is drawn where the channel meets it.
    order = sorted(range(len(loaded)), key=lambda i: (ROLES.index('bridge_support') + .5 if loaded[i][0].get('added')
                                                    else ROLES.index(loaded[i][0]['role']), i))
    rank = np.empty(len(loaded), 'i8'); rank[order] = np.arange(len(loaded))
    shown = [a['positions'][a['triangles'][keep]] for _, a, keep in loaded]
    everything = np.concatenate(shown)
    ranks = np.concatenate([np.full(len(f), rank[i]) for i, f in enumerate(shown)])
    sides = np.concatenate([np.full(len(f), entry['doubleSided']) for (entry, _, _), f in zip(loaded, shown)])
    fighting = covered(everything, everything, sides, eps=FLICKER, ranks=(ranks, ranks))
    start = 0
    for (entry, a, keep), f in zip(loaded, shown):
        index = np.flatnonzero(keep); lost = fighting[start:start + len(f)]; start += len(f)
        keep[index[lost]] = False
        if lost.any():
            print('Mesh', entry['id'], entry['role'], 'faces lying on an earlier mesh left out:', int(lost.sum()), flush=True)
    drawn = []
    for entry, a, keep in loaded:
        skipped = int(len(keep) - keep.sum())
        if entry['role'] == 'foundation':
            index = np.flatnonzero(keep)
            hidden = covered(a['positions'][a['triangles'][index]], riding, two_sided)
            keep[index[hidden]] = False
            print('Foundation', entry['id'], 'faces on a riding surface left out:', int(hidden.sum()), flush=True)
        sections.setdefault(entry['role'], []).append(a['positions'][a['triangles'][keep]])
        used = np.unique(a['triangles'][keep])
        remap = np.full(len(a['positions']), -1, 'i8'); remap[used] = np.arange(len(used))
        vertices, faces, uvs = a['positions'][used], remap[a['triangles'][keep]], a['uvs'][used]
        if entry['role'] in PLAIN:
            vertices, faces = simplify(vertices, faces); uvs = None
        drawn.append((entry, vertices, faces, uvs, skipped, int(len(keep) - keep.sum()) - skipped))
    # Faces partly on a higher-ranked mesh's face move back a few millimetres in the render; collision keeps them.
    moved = recede([(v, f) for _, v, f, _, _, _ in drawn], [rank[i] for i in range(len(loaded))],
                   [entry['doubleSided'] for entry, _, _ in loaded])
    drawn = [(entry, v, f, uvs, skipped, cov) for (entry, _, f, uvs, skipped, cov), (v, _) in zip(drawn, moved)]
    for (entry, *_), (_, count) in zip(drawn, moved):
        if count:
            print('Mesh', entry['id'], entry['role'], 'faces partly on a higher-ranked mesh moved back:', count, flush=True)
    ride = np.concatenate(sections['original']); above = riding_above(ride[unit_normals(ride.astype('f8'))[:, 1] > .2])
    final = {}
    for role, parts in sections.items():
        triangles = np.concatenate(parts)
        hidden = hidden_walls(triangles, above)
        triangles = triangles[~hidden]
        sunk = 0
        if role != 'original':
            triangles, sunk = sink_inside(triangles, above)
        final[role] = triangles
        print('Collision', role, 'faces inside the solid left out:', int(hidden.sum()), 'corners inside sunk:', sunk, flush=True)
    # Grind lines along the lips (grind.py), on the collision the board rides, each drawn as a steel coping tube.
    lines = grind.grind_lines(final['original'].astype('f8'),
                              np.concatenate([x for role, x in final.items() if role != 'original']).astype('f8'))
    print('Grind lines along the lips:', len(lines), 'of', round(sum(np.linalg.norm(np.diff(l, axis=0), axis=1).sum() for l in lines)), 'm', flush=True)
    tube = additions.coping(lines)
    if tube is not None:
        drawn.append(({'id': 'add-coping', 'role': 'coping', 'material': additions.COPING_MATERIAL}, *tube, 0, 0))
    occlusion = ambient_occlusion([(v, f) for _, v, f, _, _, _ in drawn])
    for (entry, vertices, faces, uvs, skipped, covered_faces), ao in zip(drawn, occlusion):
        mesh = export_mesh('SM_CP_' + entry['id'].replace('-', '_'), vertices, faces, [entry['material']],
                           np.zeros(len(faces), 'i4'), uvs, smooth=True, ao=ao)
        mesh.update(source_id=entry['id'], role=entry['role'], skipped=skipped,
                    covered=covered_faces, occlusion_mean=round(float(ao.mean()), 4))
        report['render'].append(mesh)
        print('Exported', mesh['name'], flush=True)
    for role, triangles in final.items():
        triangles = triangles[spatial_order(triangles)]     # sections of neighbouring faces
        for k in range(0, len(triangles), SECTION):
            chunk = triangles[k:k + SECTION]
            vertices, faces = chunk.reshape(-1, 3), np.arange(len(chunk) * 3).reshape(-1, 3)
            if role in PLAIN:
                vertices, faces = simplify(vertices, faces)
            faces = faces[spatial_order(vertices[faces])]
            entry = export_mesh(f'UC_CP_{role}_{k // SECTION}', vertices, faces, ['M_Collision'], np.zeros(len(faces), 'i4'))
            entry['source_triangles'] = len(chunk)
            entry.update(role=role, one_sided=False)
            report['collision'].append(entry)
    # Seed the FBX factory's safe reimport route with a clean triangle (import_craterpark.py).
    export_mesh('SM_CP_ImportSeed', np.asarray([[0, 0, 0], [1, 0, 0], [0, 0, 1]], 'f4'), np.asarray([[0, 2, 1]]),
                ['M_Collision'], [0], np.asarray([[0, 0], [1, 0], [0, 1]], 'f4'))
    (OUT / 'build.json').write_text(json.dumps(report, indent=1) + '\n')
    t = placement.unreal_transform()
    # The marked ramp drop-in; the rider starts there facing the park's native +x.
    ground = json.loads((SOURCE / 'drop-in.json').read_text())['groundPosition']
    rails = []
    for i, line in enumerate(lines):
        closed = len(line) > 3 and np.linalg.norm(line[0] - line[-1]) < .01
        rails.append({'id': f'cp_lip_{i:03d}', 'closed': bool(closed),
                      'points_cm': [ue(p) for p in (line[:-1] if closed else line).tolist()]})
    park = {'source_sha256': report['scene_sha256'], 'name': 'CRATERPARK', 'mesh_root': MESH_ROOT, 'rails_required': True,
            'location_cm': t['location_cm'], 'yaw_deg': t['yaw_deg'], 'placement': placement.summary(),
            'render': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['render']],
            'collision': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['collision']],
            'rails': rails, 'spawn': {'location_cm': placement.to_unreal(ground).tolist(), 'yaw_deg': t['yaw_deg']}}
    (OUT / 'park.json').write_text(json.dumps(park) + '\n')
    print('CRATERPARK BUILD COMPLETE', len(report['render']), 'render', len(report['collision']), 'collision',
          scene['counts'], flush=True)


if __name__ == '__main__':
    main()
