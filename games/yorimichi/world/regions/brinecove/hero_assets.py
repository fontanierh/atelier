"""Place the processed TRELLIS town assets into the assembled Brinecove scene."""
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from brinecove import layout as L
from brinecove import kit

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


def _place(obj, collection, x, y, z, yaw=0.0, scale=1.0, pitch=0.0):
    dup = obj.copy()
    dup.data = obj.data
    collection.objects.link(dup)
    dup.location = (x, y, z)
    dup.rotation_euler = (math.radians(pitch), 0.0, math.radians(yaw))
    dup.scale = (scale, scale, scale)
    return dup


def placements(hull):
    """{model slug: [(x, y, z, yaw, scale, pitch)...]} in layout metres; hull is the galleon hull's provenance."""
    result = {'pirate-queen-statue': [(L.STATUE[0], L.STATUE[1], 12.0, 0.0, 1.0, 0.0)]}
    if hull and (MODELS / 'galleon-hull.glb').exists():
        # Keel a quarter of the hull's height below the sea.
        depth = hull['top_z'] * 0.24
        result['galleon-hull'] = [(x, y, -0.35 - depth * scale, yaw, scale, 0.0) for _, x, y, yaw, scale, _ in L.SHIPS]
    else:
        # Two carved figureheads on the moored galleons, bracketed onto the stem under the bowsprit.
        result['galleon-figurehead'] = [(*kit.local(x, y, yaw, 0.0, 30.4 * scale), -1.1 + 4.6 * scale, yaw, 0.78, -32)
                                        for _, x, y, yaw, scale, _ in L.SHIPS[:2]]
        name, x, y, yaw, scale, sails = L.SHIPS[0]
        result['ships-wheel'] = [(*kit.local(x, y, yaw, 0.0, -16.5 * scale), -1.1 + 4.72 * scale, yaw + 90, 0.9, 0.0)]
    # The harbor cannon is procedural now (landmarks.cannon, placed by modules.props).
    # The quay anchor is procedural now (landmarks.anchor, placed by modules.props).
    result['harbor-capstan'] = [(x, y, 5.35, yaw, 1.0, 0.0) for x, y, yaw in ((8, -24, 0), (238, -50, 34))]
    return result


def import_model(slug):
    return _import(slug)


def add_hero_assets(collection):
    from brinecove.modules import HULL
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
