"""Put Paul's current head on a new Tripo body (the head stays exactly as in Paul.glb; only the body is new).

/Applications/Blender.app/Contents/MacOS/Blender -b --python-exit-code 1 --python \
    games/yorimichi/assets/characters/tools/paul_body_graft.py -- \
    --body <tripo body>.glb --head <previous Paul.glb, haras-r01> --output <dir> \
    [--head-fraction 0.195] [--renders]

The body is a headless Tripo P2 multiview body (T-pose, palms down, facing -Y, a bare neck plug). The head is the
M_Paul_1 section of the previous Paul.glb (haras-r01: face, hair, ears and neck; facing +X, metres, his rest pose).

1. The body: welded at its UV seams (1e-5), turned to face +X, scaled so the head (chin to the top of the hair)
   is `--head-fraction` of his height, its soles on z = 0 and its neck centred under the head's.
2. The neck: the body keeps its own neck, which plugs into the head. Above the collar its rings are drawn in toward
   the neck's axis, smoothly, so at the cut they sit 1.5 mm inside the head's neck; the head's neck is cut under the
   chin (NECK_KEEP above the chin at the front, lower at the nape) and overlaps the body's.
3. Skin: the arms' and hands' skin texels take the face's colour (each channel's mean and spread), blended by how
   clearly a texel is skin, so the shading stays and no texel clips.
4. One object, two materials (body, head), one UV layer, no normal maps; GLB with packed textures, facing +X,
   soles at 0, height 1.65 m. graft.json records every measured value.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
import numpy as np

HEIGHT_M = 1.65
HEAD_TOP = 1.65               # the head's hair top in Paul.glb (z, m)
HEAD_CHIN = 1.335             # its chin bottom, from its slices
NECK_PROBE = 1.315            # z where its neck section is measured, just under the chin
BODY_COLLAR = 0.906           # the body's collar top at the front (body units, from its slices)
BODY_NECK_TOP = 0.936         # the body's neck plug top
SKIN_MIN_RED = .35
NECK_DROP = .035             # the body's neck skin above (collar - this) goes (m, before the final scale)
HEAD_NECK_BELOW = .045      # the head's neck reaches this far under the collar
SHIRT_INSET = .003
ARMS_ABOVE = .9              # z (m, placed): skin above it is the arms, hands and neck, below it is cloth
SPREAD_LIMITS = (.8, 1.25)   # the arms' colour spread may be scaled this far toward the face's


def args():
    p = argparse.ArgumentParser()
    p.add_argument('--body', required=True)
    p.add_argument('--head', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--head-fraction', type=float, default=.195)
    p.add_argument('--renders', action='store_true')
    return p.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def texture_of(material):
    """The image feeding Base Color, directly or through one node (glTF imports a colour factor as a mix)."""
    for n in material.node_tree.nodes:
        if n.type != 'TEX_IMAGE' or not n.image:
            continue
        for l in n.outputs['Color'].links:
            if l.to_socket.name == 'Base Color' or any(
                    m.to_socket.name == 'Base Color' for o in l.to_node.outputs for m in o.links):
                return n.image
    raise RuntimeError(f'no base colour texture on {material.name}')


def strip_normal_maps(material):
    nt = material.node_tree
    for n in list(nt.nodes):
        if n.type == 'NORMAL_MAP' or (n.type == 'TEX_IMAGE' and n.image and 'normal' in n.image.name.lower()):
            nt.nodes.remove(n)


def vertex_colours(obj, image, material_index):
    """Mean texture colour per vertex (sRGB as Blender stores it) over the loops of one material."""
    me = obj.data
    w, h = image.size
    px = np.array(image.pixels[:], np.float32).reshape(h, w, 4)[:, :, :3]
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)
    lv = np.zeros(len(me.loops), int)
    me.loops.foreach_get('vertex_index', lv)
    mat = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get('material_index', mat)
    lmat = np.repeat(mat, [p.loop_total for p in me.polygons])
    keep = lmat == material_index
    col = px[np.clip((uv[keep, 1] * h).astype(int), 0, h - 1), np.clip((uv[keep, 0] * w).astype(int), 0, w - 1)]
    out = np.zeros((len(me.vertices), 3)); n = np.zeros(len(me.vertices))
    np.add.at(out, lv[keep], col); np.add.at(n, lv[keep], 1)
    return out / np.maximum(n, 1)[:, None], n > 0


def uv_mask(obj, w, h, vert_sel):
    """The texels covered by the UV triangles of faces whose vertices are all selected (grown by 2 texels)."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    mask = np.zeros((h, w), bool)
    for t in me.loop_triangles:
        if not all(vert_sel[i] for i in t.vertices):
            continue
        q = np.array([uv[l].uv[:] for l in t.loops]) * (w, h)
        x0, y0 = np.floor(q.min(0)).astype(int) - 2; x1, y1 = np.ceil(q.max(0)).astype(int) + 2
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        (ax, ay), (bx, by), (cx, cy) = q
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / d
        e = 2.5 / max(abs(d) ** .5, 1)
        inside = (l1 > -e) & (l2 > -e) & (1 - l1 - l2 > -e)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return mask


