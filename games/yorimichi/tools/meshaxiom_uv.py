"""Blender: add UVs and a neutral atlas without remeshing MeshAxiom geometry.

Run with Blender --background --threads 3 --python SCRIPT -- ARGS under Atelier's guard.
"""
import argparse
from array import array
import json
import math
from pathlib import Path
import sys
import time


def main():
    """@cc [owner:fontanierh,label:correctness] meshaxiom-uv-keeps-native-connectivity
    UV preparation MUST retain the input triangle connectivity without remeshing or
    subdivision. Only uniform scale, origin, UVs, shading and a neutral material MAY change.
    """
    import bpy
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--height', type=float, default=.35)
    parser.add_argument('--atlas-size', type=int, choices=[1024, 2048], default=2048)
    parser.add_argument('--angle', type=float, default=66)
    parser.add_argument('--margin', type=float, default=.008)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not (1 <= args.angle <= 89 and 0 <= args.margin <= .05):
        parser.error('UV angle must be 1–89 degrees and margin 0–0.05')
    start = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.mesh.read_text())
    lo = [min(v[i] for v in data['vertices']) for i in range(3)]
    hi = [max(v[i] for v in data['vertices']) for i in range(3)]
    scale = args.height/(hi[2]-lo[2])
    positions = [((v[0]-(lo[0]+hi[0])/2)*scale,
                  (v[1]-(lo[1]+hi[1])/2)*scale, (v[2]-lo[2])*scale) for v in data['vertices']]
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    mesh = bpy.data.meshes.new('MeshAxiomNativeConnectivity')
    mesh.from_pydata(positions, [], data['faces'])
    mesh.update()
    obj = bpy.data.objects.new('MeshAxiom', mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for face in mesh.polygons:
        face.use_smooth = True
    print(f'Adding UVs to {len(mesh.polygons)} native triangles, no remeshing or subdivision', flush=True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(args.angle), island_margin=args.margin)
    bpy.ops.object.mode_set(mode='OBJECT')
    if len(mesh.polygons) != len(data['faces']) or len(mesh.vertices) != len(positions):
        raise RuntimeError('UV preparation changed the native geometry counts')
    texture = bpy.data.images.new('NeutralAtlas', width=args.atlas_size, height=args.atlas_size, alpha=True)
    texture.pixels.foreach_set(array('f', [.58, .56, .53, 1.])*(args.atlas_size**2))
    texture.pack()
    material = bpy.data.materials.new('NeutralSurface')
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = .85
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = texture
    material.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    obj.data.materials.append(material)
    print('Exporting UV clay GLB with embedded neutral atlas', flush=True)
    bpy.ops.export_scene.gltf(filepath=str(args.output/'clay-uv.glb'), export_format='GLB',
                              use_selection=True, export_yup=True, export_apply=False)
    record = dict(source_vertices=len(positions), source_triangles=len(data['faces']),
                  authoring_vertices=len(mesh.vertices), authoring_triangles=len(mesh.polygons),
                  height_metres=args.height, uniform_scale=scale, shading='smooth',
                  geometry_changes='Uniform scale and origin only; original connectivity',
                  uv_method='Blender Smart UV Project', angle_degrees=args.angle,
                  island_margin=args.margin,
                  atlas_size=args.atlas_size, seconds=time.monotonic()-start)
    (args.output/'uv-export.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
