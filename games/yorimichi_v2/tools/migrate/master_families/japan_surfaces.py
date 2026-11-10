"""Surface masters M_Painted and M_Village from the Japan base-materials record (donor pins at 085749fd1d).
japan_vegetation.py takes M_Foliage and M_Grass with the same builder module.

Imported (master_records.py; docs/inventory/master-sources.md). keeps lists the base-materials record's other packages
at that import; only MPC_Wind is still adopted there, with its generator in that record's pinned source tree, so
`--refresh` regenerates these records. The camera collection is read from material/seethrough/collection.
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
        'village_material': 'import_village.py 17-60; atmosphere.py 14-56; sea_look.py 38-69',
    },
    'fallback': 'master/japan/surfaces/painted',
    # The adopted record's other packages, including those a family sharing it may move first.
    'keeps': [
        WIND, '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
        '/Game/Japan/Materials/M_ForestGround', '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass',
        '/Game/Japan/Materials/M_HarborWater', '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
        '/Game/Japan/Materials/M_Painterly', '/Game/Japan/Materials/M_Sea', '/Game/Japan/Materials/M_Sky',
    ],
    'masters': [
        {'id': 'master/japan/surfaces/painted', 'package': '/Game/Japan/Materials/M_Painted',
         'builder': 'painted_material', 'reads': [WHITE, SEE_THROUGH], 'inputs': ['texture/japan/white', 'material/seethrough/collection'],
         'arguments': {'white': WHITE, 'see_through': SEE_THROUGH}},
        {'id': 'master/japan/surfaces/village', 'package': '/Game/Japan/Materials/M_Village',
         'builder': 'village_material', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
