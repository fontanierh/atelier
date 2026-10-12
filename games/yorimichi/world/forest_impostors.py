"""Bake each full tree's albedo and camera-space normals for the distant HISM level."""
import math

import bpy
import numpy as np
from mathutils import Vector


def bake(obj, output, size=256):
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=size;scene.render.resolution_y=size
    scene.render.resolution_percentage=100;scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.view_settings.view_transform='Raw';scene.view_settings.exposure=0;scene.view_settings.gamma=1
    minimum=Vector(tuple(min(v.co[i] for v in obj.data.vertices) for i in range(3)))
    maximum=Vector(tuple(max(v.co[i] for v in obj.data.vertices) for i in range(3)))
    centre=(minimum+maximum)*.5;scale=max(maximum-minimum)*1.08
    data=bpy.data.cameras.new('ForestBake');camera=bpy.data.objects.new('ForestBake',data)
    scene.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO';data.ortho_scale=scale
    for other in scene.objects:other.hide_render=other not in (obj,camera)
    originals=list(obj.data.materials)
    atlases={}
    for mode in ('colour','normal'):
        scene.view_settings.view_transform='Standard' if mode=='colour' else 'Raw'
        replacements=[]
        for original in originals:
            material=bpy.data.materials.new(original.name+'_Bake_'+mode);material.use_nodes=True
            nodes=material.node_tree.nodes;links=material.node_tree.links;nodes.clear()
            out=nodes.new('ShaderNodeOutputMaterial');emit=nodes.new('ShaderNodeEmission')
            transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader')
            texture=next((n for n in original.node_tree.nodes if n.type=='TEX_IMAGE'),None)
            if texture:
                tex=nodes.new('ShaderNodeTexImage');tex.image=texture.image
                links.new(tex.outputs['Alpha'],mix.inputs[0])
            else:mix.inputs[0].default_value=1
            if mode=='normal':
                geometry=nodes.new('ShaderNodeNewGeometry');transform=nodes.new('ShaderNodeVectorTransform')
                transform.vector_type='NORMAL';transform.convert_from='WORLD';transform.convert_to='CAMERA'
                multiply=nodes.new('ShaderNodeVectorMath');multiply.operation='SCALE';multiply.inputs[3].default_value=.5
                add=nodes.new('ShaderNodeVectorMath');add.operation='ADD';add.inputs[1].default_value=(.5,.5,.5)
                links.new(geometry.outputs['Normal'],transform.inputs[0]);links.new(transform.outputs[0],multiply.inputs[0])
                links.new(multiply.outputs[0],add.inputs[0]);links.new(add.outputs[0],emit.inputs['Color'])
            elif texture:links.new(tex.outputs['Color'],emit.inputs['Color'])
            else:
                principled=next(n for n in original.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
                emit.inputs['Color'].default_value=principled.inputs['Base Color'].default_value
            links.new(transparent.outputs[0],mix.inputs[1]);links.new(emit.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],out.inputs['Surface'])
            material.surface_render_method='DITHERED';replacements.append(material)
        obj.data.materials.clear()
        for material in replacements:obj.data.materials.append(material)
        cells=[]
        for view in range(4):
            angle=view*math.tau/3
            offset=Vector((math.sin(angle)*40,-math.cos(angle)*40,0)) if view<3 else Vector((0,0,40))
            camera.location=centre+offset;camera.rotation_euler=(-offset).to_track_quat('-Z','Y').to_euler()
            path=output/(obj.name+'-'+mode+f'-{view}.png');scene.render.filepath=str(path)
            bpy.ops.render.render(write_still=True)
            image=bpy.data.images.load(str(path))
            if mode=='normal':image.colorspace_settings.name='Non-Color'
            pixels=np.array(image.pixels[:],np.float32).reshape(size,size,4)
            cells.append(pixels);bpy.data.images.remove(image)
            print('FOREST BAKE',obj.name,mode,view+1,'/4',flush=True)
        # Blender's pixels are bottom-up; cell0 is the atlas's top-left.
        pixels=np.concatenate([np.concatenate(cells[2:4],1),np.concatenate(cells[:2],1)],0)
        image=bpy.data.images.new(obj.name+'_'+mode,size*2,size*2,alpha=True)
        image.colorspace_settings.name='sRGB' if mode=='colour' else 'Non-Color'
        image.pixels[:]=pixels.ravel().tolist();path=output/(obj.name+'_'+mode+'.png')
        image.filepath_raw=str(path);image.file_format='PNG';image.save();bpy.data.images.remove(image)
        atlases[mode]=path.name
        for material in replacements:bpy.data.materials.remove(material)
    obj.data.materials.clear()
    for material in originals:obj.data.materials.append(material)
    bpy.data.objects.remove(camera,do_unlink=True)
    for other in scene.objects:other.hide_render=False
    return dict(atlases=atlases,centre=list(centre),scale=scale,
                coverage=[float((cell[:,:,3]>.4).mean()) for cell in cells])


def mesh(name, record, bark):
    import build_assets as A
    material=A.mat(name+'_Impostor')
    result=A.Mesh(name+'_LOD3');centre=Vector(record['centre']);scale=record['scale']
    for view in range(3):
        angle=view*math.tau/3
        normal=Vector((math.sin(angle),-math.cos(angle),0))
        result.card(centre,(scale,scale),angle,0,material,view,[normal]*4,col=(0.,1.))
    normal=Vector((0,0,1))
    result.card(centre,(scale,scale),0,-90,material,3,[normal]*4,col=(0.,1.))
    # A tiny real stem keeps the authored bark section and material contract.
    result.tube((0,0,0),(0,0,.25),.02,.02,bark,n=3)
    return result.build()
