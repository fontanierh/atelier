"""The japan terrain masters: the forest crown impostor and the coastal rock, two of the packages the japan_base family
left in adopted/japan/materials/base-materials (docs/inventory/master-sources.md, section 10). Both take the donor's
atmosphere.py haze. japan_terrain_ground.py takes the forest floor, the Mega Park gate ground and the northern mountains
with the same builder module.
Builders: unreal/Scripts/material_masters/japan_terrain_masters.py.
"""
_WHITE = '/Engine/EngineResources/WhiteSquareTexture'
_NORMAL = '/Game/Japan/Textures/T_ForestNormalDefault'
_COAST_ROCK = '/Game/Japan/Textures/T_CoastRock'
_GROUND_RECORD = 'adopted/japan/textures/ground'
_ROCK_RECORD = 'adopted/japan/textures/rock'

FAMILY = {
    'name': 'japan_terrain',
    'adopted': 'adopted/japan/materials/base-materials',
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'japan_terrain_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts (one file per builder, see donor_lines), with atmosphere.py 17-62 and '
             'coast_rock_look.py',
    'donor_lines': {
        'forest_impostor': 'forest_impostor_material.py 6-53; import_forest.py 43-51 (default_normal)',
        'coast_rock': 'forest_ground.py 62-112; coast_rock_look.py; material_assets.py 45-67',
    },
    # A referencing record that names neither package keeps its reference to the adopted record, which keeps its other
    # packages; the fallback is only for a dependency line naming none.
    'fallback': 'master/japan/terrain/forest-impostor',
    'keeps': [   # the adopted record's other packages, including those a family sharing it may move first
        '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_Foliage', '/Game/Japan/Materials/M_ForestGround',
        '/Game/Japan/Materials/M_Grass', '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
        '/Game/Japan/Materials/M_Painted', '/Game/Japan/Materials/M_Painterly', '/Game/Japan/Materials/M_Sky',
        '/Game/Japan/Materials/M_Village',
    ],
    'masters': [
        {'id': 'master/japan/terrain/forest-impostor', 'package': '/Game/Japan/Materials/M_ForestImpostor',
         'builder': 'forest_impostor', 'reads': [_WHITE, _NORMAL], 'inputs': [_GROUND_RECORD],
         'arguments': {'white': _WHITE, 'default_normal': _NORMAL}},
        {'id': 'master/japan/terrain/coast-rock', 'package': '/Game/Japan/Materials/M_CoastRock',
         'builder': 'coast_rock', 'reads': [_COAST_ROCK], 'inputs': [_ROCK_RECORD], 'arguments': {'texture': _COAST_ROCK}},
    ],
}
