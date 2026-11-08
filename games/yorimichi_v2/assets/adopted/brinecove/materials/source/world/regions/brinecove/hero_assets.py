"""Place the processed TRELLIS town assets into the assembled Brinecove scene."""
import math

import bpy
from brinecove.hero_model import _import
from brinecove.hero_placements import placements

def _place(obj, collection, x, y, z, yaw=0.0, scale=1.0, pitch=0.0):
    dup = obj.copy()
    dup.data = obj.data
    collection.objects.link(dup)
    dup.location = (x, y, z)
    dup.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
    dup.scale = (scale, scale, scale)
    return dup

def import_model(slug):
    return _import(slug)


def add_hero_assets(collection):
    from brinecove.procedural.hero_presence import HULL
    placed = []
    for slug, spots in placements(HULL).items():
        model = _import(slug)
        if model is None:
            continue
        for x, y, z, yaw, scale, pitch in spots:
            placed.append(_place(model, collection, x, y, z, yaw, scale, pitch))
        bpy.data.objects.remove(model, do_unlink=True)
    if not placed:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    for obj in placed:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = placed[0]
    bpy.ops.object.join()
    result = bpy.context.object
    result.name = '10_hero_assets'
    result['brinecove_module'] = '10_hero_assets'
    return result
