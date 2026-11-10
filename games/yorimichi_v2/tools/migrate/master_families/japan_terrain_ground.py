"""The japan ground masters: the forest floor, the Mega Park gate ground and the northern mountains, three of the
packages the japan_base family left in adopted/japan/materials/base-materials (docs/inventory/master-sources.md,
section 10). japan_terrain.py takes the other two terrain masters, the forest crown impostor and the coastal rock; these
three share its builder module and take the donor's atmosphere.py haze through a Custom node.
Builders: unreal/Scripts/material_masters/japan_terrain_masters.py.

The donor read some values from its build output at build time. They are recipe arguments here, as the donor export
(build/yorimichi at the baseline, preserved privately) held them:
- hidamari/north_snow.json (sha256 3ae4c88f...): bounds, step_m, volcano_m, rock_radius_m, rock_prominence_m, south_join_m;
- hidamari/north_crater.json (sha256 76761c4e...): bounds, step_m, size;
- craterpark/textures/textures.json (sha256 ccf5c3fa...): world_aligned.crater_floor.metres;
- tools/craterpark_textures.py (blob bd799134...) WORLD_ALIGNED['crater_floor'][2]: the painting's sRGB mean.
"""
_GROUND = '/Game/Japan/Textures/T_ground'
_DETAIL = '/Game/Japan/Textures/T_ground_detail'
_ROCK = '/Game/Japan/Textures/T_VolcanicRock'
_SNOW = '/Game/Japan/Textures/T_NorthSnowMask'
_CRATER = '/Game/Japan/Textures/T_NorthCraterMask'
_FLOOR = '/Game/Japan/Textures/T_NorthCraterFloor'
_WIND = '/Game/Japan/Materials/MPC_Wind'
_GROUND_RECORD = 'adopted/japan/textures/ground'
_ROCK_RECORD = 'adopted/japan/textures/rock'
_BASE_RECORD = 'adopted/japan/materials/base-materials'   # MPC_Wind, a kept package of the adopted record

FAMILY = {
    'name': 'japan_terrain_ground',
    'adopted': _BASE_RECORD,
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'japan_terrain_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts (one file per builder, see donor_lines), with atmosphere.py 17-62 and '
             'ground_grain.py',
    'donor_lines': {
        'forest_ground': 'forest_ground.py 16-59',
        'north_gate': 'mountain_material.py 249-296',
        'north_mountains': 'mountain_material.py 14-40, 42-233',
    },
    # A referencing record that names none of the three packages keeps its reference to the adopted record, which keeps
    # its other packages; the fallback is only for a dependency line naming none.
    'fallback': 'master/japan/terrain/forest-ground',
    'keeps': [   # the adopted record's other packages, including those a family sharing it may move first
        '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
        '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass', '/Game/Japan/Materials/M_Painted',
        '/Game/Japan/Materials/M_Painterly', '/Game/Japan/Materials/M_Sky', '/Game/Japan/Materials/M_Village',
    ],
    'masters': [
        {'id': 'master/japan/terrain/forest-ground', 'package': '/Game/Japan/Materials/M_ForestGround',
         'builder': 'forest_ground', 'reads': [_GROUND, _DETAIL], 'inputs': [_GROUND_RECORD],
         'arguments': {'near': _GROUND, 'detail': _DETAIL, 'south_join_m': 3600.0}},
        {'id': 'master/japan/terrain/north-gate', 'package': '/Game/Japan/Materials/M_NorthGate',
         'builder': 'north_gate', 'reads': [_GROUND], 'inputs': [_GROUND_RECORD], 'arguments': {'ground': _GROUND}},
        {'id': 'master/japan/terrain/north-mountains', 'package': '/Game/Japan/Materials/M_NorthMountains',
         'builder': 'north_mountains', 'reads': [_ROCK, _DETAIL, _SNOW, _CRATER, _FLOOR, _WIND],
         'inputs': [_ROCK_RECORD, _GROUND_RECORD, _BASE_RECORD],
         'arguments': {'rock': _ROCK, 'ground_detail': _DETAIL, 'snow_mask': _SNOW, 'crater_mask': _CRATER,
                       'crater_floor': _FLOOR, 'collection': _WIND,
                       # hidamari/north_snow.json and north_crater.json (same bounds and step), see the docstring
                       'bounds_x0_m': -430.0, 'bounds_y0_m': 1120.0, 'bounds_x1_m': 2127.5, 'bounds_y1_m': 3677.5,
                       'step_m': 2.5, 'mask_size': 1024, 'volcano_x_m': 850.0, 'volcano_y_m': 2400.0,
                       'rock_radius_inner_m': 1263.906976744186, 'rock_radius_outer_m': 1433.0232558139535,
                       'rock_prominence_low_m': 175.5, 'rock_prominence_high_m': 337.5, 'south_join_m': 3600.0,
                       # craterpark/textures/textures.json and tools/craterpark_textures.py
                       'floor_metres': 16, 'floor_mean_r': 100, 'floor_mean_g': 98, 'floor_mean_b': 100}},
    ],
}
