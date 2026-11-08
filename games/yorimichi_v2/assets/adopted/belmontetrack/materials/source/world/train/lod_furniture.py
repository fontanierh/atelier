"""Levels of detail for the fitted Tripo furniture (Blender, headless): `atelier build yorimichi world.belmonte_train_furniture_lods`.

    uv run atelier build yorimichi world.belmonte_train_furniture_lods

Reads each fitted asset, build/yorimichi/belmonte-train/furniture/<asset>.glb (fit_furniture.py), and leaves it as it
is: it stays the high-poly source. For each asset in budgets.FURNITURE it writes furniture/lod/<asset>_LOD0.glb and,
when the asset has one, <asset>_LOD1.glb, and records files, checksums, budgets and screen sizes in furniture/lod/summary.json.
Fitted GLBs and source reports remain unchanged. This is a required incremental game-build step.

LOD0: the fitted mesh welded (Tripo splits every vertex on its UV seams), decimated by edge collapse to the budget,
smoothed with hard edges above 60 degrees, unwrapped again (smart projection, packed) and given one material whose
maps are baked from the full mesh in Cycles, ray-cast from a slightly inflated cage: base colour, a tangent-space normal
map that keeps the carving, tufting and grain the decimation removed, and the metal and roughness when the source has
them (else constant factors). Maps are at most budgets.texture_cap(asset) pixels, a power of two.

LOD1: the same from the fitted mesh at its own budget, with maps a quarter of LOD0's size (collapsing LOD0 further stalls
on its UV seams).

The carved bench keeps its carved M+L on the front only, as fitted: its front is baked from the source's front faces
(the mark) and a reversed twin from the clean back faces, both packed in the one map. The pot's porridge surface stays a
separate mesh and material (the game animates it), decimated with its UVs.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import hashlib
import json
import math
import sys

import bmesh
import bpy
from mathutils import Vector

from train import budgets as B
from train import bake_manifest as BM

FURN = yori.OUT / 'belmonte-train' / 'furniture'
LOD = FURN / 'lod'
SHARP_DEG = 60.
MARGIN_PX = 8
# parts smaller than this fraction of the asset's size are left to the bake, per level
DROP = {0: .03, 1: .12}
KEEP_FOLDS = set()     # assets whose folds stay closed
# per asset: the budget share by area ** exp (higher favours the big parts: the lamp's round base and shade, the
# table's cloth), and the size under which parts go to the bake (the pot's drips: left to the maps, they read as
# relief instead of faceted shards)
PART_EXP = {'canteen-pot': {0: .5}, 'table-lamp': {0: .8}, 'restaurant-table': {0: 1., 1: 1.}}
# share by the parts' own detail (source triangles) instead of area: the lamp's round, beaded base needs more than
# its plain shade, whose pleats the normal map carries
BY_DETAIL = {'table-lamp'}
# thin sheets turned towards open air rather than like the source (the cloth's own winding faces in and out)
OUTWARD = {'restaurant-table'}
# parts hidden from every side, below included, left out of LOD0 too (the cap Tripo closed the cloth with, sitting
# between its top and the modelled wooden top): their triangles go to the drapes
HIDDEN0 = {'restaurant-table'}
# LOD1 decimated from LOD0 (already turned right, its cloth one clean sheet) rather than from the source
LOD1_FROM_LOD0 = {'restaurant-table'}
ROUND = {'table-lamp'}     # turned base: decimate() holds the walls of its lower parts
PART_DROP = {'canteen-pot': {0: .16, 1: .2}}
EXP = .35          # the budget shared between parts by area ** EXP: below 0.5 favours the small, thin parts


def title(asset):
    return ''.join(p.title() for p in asset.split('-'))


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def select(objs, active):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def bake_device(scene):
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type != 'CPU']
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        scene.cycles.device = 'GPU' if gpus else 'CPU'
    except Exception as e:          # no GPU in this session: the CPU bakes the same maps, slower
        print(f'LOD: GPU unavailable ({e}), baking on the CPU', flush=True)
        scene.cycles.device = 'CPU'
    print(f'LOD: baking on {scene.cycles.device}', flush=True)


# ---------------------------------------------------------------- meshes
def bare_copy(src, name, keep=None, split=True):
    """Geometry only (no UVs, materials or normals) of src's faces whose material index passes keep, welded. split:
    open the edges shared by three faces or more (Tripo's folds and patches), which stop edge collapse."""
    me = src.data
    faces = [list(p.vertices) for p in me.polygons if keep is None or keep(p.material_index)]
    new = bpy.data.meshes.new(name)
    new.from_pydata([v.co.copy() for v in me.vertices], [], faces)
    bm = bmesh.new(); bm.from_mesh(new)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    if split:
        bmesh.ops.split_edges(bm, edges=[e for e in bm.edges if len(e.link_faces) > 2])
    bm.to_mesh(new); bm.free()
    return link(bpy.data.objects.new(name, new))


def subset(src, name, keep):
    """A copy of src (materials and UVs kept) holding only the faces whose material index passes keep."""
    o = link(bpy.data.objects.new(name, src.data.copy()))
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f.material_index)], context='FACES')
    bm.to_mesh(o.data); bm.free()
    return o


