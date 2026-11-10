"""Prepared sky and painterly master sources; no record move or native import is implied.

The keeps list describes the fourteen-package base-materials checkpoint at PR803. Before applying this family after
another base-materials family, reconcile keeps to that adopted record's remaining outputs, excluding only M_Sky and
M_Painterly. Do not restore packages a preceding family already moved. See docs/inventory/sky-painterly-sources.md.
"""
_SKY = '/Game/Japan/Textures/T_sky'

FAMILY = {
    'name': 'japan_sky_painterly',
    'adopted': 'adopted/japan/materials/base-materials',
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'sky_painterly_masters.py',
    'donor': 'games/yorimichi/unreal/Scripts/shared_materials.py and painterly_kernel.py',
    'donor_lines': {
        'sky_material': 'shared_materials.py 169-221, material_assets.py 34-42',
        'painterly_material': 'shared_materials.py 103-166, painterly_kernel.py 9-57, material_assets.py 34-42',
    },
    'fallback': ['master/japan/base/sky', 'master/japan/base/painterly'],
    'keeps': [
        '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
        '/Game/Japan/Materials/M_ForestGround', '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass',
        '/Game/Japan/Materials/M_HarborWater', '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
        '/Game/Japan/Materials/M_Painted', '/Game/Japan/Materials/M_Sea', '/Game/Japan/Materials/M_Village',
    ],
    'masters': [
        {'id': 'master/japan/base/sky', 'package': '/Game/Japan/Materials/M_Sky',
         'builder': 'sky_material', 'reads': [_SKY], 'inputs': ['texture/japan/sky'],
         'arguments': {'texture': _SKY}},
        {'id': 'master/japan/base/painterly', 'package': '/Game/Japan/Materials/M_Painterly',
         'builder': 'painterly_material', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
