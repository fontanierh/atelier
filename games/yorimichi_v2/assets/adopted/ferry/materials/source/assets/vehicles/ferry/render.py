"""Review renders of the ferry: the concept C camera, a side elevation and a top view.

blender --background --factory-startup --threads 3 -P games/yorimichi/assets/vehicles/ferry/render.py
Opens build/yorimichi/ferry/ferry.blend (from build.py) and writes RGBA PNGs to build/yorimichi/ferry/review/.
compare.py then puts each next to the concept. Flat warm sun and sky-blue fill over still water at the waterline,
against a sky gradient backdrop.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
import math

import bpy
from mathutils import Matrix, Vector

OUT = yori.OUT / 'ferry'
REVIEW = OUT / 'review'

# Pinhole camera fitted to the hull lines of ferry_oldschool_c.jpg (1536 x 1024): position, heading of the view
# direction, downward pitch, roll and focal length in pixels.
CONCEPT_CAMERA = dict(pos=(75.988, -68.616, 21.473), yaw=2.33742, pitch=0.16086, roll=0.02183, focal_px=2494.75, size=(1536, 1024))


def srgb(c):
    return tuple(((v / 255) / 12.92) if v / 255 <= 0.04045 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in c)


def setup(scene):
    for engine in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.view_transform = 'Standard'
    try:
        scene.eevee.taa_render_samples = 48
    except AttributeError:
        pass
    world = bpy.data.worlds.new('FerryDaylight'); scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    # Flat sky-blue fill light; camera rays see a painted-sky gradient (deep blue overhead, pale at the horizon).
    nodes, links = world.node_tree.nodes, world.node_tree.links
    bg = nodes.get('Background')
    bg.inputs['Color'].default_value = (*srgb((178, 204, 236)), 1); bg.inputs['Strength'].default_value = 0.62
    sky = nodes.new('ShaderNodeBackground'); sky.inputs['Strength'].default_value = 1.0
    coord = nodes.new('ShaderNodeTexCoord'); sep = nodes.new('ShaderNodeSeparateXYZ'); ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.45; ramp.color_ramp.elements[0].color = (*srgb((176, 206, 238)), 1)
    ramp.color_ramp.elements[1].position = 1.0; ramp.color_ramp.elements[1].color = (*srgb((62, 128, 226)), 1)
    links.new(coord.outputs['Window'], sep.inputs[0]); links.new(sep.outputs['Y'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], sky.inputs['Color'])
    path = nodes.new('ShaderNodeLightPath'); mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(bg.outputs['Background'], mix.inputs[1]); links.new(sky.outputs['Background'], mix.inputs[2])
    out = nodes.get('World Output'); links.new(mix.outputs['Shader'], out.inputs['Surface'])
    # Warm late-morning sun, as painted.
    sun = bpy.data.lights.new('Sun', 'SUN'); sun.energy = 4.4; sun.color = srgb((255, 226, 186)); sun.angle = math.radians(6)
    ob = bpy.data.objects.new('Sun', sun); scene.collection.objects.link(ob)
    # Warm sun from high over the starboard quarter, behind the funnel, as in the concept.
    ob.rotation_euler = (math.radians(44), 0, math.radians(-66))
    water = bpy.data.materials.new('Water')
    try:
        water.use_nodes = True
    except Exception:
        pass
    bsdf = water.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*srgb((44, 110, 164)), 1); bsdf.inputs['Roughness'].default_value = 0.9
    # A water block, not a sheet, so the side elevation also cuts the hull at the waterline.
    mesh = bpy.data.meshes.new('Water'); s = 3000; d = 30
    v = [(-s, -s, -d), (s, -s, -d), (s, s, -d), (-s, s, -d), (-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)]
    mesh.from_pydata(v, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]); mesh.materials.append(water)
    plane = bpy.data.objects.new('Water', mesh); scene.collection.objects.link(plane)
    return plane


def camera(scene, name, ortho=None, size=(1600, 900)):
    data = bpy.data.cameras.new(name); ob = bpy.data.objects.new(name, data); scene.collection.objects.link(ob)
    scene.render.resolution_x, scene.render.resolution_y = size; scene.render.resolution_percentage = 100
    data.sensor_fit = 'HORIZONTAL'; data.sensor_width = 36.0; data.clip_end = 2000
    if ortho:
        data.type = 'ORTHO'; data.ortho_scale = ortho
    return ob


def concept_camera(scene):
    c = CONCEPT_CAMERA; w, h = c['size']
    ob = camera(scene, 'ConceptCam', size=(w, h))
    yaw, pitch, roll = c['yaw'], c['pitch'], c['roll']
    d = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), -math.sin(pitch)))
    right = d.cross(Vector((0, 0, 1))).normalized(); up = right.cross(d)
    r2 = math.cos(roll) * right + math.sin(roll) * up; u2 = -math.sin(roll) * right + math.cos(roll) * up
    ob.matrix_world = Matrix.Translation(c['pos']) @ Matrix((r2, u2, -d)).transposed().to_4x4()
    ob.data.lens = c['focal_px'] * 36.0 / w
    return ob


def render(scene, cam, name):
    scene.camera = cam
    scene.render.filepath = str(REVIEW / f'ferry_{name}.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', scene.render.filepath)


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(OUT / 'ferry.blend'))
    scene = bpy.context.scene
    water = setup(scene)
    render(scene, concept_camera(scene), 'three_quarter')
    side = camera(scene, 'SideCam', ortho=88, size=(1760, 640))
    side.location = (0, -200, 10.0); side.rotation_euler = (math.radians(90), 0, 0)
    water.location.y = 3000 - 40  # the block's near face stands between the camera and the hull
    render(scene, side, 'side')
    water.hide_render = True
    top = camera(scene, 'TopCam', ortho=88, size=(1760, 400))
    top.location = (0, 0, 200); top.rotation_euler = (0, 0, 0)
    render(scene, top, 'top')


if __name__ == '__main__':
    main()
