"""Prepared surface masters from the fourteen remaining Japan base packages at 085749fd1d.

No records or packages have moved. The native controller must reconcile this family's keeps with the
current adopted outputs after the sea and sky families; the only removal set here is these four masters.
The camera collection is read from adopted/seethrough. MPC_Wind remains an adopted input, with its generator retained in that record's pinned source tree.
"""
WHITE = '/Game/Japan/Textures/T_white'
WIND = '/Game/Japan/Materials/MPC_Wind'
COVERAGE = '/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA'
ADOPTED = 'adopted/japan/materials/base-materials'
SEE_THROUGH = '/Game/SeeThrough/MPC_SeeThrough'

FAMILY = {
    'name': 'japan_surfaces',
    'adopted': ADOPTED,
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'japan_surface_masters.py',
    'helpers': ['master_haze.py'],
    'donor': 'games/yorimichi/unreal/Scripts at 7eec0f98dd (pins in docs/inventory/japan-surfaces-prep.md)',
    'donor_lines': {
        'painted_material': 'shared_materials.py 169-221 (lit opaque); atmosphere.py 14-56; see_through.py 381-435, 509-525',
        'foliage_material': 'shared_materials.py 37-81, 169-221; foliage_material.py 5-17; see_through.py 381-435, 509-516',
        'grass_material': 'shared_materials.py 224-248, plus foliage_material dependencies; see_through.py 517-520',
        'village_material': 'import_village.py 17-60; atmosphere.py 14-56; sea_look.py 38-69',
    },
    'fallback': 'master/japan/surfaces/painted',
    # Baseline keeps only: reconcile against current outputs at the claimed apply boundary.
    'keeps': [
        WIND, '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_ForestGround',
        '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_HarborWater',
        '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
        '/Game/Japan/Materials/M_Painterly', '/Game/Japan/Materials/M_Sea', '/Game/Japan/Materials/M_Sky',
    ],
    'masters': [
        {'id': 'master/japan/surfaces/painted', 'package': '/Game/Japan/Materials/M_Painted',
         'builder': 'painted_material', 'reads': [WHITE, SEE_THROUGH], 'inputs': ['texture/japan/white', 'adopted/seethrough'],
         'arguments': {'white': WHITE, 'see_through': SEE_THROUGH}},
        {'id': 'master/japan/surfaces/foliage', 'package': '/Game/Japan/Materials/M_Foliage',
         'builder': 'foliage_material', 'reads': [WHITE, WIND, SEE_THROUGH], 'inputs': ['texture/japan/white', ADOPTED, 'adopted/seethrough'],
         'arguments': {'white': WHITE, 'wind': WIND, 'see_through': SEE_THROUGH}},
        {'id': 'master/japan/surfaces/grass', 'package': '/Game/Japan/Materials/M_Grass',
         'builder': 'grass_material', 'reads': [WHITE, WIND, COVERAGE, SEE_THROUGH],
         'inputs': ['texture/japan/white', ADOPTED, 'adopted/seethrough'],
         'arguments': {'white': WHITE, 'wind': WIND, 'coverage': COVERAGE, 'see_through': SEE_THROUGH}},
        {'id': 'master/japan/surfaces/village', 'package': '/Game/Japan/Materials/M_Village',
         'builder': 'village_material', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
