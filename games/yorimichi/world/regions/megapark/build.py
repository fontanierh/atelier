"""Build ordinary Unreal static-mesh interchange files from bundled map arrays.

Run with Blender. There is no game-data decoder in this stage. Render geometry
and authoritative riding collision stay separate, and neither is simplified.
The restyle (docs/MEGAPARK.md) leaves out the desert plants (plants.py) and
the traffic cars (cars.py) and turns the SHARKS letters into 寄り道 (sign.py);
every other triangle is kept. The seam (placement.py) gives the park in the
island a piece of the source's hills, with a skirt under its open edges.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori
from megapark import cars, placement, plants, sign

import bpy
import bmesh
import hashlib
import json
import struct
import zlib
import numpy as np

SOURCE = yori.ASSETS / 'megapark'
OUT = yori.OUT / 'megapark'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_fallbacks():
    # Exact linear normal pixel, without depending on Blender's view transform.
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    for name, pixel in {'white': (255,255,255,255), 'black': (0,0,0,255), 'normal': (128,128,255,255)}.items():
        data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>2I5B',1,1,8,6,0,0,0))
        data += chunk(b'IDAT', zlib.compress(b'\0'+bytes(pixel)))+chunk(b'IEND', b'')
        (OUT/f'{name}.png').write_bytes(data)


def material_key(part):
    # Name is a provenance label; the draw parameters and channel bindings
    # determine whether two source parts may share one Unreal material.
    parameters = {key: values for key, values in part.get('retail_parameters', {}).items()
                  if key not in ('Name',)}
    identity = [part.get('shader_name'), part.get('retail_texture_ids'), parameters,
                part.get('alpha_mode'), part.get('alpha_cutoff')]
    return 'M_' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def native_to_blender(values):
    result = np.asarray(values)[:, [0, 2, 1]].copy()
    result[:, 1] *= -1
    return result


def export_mesh(name, vertices, faces, materials, face_materials, channels=None, normals=None):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # A local origin makes each source chunk straightforward to select/move.
    # Keep source float words in the committed arrays; validate imported world bounds.
    origin = np.round((vertices.min(axis=0).astype('f8') + vertices.max(axis=0)) / 2 / 32) * 32
    local = native_to_blender(vertices.astype('f8') - origin)
    data = bpy.data.meshes.new(name)
    data.from_pydata(local.tolist(), [], faces.tolist())
    data.update()
    for key in materials:
        material = bpy.data.materials.get(key) or bpy.data.materials.new(key)
        data.materials.append(material)
    if len(face_materials):
        data.polygons.foreach_set('material_index', np.asarray(face_materials, dtype='i4'))
    loops = np.empty(len(data.loops), dtype='i4')
    data.loops.foreach_get('vertex_index', loops)
    for key, values in (channels or {}).items():
        layer = data.uv_layers.new(name=key)
        uv = values.copy(); uv[:, 1] = 1 - uv[:, 1]
        layer.data.foreach_set('uv', uv[loops].ravel())
    if normals is not None:
        data.polygons.foreach_set('use_smooth', np.ones(len(data.polygons), dtype=bool))
        data.normals_split_custom_set_from_vertices(native_to_blender(normals).tolist())
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    path = OUT / 'fbx' / f'{name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={'MESH'},
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', global_scale=1.,
        axis_forward='-Z', axis_up='Y', use_mesh_modifiers=False, mesh_smooth_type='FACE',
        use_tspace=bool(channels), bake_anim=False, add_leaf_bones=False, path_mode='STRIP')
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    result = {'name': name, 'fbx': f'fbx/{name}.fbx', 'sha256': sha(path),
        'native_origin': origin.tolist(), 'bounds': {'minimum': lo.tolist(), 'maximum': hi.tolist()},
        'vertices': len(vertices), 'triangles': len(faces), 'materials': materials}
    bpy.data.meshes.remove(data, do_unlink=True)
    return result


def channels(arrays, i, v, f):
    """(normals, uvs, lightmap uvs, decal uvs) of source part i with vertices v and faces f."""
    n = arrays.get(f'retail_normals_{i}', arrays.get(f'normals_{i}'))
    if n is None:
        n = np.zeros_like(v)
        face_normals = np.cross(v[f[:,1]]-v[f[:,0]], v[f[:,2]]-v[f[:,0]])
        for corner in range(3):
            np.add.at(n, f[:,corner], face_normals)
    n = n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
    uv = arrays.get(f'uvs_{i}', np.zeros((len(v),2), dtype='f4'))
    return n, uv, np.abs(arrays.get(f'lightmap_uvs_{i}', uv)), arrays.get(f'decal_uvs_{i}', uv)


def export_seam(source, report):
    """The seam (placement.SEAM, docs/MEGAPARK.md "Seam"): its parts and the skirt under their open edges as one
    render mesh, its collision triangles and the skirt as one collision mesh. Only the island places them."""
    models = {m['asset_id']: m for m in source['models']}
    skirt = {}
    for asset, i, a, b, out in placement.seam_skirt():
        skirt.setdefault((asset, i), []).append((a, b, out))
    drop = np.array([0., placement.SKIRT_DROP, 0.])
    vertices, faces, normals, uvs, lightmaps, decals, material_indices, slots = [], [], [], [], [], [], [], []
    offset = 0
    for asset, i, _, f in placement.seam_parts():
        part = next(p for p in models[asset]['meshes'] if p['index'] == i)
        key = material_key(part)
        if key not in slots:
            slots.append(key)
        report['materials'].setdefault(key, part)
        with np.load(SOURCE / models[asset]['npz'], allow_pickle=False) as arrays:
            v = arrays[f'vertices_{i}']
            n, uv, lightmap, decal = channels(arrays, i, v, f)
        vertices.append(v); faces.append(f+offset); material_indices.extend([slots.index(key)]*len(f))
        normals.append(n); uvs.append(uv); lightmaps.append(lightmap); decals.append(decal)
        offset += len(v)
        # The skirt: a, b, b', a' under each open edge, its texture running on past the edge (away from the face) at the
        # part's own density, the lightmap's edge texels drawn down with it, and a level normal facing out.
        t = v[f].astype('f8'); q = uv[f].astype('f8')
        world = np.linalg.norm(np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0]), axis=1)
        texels = np.abs(np.cross(q[:,1]-q[:,0], q[:,2]-q[:,0]))
        density = float(np.median(np.sqrt(texels[world > 1e-6]/world[world > 1e-6])))
        third = {(int(face[k]), int(face[(k+1) % 3])): int(face[(k+2) % 3]) for face in f for k in range(3)}
        for a, b, out in skirt.get((asset, i), ()):
            o = third.get((a, b), third.get((b, a)))
            along = (uv[b]-uv[a]).astype('f8')
            across = np.array([-along[1], along[0]])/max(np.linalg.norm(along), 1e-9)
            if np.dot(across, uv[o]-uv[a]) > 0:
                across = -across
            down = across*placement.SKIRT_DROP*density
            vertices.append(np.stack([v[a], v[b], v[b]-drop, v[a]-drop]).astype(v.dtype))
            faces.append(np.array([[0, 1, 2], [0, 2, 3]])+offset); material_indices.extend([slots.index(key)]*2)
            normals.append(np.tile([out[0], 0., out[1]], (4, 1)))
            uvs.append(np.stack([uv[a], uv[b], uv[b]+down, uv[a]+down]).astype(uv.dtype))
            lightmaps.append(lightmap[[a, b, b, a]]); decals.append(decal[[a, b, b, a]])
            offset += 4
    render = export_mesh('SM_MP_Seam', np.concatenate(vertices), np.concatenate(faces), slots, material_indices,
        {'UVMap': np.concatenate(uvs), 'RetailLightmap': np.concatenate(lightmaps), 'RetailDecal': np.concatenate(decals)},
        np.concatenate(normals))
    render['seam_parts'] = {asset: list(parts) for asset, parts in placement.SEAM.items()}
    render['skirt_edges'] = len(placement.seam_skirt())
    section = next(c for c in source['collision'] if c['id'] == placement.SEAM_SECTION)
    with np.load(SOURCE / section['npz'], allow_pickle=False) as arrays:
        triangles = arrays['triangles']
    kept = np.concatenate([triangles[placement.seam_mask()], placement.skirt_triangles().astype(triangles.dtype)])
    vertices = kept.reshape(-1, 3)
    collision = export_mesh('UC_MP_Seam', vertices, np.arange(len(vertices), dtype='u4').reshape(-1, 3), ['M_Collision'],
        np.zeros(len(kept), dtype='i4'))
    collision['source_id'] = section['id']; collision['seam_triangles'] = int(placement.seam_mask().sum())
    collision['one_sided'] = bool(section['mesh_flags'] & 0x10)
    return [render, collision]


def letters():
    """寄り道 where SHARKS stood (sign.py): native vertices (float32, one per face corner so the concrete keeps crisp
    edges), triangles, normals and UVs."""
    curve = bpy.data.curves.new('letters', 'FONT')
    curve.body = sign.TEXT
    curve.font = bpy.data.fonts.load(str(OUT / sign.BLACK), check_existing=True)
    curve.align_x = 'CENTER'; curve.space_character = sign.SPACING; curve.resolution_u = 4
    ob = bpy.data.objects.new('letters', curve)
    bpy.context.collection.objects.link(ob)

    def evaluate():
        bpy.context.view_layer.update()
        data = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        bm = bmesh.new(); bm.from_mesh(data); bpy.data.meshes.remove(data)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        v = np.array([x.co[:] for x in bm.verts], 'f8'); f = np.array([[x.index for x in t.verts] for t in bm.faces], 'i8')
        bm.free()
        return v, f
    frame = sign.frame()
    try:
        v, _ = evaluate()
        curve.size = min(sign.HEIGHT / np.ptp(v[:, 1]), frame['length'] / np.ptp(v[:, 0]))
        curve.extrude = sign.DEPTH / 2
        v, f = evaluate()
    finally:
        bpy.data.objects.remove(ob, do_unlink=True); bpy.data.curves.remove(curve)
    local = v - [(v[:, 0].min() + v[:, 0].max()) / 2, v[:, 1].min(), -sign.DEPTH / 2]
    t = local[f]
    t = t[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-6]
    # Blender fills the caps with the union of overlapping strokes, but every stroke keeps its own walls: walls
    # inside the union are dropped, and the few that face into the letters are turned round.
    front = (np.abs(t[:, :, 2] - sign.DEPTH) < 1e-4).all(1)
    wall = ~front & ~(np.abs(t[:, :, 2]) < 1e-4).all(1)
    caps = t[front][:, :, :2]
    a, b, c = caps[:, 0], caps[:, 1], caps[:, 2]
    cross = lambda u, w: u[..., 0] * w[..., 1] - u[..., 1] * w[..., 0]
    det = cross(b - a, c - a)

    def filled(points):
        p = points[:, None, :]
        w1 = cross(b - p, c - p) / det; w2 = cross(c - p, a - p) / det
        return ((w1 >= -1e-9) & (w2 >= -1e-9) & (1 - w1 - w2 >= -1e-9)).any(1)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, :2]
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    middle = t.mean(1)[:, :2]
    outside = np.zeros(len(t), bool); inside = np.zeros(len(t), bool)
    outside[wall] = filled(middle[wall] + n[wall] * .01); inside[wall] = filled(middle[wall] - n[wall] * .01)
    t[wall & outside & ~inside] = t[wall & outside & ~inside][:, ::-1]
    t = t[~(wall & outside & inside)]
    normals = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    normals = np.repeat(normals / np.linalg.norm(normals, axis=1, keepdims=True), 3, 0)
    corners = t.reshape(-1, 3)
    native = sign.place(corners).astype('f4')
    assert abs(frame['bottom'] - native[:, 1].min()) < 1e-3
    world_normals = (sign.place(normals) - sign.place(np.zeros(3))).astype('f4')
    return native, np.arange(len(native), dtype='u4').reshape(-1, 3), world_normals, sign.uvs(corners, normals).astype('f4')


def letters_material(part):
    """The original letters' concrete without their lightmap page, which belonged to the old shapes."""
    drop = ('lightmap',)
    return dict(part, retail_texture_ids={k: v for k, v in part['retail_texture_ids'].items() if k not in drop},
                retail_parameters={k: v for k, v in part['retail_parameters'].items() if k not in drop})


