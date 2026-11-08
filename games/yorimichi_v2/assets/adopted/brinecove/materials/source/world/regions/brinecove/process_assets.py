#!/usr/bin/env python3
"""Normalize, reduce, validate and review local TRELLIS town assets.

    blender -b --factory-startup --threads 3 --python world/regions/brinecove/process_assets.py -- --only statue

The neural source stays in build/.  Only the selected, processed GLB and its
provenance are written under assets/brinecove/models.
"""
import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from brinecove import layout as L  # noqa: E402
from brinecove.paths import MODELS, REFERENCES, REPO, REVIEW as BUILD, TEXTURES  # noqa: E402
REVIEWS = BUILD / 'asset-reviews'

ASSETS = {
    'pirate-queen-statue': dict(
        source=BUILD / 'trellis/out/statue/head.glb', height=22.0, remesh=True, resolution=360, triangles=40000, prune=50, palette=('stone_light', 'stone', 'stone_dark', 'cream', 'rope', 'sail'),
        dilate=True, base=8.0,
        notes='harbor statue; full figure and plinth; dilated learned stone texture'),
    'galleon-figurehead': dict(
        source=BUILD / 'trellis/out/figurehead/head.glb', height=6.5, remesh=True, resolution=340, triangles=45000, prune=100, palette=('wood_light', 'wood', 'cream', 'coral', 'flag_red', 'gold'),
        dilate=True, base=0.0, notes='siren figurehead for the two galleons'),
    'harbor-cannon': dict(
        source=BUILD / 'trellis/out/cannon/head.glb', height=4.8, remesh=True, resolution=300, triangles=20000, prune=50, palette=('metal', 'stone_dark', 'wood', 'wood_dark', 'rope'),
        dilate=True, base=0.0, notes='iron cannon on oak carriage'),
    'ship-anchor': dict(
        source=BUILD / 'trellis/out/anchor/head.glb', height=4.8, remesh=True, resolution=300, triangles=20000, prune=100, palette=('metal', 'wood_dark', 'stone_dark', 'rope'),
        dilate=True, base=0.0, notes='quay anchor with rope'),
    'harbor-capstan': dict(
        source=BUILD / 'trellis/out/capstan/head.glb', height=2.8, remesh=True, resolution=320, triangles=18000, prune=200, palette=('wood', 'wood_light', 'wood_dark', 'metal', 'rope'),
        dilate=True, base=0.0, notes='working pier capstan'),
    'ships-wheel': dict(
        source=BUILD / 'trellis/out/wheel/head.glb', height=2.8, remesh=True, resolution=300, triangles=12000, prune=50, palette=('wood_light', 'wood', 'wood_dark', 'gold', 'metal', 'rope'),
        dilate=True, base=0.0, notes="ship's wheel for the stern deck"),
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi


def import_one(source):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == 'MESH']
    if not imported:
        raise RuntimeError(f'No mesh imported from {source}')
    for obj in bpy.data.objects:
        obj.select_set(obj in imported)
    bpy.context.view_layer.objects.active = imported[0]
    if len(imported) > 1:
        bpy.ops.object.join()
    obj = bpy.context.object
    obj.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    weld(obj)
    return obj


