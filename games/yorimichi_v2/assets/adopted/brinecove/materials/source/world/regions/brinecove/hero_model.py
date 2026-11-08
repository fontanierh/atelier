"""Import exactly one committed hero source without placement or regional geometry."""
import bpy
from brinecove.paths import MODELS


def _import(slug):
    source = MODELS / f'{slug}.glb'
    if not source.exists():
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == 'MESH']
    if not imported:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    if len(imported) > 1:
        bpy.ops.object.join()
    obj = bpy.context.object
    obj.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj
