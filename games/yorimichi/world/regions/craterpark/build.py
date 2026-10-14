"""Build Crater Park's Unreal interchange files from the committed library arrays (docs/CRATERPARK.md).

Run with Blender. Every mesh except the helpers is kept, with no simplification:
- render: one mesh per source mesh, without the faces its `render_skip` hides (coplanar flicker), smoothed only
  across edges under SMOOTH degrees; the PLAIN roles, drawn with world-aligned materials, are simplified (simplify);
  foundation faces lying on a drawn riding surface are left out (covered); every drawn vertex carries its baked
  ambient occlusion in its vertex colour (ambient_occlusion);
- collision: every face of each role, the hidden ones included, simplified, from sections of at most SECTION source
  triangles.
park.json places them on the caldera floor for ASuperUltraMegaPark::Spawn (placement.py).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori
from craterpark import placement

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
FLAT = .5              # degrees: faces this close to coplanar are merged (a shape-preserving simplification)
COVER = .05             # metres: foundation faces this close to a drawn riding surface, and parallel to it, are not drawn
CHUNK = 20000           # points or vertices per vectorised batch (covered, ambient_occlusion): bounds the memory
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


def covered(triangles, surfaces, two_sided, eps=COVER, cell=1.):
    """Mask of `triangles` (n, 3, 3) that lie on the drawn riding `surfaces` (m, 3, 3): the centroid and the three corners
    are each within eps of the plane of a surface triangle facing the same way (either way where `two_sided`), and inside
    it, or within eps of its edges. Drawn under the riding surface they only flicker through it."""
    s = surfaces.astype('f8'); ns = unit_normals(s)
    lo = np.floor((s.min(1) - eps) / cell).astype('i8'); hi = np.floor((s.max(1) + eps) / cell).astype('i8')
    size = hi - lo + 1; count = size.prod(1)
    owner = np.repeat(np.arange(len(s)), count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    sx, sy = size[owner, 0], size[owner, 1]
    keys = cell_keys(lo[owner] + np.stack([local % sx, (local // sx) % sy, local // (sx * sy)], -1))
    order = np.argsort(keys, kind='stable'); keys, owner = keys[order], owner[order]
    t = triangles.astype('f8'); nt = unit_normals(t)
    points = np.concatenate([t.mean(1, keepdims=True), t], 1).reshape(-1, 3)
    pn = np.repeat(nt, 4, 0)
    on = np.zeros(len(points), bool)
    for start in range(0, len(points), CHUNK):
        p = points[start:start + CHUNK]; n = pn[start:start + CHUNK]
        k = cell_keys(np.floor(p / cell))
        a = np.searchsorted(keys, k, 'left'); b = np.searchsorted(keys, k, 'right')
        reps = b - a
        which = np.repeat(np.arange(len(p)), reps)
        cand = owner[np.repeat(a, reps) + np.arange(reps.sum()) - np.repeat(np.cumsum(reps) - reps, reps)]
        q = p[which]; v = s[cand]; m = ns[cand]
        facing = (n[which] * m).sum(1)
        ok = (np.abs(((q - v[:, 0]) * m).sum(1)) < eps) & ((facing > .98) | (two_sided[cand] & (facing < -.98)))
        for i in range(3):
            e = v[:, (i + 1) % 3] - v[:, i]
            inward = (np.cross(e, q - v[:, i]) * m).sum(1) / np.maximum(np.linalg.norm(e, axis=1), 1e-12)
            ok &= inward > -eps
        hit = np.zeros(len(p), bool); hit[which[ok]] = True
        on[start:start + CHUNK] = hit
    return on.reshape(-1, 4).all(1)


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
        sections.setdefault(entry['role'], []).append(a['positions'][a['triangles'][keep]])
        keep[a['render_skip']] = False
        loaded.append((entry, a, keep))
    # The riding surfaces as drawn; foundation faces lying on them are left out of the render (collision keeps them).
    surfaces = [(a['positions'][a['triangles'][keep]], entry['doubleSided']) for entry, a, keep in loaded
                if entry['role'] == 'original']
    riding = np.concatenate([t for t, _ in surfaces])
    two_sided = np.concatenate([np.full(len(t), d) for t, d in surfaces])
    drawn = []
    for entry, a, keep in loaded:
        skipped = int(len(keep) - keep.sum())
        if entry['role'] == 'foundation':
            index = np.flatnonzero(keep)
            hidden = covered(a['positions'][a['triangles'][index]], riding, two_sided)
            keep[index[hidden]] = False
            print('Foundation', entry['id'], 'faces on a riding surface left out:', int(hidden.sum()), flush=True)
        used = np.unique(a['triangles'][keep])
        remap = np.full(len(a['positions']), -1, 'i8'); remap[used] = np.arange(len(used))
        vertices, faces, uvs = a['positions'][used], remap[a['triangles'][keep]], a['uvs'][used]
        if entry['role'] in PLAIN:
            vertices, faces = simplify(vertices, faces); uvs = None
        drawn.append((entry, vertices, faces, uvs, skipped, int(len(keep) - keep.sum()) - skipped))
    occlusion = ambient_occlusion([(v, f) for _, v, f, _, _, _ in drawn])
    for (entry, vertices, faces, uvs, skipped, covered_faces), ao in zip(drawn, occlusion):
        mesh = export_mesh('SM_CP_' + entry['id'].replace('-', '_'), vertices, faces, [entry['material']],
                           np.zeros(len(faces), 'i4'), uvs, smooth=True, ao=ao)
        mesh.update(source_id=entry['id'], role=entry['role'], skipped=skipped,
                    covered=covered_faces, occlusion_mean=round(float(ao.mean()), 4))
        report['render'].append(mesh)
        print('Exported', mesh['name'], flush=True)
    for role, parts in sections.items():
        triangles = np.concatenate(parts)
        for k in range(0, len(triangles), SECTION):
            chunk = triangles[k:k + SECTION]
            vertices, faces = simplify(chunk.reshape(-1, 3), np.arange(len(chunk) * 3).reshape(-1, 3))
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
    park = {'source_sha256': report['scene_sha256'], 'name': 'CRATERPARK', 'mesh_root': MESH_ROOT, 'rails_required': False,
            'location_cm': t['location_cm'], 'yaw_deg': t['yaw_deg'], 'placement': placement.summary(),
            'render': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['render']],
            'collision': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['collision']],
            'rails': [], 'spawn': {'location_cm': placement.to_unreal(ground).tolist(), 'yaw_deg': t['yaw_deg']}}
    (OUT / 'park.json').write_text(json.dumps(park) + '\n')
    print('CRATERPARK BUILD COMPLETE', len(report['render']), 'render', len(report['collision']), 'collision',
          scene['counts'], flush=True)


if __name__ == '__main__':
    main()
