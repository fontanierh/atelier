#!/usr/bin/env python3
"""Build and render the Brinecove proposal in headless Blender.

    blender -b --factory-startup --python world/regions/brinecove/review_build.py -- --stage all
    blender -b --factory-startup --python world/regions/brinecove/review_build.py -- --stage render

The review build writes one GLB per module, an assembled .blend, a full-scene GLB, Eevee review renders and the
three.js viewer payload to build/yorimichi/brinecove-review. The game reads none of it (world.brinecove exports
the game meshes).
"""
import argparse
import json
import math
import random
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401

import bpy  # noqa: E402
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402

from brinecove import layout as L  # noqa: E402
from brinecove import modules  # noqa: E402
from brinecove import hero_assets  # noqa: E402
from brinecove import flora  # noqa: E402
from brinecove import surfaces as S  # noqa: E402
from brinecove.paths import REGION, REPO, REFERENCES, REVIEW, TEXTURES  # noqa: E402

OUT = REVIEW
SCENE_OUT = OUT / 'scene'
MODEL_OUT = OUT / 'models'
VIEWER_OUT = OUT / 'viewer'
RENDER_OUT = OUT / 'renders'
TEXTURE_DIR = TEXTURES


def srgb_to_linear(value):
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def make_material(name, hex_color):
    r = srgb_to_linear(int(hex_color[1:3], 16))
    g = srgb_to_linear(int(hex_color[3:5], 16))
    b = srgb_to_linear(int(hex_color[5:7], 16))
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.88
    texture = TEXTURE_DIR / f'{name}.png'
    if not texture.exists():
        texture = TEXTURE_DIR / f'{name}.jpg'
    if texture.exists():
        image = bpy.data.images.load(str(texture), check_existing=True)
        image.colorspace_settings.name = 'sRGB'
        tex = nodes.new('ShaderNodeTexImage')
        tex.name = f'{name} painted surface'
        tex.image = image
        tex.interpolation = 'Linear'
        mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        bsdf.inputs['Base Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        if name.startswith(('roof_', 'stone', 'cobble')):
            bsdf.inputs['Roughness'].default_value = 0.94
        elif name.startswith(('wood', 'plaster', 'cream', 'ochre', 'coral', 'sage', 'teal')):
            bsdf.inputs['Roughness'].default_value = 0.9
    if name == 'mist' and texture.exists():
        # Spray is soft and see-through; a clipped mask turned it into cotton balls.
        mat.node_tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        try:
            mat.surface_render_method = 'BLENDED'
        except (AttributeError, TypeError):
            pass
        mat.use_backface_culling = False
        bsdf.inputs['Roughness'].default_value = 0.9
    elif name.startswith(('leaf_', 'palm_', 'waterfall', 'spray')) and texture.exists():
        # An explicit greater-than node makes the glTF exporter emit
        # alphaMode MASK with a cutoff instead of blended transparency.
        clip = nodes.new('ShaderNodeMath')
        clip.operation = 'GREATER_THAN'
        clip.inputs[1].default_value = 0.45
        mat.node_tree.links.new(tex.outputs['Alpha'], clip.inputs[0])
        mat.node_tree.links.new(clip.outputs['Value'], bsdf.inputs['Alpha'])
        try:
            mat.surface_render_method = 'DITHERED'
        except (AttributeError, TypeError):
            pass
        try:
            mat.blend_method = 'CLIP'
            mat.alpha_threshold = 0.45
        except (AttributeError, TypeError):
            pass
        mat.use_backface_culling = False
        bsdf.inputs['Roughness'].default_value = 0.82
    if name in ('metal', 'gold'):
        bsdf.inputs['Metallic'].default_value = 0.65
        bsdf.inputs['Roughness'].default_value = 0.45
    if name in ('glass', 'glass_warm'):
        bsdf.inputs['Roughness'].default_value = 0.25
    if name in ('lantern', 'glass_warm'):
        bsdf.inputs['Emission Color'].default_value = (r, g, b, 1.0)
        bsdf.inputs['Emission Strength'].default_value = 2.5
    if name == 'water':
        bsdf.inputs['Roughness'].default_value = 0.22
        bsdf.inputs['Metallic'].default_value = 0.0
    return mat


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def make_object(builder, collection, materials):
    used = [name for name in materials if name in set(builder.mats)]
    index = {name: i for i, name in enumerate(used)}
    mesh = bpy.data.meshes.new(builder.name)
    mesh.from_pydata(builder.verts, [], builder.faces)
    uv_layer = mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = builder.uvs[loop.vertex_index]
    for name in used:
        mesh.materials.append(materials[name])
    custom = builder.normals is not None
    for poly, mat in zip(mesh.polygons, builder.mats):
        poly.material_index = index[mat]
        poly.use_smooth = custom
    mesh.validate(verbose=False)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    # Faces with authored custom normals (leaf cards, the smooth cannon barrel) keep their winding: recalculating a
    # lone face can flip it, and Blender then shades its back with the custom normal reversed, as dark bands.
    authored = builder.normals
    bm.verts.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces
                                             if authored is None or authored[f.verts[0].index] is None])
    bm.to_mesh(mesh)
    bm.free()
    if custom:
        # Every face owns its vertices, so per-vertex normals are per-corner: crown normals on the leaf cards,
        # the flat face normal everywhere else.
        normals = list(builder.normals)
        for poly in mesh.polygons:
            for v in poly.vertices:
                if normals[v] is None:
                    normals[v] = tuple(poly.normal)
        mesh.normals_split_custom_set_from_vertices(normals)
    obj = None
    if collection is not None:
        obj = bpy.data.objects.new(builder.name, mesh)
        collection.objects.link(obj)
    return (obj if obj is not None else mesh), len(used)


