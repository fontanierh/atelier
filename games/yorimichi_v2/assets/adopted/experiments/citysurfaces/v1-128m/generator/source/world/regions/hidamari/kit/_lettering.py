"""Single closed glyph meshes for readable kit signage without overlapping copies."""
import math
from pathlib import Path
import bpy

FONT=Path(__file__).resolve().parents[1]/'fonts/NotoSansJP.ttf'


def raised_text(m,text,position,size,color,weight=.012,depth=.02):
    """Expand the font outline and extrude once; mesh local front faces -Y.

    Offset adds actual stroke width, unlike depth-stacked or displaced duplicate
    sheets. Keep small characters' counters open by capping weight to font size.
    Mesh.at transforms are applied by m.poly just as for the shared letterer.
    """
    curve=bpy.data.curves.new('kit_sign','FONT')
    curve.body=text
    if any(ord(c)>127 for c in text):
        curve.font=bpy.data.fonts.load(str(FONT),check_existing=True)
    curve.align_x='CENTER'
    curve.size=size
    curve.offset=min(weight,size*.014)
    curve.extrude=depth
    curve.resolution_u=1
    ob=bpy.data.objects.new('kit_sign',curve)
    bpy.context.collection.objects.link(ob)
    ob.location=position
    ob.rotation_euler.x=math.pi/2
    data=None
    try:
        # Evaluating directly avoids selection-dependent object.convert operators.
        bpy.context.view_layer.update()
        data=bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        for face in data.polygons:
            m.poly([ob.matrix_world@data.vertices[i].co for i in face.vertices],color)
    finally:
        if data is not None:bpy.data.meshes.remove(data)
        bpy.data.objects.remove(ob,do_unlink=True)
        bpy.data.curves.remove(curve)
