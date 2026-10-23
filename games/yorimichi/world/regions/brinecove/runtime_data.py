"""Material and placement records shared by coastal production assembly; no geometry exports."""
import math
from brinecove import layout as L
from brinecove.paths import TEXTURES


ROOT = '/Game/Brinecove'


IDENTITY = {'translation_cm': [0., 0., 0.], 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [1., 1., 1.]}


MASKED = ('leaf_', 'palm_', 'waterfall', 'spray', 'foam')


TERRAIN = ('terrain', 'rock')


TRANSLUCENT = ('mist',)


EMISSIVE = ('lantern', 'glass_warm')


PAN_CM_S = {'waterfall': 0.9, 'foam': 0.05}


MOTION = {'waterfall': {'Layer': 1.0}, 'foam': {'Drift': 0.03, 'Wash': 0.22},
          'mist': {'Opacity': 0.42}}  # spray, not an opaque white cloud at the plunge (note 9 review)


TEXTURE = {'waterfall': 'waterfall_streaks', 'foam': 'foam_lace'}


TERRAIN_LAYERS = {'Sand': 'terrain_sand', 'Meadow': 'terrain_meadow', 'Forest': 'terrain_forest', 'Rock': 'terrain_rock'}


ROCK_TINT = {'rock': 1.0, 'rock_light': 1.12, 'rock_dark': 0.72, 'rock_strata': 0.95}


def srgb_to_linear(value):
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def kind(mat):
    if mat.startswith(TRANSLUCENT):
        return 'translucent'
    if mat.startswith(MASKED):
        return 'masked'
    if mat.startswith(TERRAIN):
        return 'terrain'
    if mat.startswith(EMISSIVE):
        return 'emissive'
    return 'opaque'


def material_report(names):
    sources = {}

    def texture_file(stem):
        texture = next((TEXTURES / f'{stem}{ext}' for ext in ('.png', '.jpg') if (TEXTURES / f'{stem}{ext}').exists()), None)
        if texture is None:
            return None
        file = f'T_BC_{stem}{texture.suffix}'
        sources[file] = texture
        return file
    report = {}
    for name in sorted(names):
        hex_colour = L.COLORS.get(name, '#808080')
        colour = [srgb_to_linear(int(hex_colour[i:i + 2], 16)) for i in (1, 3, 5)]
        entry = {'name': 'MI_BC_' + name, 'colour': colour, 'texture': texture_file(TEXTURE.get(name, name)),
                 'kind': kind(name), 'pan': PAN_CM_S.get(name, 0.), 'motion': MOTION.get(name, {}),
                 'roughness': .3 if name.startswith('water') else .88, 'metal': name in ('metal', 'gold')}
        if entry['kind'] == 'terrain':
            # Layers in world space: no texture of its own; rock meshes use the rock layer alone, tinted.
            entry['texture'] = None
            entry['layers'] = {key: texture_file(stem) for key, stem in TERRAIN_LAYERS.items()}
            entry['normals'] = {key + 'N': texture_file(stem + '_n') for key, stem in TERRAIN_LAYERS.items()}
            entry['rock_only'] = name != 'terrain'
            entry['colour'] = [ROCK_TINT.get(name, 1.0)] * 3
        report[name] = entry
    return report, sources


def transform(x, y, z, yaw=0.0, scale=1.0, pitch=0.0):
    """Unreal transform relative to the region origin from local metres and Blender degrees.

    Unreal's y is Blender's -y, so a turn about z by yaw becomes -yaw; pitch turns about local x first."""
    hy, hp = math.radians(-yaw) / 2, math.radians(-pitch) / 2
    qz = (0., 0., math.sin(hy), math.cos(hy))
    qx = (math.sin(hp), 0., 0., math.cos(hp))
    x1, y1, z1, w1 = qz
    x2, y2, z2, w2 = qx
    q = (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
         w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
    return {'translation_cm': [round(x * 100, 1), round(-y * 100, 1), round(z * 100, 1)],
            'rotation_xyzw': [round(c, 5) for c in q], 'scale': [round(scale, 3)] * 3}  # runtime.json carries ~10^5 of these


def group(name, slots, transforms, *, collision, shadow, cull_cm):
    return {'asset': f'{ROOT}/Meshes/{name}.{name}', 'materials': [f'{ROOT}/Materials/MI_BC_{s}.MI_BC_{s}' for s in slots],
            'plant': False, 'collision': collision, 'shadow': shadow, 'cull_cm': cull_cm, 'transforms': transforms}