def sample_rail(rail):
    """Bound chord error by subdividing the original cubic's Bezier controls."""
    points = []
    def split(control, depth=0):
        a, b, c, d = control
        chord = d-a
        length = np.linalg.norm(chord)
        def distance(point):
            fraction = np.clip(np.dot(point-a, chord)/max(length*length, 1e-24), 0., 1.)
            return np.linalg.norm(point-(a+fraction*chord))
        error = max(distance(b), distance(c))
        if depth >= 16 or (error <= .002 and length <= .5):
            if not points:
                points.append(a.tolist())
            points.append(d.tolist())
            return
        ab, bc, cd = (a+b)/2, (b+c)/2, (c+d)/2
        abc, bcd = (ab+bc)/2, (bc+cd)/2
        middle = (abc+bcd)/2
        split((a, ab, abc, middle), depth+1)
        split((middle, bcd, cd, d), depth+1)
    for raw in rail['native_segment_payloads']:
        values = np.asarray(struct.unpack('>30f', bytes.fromhex(raw)), dtype='f8')
        a, b, c, d = (values[offset:offset+3] for offset in (0,4,8,12))
        split((d, d+c/3, d+2*c/3+b/3, d+c+b+a))
    return {'id': f"{rail['asset_id']}_{rail['section_index']}_{rail['rail_index']}",
            'closed': rail['closed'], 'points': points, 'original_segments': rail['native_segment_payloads']}


