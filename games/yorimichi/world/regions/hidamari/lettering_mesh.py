"""Selected city construction primitive; no sibling geometry or export."""
import math
import bpy
from hidamari.environment import ROOT


def lettering(m,text,position,size=1.0,color='cream'):
    curve=bpy.data.curves.new('sign','FONT');curve.body=text;
    if any(ord(c)>127 for c in text):curve.font=bpy.data.fonts.load(str(ROOT/'hidamari/fonts/NotoSansJP.ttf'),check_existing=True)
    curve.align_x='CENTER';curve.size=size;curve.extrude=.006;curve.resolution_u=1
    ob=bpy.data.objects.new('sign',curve);bpy.context.collection.objects.link(ob);ob.location=position;ob.rotation_euler.x=math.pi/2
    bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH')
    for face in ob.data.polygons:m.poly([ob.matrix_world@ob.data.vertices[i].co for i in face.vertices],color)
    bpy.data.objects.remove(ob,do_unlink=True)
