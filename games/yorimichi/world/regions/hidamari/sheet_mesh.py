"""Selected city construction primitive; no sibling geometry or export."""
import bpy
import numpy as np


class SheetMesh:
    """A terrain surface: one smooth sheet with shared vertices, its own normals, the island's
    ground texture's UVs (metres / 6, as the terrain's) and Color = linear RGB and the texture's amount."""
    def __init__(self,name,data):
        self.name=name;self.vertices=data['vertices'];self.faces=data['faces'];self.colliders=[];self.data=data
    def object(self,material):
        d=self.data;me=bpy.data.meshes.new(self.name)
        me.from_pydata(d['vertices'].tolist(),[],d['faces'].tolist());me.update();me.materials.append(material)
        index=np.empty(len(me.loops),dtype=np.int32);me.loops.foreach_get('vertex_index',index)
        uv=me.uv_layers.new(name='UVMap');uv.data.foreach_set('uv',(d['vertices'][index,:2]/6.).astype(np.float32).ravel())
        col=me.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
        col.data.foreach_set('color',np.asarray(d['colours'],np.float32).ravel())
        me.polygons.foreach_set('use_smooth',np.ones(len(me.polygons),bool))
        me.normals_split_custom_set_from_vertices(d['normals'].tolist())
        ob=bpy.data.objects.new(self.name,me);bpy.context.collection.objects.link(ob)
        return ob