def ue(point):
    return [point[0] * 100., point[2] * 100., point[1] * 100.]


def island_runs(points):
    """The parts of a grind path over the park's own ground: a few road rails ran on into the left-out campus."""
    over = placement.contains(*placement.native_to_island(np.asarray(points))[:, :2].T, margin=3.)
    if over.all():
        return [('', points)]
    runs, start = [], None
    for i, inside in enumerate(list(over) + [False]):
        if inside and start is None: start = i
        if not inside and start is not None:
            if i - start >= 2: runs.append(points[start:i])
            start = None
    return [(f'_{k}', run) for k, run in enumerate(runs)]


def write_island(report):
    """The park in the island for ASuperUltraMegaPark::Spawn (docs/MEGAPARK.md, "Placement", "Seam" and "Restyle"):
    the actor transform, the park's own render and collision meshes and the seam's at their native origins, every grind
    path, the upper deck start, the island trees that replace the original plants ([x, y, z cm, yaw, scale] in the
    park's frame) and the kei cars that replace its traffic cars (props: mesh, location, forward and up)."""
    models, sections = placement.kept()
    render = {'SM_MP_' + m['asset_id'][2:] for m in models}
    collision = {'UC_MP_' + c['id'] for c in sections}
    t = placement.unreal_transform()
    spawn = report['spawn']
    island = {'source_sha256': report['source_sha256'], 'location_cm': t['location_cm'], 'yaw_deg': t['yaw_deg'],
        'placement': placement.summary(),
        'render': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['render'] if e['name'] in render],
        'collision': [{'name': e['name'], 'origin_cm': ue(e['native_origin'])} for e in report['collision'] if e['name'] in collision],
        'rails': [{'id': r['id'] + suffix, 'closed': r['closed'] and not suffix, 'points_cm': [ue(p) for p in points]}
                  for r in report['rails'] for suffix, points in island_runs(r['points'])],
        'spawn': {'location_cm': placement.to_unreal(spawn['position']).tolist(), 'yaw_deg': spawn['heading_degrees'] + t['yaw_deg']},
        'trees': {name: [ue(p[:3]) + p[3:] for p in items] for name, items in plants.trees().items()},
        'props': cars.props()}
    assert len(island['render']) + len(render & set(report['foliage_only'])) == len(render)
    assert len(island['collision']) == len(collision)
    for e in report['seam']:
        island['collision' if e['name'].startswith('UC_') else 'render'].append({'name': e['name'], 'origin_cm': ue(e['native_origin'])})
    (OUT / 'park.json').write_text(json.dumps(island) + '\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'fbx').mkdir(exist_ok=True)
    write_fallbacks()
    source = json.loads((SOURCE / 'map.json').read_text())
    report = {'source_sha256': sha(SOURCE / 'map.json'), 'render': [], 'foliage_only': [], 'collision': [], 'materials': {}, 'rails': [],
        'spawn': source['spawn'], 'summary': source['summary'], 'textures': source['textures']}
    scene = bpy.context.scene
    scene.unit_settings.system='METRIC'; scene.unit_settings.scale_length=1.
    new_letters = letters()
    np.savez(OUT / 'letters.npz', triangles=new_letters[0][new_letters[1]])
    for model in source['models']:
        assert sha(SOURCE/model['npz']) == model['sha256'], model['npz']
        vertices, faces, normals, uvs, lightmaps, decals, material_indices, slots = [], [], [], [], [], [], [], []
        offset = 0; degenerates = 0; foliage = 0; car = 0
        with np.load(SOURCE / model['npz'], allow_pickle=False) as arrays:
            for part in model['meshes']:
                i = part['index']; v = arrays[f'vertices_{i}']; f = arrays[f'faces_{i}']
                if plants.is_foliage(part):
                    # The desert plants give way to island trees, planted by the park actor (write_island).
                    foliage += len(f)
                    continue
                if cars.is_car(model, part):
                    # The traffic cars give way to the kei cars, parked by the park actor (write_island).
                    car += len(f)
                    continue
                if sign.is_letters(model, part):
                    v, f, n, uv = new_letters
                    key = material_key(letters_material(part))
                    if key not in slots:
                        slots.append(key)
                    report['materials'].setdefault(key, letters_material(part))
                    vertices.append(v); faces.append(f+offset); material_indices.extend([slots.index(key)]*len(f))
                    normals.append(n); uvs.append(uv); lightmaps.append(np.zeros_like(uv)); decals.append(uv)
                    offset += len(v)
                    continue
                t = v[f].astype('f8')
                valid = np.linalg.norm(np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0]), axis=1) > 1e-12
                degenerates += int((~valid).sum()); f = f[valid]
                if not len(v) or not len(f):
                    continue
                key = material_key(part)
                if key not in slots:
                    slots.append(key)
                report['materials'].setdefault(key, part)
                vertices.append(v); faces.append(f+offset); material_indices.extend([slots.index(key)]*len(f))
                n, uv, lightmap, decal = channels(arrays, i, v, f)
                normals.append(n); uvs.append(uv); lightmaps.append(lightmap); decals.append(decal)
                offset += len(v)
        if not vertices:
            if foliage:
                report['foliage_only'].append('SM_MP_'+model['asset_id'][2:])
            continue
        entry = export_mesh('SM_MP_'+model['asset_id'][2:], np.concatenate(vertices), np.concatenate(faces), slots,
            material_indices, {'UVMap': np.concatenate(uvs), 'RetailLightmap': np.concatenate(lightmaps), 'RetailDecal': np.concatenate(decals)}, np.concatenate(normals))
        entry['source_asset_id'] = model['asset_id']
        entry['degenerate_faces_removed'] = degenerates
        entry['foliage_faces_removed'] = foliage
        if car:
            entry['car_faces_removed'] = car
        report['render'].append(entry)
        print('Exported', entry['name'], flush=True)
    for mesh in source['collision']:
        assert sha(SOURCE/mesh['npz']) == mesh['sha256'], mesh['npz']
        with np.load(SOURCE / mesh['npz'], allow_pickle=False) as arrays:
            triangles = arrays['triangles']
            cross = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
            valid = np.linalg.norm(cross, axis=1) > 1e-12
            # Only geometrically degenerate faces cannot be represented in Chaos.
            # Opposite-wound contacts and feature boundaries remain untouched.
            kept = triangles[valid]
            if mesh['id'] == sign.SECTION:
                # SHARKS gives way to 寄り道, solid like the letters it replaces (sign.py).
                kept = np.concatenate([kept[~sign.letters_mask(kept)], new_letters[0][new_letters[1]].astype(kept.dtype)])
            car = cars.collision_mask(kept) if mesh['id'] == cars.SECTION else np.zeros(len(kept), bool)
            kept = kept[~car]     # the kei cars bring their own collision
            vertices = kept.reshape(-1,3)
            faces = np.arange(len(vertices), dtype='u4').reshape(-1,3)
            entry = export_mesh('UC_MP_'+mesh['id'], vertices, faces, ['M_Collision'], np.zeros(len(faces), dtype='i4'))
            entry['source_id'] = mesh['id']; entry['degenerate_faces_removed'] = int((~valid).sum())
            if car.any():
                entry['car_faces_removed'] = int(car.sum())
            entry['one_sided'] = bool(mesh['mesh_flags'] & 0x10)
            report['collision'].append(entry)
    report['seam'] = export_seam(source, report)
    report['rails'] = [sample_rail(rail) for rail in source['rails']]
    # Seed the existing FBX factory's safe reimport route with a clean triangle.
    export_mesh('SM_MP_ImportSeed', np.asarray([[0,0,0],[1,0,0],[0,0,1]], dtype='f4'),
                np.asarray([[0,2,1]], dtype='u4'), ['M_Collision'], [0],
                {'UVMap': np.asarray([[0,0],[1,0],[0,1]], dtype='f4')})
    (OUT / 'build.json').write_text(json.dumps(report, indent=1) + '\n')
    write_island(report)
    print('MEGAPARK BUILD COMPLETE', source['summary'], flush=True)


if __name__ == '__main__':
    main()