def add_foliage(collection, materials):
    """Linked instances of the flora library, parented to one empty so glTF writes EXT_mesh_gpu_instancing."""
    protos = flora.prototypes()
    meshes = {name: make_object(builder, None, materials)[0] for name, builder in protos.items()}
    root = bpy.data.objects.new('09_foliage_instances', None)
    collection.objects.link(root)
    placements = flora.scatter() + flora.bloom_spots(random.Random(5))
    counts = {}
    # Shuffled names, so the exported instance order is spatially random and the viewer's density slider can draw
    # any prefix evenly.
    order = list(range(len(placements)))
    random.Random(1).shuffle(order)
    for i, (proto, x, y, z, yaw, scale) in enumerate(placements):
        obj = bpy.data.objects.new(f'{proto}.{order[i]:05d}', meshes[proto])
        obj.location = (x, y, z)
        obj.rotation_euler = (0.0, 0.0, math.radians(yaw))
        obj.scale = (scale, scale, scale)
        obj.parent = root
        collection.objects.link(obj)
        counts[proto] = counts.get(proto, 0) + 1
    tris = {name: sum(len(f) - 2 for f in b.faces) for name, b in protos.items()}
    stats = dict(prototypes=len(protos), instances=len(placements), unique_triangles=sum(tris.values()),
                 instanced_triangles=sum(tris[k] * n for k, n in counts.items()))
    return root, stats


