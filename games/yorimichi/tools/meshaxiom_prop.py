"""Blender authoring: scale a generated bin to metres, assign game materials and render evidence.

Run after mesh generation, through the Atelier guard. Geometry comes entirely from mesh.json;
this script changes scale, origin, face materials and export format, not vertices or connectivity.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--previews',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True,exist_ok=True);args.previews.mkdir(parents=True,exist_ok=True)
    data=json.loads(args.mesh.read_text())
    verts=data['vertices'];faces=data['faces']
    lo=[min(p[i] for p in verts) for i in range(3)];hi=[max(p[i] for p in verts) for i in range(3)]
    scale=1./(hi[2]-lo[2])
    verts=[((p[0]-(lo[0]+hi[0])/2)*scale,(p[1]-(lo[1]+hi[1])/2)*scale,(p[2]-lo[2])*scale) for p in verts]
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    mesh=bpy.data.meshes.new('MeshAxiom_RecyclingBin');mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new('RecyclingBin_MeshAxiom',mesh);bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    palette=[('Indigo',(.055,.10,.18,1)),('Ochre',(.65,.38,.075,1)),('Rust',(.20,.08,.035,1))]
    for name,color in palette:
        material=bpy.data.materials.new(name);material.diffuse_color=color;material.use_nodes=True
        bsdf=material.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=color
        bsdf.inputs['Roughness'].default_value=.85
        obj.data.materials.append(material)
    for face in mesh.polygons:
        z=sum(mesh.vertices[i].co.z for i in face.vertices)/len(face.vertices)
        face.material_index=1 if z>.78 else 0
        face.use_smooth=False
    bpy.ops.export_scene.gltf(filepath=str(args.output/'recycling_bin.glb'),export_format='GLB',use_selection=True,export_yup=True)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.002));ground=bpy.context.object
    material=bpy.data.materials.new('PreviewGround');material.diffuse_color=(.12,.14,.16,1);ground.data.materials.append(material)
    world=bpy.data.worlds.new('Studio');bpy.context.scene.world=world;world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.18,.21,.26,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.7
    for name,position,power,size in [('Key',(3,-4,5),500,4),('Fill',(-3,-1,2.5),300,3),('Rim',(0,4,4),550,3)]:
        lamp=bpy.data.lights.new(name,'AREA');lamp.energy=power;lamp.shape='DISK';lamp.size=size
        light=bpy.data.objects.new(name,lamp);bpy.context.collection.objects.link(light);light.location=position
        light.rotation_euler=(Vector((0,0,.5))-light.location).to_track_quat('-Z','Y').to_euler()
    camera_data=bpy.data.cameras.new('Preview');camera=bpy.data.objects.new('Preview',camera_data);bpy.context.collection.objects.link(camera)
    scene=bpy.context.scene;scene.camera=camera;camera_data.type='ORTHO';camera_data.ortho_scale=1.6
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24
    scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    for i,position in enumerate([(2,-3,1.8),(-2,3,1.8),(3,2,1.8),(-3,-2,1.8)]):
        camera.location=position;camera.rotation_euler=(Vector((0,0,.50))-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(args.previews/f'view-{i+1}.png')
        print(f'Rendering MeshAxiom prop view {i+1}/4',flush=True);bpy.ops.render.render(write_still=True)
    print(json.dumps({'vertices':len(verts),'faces':len(faces),'height_metres':1.,'scale':scale,'geometry_changes':'uniform scale and origin only','material_rule':'ochre above 0.78m; indigo below'}),flush=True)

if __name__=='__main__':main()
