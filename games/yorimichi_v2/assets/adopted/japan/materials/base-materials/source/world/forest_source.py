"""One deterministic forest species/detail level, before any mesh export."""
import math
import bpy
from mathutils import Euler, Vector
import asset_mesh as A
from forest_trees import tree
import far_crown
import forest_impostors

SCREEN_SIZES = [1., .24, .075, .018, .0054]


def initialize(name, args):
    """Fresh material/image caches preserve the original source palette in batched workers."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    A.MATS.clear(); A.LEAF_CROPS.clear()
    if name.startswith('Tree_Tuscan_'):
        from asset_catalog import check_material_namespace
        check_material_namespace([args[-1]], 'forest')
    bark = 'BarkOlive' if args[0] == 'olive' else 'BarkTuscan' if name.startswith('Tree_Tuscan_') else 'Bark'
    A.materials([bark] + ([] if name.startswith('Tree_Tuscan_') else [args[-1]]))
    if name.startswith('Tree_Tuscan_'):
        import yori
        old = A.TEX
        try:
            A.TEX = str(yori.OUT / 'forest/textures')
            A.mat(args[-1], texture='T_' + args[-1] + '.png', alpha=True)
        finally:
            A.TEX = old
    return bark


def base(name, args):
    return tree(name, *args, library=A)


def bounds(obj):
    minimum = Vector(tuple(min(v.co[i] for v in obj.data.vertices) for i in range(3)))
    maximum = Vector(tuple(max(v.co[i] for v in obj.data.vertices) for i in range(3)))
    return dict(minimum=list(minimum), maximum=list(maximum), height=maximum.z,
                spread=max(maximum.x - minimum.x, maximum.y - minimum.y))


def detail(name, args, level, frame):
    """@cc [owner:fontanierh,label:correctness;performance] authored-forest-level-construction
    Construct only this selected species and level. Seed, original base bounds,
    exact card selection/clipping and branch detail MUST remain the original
    authored policy. A rendered export MUST NOT be an input to another level.
    """
    if level not in (1, 2):
        raise ValueError('Only the two authored branch/card LODs use detail construction')
    minimum, maximum = Vector(frame['minimum']), Vector(frame['maximum'])
    original = A.Mesh; stride = (4, 12)[level - 1]
    class LodMesh(original):
        def __init__(self, *args):
            super().__init__(*args); self.cards = 0; self.branch_detail = level < 2
        def begin_canopy(self, count):
            self.cards = 0
            keep = min(count, max(4, math.ceil(count / stride)))
            self.selected = {round(i * (count - 1) / max(keep - 1, 1)) for i in range(keep)}
            self.card_scale = math.sqrt(count / keep)
        def card(self, centre, size, yaw, tilt, *args, **kwargs):
            index = self.cards; self.cards += 1
            if index not in self.selected:
                return
            scale = self.card_scale
            rotation = Euler((math.radians(tilt), math.radians(kwargs.get('roll', 0.)), yaw), 'XYZ').to_matrix()
            for sx, sz in ((-1,-1),(1,-1),(1,1),(-1,1)):
                offset = rotation @ Vector((sx * size[0] / 2, 0, sz * size[1] / 2))
                for axis in range(3):
                    if offset[axis] > 1e-8:
                        scale = min(scale, (maximum[axis] - centre[axis]) / offset[axis])
                    elif offset[axis] < -1e-8:
                        scale = min(scale, (minimum[axis] - centre[axis]) / offset[axis])
            scale = max(scale, .01)
            super().card(centre, (size[0] * scale, size[1] * scale), yaw, tilt, *args, **kwargs)
        def tube(self, *args, **kwargs):
            kwargs['n'] = min(kwargs.get('n', 8), 5 if level == 1 else 3)
            super().tube(*args, **kwargs)
    try:
        A.Mesh = LodMesh
        return tree(f'{name}_LOD{level}', *args, library=A)
    finally:
        A.Mesh = original


def crown(name, args, frame):
    obj = tree(f'{name}_LOD4', *args, library=A)
    record = far_crown.replace(obj, A.MATS[args[-1]], A.mat(far_crown.slot(name), color=(1.,1.,1.)),
        (Vector(frame['maximum']) - Vector(frame['minimum'])).length,
        far_crown.LEAF_TINTS.get(args[-1], (1.,1.,1.)))
    return obj, record


def trunk(obj):
    """Capture the exact original authored cube after rotation/scale application, once."""
    if 'trunk_collision' not in obj:
        return []
    values = obj['trunk_collision']; radius = values[0]; a = Vector(values[1:4]); b = Vector(values[4:7])
    bpy.ops.mesh.primitive_cube_add(size=1, location=(a + b) * .5)
    hull = bpy.context.object; hull.name = 'UCX_' + obj.name + '_00'
    hull.scale = (radius * 2, radius * 2, (b - a).length + .2)
    hull.rotation_euler = (b - a).to_track_quat('Z','Y').to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    from region_mesh_parts import capture_collision
    value = capture_collision(hull)
    bpy.data.objects.remove(hull, do_unlink=True)
    return [value]
