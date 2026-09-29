"""Import a downloaded Tripo model into a separate Blender review scene.

blender -b --python games/yorimichi/assets/characters/tools/review_tripo_model.py -- --input model.glb --output review
No cleanup, remeshing or rigging is performed. The imported materials and mesh
are packed into a review .blend; cameras use the provider's default +X front.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
import bmesh


def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def material(name, color):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = .75
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--turntable-frames', type=int, default=96)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = args.input.resolve()
    if source.suffix.lower() in {'.glb', '.gltf'}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif source.suffix.lower() == '.fbx':
        bpy.ops.import_scene.fbx(filepath=str(source))
    else:
        raise RuntimeError('Expected a GLB, GLTF or FBX source')
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not meshes:
        raise RuntimeError('Import produced no mesh objects')
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector([min(point[i] for point in corners) for i in range(3)])
    high = Vector([max(point[i] for point in corners) for i in range(3)])
    center = (low+high)/2
    extent = high-low
    scale = max(extent)
    if scale <= 0:
        raise RuntimeError('Model bounds have no extent')
    mesh_report = []
    for obj in meshes:
        polygons = Counter(len(face.vertices) for face in obj.data.polygons)
        topology = bmesh.new()
        topology.from_mesh(obj.data)
        mesh_report.append({'object':obj.name, 'vertices':len(obj.data.vertices),
                            'polygons':len(obj.data.polygons), 'polygon_sizes':dict(polygons),
                            'triangles_after_triangulation':sum(max(0, len(p.vertices)-2) for p in obj.data.polygons),
                            'uv_layers':[layer.name for layer in obj.data.uv_layers],
                            'materials':[slot.material.name if slot.material else None for slot in obj.material_slots],
                            'boundary_edges':sum(edge.is_boundary for edge in topology.edges),
                            'non_manifold_edges':sum(not edge.is_manifold for edge in topology.edges)})
        topology.free()
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.render.fps = 24
    world = bpy.data.worlds.new('Neutral review world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.64,.66,.69,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .35
    scene.world = world
    for name, position, energy, size in [
        ('Key', (2,-2,3), 85, 3), ('Fill', (1,2,1), 45, 3), ('Rear fill', (-2,1,2), 60, 2)]:
        light = bpy.data.lights.new(name, 'AREA')
        light.energy = energy*scale*scale
        light.shape = 'DISK'
        light.size = size*scale
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = center+Vector(position)*scale
        aim(obj, center)
    camera_data = bpy.data.cameras.new('Review camera')
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = scale*1.15
    camera_data.clip_start = scale*.001
    camera_data.clip_end = scale*100
    camera = bpy.data.objects.new('Review camera', camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    clay = material('Review clay override', (.57,.61,.65))
    wire = material('Review wireframe override', (.72,.75,.78))
    nodes = wire.node_tree.nodes
    frame = nodes.new('ShaderNodeWireframe')
    frame.use_pixel_size = True
    frame.inputs['Size'].default_value = 1
    mix = nodes.new('ShaderNodeMixRGB')
    mix.inputs[1].default_value = (.68,.71,.74,1)
    mix.inputs[2].default_value = (.035,.045,.055,1)
    wire.node_tree.links.new(frame.outputs['Fac'], mix.inputs[0])
    wire.node_tree.links.new(mix.outputs[0], nodes['Principled BSDF'].inputs['Base Color'])
    views = {'front':(1,0,0), 'left':(0,1,0), 'back':(-1,0,0),
             'right':(0,-1,0), 'three-quarter':(1, .65, .12)}
    renders = output/'renders'
    renders.mkdir(exist_ok=True)
    for mode, override in [('textured',None), ('clay',clay)]:
        bpy.context.view_layer.material_override = override
        for name, direction in views.items():
            camera.location = center+Vector(direction).normalized()*scale*4
            aim(camera, center)
            scene.render.filepath = str(renders/(mode+'-'+name+'.png'))
            bpy.ops.render.render(write_still=True)
    bpy.context.view_layer.material_override = wire
    camera.location = center+Vector(views['three-quarter']).normalized()*scale*4
    aim(camera, center)
    scene.render.filepath = str(renders/'wireframe-three-quarter.png')
    bpy.ops.render.render(write_still=True)
    bpy.context.view_layer.material_override = None
    if args.turntable_frames:
        turntable = output/'turntable-frames'
        turntable.mkdir(exist_ok=True)
        scene.render.resolution_x = scene.render.resolution_y = 600
        for index in range(args.turntable_frames):
            angle = 2*math.pi*index/args.turntable_frames
            camera.location = center+Vector((math.cos(angle),math.sin(angle),.06))*scale*4
            aim(camera, center)
            scene.render.filepath = str(turntable/f'{index:04d}.png')
            bpy.ops.render.render(write_still=True)
    scene.render.resolution_x = scene.render.resolution_y = 900
    camera.location = center+Vector(views['three-quarter']).normalized()*scale*4
    aim(camera, center)
    # Leave an uncluttered material-preview viewport focused on the imported asset.
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.shading.type = 'MATERIAL'
                space.overlay.show_extras = False
                space.overlay.show_floor = False
                space.overlay.show_axis_x = space.overlay.show_axis_y = False
                space.region_3d.view_location = center
                space.region_3d.view_distance = scale*1.8
                space.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
                space.region_3d.view_perspective = 'ORTHO'
                space.clip_start, space.clip_end = scale*.001, scale*100
    bpy.ops.file.pack_all()
    # GLB is a derived browser preview. Keep native FBX/Blender polygon topology.
    preview = output/'WarmOriginal-Tripo-r01.glb'
    bpy.ops.export_scene.gltf(filepath=str(preview), export_format='GLB',
                              use_selection=True, export_animations=False)
    blend = output/'WarmOriginal-Tripo-r01.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    report = {'source':str(source), 'blender_version':bpy.app.version_string,
              'bounds_min':list(low), 'bounds_max':list(high), 'dimensions':list(extent),
              'front_axis_assumption':'+X, provider default; verify against renders',
              'mesh_objects':mesh_report,
              'textures':[{'name':img.name,'size':list(img.size)} for img in bpy.data.images if img.type=='IMAGE'],
              'material_connections':{mat.name:[{'from_node':link.from_node.name,
                  'from_socket':link.from_socket.name, 'to_node':link.to_node.name,
                  'to_socket':link.to_socket.name} for link in mat.node_tree.links]
                  for mat in bpy.data.materials if mat.use_nodes and mat.name.startswith('tripo')},
              'armature_count':sum(o.type=='ARMATURE' for o in scene.objects),
              'geometry_modified':False, 'materials_modified':False,
              'blend_file':blend.name, 'browser_preview':preview.name, 'render_directory':'renders',
              'turntable_frames':args.turntable_frames,
              'note':('Native FBX polygon counts are preserved in Blender. The derived GLB and wireframe shader show triangulation.'
                      if source.suffix.lower()=='.fbx' else 'GLTF import is triangulated; native quad topology cannot be inferred.')}
    (output/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Review saved: '+str(blend), flush=True)


if __name__ == '__main__':
    main()