def weld(obj):
    """Merge the marching-cubes duplicate vertices before any reduction."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    print(f'welded {obj.name}: {before} -> {len(obj.data.vertices)} vertices', flush=True)


def normalize(obj, target_height):
    lo, hi = bounds(obj)
    height = hi.z - lo.z
    if height <= 1e-6:
        raise RuntimeError('Imported asset has zero height')
    scale = target_height / height
    obj.scale = (scale, scale, scale)
    bpy.ops.object.transform_apply(scale=True)
    lo, hi = bounds(obj)
    obj.location.x -= (lo.x + hi.x) / 2
    obj.location.y -= (lo.y + hi.y) / 2
    obj.location.z -= lo.z
    bpy.ops.object.transform_apply(location=True)
    return bounds(obj)


def prune_islands(obj, max_faces):
    """Drop the thousands of tiny disconnected shells TRELLIS leaves behind.

    A collapse decimation can never go below roughly four faces per connected
    shell.  The raw props contain 50k-150k shells, so pruning the specks first
    is what makes a 12k-45k triangle budget reachable at all.
    """
    mesh = obj.data
    n = len(mesh.vertices)
    parent = list(range(n))
    rank = [0] * n

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for edge in mesh.edges:
        a, b = edge.vertices
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
    face_root = [find(poly.vertices[0]) for poly in mesh.polygons]
    sizes = {}
    for root in face_root:
        sizes[root] = sizes.get(root, 0) + 1
    doomed = [i for i, root in enumerate(face_root) if sizes[root] <= max_faces]
    if not doomed:
        return 0, len(sizes)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in doomed], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    print(f'pruned {len(doomed)} faces in shells <= {max_faces} faces '
          f'({len(sizes)} -> {len(sizes) - sum(1 for size in sizes.values() if size <= max_faces)} shells)',
          flush=True)
    return len(doomed), len(sizes)


PALETTE = ('stone_light', 'stone', 'stone_dark', 'cream', 'wood', 'wood_light', 'wood_dark',
           'metal', 'gold', 'rope', 'coral', 'flag_red', 'sail')


def srgb_channel(value):
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def linear_color(name):
    hex_color = L.COLORS.get(name, '#808080')
    return tuple(srgb_channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))


def palette_material(name):
    material = bpy.data.materials.get(f'Brinecove {name}')
    if material:
        return material
    material = bpy.data.materials.new(f'Brinecove {name}')
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    texture = TEXTURES / f'{name}.jpg'
    if texture.exists():
        image = bpy.data.images.load(str(texture), check_existing=True)
        node = material.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        material.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        red, green, blue = linear_color(name)
        bsdf.inputs['Base Color'].default_value = (red, green, blue, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.9
    return material


def basecolor_image(obj):
    for material in obj.data.materials:
        if not material or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image and node.image.size[0] > 0:
                return node.image
    return None


def remesh_retopo(obj, source, target, resolution, palette_names=None):
    """Voxel-remesh a shredded TRELLIS surface, decimate it, and repaint it.

    The neural meshes are triangle soup with tens of thousands of holes and
    non-manifold rims, which pins a collapse decimation far above any game
    budget.  A voxel remesh produces a clean manifold surface; the original
    surface is then sampled per face so the new low-poly prop keeps the
    painted wood, iron, stone and rope zones using the proposal palette.
    """
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.geometry import barycentric_transform

    image = basecolor_image(source)
    src_mesh = source.data
    bvh = BVHTree.FromPolygons([vertex.co.copy() for vertex in src_mesh.vertices],
                               [tuple(poly.vertices) for poly in src_mesh.polygons],
                               all_triangles=False)
    pixels = None
    if image is not None:
        width, height = image.size
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)[..., :3]

    thickness = max(0.008, source_height(source) * 0.006)
    shell = obj.modifiers.new('Brinecove shell', 'SOLIDIFY')
    shell.thickness = thickness
    shell.offset = 0.0
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=shell.name)
    print(f'solidified by {thickness:.3f} m', flush=True)
    voxel = max(0.004, source_height(source) / resolution)
    modifier = obj.modifiers.new('Brinecove retopo', 'REMESH')
    modifier.mode = 'VOXEL'
    modifier.voxel_size = voxel
    if hasattr(modifier, 'use_smooth_shade'):
        modifier.use_smooth_shade = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    print(f'remeshed at {voxel:.4f} m: {len(obj.data.polygons)} faces', flush=True)
    reduce_mesh(obj, target)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(62), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

    names = tuple(palette_names or PALETTE)
    materials = [palette_material(name) for name in names]
    obj.data.materials.clear()
    for material in materials:
        obj.data.materials.append(material)
    palette = [(i, linear_color(name)) for i, name in enumerate(names)]
    src_uv = src_mesh.uv_layers.active.data if src_mesh.uv_layers.active else None
    mesh = obj.data
    counts = [0] * len(names)
    for poly in mesh.polygons:
        location, normal, index, distance = bvh.find_nearest(poly.center)
        best = 0
        if location is not None and index is not None and index < len(src_mesh.polygons):
            source_poly = src_mesh.polygons[index]
            verts = [src_mesh.vertices[v].co for v in source_poly.vertices[:3]]
            if len(verts) == 3 and src_uv is not None:
                weights = barycentric_transform(location, verts[0], verts[1], verts[2],
                                                Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)),
                                                Vector((0.0, 0.0, 1.0)))
                loops = list(source_poly.loop_indices)[:3]
                u = sum(weights[i] * src_uv[loops[i]].uv.x for i in range(3))
                v = sum(weights[i] * src_uv[loops[i]].uv.y for i in range(3))
                if pixels is not None:
                    x = int((u % 1.0) * (pixels.shape[1] - 1))
                    y = int((v % 1.0) * (pixels.shape[0] - 1))
                    sample = pixels[y, x]
                    best = min(palette, key=lambda item: sum((sample[k] - item[1][k]) ** 2 for k in range(3)))[0]
                else:
                    best = 1
        poly.material_index = best
        counts[best] += 1
    mesh.update()
    summary = ', '.join(f'{names[i]}:{count}' for i, count in enumerate(counts) if count)
    print(f'palette faces: {summary}', flush=True)


def source_height(obj):
    lo, hi = bounds(obj)
    return max(1e-6, hi.z - lo.z)


def close_holes(obj):
    """Fill the thousands of tiny boundary loops before decimation.

    TRELLIS surfaces carry roughly 6k-10k small holes.  A collapse decimation
    preserves boundary rims, so those holes pin the triangle count far above
    any game budget.  Filling them (and carrying an averaged UV onto each new
    patch) lets the quadric collapse run to the real target.
    """
    from mathutils import Vector
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active
    vert_uv = {}
    if uv_layer is not None:
        for face in bm.faces:
            for loop in face.loops:
                vert_uv.setdefault(loop.vert.index, []).append(loop[uv_layer].uv.copy())
    boundary = [edge for edge in bm.edges if len(edge.link_faces) == 1]
    if not boundary:
        bm.free()
        return 0, 0
    before = len(bm.faces)
    result = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    new_faces = result.get('faces', [])
    if uv_layer is not None:
        for face in new_faces:
            for loop in face.loops:
                uvs = vert_uv.get(loop.vert.index)
                if uvs:
                    total = Vector((0.0, 0.0))
                    for uv in uvs:
                        total += uv
                    loop[uv_layer].uv = total / len(uvs)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    print(f'closed holes: {len(new_faces)} faces added from {len(boundary)} boundary edges '
          f'({before} -> {len(obj.data.polygons)})', flush=True)
    return len(new_faces), len(boundary)


def reduce_mesh(obj, target):
    def triangles():
        return sum(len(poly.vertices) - 2 for poly in obj.data.polygons)

    before = triangles()
    if before <= target:
        return before, before
    # A single traversal can stall on dense TRELLIS boundaries. Repeat from
    # the reduced mesh until it reaches the budget or stops making progress,
    # and report every pass so a plateau is visible in the build log.
    for attempt in range(14):
        current = triangles()
        if current <= target * 1.05:
            break
        modifier = obj.modifiers.new(f'Brinecove reduction {attempt}', 'DECIMATE')
        modifier.decimate_type = 'COLLAPSE'
        modifier.ratio = max(0.002, min(1.0, target / current))
        modifier.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        after = triangles()
        print(f'reduce pass {attempt}: {current} -> {after} (target {target})', flush=True)
        if after >= current * 0.995:
            print(f'reduction plateau at {after} triangles', flush=True)
            break
    return before, triangles()


def remesh_and_stone(obj, voxel, texture):
    modifier = obj.modifiers.new('Brinecove solid remesh', 'REMESH')
    modifier.mode = 'VOXEL'
    modifier.voxel_size = voxel
    if hasattr(modifier, 'use_smooth_shade'):
        modifier.use_smooth_shade = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(62), island_margin=0.025)
    bpy.ops.object.mode_set(mode='OBJECT')
    mat = bpy.data.materials.new('Brinecove carved stone')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get('Principled BSDF')
    image = bpy.data.images.load(str(TEXTURES / f'{texture}.jpg'), check_existing=True)
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = image
    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.93
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def dilate_basecolor(obj, slug):
    """Grow the painted island colours into the white atlas background.

    The TRELLIS atlas has almost no gutter.  At glancing UVs the renderer samples
    the white page behind the island and draws bright streaks.  A few vectorized
    dilation steps remove those seams without changing the UV layout.
    """
    import numpy as np
    from collections import deque
    for material in obj.data.materials:
        if not material or not material.use_nodes:
            continue
        bsdf = material.node_tree.nodes.get('Principled BSDF')
        if not bsdf:
            continue
        image_node = None
        for link in material.node_tree.links:
            if link.to_node == bsdf and link.to_socket.name == 'Base Color':
                if link.from_node.type == 'TEX_IMAGE' and link.from_node.image:
                    image_node = link.from_node
                    break
        if image_node is None:
            continue
        image = image_node.image
        width, height = image.size
        rgba = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
        rgb = rgba[..., :3]
        near_white = (rgb.min(axis=2) > 0.90) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 0.035)
        near_black = rgb.max(axis=2) < 0.035
        near_background = near_white | near_black
        # Only the background connected to the image border is safe to repaint;
        # pale highlights inside the statue stay untouched.
        border = np.zeros_like(near_white)
        border[0, :] = border[-1, :] = True
        border[:, 0] = border[:, -1] = True
        bg = np.zeros_like(near_white)
        queue = deque()
        for y, x in zip(*np.where(border & near_background)):
            bg[y, x] = True
            queue.append((int(y), int(x)))
        while queue:
            y, x = queue.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < height and 0 <= xx < width and near_background[yy, xx] and not bg[yy, xx]:
                    bg[yy, xx] = True
                    queue.append((yy, xx))
        valid = ~bg
        for _ in range(14):
            filled = np.zeros_like(bg)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                shifted_valid = np.roll(valid, (dy, dx), axis=(0, 1))
                shifted_color = np.roll(rgb, (dy, dx), axis=(0, 1))
                take = bg & ~filled & shifted_valid
                rgb[take] = shifted_color[take]
                filled |= take
            if not filled.any():
                break
            valid |= filled
            bg &= ~filled
        rgba[..., :3] = np.clip(rgb, 0, 1)
        image.pixels = rgba.ravel().tolist()
        image.pack()
        out = BUILD / 'texture-dilation' / f'{slug}-{image.name}.png'
        out.parent.mkdir(parents=True, exist_ok=True)
        image.filepath_raw = str(out)
        image.file_format = 'PNG'
        image.save()
        return str(out.relative_to(REPO))
    return None


def validate(obj):
    mesh = obj.data
    if not mesh.uv_layers:
        raise RuntimeError('No UV layer after processing')
    textured = 0
    for material in mesh.materials:
        if not material or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                textured += 1
                break
    if not textured:
        raise RuntimeError('No base-color texture survived processing')
    if any(not all(math.isfinite(c) for c in vertex.co) for vertex in mesh.vertices):
        raise RuntimeError('Non-finite vertex coordinate')
    return dict(triangles=sum(len(p.vertices) - 2 for p in mesh.polygons), vertices=len(mesh.vertices),
                uv_layers=len(mesh.uv_layers), materials=len(mesh.materials), textured_materials=textured,
                images=len([img for img in bpy.data.images if img.size[0] > 0]))


def review_views(obj, slug, height):
    REVIEWS.mkdir(parents=True, exist_ok=True)
    lo, hi = bounds(obj)
    span = max(height, hi.x - lo.x, hi.y - lo.y)
    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new(f'{slug} review world')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.72, 0.74, 0.72, 1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    bpy.ops.mesh.primitive_plane_add(size=max(20.0, span * 3.0), location=(0, 0, -0.03))
    floor = bpy.context.object
    floor.name = 'Review floor'
    mat = bpy.data.materials.new('Review floor material')
    mat.use_nodes = True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.46, 0.42, 0.35, 1)
    floor.data.materials.append(mat)
    sun_data = bpy.data.lights.new('Review sun', 'SUN')
    sun_data.energy = 3.4
    sun_data.color = (1.0, 0.86, 0.68)
    sun = bpy.data.objects.new('Review sun', sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(52), math.radians(4), math.radians(-34))
    cam_data = bpy.data.cameras.new('Review camera')
    cam = bpy.data.objects.new('Review camera', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 62
    dist = max(8.0, span * 2.2)
    center = Vector((0, 0, height * 0.50))
    for name, pos in (
        ('front', (0, -dist, height * 0.58)),
        ('three-quarter', (dist * 0.72, -dist * 0.72, height * 0.58)),
        ('side', (dist, 0, height * 0.52)),
    ):
        cam.location = pos
        cam.rotation_euler = (center - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(REVIEWS / f'{slug}-{name}.png')
        bpy.ops.render.render(write_still=True)


def process(slug):
    config = ASSETS[slug]
    source = config['source']
    if not source.exists():
        raise SystemExit(f'Missing neural source: {source}')
    clear()
    obj = import_one(source)
    obj.name = slug
    lo, hi = normalize(obj, config['height'])
    if config.get('remesh'):
        before = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
        reference = obj.copy()
        reference.data = obj.data.copy()
        bpy.context.scene.collection.objects.link(reference)
        remesh_retopo(obj, reference, config['triangles'], config.get('resolution', 340),
                      config.get('palette'))
        bpy.data.objects.remove(reference, do_unlink=True)
        pruned, shells, filled, rims = 0, 0, 0, 0
        after = sum(len(poly.vertices) - 2 for poly in obj.data.polygons)
        lo, hi = bounds(obj)
        dilation = None
    else:
        pruned, shells = prune_islands(obj, config.get('prune', 50))
        filled, rims = close_holes(obj)
        lo, hi = normalize(obj, config['height'])
        before, after = reduce_mesh(obj, config['triangles'])
        dilation = dilate_basecolor(obj, slug) if config.get('dilate') else None
    checks = validate(obj)
    review_views(obj, slug, config['height'])
    MODELS.mkdir(parents=True, exist_ok=True)
    target = MODELS / f'{slug}.glb'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', use_selection=True,
                              export_apply=True, export_yup=True, export_animations=False,
                              export_skins=False, export_cameras=False, export_lights=False,
                              export_image_format='JPEG', export_image_quality=88)
    generation = source.parent / 'generation-report.json'
    gen = json.loads(generation.read_text()) if generation.exists() else {}
    reference = REFERENCES / 'props' / f'{slug}.png'
    report = dict(
        slug=slug, stage='brinecove-trellis-processed', generated=datetime.now(timezone.utc).isoformat(),
        source=str(source.relative_to(REPO)), source_sha256=sha(source),
        reference=str(reference.relative_to(REPO)) if reference.exists() else None,
        reference_sha256=sha(reference) if reference.exists() else None,
        generation=gen, target_height_m=config['height'], notes=config['notes'],
        triangles_before=before, triangles_after=after, pruned_faces=pruned, shells=shells,
        filled_faces=filled, boundary_rim_edges=rims, bounds=dict(
            min=[round(v, 4) for v in lo], max=[round(v, 4) for v in hi]),
        output=str(target.relative_to(REPO)), output_sha256=sha(target), checks=checks,
        texture_dilation=dilation,
        processing=['parent clear', 'transform apply', 'uniform scale to target height',
                    'solidify open surface', 'voxel remesh to a manifold shell',
                    'collapse decimate', 'smart UV unwrap', 'nearest-surface palette paint',
                    'UV/texture/material and finite-vertex validation', 'three Blender review renders'],
    )
    (MODELS / f'{slug}.provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    slugs = [s for s in args.only.split(',') if s] or list(ASSETS)
    for slug in slugs:
        process(slug)


if __name__ == '__main__':
    main()