def skin_weight(c):
    """0 for cloth, 1 for clear skin, a ramp between (red over green and over blue, as is_skin)."""
    r, g, b = c[..., 0], np.maximum(c[..., 1], 1e-3), np.maximum(c[..., 2], 1e-3)
    ramp = lambda x, lo, hi: np.clip((x - lo) / (hi - lo), 0, 1)
    return ramp(r / g, 1.05, 1.2) * ramp(r / b, 1.15, 1.4) * ramp(r, SKIN_MIN_RED - .05, SKIN_MIN_RED + .05)


def is_skin(c):
    return (c[..., 0] > c[..., 1] * 1.15) & (c[..., 0] > c[..., 2] * 1.3) & (c[..., 0] > SKIN_MIN_RED)


def main():
    a = args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    report = {'body': Path(a.body).name, 'head': Path(a.head).name, 'head_fraction': a.head_fraction,
              'blender_version': bpy.app.version_string}

    # --- the head: Paul.glb's head section, in his rest pose -------------------------------------------------
    new = import_glb(a.head)
    src = next(o for o in new if o.type == 'MESH' and len(o.data.materials) == 2)
    head = bpy.data.objects.new('Head', src.data.copy())
    bpy.context.scene.collection.objects.link(head)
    head.matrix_world = src.matrix_world.copy()
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    bm = bmesh.new(); bm.from_mesh(head.data)
    head_mat = 1
    gone = [f for f in bm.faces if f.material_index != head_mat]
    bmesh.ops.delete(bm, geom=gone, context='FACES')
    co = np.array([v.co[:] for v in bm.verts])
    probe = co[np.abs(co[:, 2] - NECK_PROBE) < .005]
    neck_c = probe[:, :2].mean(0)
    bm.to_mesh(head.data); bm.free()
    head.data.materials.clear()
    hm = src_mat = bpy.data.materials.get('M_Paul_1')
    head.data.materials.append(hm)
    for p in head.data.polygons:
        p.material_index = 0
    strip_normal_maps(hm)
    # the head's neck section at the cut, in its own frame: the half widths along X and Y around neck_c
    hco = np.array([v.co[:] for v in head.data.vertices])
    ring = hco[np.abs(hco[:, 2] - NECK_PROBE) < .004]
    head_neck = {'centre': neck_c.round(4).tolist(),
                 'half_x': float(np.abs(ring[:, 0] - neck_c[0]).max()),
                 'half_y': float(np.abs(ring[:, 1] - neck_c[1]).max())}
    report['head_neck'] = head_neck

    # --- the body ------------------------------------------------------------------------------------------------
    new = import_glb(a.body)
    body = next(o for o in new if o.type == 'MESH')
    body.data.transform(body.matrix_world)
    body.parent = None; body.matrix_world = Matrix()
    for o in new:
        if o is not body:
            bpy.data.objects.remove(o, do_unlink=True)
    body.name = 'Paul_Body'
    bm = bmesh.new(); bm.from_mesh(body.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    report['body_vertices_welded'] = [n0, len(bm.verts)]
    bm.to_mesh(body.data); bm.free()
    # face +X: the body faces -Y; +90 degrees about Z takes -Y to +X
    body.data.transform(Matrix.Rotation(math.radians(90), 4, 'Z'))
    bco = np.array([v.co[:] for v in body.data.vertices])
    floor = bco[:, 2].min()
    # scale: the head (chin to hair top) is head_fraction of the height; the chin sits CHIN_OVER_COLLAR over the collar
    head_h = HEAD_TOP - HEAD_CHIN
    total = head_h / a.head_fraction
    chin_over_collar = .028 * total / HEIGHT_M
    k = (total - head_h - chin_over_collar) / (BODY_COLLAR - floor)
    report['body_scale'] = round(k, 5)
    body.data.transform(Matrix.Scale(k, 4))
    bco = np.array([v.co[:] for v in body.data.vertices])
    body_tex = texture_of(body.data.materials[0])
    bcol, _ = vertex_colours(body, body_tex, 0)
    skin = is_skin(bcol)
    collar_z = (BODY_COLLAR - floor) * k
    top_z = (BODY_NECK_TOP - floor) * k
    mid = skin & (bco[:, 2] > collar_z + .3 * (top_z - collar_z)) & (bco[:, 2] < collar_z + .7 * (top_z - collar_z)) \
        & (np.abs(bco[:, 1]) < .07 * k)
    neck_axis = (bco[mid][:, :2].min(0) + bco[mid][:, :2].max(0)) / 2
    report['body_neck_mid_half'] = ((bco[mid][:, :2].max(0) - bco[mid][:, :2].min(0)) / 2).round(4).tolist()
    # place: soles at 0, body neck axis under the head's neck centre; the head's chin at collar + chin_over_collar
    lift = -bco[:, 2].min()
    head_lift = (collar_z + lift + chin_over_collar) - HEAD_CHIN
    shift = Vector((neck_c[0] - neck_axis[0], neck_c[1] - neck_axis[1], lift))
    body.data.transform(Matrix.Translation(shift))
    head.data.transform(Matrix.Translation((0, 0, head_lift)))
    report['head_lift'] = round(head_lift, 5)
    report['body_shift'] = [round(x, 5) for x in shift]

    # --- the neck: the head's own neck, down into the collar ---------------------------------------------------
    # The body's neck skin above COLLAR - NECK_DROP goes (the head's neck replaces it, so the visible neck is the face's
    # own paint). The head keeps its neck down to COLLAR - HEAD_NECK_BELOW; any of it under COLLAR + 1 cm that lies
    # outside the body's shirt is moved back inside it, SHIRT_INSET under the cloth.
    from mathutils.bvhtree import BVHTree
    bco = np.array([v.co[:] for v in body.data.vertices])
    collar_w = collar_z + lift
    chin_w = HEAD_CHIN + head_lift
    near = (np.abs(bco[:, 0] - neck_c[0]) < .09) & (np.abs(bco[:, 1] - neck_c[1]) < .09)
    drop = is_skin(bcol) & near & (bco[:, 2] > collar_w - NECK_DROP)
    bm = bmesh.new(); bm.from_mesh(body.data); bm.verts.ensure_lookup_table()
    gone = [f for f in bm.faces if all(drop[v.index] for v in f.verts)]
    report['body_neck_faces_removed'] = len(gone)
    bmesh.ops.delete(bm, geom=gone, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(body.data); bm.free()
    bcol = None
    bm = bmesh.new(); bm.from_mesh(head.data)
    deep = [v for v in bm.verts if v.co.z < collar_w - HEAD_NECK_BELOW]
    bmesh.ops.delete(bm, geom=deep, context='VERTS')
    bm.to_mesh(head.data); bm.free()
    # the shirt alone (the skin left under it must not count as the cloth to stay under)
    bcol2, _ = vertex_colours(body, texture_of(body.data.materials[0]), 0)
    cloth = ~is_skin(bcol2)
    bverts = [v.co.copy() for v in body.data.vertices]
    polys = [list(p.vertices) for p in body.data.polygons if all(cloth[i] for i in p.vertices)]
    tree = BVHTree.FromPolygons(bverts, polys)
    pushed = 0
    for v in head.data.vertices:
        if v.co.z > collar_w + .01:
            continue
        loc, nrm, _, _ = tree.find_nearest(v.co)
        if loc is None:
            continue
        if (v.co - loc).dot(nrm) > -SHIRT_INSET:
            v.co = loc - nrm * SHIRT_INSET
            pushed += 1
    report['head_neck_vertices_pushed_inside_shirt'] = pushed

    # --- skin colour: the body's skin to the head's neck colour ------------------------------------------------
    # Each channel's mean and spread over the arms' skin texels are carried to the face's (the head texture's skin
    # texels, as the shared material renders them), so the shading stays and nothing clips; a soft skin weight
    # blends it in, so neighbouring texels never split between corrected and not.
    head_tex = texture_of(hm)
    hw, hh = head_tex.size
    hpx = np.array(head_tex.pixels[:], np.float32).reshape(hh, hw, 4)[..., :3]
    face = hpx[is_skin(hpx)]
    bco = np.array([v.co[:] for v in body.data.vertices])
    bcol, _ = vertex_colours(body, body_tex, 0)
    w, h = body_tex.size
    px = np.array(body_tex.pixels[:], np.float32).reshape(h, w, 4)
    arms = uv_mask(body, w, h, (bco[:, 2] > ARMS_ABOVE) & is_skin(bcol))
    weight = arms * skin_weight(px[..., :3])
    sample = px[..., :3][weight > .5]
    mu_a, sd_a = sample.mean(0), sample.std(0)
    mu_f, sd_f = face.mean(0), face.std(0)
    spread = np.clip(sd_f / np.maximum(sd_a, 1e-3), *SPREAD_LIMITS)
    matched = np.clip((px[..., :3] - mu_a) * spread + mu_f, 0, 1)
    px[..., :3] += weight[..., None] * (matched - px[..., :3])
    report['skin'] = {'face_mean': mu_f.round(3).tolist(), 'face_sd': sd_f.round(3).tolist(),
                      'arms_mean': mu_a.round(3).tolist(), 'arms_sd': sd_a.round(3).tolist(),
                      'spread': spread.round(3).tolist(), 'texels': int((weight > 0).sum())}
    img = bpy.data.images.new('T_Paul_Body', w, h)
    img.pixels.foreach_set(px.ravel())
    img.file_format = 'PNG'
    img.filepath_raw = str(out / 'T_Paul_Body.png'); img.save()
    for n in body.data.materials[0].node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image == body_tex:
            n.image = img
    strip_normal_maps(body.data.materials[0])
    body.data.materials[0].name = 'M_Paul_0'

    # --- one object, his height, the GLB ---------------------------------------------------------------------------
    for o in (body, head):
        o.data.uv_layers.active.name = 'UVMap'
    bpy.ops.object.select_all(action='DESELECT')
    head.select_set(True); body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    co = np.array([v.co[:] for v in body.data.vertices])
    s = HEIGHT_M / (co[:, 2].max() - co[:, 2].min())
    body.data.transform(Matrix.Scale(s, 4))
    report['final_scale'] = round(float(s), 5)
    co = np.array([v.co[:] for v in body.data.vertices])
    report['bbox'] = [co.min(0).round(4).tolist(), co.max(0).round(4).tolist()]
    me = body.data; me.calc_loop_triangles()
    report['vertices'] = len(me.vertices); report['triangles'] = len(me.loop_triangles)
    for im in bpy.data.images:
        if im.users:
            im.pack()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'Paul-graft.blend'))
    bpy.ops.export_scene.gltf(filepath=str(out / 'Paul-graft.glb'), export_format='GLB', use_selection=False,
                              export_image_format='AUTO')
    (out / 'graft.json').write_text(json.dumps(report, indent=1) + '\n')
    print('GRAFT', json.dumps(report))
    if a.renders:
        render(body, out)


def render(obj, out):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x = 700; sc.render.resolution_y = 1100
    sc.view_settings.view_transform = 'Standard'
    sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
    sc.world.node_tree.nodes['Background'].inputs[0].default_value = (.85, .83, .8, 1)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'
    def shot(name, target, direction, scale, res=(700, 1100)):
        sc.render.resolution_x, sc.render.resolution_y = res
        cam.data.ortho_scale = scale
        cam.location = Vector(target) + Vector(direction).normalized() * 4
        cam.rotation_euler = (Vector(target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = str(out / f'{name}.png'); bpy.ops.render.render(write_still=True)
    for name, d in (('front', (1, 0, 0)), ('q', (1, -1, 0)), ('side', (0, -1, 0)), ('back', (-1, 0, 0))):
        shot(name, (0, 0, .85), d, 1.9)
    for name, d in (('neck_front', (1, 0, 0)), ('neck_q', (1, -1, .2)), ('neck_side', (0, -1, 0)),
                    ('neck_back', (-1, 0, .1)), ('neck_under', (1, 0, -.6))):
        shot(name, (0, 0, 1.33), d, .35, (700, 700))


main()