def build_modules(only=()):
    SCENE_OUT.mkdir(parents=True, exist_ok=True)
    MODEL_OUT.mkdir(parents=True, exist_ok=True)
    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'METERS'
    materials = {name: make_material(name, color) for name, color in L.COLORS.items()}
    objects = {}
    report = {}
    for name, fn in modules.MODULES.items():
        if only and not name.startswith(only):
            continue
        started = time.time()
        builder = fn()
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)
        obj, mat_count = make_object(builder, collection, materials)
        obj['brinecove_module'] = name
        objects[name] = [obj]
        report[name] = dict(vertices=len(builder.verts), triangles=sum(len(f) - 2 for f in builder.faces),
                            materials=mat_count, seconds=round(time.time() - started, 2))
        if name == '09_vegetation':
            root, stats = add_foliage(collection, materials)
            objects[name] += [root] + list(root.children)
            report[name]['triangles'] += stats['instanced_triangles']
            report[name]['foliage'] = stats
            report[name]['seconds'] = round(time.time() - started, 2)
        print(f'built {name}: {report[name]}', flush=True)
    hero_collection = bpy.data.collections.new('10_hero_assets')
    scene.collection.children.link(hero_collection)
    hero = None if only else hero_assets.add_hero_assets(hero_collection)
    if hero is not None:
        objects['10_hero_assets'] = [hero]
        report['10_hero_assets'] = dict(vertices=len(hero.data.vertices),
                                        triangles=sum(len(p.vertices) - 2 for p in hero.data.polygons),
                                        materials=len(hero.data.materials), seconds=0.0)
        print(f'built 10_hero_assets: {report["10_hero_assets"]}', flush=True)
    # Full scene and per-module GLBs. Foliage carries its crown normals; every other module is flat-shaded, so
    # its normals are left for the viewer to derive.
    def select(names):
        for group in objects.values():
            for obj in group:
                obj.select_set(False)
        for name in names:
            for obj in objects[name]:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[names[0]][0]

    def export(path, foliage):
        bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB',
                                  use_selection=True, export_apply=True, export_yup=True,
                                  export_animations=False, export_skins=False, export_cameras=False,
                                  export_lights=False, export_extras=True, export_gpu_instances=True,
                                  export_image_format='JPEG', export_image_quality=86, export_normals=foliage)

    select(list(objects))
    if only:
        # A sketch: a partial scene for quick renders, never the published scene or models.
        bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_OUT / 'sketch.blend'))
        return
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_OUT / 'brinecove.blend'))
    export(SCENE_OUT / 'brinecove.glb', False)
    for name in objects:
        select([name])
        export(MODEL_OUT / f'{name}.glb', name == '09_vegetation')
    for group in objects.values():
        for obj in group:
            obj.select_set(False)
    report['_totals'] = dict(vertices=sum(v['vertices'] for k, v in report.items() if not k.startswith('_')),
                             triangles=sum(v['triangles'] for k, v in report.items() if not k.startswith('_')))
    report['_area'] = L.area()
    (OUT / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print('BRINECOVE BUILD COMPLETE', flush=True)
    return objects, report


def sea_plane():
    bpy.ops.mesh.primitive_plane_add(size=5000, location=(0, 0, -0.35))
    obj = bpy.context.object
    obj.name = 'REVIEW_Sea'
    mat = make_material('sea_review', L.COLORS['water'])
    tex = bpy.data.images.load(str(TEXTURE_DIR / 'water.jpg'), check_existing=True)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.32
    for key in ('Specular IOR Level', 'Specular'):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.1  # the pale horizon sky washed the sea out
            break
    image = nodes.new('ShaderNodeTexImage')
    image.image = tex
    # The painted turquoise reads as shallow water. Out at sea, away from the cove and the headland toes,
    # tint it towards the paintings' deep cobalt.
    geo = nodes.new('ShaderNodeNewGeometry')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(geo.outputs['Position'], sep.inputs['Vector'])
    near = nodes.new('ShaderNodeMapRange')
    near.inputs['From Min'].default_value = -620.0
    near.inputs['From Max'].default_value = -180.0
    links.new(sep.outputs['Y'], near.inputs['Value'])
    tint = nodes.new('ShaderNodeMixRGB')
    tint.inputs['Color1'].default_value = (0.20, 0.42, 1.0, 1.0)
    tint.inputs['Color2'].default_value = (0.62, 0.88, 1.0, 1.0)
    links.new(near.outputs['Result'], tint.inputs['Fac'])
    mul = nodes.new('ShaderNodeMixRGB')
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Fac'].default_value = 1.0
    links.new(image.outputs['Color'], mul.inputs['Color1'])
    links.new(tint.outputs['Color'], mul.inputs['Color2'])
    links.new(mul.outputs['Color'], bsdf.inputs['Base Color'])
    obj.data.materials.append(mat)
    uv_layer = obj.data.uv_layers.active
    if uv_layer:
        for datum in uv_layer.data:
            datum.uv = (datum.uv[0] * 190.0, datum.uv[1] * 190.0)
    return obj


def add_render_objects():
    scene = bpy.context.scene
    sea_plane()
    world = bpy.data.worlds.new('Brinecove review sky')
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    bg = nodes['Background']
    bg.inputs['Strength'].default_value = 1.0
    coord = nodes.new('ShaderNodeTexCoord')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.56, 0.72, 0.90, 1.0)
    ramp.color_ramp.elements[1].position = 0.42
    ramp.color_ramp.elements[1].color = (0.08, 0.30, 0.74, 1.0)
    links.new(coord.outputs['Generated'], sep.inputs['Vector'])
    links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 3.6
    noise.inputs['Detail'].default_value = 7.0
    noise.inputs['Roughness'].default_value = 0.62
    links.new(coord.outputs['Generated'], noise.inputs['Vector'])
    cloud_ramp = nodes.new('ShaderNodeValToRGB')
    cloud_ramp.color_ramp.elements[0].position = 0.47
    cloud_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 0.0)
    cloud_ramp.color_ramp.elements[1].position = 0.60
    cloud_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    links.new(noise.outputs['Fac'], cloud_ramp.inputs['Fac'])
    cloud = nodes.new('ShaderNodeMixRGB')
    cloud.blend_type = 'MIX'
    cloud.inputs['Color2'].default_value = (0.93, 0.91, 0.85, 1.0)
    links.new(ramp.outputs['Color'], cloud.inputs['Color1'])
    links.new(cloud_ramp.outputs['Alpha'], cloud.inputs['Fac'])
    links.new(cloud.outputs['Color'], bg.inputs['Color'])
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 6.2
    sun_data.angle = math.radians(4)
    sun_data.color = (1.0, 0.81, 0.56)
    sun = bpy.data.objects.new('Sun', sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(57), math.radians(8), math.radians(-38))
    fill_data = bpy.data.lights.new('Sky fill', 'AREA')
    fill_data.energy = 320
    fill_data.size = 700
    fill_data.color = (0.62, 0.78, 1.0)
    fill = bpy.data.objects.new('Sky fill', fill_data)
    scene.collection.objects.link(fill)
    fill.location = (-250, -350, 240)
    fill.rotation_euler = (math.radians(28), 0, math.radians(-35))
    cam_data = bpy.data.cameras.new('Review camera')
    cam = bpy.data.objects.new('Review camera', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.clip_end = 6000.0
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        # Blender 5.2 dropped the _NEXT suffix from the Eevee engine id.
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'):
        scene.eevee.taa_render_samples = 32
    if hasattr(scene, 'eevee'):
        for attr, value in (('use_gtao', True), ('gtao_distance', 3.5), ('gtao_factor', 1.2),
                            ('use_raytracing', True), ('use_shadows', True)):
            if hasattr(scene.eevee, attr):
                try:
                    setattr(scene.eevee, attr, value)
                except Exception:
                    pass
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    scene.view_settings.exposure = 0.1
    return cam, sun, fill, bg, ramp, cloud


def look_at(cam, location, target, lens=42):
    cam.location = Vector(location)
    direction = Vector(target) - Vector(location)
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens


VIEWS = {
    '01-aerial-hero': ((-300, -380, 220), (0, 120, 30), 38, 'day'),
    '02-harbor-approach': ((-90, -360, 32), (0, 80, 18), 48, 'day'),
    '03-market-square': ((-58, 102, 6.8), (54, 210, 9.0), 35, 'day'),
    '04-upper-terrace': ((20, 330, 54), (-20, 30, 2), 30, 'day'),
    '05-lighthouse-headland': ((-480, -300, 108), (-618, -38, 70), 50, 'day'),
    '06-shipyard': ((290, -200, 24), (380, 105, 14), 50, 'day'),
    '07-waterfall-bridge': ((360, -70, 24), (466, 34, 26), 36, 'day'),
    '08-night-harbor': ((-90, -360, 32), (0, 80, 18), 48, 'night'),
    '09-rum-row': ((-296, 94, 7), (-250, 130, 10), 38, 'day'),
    '10-topdown': ((0, -40, 1580), (0, -20, 0), 52, 'day'),
    '11-cliff-shacks': ((-430, -170, 32), (-512, 10, 34), 48, 'day'),
    '12-forest-canopy': ((470, 140, 86), (660, 330, 52), 40, 'day'),
    '13-cliff-face': ((-380, -150, 12), (-505, -50, 30), 42, 'day'),
}


def render_views(only=(), preview=False, sketch=False):
    RENDER_OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SCENE_OUT / ('sketch.blend' if sketch else 'brinecove.blend')))
    cam, sun, fill, bg, sky_ramp, cloud_mix = add_render_objects()
    scene = bpy.context.scene
    if preview:
        scene.render.resolution_x = 960
        scene.render.resolution_y = 540
        if hasattr(scene, 'eevee'):
            if hasattr(scene.eevee, 'taa_render_samples'):
                scene.eevee.taa_render_samples = 12
            if hasattr(scene.eevee, 'use_raytracing'):
                scene.eevee.use_raytracing = False
    files = []
    views = {k: v for k, v in VIEWS.items() if not only or k in only}
    for name, (loc, target, lens, mood) in views.items():
        if mood == 'night':
            sky_ramp.color_ramp.elements[0].color = (0.08, 0.15, 0.23, 1.0)
            sky_ramp.color_ramp.elements[1].color = (0.01, 0.04, 0.10, 1.0)
            bg.inputs['Strength'].default_value = 0.8
            sun.data.energy = 0.55
            sun.data.color = (0.45, 0.62, 1.0)
            fill.data.energy = 700
            fill.data.color = (0.22, 0.35, 0.65)
            scene.view_settings.exposure = 0.5
            cloud_mix.inputs['Color2'].default_value = (0.10, 0.15, 0.24, 1.0)
            add_night_lights(scene)
        else:
            sky_ramp.color_ramp.elements[0].color = (0.56, 0.72, 0.90, 1.0)
            sky_ramp.color_ramp.elements[1].color = (0.08, 0.30, 0.74, 1.0)
            bg.inputs['Strength'].default_value = 1.0
            sun.data.energy = 6.2
            sun.data.color = (1.0, 0.81, 0.56)
            fill.data.energy = 320
            fill.data.color = (0.62, 0.78, 1.0)
            scene.view_settings.exposure = 0.1
            cloud_mix.inputs['Color2'].default_value = (0.93, 0.91, 0.85, 1.0)
        look_at(cam, loc, target, lens)
        scene.render.filepath = str(RENDER_OUT / (f'sketch-{name}.png' if sketch else f'{name}.png'))
        print('rendering', name, flush=True)
        bpy.ops.render.render(write_still=True)
        files.append(name)
    if not sketch:
        (OUT / 'renders.json').write_text(json.dumps(files, indent=2) + '\n')
    print('BRINECOVE RENDER COMPLETE', flush=True)