def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()
    old = obj.data; obj.data = me; me.name = old.name
    bpy.data.meshes.remove(old)


def decimate(obj, target, size=1., round_=False):
    """Edge-collapse obj down to at most target triangles (a few passes: collapse lands near, not on, its ratio).
    round_: hold the vertices whose normal is near horizontal (the walls of a turned base or column), so a round
    part keeps a round outline instead of collapsing to a few facets."""
    if round_:
        g = obj.vertex_groups.get('keep') or obj.vertex_groups.new(name='keep')
        for v in obj.data.vertices:
            g.add([v.index], (1 - abs(v.normal.z)) ** 2, 'REPLACE')
    for attempt in range(10):
        n = tris(obj)
        if n <= target:
            return n
        m = obj.modifiers.new('decimate', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'; m.use_collapse_triangulate = True
        m.ratio = max(target / n * (.985 ** attempt), .0005)
        if round_:
            m.vertex_group = 'keep'; m.vertex_group_factor = 6.
        apply_modifiers(obj)
    return tris(obj)


def orient(low, highs):
    """Turn every low face to face the way the source surface under it faces: Tripo's winding is not consistent, and
    the bake casts its rays from a cage pushed out along the low normals (a face turned inside bakes what lies behind)."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    trees = [(BVHTree.FromObject(h, dg), h.matrix_world) for h in highs]
    bm = bmesh.new(); bm.from_mesh(low.data); bm.faces.ensure_lookup_table()
    flip = []
    for f in bm.faces:
        c = f.calc_center_median()
        best = None
        for tree, mw in trees:
            loc, n, _, d = tree.find_nearest(mw.inverted() @ c)
            if loc is not None and (best is None or d < best[1]):
                best = ((mw.to_3x3() @ n).normalized(), d)
        if best and f.normal.dot(best[0]) < 0:
            flip.append(f)
    bmesh.ops.reverse_faces(bm, faces=flip)
    bm.to_mesh(low.data); bm.free()
    return len(flip)


def outward(low):
    """Turn a thin sheet's faces towards open air (a tablecloth's drapes). The winding is first made consistent over
    each connected part, then each part is turned as a whole by a vote: from every face, rays fanned over both of its
    sides; the side where more escape the mesh, weighted by face area, is the outside. Unreal draws one side of a
    face; a drape turned inwards reads there as transparent shards, whatever the double-sided preview shows."""
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new(); bm.from_mesh(low.data); bm.faces.ensure_lookup_table()
    turned = 0
    for part in islands(low.data):
        faces = [bm.faces[i] for i in part]
        bmesh.ops.recalc_face_normals(bm, faces=faces)
    bm.normal_update()
    tree = BVHTree.FromBMesh(bm)
    for part in islands(low.data):
        vote = 0.
        for i in part:
            f = bm.faces[i]
            n = f.normal
            if n.length < .5:
                continue
            t = (f.verts[1].co - f.verts[0].co).normalized()
            b = n.cross(t)
            c = f.calc_center_median()
            fan = [n] + [(n + .8 * (t * math.cos(a) + b * math.sin(a))).normalized() for a in (0, 1.57, 3.14, 4.71)]
            out = sum(tree.ray_cast(c + d * 1e-4, d)[0] is None for d in fan)
            back = sum(tree.ray_cast(c - d * 1e-4, -d)[0] is None for d in fan)
            vote += f.calc_area() * (out - back)
        if vote < 0:
            bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in part]); turned += 1
    bm.to_mesh(low.data); bm.free()
    print(f'LOD: winding made consistent per part, {turned} parts turned towards open air', flush=True)
    return turned


def islands(me):
    """Face index lists of the connected parts of a mesh."""
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    seen, parts = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, part = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop(); part.append(g.index)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        parts.append(part)
    bm.free()
    return parts


def share(parts, target, exp, by=2, least=12):
    """Triangles for each part, by area ** exp (by=2) or source triangles ** exp (by=3), at least `least` and at most what it has: what a small part cannot use goes
    back to the others (water filling), so the asset uses its whole budget."""
    alloc, left, free = {}, target, list(range(len(parts)))
    while free:
        w = sum(parts[i][by] ** exp for i in free)
        full = [i for i in free if left * parts[i][by] ** exp / w >= parts[i][3]]
        if not full:
            for i in free:
                alloc[i] = max(least, int(left * parts[i][by] ** exp / w))
            break
        for i in full:
            alloc[i] = parts[i][3]; left -= parts[i][3]; free.remove(i)
    return [alloc[i] for i in range(len(parts))]


def seen_only(highs, below=False):
    """Copies of the source keeping only the parts seen from above or the sides, for LOD1 (from its distance nobody
    looks under a table): a part (connected once welded) every one of whose sample points hits another part looking
    up and along +-X and +-Y goes, from the LOD1 mesh and from its bake. Without this the restaurant table's cloth
    top, decimated this far, sinks into the cap, wooden top and apron modelled under it and bakes them."""
    from mathutils.bvhtree import BVHTree
    dirs = [Vector(d) for d in ((0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0))] + ([Vector((0, 0, -1))] if below else [])
    out = []
    for h in highs:
        o = link(bpy.data.objects.new('HIGH_lod1_' + h.name, h.data.copy()))
        o.matrix_world = h.matrix_world
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        bm.faces.ensure_lookup_table()
        seen, parts = set(), []
        for f in bm.faces:
            if f.index in seen:
                continue
            stack, part = [f], []
            seen.add(f.index)
            while stack:
                g = stack.pop(); part.append(g)
                for e in g.edges:
                    for nb in e.link_faces:
                        if nb.index not in seen:
                            seen.add(nb.index); stack.append(nb)
            parts.append(part)
        verts = [v.co.copy() for v in bm.verts]
        drop = []
        for part in parts if len(parts) > 1 else []:
            mine = {f.index for f in part}
            tree = BVHTree.FromPolygons(verts, [[v.index for v in f.verts] for f in bm.faces if f.index not in mine])
            samples = [f.calc_center_median() for f in part[::max(1, len(part) // 60)]]
            if not any(tree.ray_cast(c + d * 1e-4, d)[0] is None for c in samples for d in dirs):
                drop += part
        print(f'LOD: LOD1 leaves out {len(drop)} hidden faces of {len(bm.faces)}', flush=True)
        bmesh.ops.delete(bm, geom=drop, context='FACES')
        bm.to_mesh(o.data); bm.free()
        out.append(o)
    return out


def decimate_parts(obj, target, size, drop, exp=EXP, by=2, round_=False, least=12, min_tris=0):
    """Share the budget between the mesh's connected parts (arms, pipes, drips, slats) by their area to the power EXP, so edge collapse's global error measure does not spend it all on the big surfaces and fold the thin parts
    away. Parts smaller than drop x size are removed: the bake keeps their look on what lies under them."""
    me = obj.data
    parts = islands(me)
    if len(parts) == 1:
        return decimate(obj, target, size)
    info = []
    for part in parts:
        pts = [me.vertices[v].co for i in part for v in me.polygons[i].vertices]
        lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
        area = sum(me.polygons[i].area for i in part)
        info.append((part, (hi - lo).length, area, sum(len(me.polygons[i].vertices) - 2 for i in part), hi.z))
    kept = [x for x in info if x[1] >= drop * size and x[3] > min_tris] or [max(info, key=lambda x: x[2])]
    while True:
        alloc = share(kept, target, exp, by, least)
        if sum(alloc) <= target or len(kept) == 1:
            break
        kept.remove(min(kept, key=lambda x: x[2]))      # too many parts for the budget: the smallest goes to the bake
    objs = []
    zs = [v.co.z for v in me.vertices]
    z_low = min(zs) + .45 * (max(zs) - min(zs))      # round_ holds only the lower parts (a lamp's base, not its shade)
    print('LOD: parts', sorted(((x[3], t) for x, t in zip(kept, alloc)), reverse=True)[:12], flush=True)
    for (part, _, _, n, top), t in zip(kept, alloc):
        new = bpy.data.meshes.new(obj.name + '_part')
        vmap = {}
        verts, faces = [], []
        for i in part:
            face = []
            for v in me.polygons[i].vertices:
                if v not in vmap:
                    vmap[v] = len(verts); verts.append(me.vertices[v].co.copy())
                face.append(vmap[v])
            faces.append(face)
        new.from_pydata(verts, [], faces)
        o = link(bpy.data.objects.new(obj.name + '_part', new))
        decimate(o, t, size, round_ and top < z_low)
        objs.append(o)
    for _ in range(8):                                   # collapse overshoots on some parts: take it from the others
        over = sum(tris(o) for o in objs) - target
        if over <= 0:
            break
        before = sum(tris(o) for o in objs)
        for o in sorted(objs, key=tris, reverse=True):
            n = tris(o)
            decimate(o, max(12, n - int(over * n / before) - 1), size)
        if sum(tris(o) for o in objs) >= before and len(objs) > 1:   # stalled: the smallest part goes to the bake
            small = min(objs, key=lambda o: sum(p.area for p in o.data.polygons))
            objs.remove(small); bpy.data.objects.remove(small)
    while sum(tris(o) for o in objs) > target and len(objs) > 1:     # never over the budget
        small = min(objs, key=lambda o: sum(p.area for p in o.data.polygons))
        objs.remove(small); bpy.data.objects.remove(small)
    select(objs, objs[0]); bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    old = obj.data; obj.data = joined.data; bpy.data.objects.remove(joined); bpy.data.meshes.remove(old)
    print(f'LOD: {obj.name}: {len(kept)} of {len(parts)} parts kept, {tris(obj)} triangles (target {target})', flush=True)
    return tris(obj)


def triangulate(obj):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(obj.data); bm.free()


def shade(obj):
    obj.data.set_sharp_from_angle(angle=math.radians(SHARP_DEG))


def unwrap(objs, angle=SHARP_DEG, margin=.004):
    select(objs, objs[0])
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle - 1), island_margin=margin, area_weight=0., correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')


def pack(objs, margin=.004):
    select(objs, objs[0])
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode='OBJECT')


def reversed_twin(obj, name, uv_scale=1.):
    o = link(bpy.data.objects.new(name, obj.data.copy()))
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        for lp in f.loops:
            lp[uv].uv = lp[uv].uv * uv_scale
    bm.to_mesh(o.data); bm.free()
    shade(o)
    return o


# ---------------------------------------------------------------- materials and bakes
def principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def needs_mr(highs):
    """Whether the source has metal or roughness worth a map (else constant factors), and those constants."""
    vals = set()
    for h in highs:
        for m in h.data.materials:
            if not m or not m.node_tree:
                continue
            b = principled(m)
            if b.inputs['Roughness'].links or b.inputs['Metallic'].links:
                return True, None
            vals.add((round(b.inputs['Roughness'].default_value, 3), round(b.inputs['Metallic'].default_value, 3)))
    if len(vals) == 1:
        r, mt = vals.pop()
        return False, (r, mt)
    return True, None


def emit(highs, what):
    """Route what ('base' colour, or 'mr': roughness in green and metal in blue) to an emission shader on every source
    material, for an EMIT bake."""
    for m in {m for h in highs for m in h.data.materials if m}:
        nt = m.node_tree; b = principled(m)
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
        em = nt.nodes.get('BAKE_EMIT') or nt.nodes.new('ShaderNodeEmission'); em.name = 'BAKE_EMIT'
        for lk in list(em.inputs['Color'].links):
            nt.links.remove(lk)
        if what == 'base':
            s = b.inputs['Base Color']
            if s.links:
                nt.links.new(s.links[0].from_socket, em.inputs['Color'])
            else:
                em.inputs['Color'].default_value = s.default_value
        else:
            cc = nt.nodes.get('BAKE_MR') or nt.nodes.new('ShaderNodeCombineColor'); cc.name = 'BAKE_MR'
            cc.inputs['Red'].default_value = 1.
            for src, dst in (('Roughness', 'Green'), ('Metallic', 'Blue')):
                s = b.inputs[src]
                for lk in list(cc.inputs[dst].links):
                    nt.links.remove(lk)
                if s.links:
                    nt.links.new(s.links[0].from_socket, cc.inputs[dst])
                else:
                    cc.inputs[dst].default_value = s.default_value
            nt.links.new(cc.outputs['Color'], em.inputs['Color'])
        nt.links.new(em.outputs['Emission'], out.inputs['Surface'])


def restore(highs):
    for m in {m for h in highs for m in h.data.materials if m}:
        nt = m.node_tree
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
        nt.links.new(principled(m).outputs['BSDF'], out.inputs['Surface'])


def new_image(name, px, color, non_color):
    img = bpy.data.images.new(name, px, px, alpha=False)
    img.generated_color = color
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    return img


def low_material(name, px, mr, constants, double_sided):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree; b = principled(mat)
    imgs = dict(base=new_image(f'{name}_base', px, (.5, .5, .5, 1), False),
                normal=new_image(f'{name}_normal', px, (.5, .5, 1, 1), True))
    if mr:
        imgs['mr'] = new_image(f'{name}_mr', px, (1, .5, 0, 1), True)
    nodes = {}
    for k, img in imgs.items():
        n = nt.nodes.new('ShaderNodeTexImage'); n.image = img; n.name = k; nodes[k] = n
    nt.links.new(nodes['base'].outputs['Color'], b.inputs['Base Color'])
    nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(nodes['normal'].outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    if mr:
        sep = nt.nodes.new('ShaderNodeSeparateColor')
        nt.links.new(nodes['mr'].outputs['Color'], sep.inputs['Color'])
        nt.links.new(sep.outputs['Green'], b.inputs['Roughness']); nt.links.new(sep.outputs['Blue'], b.inputs['Metallic'])
    else:
        b.inputs['Roughness'].default_value, b.inputs['Metallic'].default_value = constants
    mat.use_backface_culling = not double_sided
    return mat, nodes


def bake(kind, low, highs, node, size, clear, cage=1.):
    select(highs + [low], low)
    low.active_material.node_tree.nodes.active = node
    ext = min(max(.025 * size, .006), .03) * cage
    bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=ext, max_ray_distance=ext + .1 * size,
                        margin=MARGIN_PX, use_clear=clear, normal_space='TANGENT')


def bake_all(pairs, nodes, size, mr, cage=1.):
    """pairs: [(low, highs)] baked into the same maps, the first clearing them."""
    for i, (low, highs) in enumerate(pairs):
        bake('NORMAL', low, highs, nodes['normal'], size, i == 0, cage)
    for i, (low, highs) in enumerate(pairs):
        emit(highs, 'base'); bake('EMIT', low, highs, nodes['base'], size, i == 0, cage)
    if mr:
        for i, (low, highs) in enumerate(pairs):
            emit(highs, 'mr'); bake('EMIT', low, highs, nodes['mr'], size, i == 0, cage)
    for _, highs in pairs:
        restore(highs)


def face_normals(img):
    """Where the source surface faces away from the low one (Tripo leaves some parts wound inside out and shows them
    double-sided), the baked normal points into the surface: turn it round."""
    import numpy as np
    px = np.empty(len(img.pixels), np.float32); img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    v = px[:, :3] * 2 - 1
    back = v[:, 2] < 0
    v[back] = -v[back]
    px[:, :3] = (v + 1) / 2
    img.pixels.foreach_set(px.ravel())
    print(f'LOD: {back.mean():.1%} of the normal map turned round', flush=True)


def save_maps(asset, nodes):
    """Write the baked maps (base colour JPEG, normal and metal-roughness PNG) and put the files themselves in the
    material: the glTF exporter embeds an image file's own bytes."""
    out = {}
    face_normals(nodes['normal'].image)
    for k, n in nodes.items():
        img = n.image
        ext, fmt = ('jpg', 'JPEG') if k == 'base' else ('png', 'PNG')
        path = LOD / f'{asset}-{k}.{ext}'
        img.filepath_raw = str(path); img.file_format = fmt; img.save()
        fresh = bpy.data.images.load(str(path), check_existing=False)
        if k != 'base':
            fresh.colorspace_settings.name = 'Non-Color'
        n.image = fresh
        out[k] = list(fresh.size)
    return out