def add_night_lights(scene):
    # A few warm pools stand in for the lantern strings. The emissive material carries the close-up detail.
    points = [(-320, 88, 7), (-190, 88, 7), (-60, 88, 7), (70, 88, 7), (200, 88, 7), (330, 88, 7),
              (-200, 155, 8), (0, 160, 9), (200, 155, 8), (-120, 338, 26), (110, 338, 26),
              (-618, -40, 86), (355, 92, 15)]
    for i, (x, y, z) in enumerate(points):
        data = bpy.data.lights.new(f'Lantern {i}', 'POINT')
        data.energy = 900 if i < 8 else 1400
        data.color = (1.0, 0.62, 0.28)
        data.shadow_soft_size = 4.0
        obj = bpy.data.objects.new(f'Lantern {i}', data)
        scene.collection.objects.link(obj)
        obj.location = (x, y, z)


def sync_viewer():
    VIEWER_OUT.mkdir(parents=True, exist_ok=True)
    for src in (REGION / 'viewer').iterdir():
        if src.is_file():
            shutil.copy2(src, VIEWER_OUT / src.name)
    vendor_src = REPO / 'games/yorimichi/tools/character_review_web/vendor'
    vendor_dst = VIEWER_OUT / 'vendor'
    if vendor_dst.exists():
        shutil.rmtree(vendor_dst)
    shutil.copytree(vendor_src, vendor_dst)
    refs_src = OUT / 'references'
    refs_dst = VIEWER_OUT / 'refs'
    if refs_dst.exists():
        shutil.rmtree(refs_dst)
    refs_dst.mkdir()
    for src in sorted(refs_src.glob('*.png')):
        shutil.copy2(src, refs_dst / src.name)
    props_src = REFERENCES / 'props'
    props_dst = VIEWER_OUT / 'refs' / 'props'
    if props_dst.exists():
        shutil.rmtree(props_dst)
    if props_src.exists():
        shutil.copytree(props_src, props_dst)
    bridge_src = OUT / 'references-bridge'
    bridge_dst = refs_dst / 'bridge'
    if bridge_src.exists():
        bridge_dst.mkdir()
        for src in sorted(bridge_src.glob('*.png')):
            shutil.copy2(src, bridge_dst / src.name)
    review_sheet = OUT / 'asset-reviews' / 'contact-sheet.jpg'
    if review_sheet.exists():
        shutil.copy2(review_sheet, VIEWER_OUT / 'refs' / 'trellis-processed.jpg')
    for pattern in ('*.png', '*.jpg'):
        for src in (OUT / 'renders').glob(pattern):
            shutil.copy2(src, VIEWER_OUT / src.name)
    tex_src = TEXTURES
    tex_dst = VIEWER_OUT / 'textures'
    if tex_dst.exists():
        shutil.rmtree(tex_dst)
    shutil.copytree(tex_src, tex_dst)
    sheet = OUT / 'textures' / 'contact-sheet.jpg'
    if sheet.exists():
        shutil.copy2(sheet, VIEWER_OUT / 'textures' / 'contact-sheet.jpg')
    models_dst = VIEWER_OUT / 'models'
    if models_dst.exists():
        shutil.rmtree(models_dst)
    shutil.copytree(MODEL_OUT, models_dst)
    shutil.make_archive(str(VIEWER_OUT / 'brinecove-models'), 'zip', MODEL_OUT)
    scene_dst = VIEWER_OUT / 'scene'
    if scene_dst.exists():
        shutil.rmtree(scene_dst)
    scene_dst.mkdir()
    for name in ('brinecove.blend', 'brinecove.glb'):
        src = SCENE_OUT / name
        if src.exists():
            shutil.copy2(src, scene_dst / name)
    for src in (OUT / 'references').glob('contact-sheet.jpg'):
        shutil.copy2(src, VIEWER_OUT / src.name)
    (VIEWER_OUT / 'build.json').write_text((OUT / 'build.json').read_text())
    print('viewer payload:', VIEWER_OUT, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=('all', 'build', 'render', 'sync'), default='all')
    ap.add_argument('--view', default='', help='comma-separated render view names')
    ap.add_argument('--preview', action='store_true', help='low-resolution review render')
    ap.add_argument('--sketch', default='', help='comma-separated module prefixes (e.g. 01,09): a partial scene '
                    'rendered to renders/sketch-*.png, leaving the published scene alone')
    args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    OUT.mkdir(parents=True, exist_ok=True)
    sketch = tuple(m for m in args.sketch.split(',') if m)
    if args.stage in ('all', 'build'):
        build_modules(sketch)
    if args.stage in ('all', 'render'):
        render_views(tuple(v for v in args.view.split(',') if v), args.preview, bool(sketch))
    if args.stage in ('all', 'sync') and not sketch:
        sync_viewer()


if __name__ == '__main__':
    main()