def export(path, objs):
    select(objs, objs[0])
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                              export_image_format='AUTO', export_tangents=True)
    return path


# ---------------------------------------------------------------- one asset
def level(asset, k, highs, target, px, size, mr, constants, carved, start=None):
    """One level of detail: the source welded and decimated to target, unwrapped, its maps baked at px from highs.
    Returns the low object and its maps' sizes."""
    name = f'SM_BT_{title(asset)}' + ('' if k == 0 else f'_LOD{k}')
    mname = f'M_BT_{title(asset)}' + ('' if k == 0 else f'_LOD{k}')
    if carved and k:    # at LOD1 distance one double-sided surface baked from the front (the mark) will do
        h = highs[0]
        back = next(i for i, m in enumerate(h.data.materials) if m.name.endswith('_back'))
        highs = [subset(h, f'HIGH_front{k}', lambda i: i != back)]
        carved = False
    if carved:
        h = highs[0]
        back = next(i for i, m in enumerate(h.data.materials) if m.name.endswith('_back'))
        high_front = subset(h, f'HIGH_front{k}', lambda i: i != back)
        high_back = subset(h, f'HIGH_back{k}', lambda i: i == back)
        low = bare_copy(high_front, name)
        decimate_parts(low, target // 2, size, DROP[k])
        orient(low, [high_front])
        shade(low)
        unwrap([low])
        twin = reversed_twin(low, name + '_twin', uv_scale=.5)    # the clean back: a quarter of the front's map area
        pack([low, twin])
        mat, nodes = low_material(mname, px, mr, constants, double_sided=False)
        for o in (low, twin):
            o.data.materials.append(mat)
        bake_all([(low, [high_front]), (twin, [high_back])], nodes, size, mr)
        select([low, twin], low); bpy.ops.object.join()
        for o in (high_front, high_back):
            o.hide_set(True); o.hide_render = True
    else:
        low = bare_copy(start or (highs[0] if len(highs) == 1 else join_copy(highs)), name, split=asset not in KEEP_FOLDS)
        decimate_parts(low, target, size, PART_DROP.get(asset, DROP)[k], PART_EXP.get(asset, {}).get(k, EXP),
                       3 if asset in BY_DETAIL else 2, asset in ROUND,
                       least=12 if k == 0 else 6,
                       min_tris=12 if start is not None else 0)   # from LOD0: its boxes (12 triangles) are inside   # LOD1: a slat may be a thin wedge, so a bench keeps its back
        if start is None:             # a start mesh (LOD0) is already turned right
            orient(low, highs)
            if asset in OUTWARD:
                outward(low)
        shade(low)
        unwrap([low]); pack([low])
        # a sheet turned outward is drawn one-sided, as in the game, so the review shows any face still turned in
        mat, nodes = low_material(mname, px, mr, constants, double_sided=asset not in OUTWARD)
        low.data.materials.append(mat)
        # LOD1 sags further from the source (a table's cloth top sinks under the wooden top inside it): a deeper cage
        bake_all([(low, highs)], nodes, size, mr, cage=2. if k else 1.)
    return low, save_maps(asset + ('' if k == 0 else f'-lod{k}'), nodes)


def make(asset):
    lod0_t, lod1_t, px = B.FURNITURE[asset]
    lod1_t = B.LOD1_AIM.get(asset, lod1_t)
    src = FURN / f'{asset}.glb'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bake_device(scene)
    bpy.ops.import_scene.gltf(filepath=str(src))
    meshes = [o for o in scene.objects if o.type == 'MESH']
    porridge = next((o for o in meshes if o.name.endswith('_PorridgeSurface')), None)
    highs = [o for o in meshes if o is not porridge]
    for o in highs:
        o.name = 'HIGH_' + o.name
    lo = Vector([min((o.matrix_world @ v.co)[i] for o in highs for v in o.data.vertices) for i in range(3)])
    hi = Vector([max((o.matrix_world @ v.co)[i] for o in highs for v in o.data.vertices) for i in range(3)])
    size = max(hi - lo)
    high_tris = sum(tris(o) for o in highs) + (tris(porridge) if porridge else 0)
    mr, constants = needs_mr(highs)
    carved = any(m and m.name.endswith('_back') for o in highs for m in o.data.materials)
    extra = []
    if porridge:                                          # its own mesh and material: lighter, UVs kept
        decimate(porridge, 120); extra = [porridge]
    LOD.mkdir(parents=True, exist_ok=True)
    radius = (hi - lo).length / 2
    sizes = B.screen_sizes(asset, radius)
    low, textures = level(asset, 0, seen_only(highs, below=True) if asset in HIDDEN0 else highs, lod0_t - sum(tris(o) for o in extra), px, size, mr, constants, carved)
    files = [export(LOD / f'{asset}_LOD0.glb', [low] + extra)]
    record = [dict(level=0, glb=files[0].name, triangles=tris(low) + sum(tris(o) for o in extra), screen_size=sizes['lod0'],
                   textures=textures)]
    if lod1_t:          # its own small bake: collapsing LOD0 further stalls on its UV seams
        l1, tex1 = level(asset, 1, seen_only(highs), lod1_t, max(px // 4, 128), size, mr, constants, carved,
                         start=low if asset in LOD1_FROM_LOD0 else None)
        files.append(export(LOD / f'{asset}_LOD1.glb', [l1]))
        record.append(dict(level=1, glb=files[1].name, triangles=tris(l1), screen_size=sizes['lod1'], textures=tex1))
    for r, f in zip(record, files):
        r.update(bytes=f.stat().st_size, sha256=sha(f))
    result = dict(source=src.name, source_sha256=sha(src), source_triangles=high_tris, levels=record,
                  cull_screen_size=sizes['cull'], bounds_radius_m=round(radius, 4), textures=textures,
                  materials=1 + len(extra), metal_roughness_map=mr,
                  constants=None if mr else dict(roughness=constants[0], metallic=constants[1]),
                  tool='games/yorimichi/world/train/lod_furniture.py')
    print('LOD', asset, json.dumps(dict(source=high_tris, levels=[(r['level'], r['triangles']) for r in record], textures=textures)), flush=True)
    return result


def join_copy(objs):
    """One temporary object holding the geometry of several (for bare_copy)."""
    copies = [link(bpy.data.objects.new(o.name + '_j', o.data.copy())) for o in objs]
    for c, o in zip(copies, objs):
        c.matrix_world = o.matrix_world
    select(copies, copies[0]); bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active
    j.data.transform(j.matrix_world); j.matrix_world.identity()
    j.hide_render = True
    return j


def main():
    """Bake every production asset, publishing a summary only after complete budget verification."""
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if args:
        raise ValueError('production furniture baking requires the complete asset set')
    missing = [a for a in B.FURNITURE if not (FURN / f'{a}.glb').is_file()]
    if missing:
        raise FileNotFoundError(f'furniture sources missing: {missing}')
    LOD.mkdir(parents=True, exist_ok=True)
    path = LOD / 'summary.json'
    path.unlink(missing_ok=True)
    summary = {}
    for k, a in enumerate(B.FURNITURE):
        print(f'LOD [{k + 1}/{len(B.FURNITURE)}] {a}', flush=True)
        summary[a] = make(a)
    pending = LOD / 'summary.pending.json'
    pending.write_text(json.dumps(summary, indent=2) + '\n')
    BM.read(FURN, summary_path=pending)
    pending.replace(path)
    print('BELMONTE TRAIN FURNITURE LODS COMPLETE', flush=True)


if __name__ == '__main__':
    main()
