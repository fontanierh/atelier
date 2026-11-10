"""The japan base masters: thirteen of the 27 packages that adopted/japan/materials/base-materials owns (docs/inventory/master-sources.md,
section 10). The other fourteen stay in that record, which the planner refuses to move until they are kept (see section 10).
Builders: unreal/Scripts/material_masters/japan_base_masters.py, with one donor pin per builder.
"""
_ARCADE = '/Game/Japan/Textures/T_Arcade_timber'
_ARCADE_PAVING = '/Game/Japan/Textures/T_Arcade_paving'
_HARBOR_PAVING = '/Game/Japan/Textures/T_Harbor_paving'
_HARBOR_TIMBER = '/Game/Japan/Textures/T_Harbor_timber'
_CLOUD_MASK = '/Game/Japan/Textures/T_cloudmask'

FAMILY = {
    'name': 'japan_base',
    'adopted': 'adopted/japan/materials/base-materials',
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'japan_base_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts (one file per builder, see donor_lines)',
    'donor_lines': {
        'arcade_material': 'arcade_material.py 24-63',
        'bike_material': 'bike_material.py 6-32',
        'harbor_material': 'harbor_material.py 39-61, 143-176',
        'plaza_water': 'plaza_material.py 5-34',
        'plaza_paving': 'plaza_material.py 37-68',
        'sailboat_material': 'sailboat_material.py 5-40',
        'fabric_material': 'import_zeppelin.py 13-30',
        'forest_lake_water': 'forest_lake_material.py 20-36, 39-86',
        'village_resident': 'import_village.py 63-85',
        'cloud_shadow': 'shared_materials.py 84-100, material_assets.py 34-42',
    },
    # A referencing record that names none of the family's master packages points here. The 49 such records are
    # adopted tree, bark, ground, rock and water materials whose `references` name this record as their generator unit,
    # with no instance parent in it. Nothing in the record's own graph picks a master for them, so this stand-in is the
    # owner's to change; keeping the record's packages (section 10) avoids the choice entirely.
    'fallback': 'master/japan/base/forest-lake-water',
    # The packages the adopted record keeps: the planner's keeps mechanism leaves them in the record, and referencing
    # records keep their adopted reference (see docs/inventory/master-sources.md, section 10). M_Sea and M_HarborWater,
    # kept here at first, moved later to the japan_sea family.
    'keeps': [
        '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
        '/Game/Japan/Materials/M_ForestGround', '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass',
        '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains',
        '/Game/Japan/Materials/M_Painted', '/Game/Japan/Materials/M_Painterly',
        '/Game/Japan/Materials/M_Sky', '/Game/Japan/Materials/M_Village',
    ],
    'masters': [
        {'id': 'master/japan/base/arcade', 'package': '/Game/Japan/Materials/M_Arcade',
         'builder': 'arcade_material', 'reads': [_ARCADE], 'inputs': ['texture/japan/arcade-timber'],
         'arguments': {'texture': _ARCADE, 'paving': False}},
        {'id': 'master/japan/base/arcade-paving', 'package': '/Game/Japan/Materials/M_ArcadePaving',
         'builder': 'arcade_material', 'reads': [_ARCADE_PAVING], 'inputs': ['texture/japan/arcade-paving'],
         'arguments': {'texture': _ARCADE_PAVING, 'paving': True}},
        {'id': 'master/japan/base/bike', 'package': '/Game/Japan/Materials/M_Bike',
         'builder': 'bike_material', 'reads': [], 'inputs': [], 'arguments': {}},
        {'id': 'master/japan/base/harbor', 'package': '/Game/Japan/Materials/M_Harbor',
         'builder': 'harbor_material', 'reads': [_HARBOR_PAVING, _HARBOR_TIMBER],
         'inputs': ['texture/japan/harbor-paving', 'texture/japan/harbor-timber'],
         'arguments': {'paving': _HARBOR_PAVING, 'timber': _HARBOR_TIMBER}},
        {'id': 'master/japan/base/plaza-paving', 'package': '/Game/Japan/Materials/M_PlazaPaving',
         'builder': 'plaza_paving', 'reads': [_ARCADE_PAVING], 'inputs': ['texture/japan/arcade-paving'],
         'arguments': {'texture': _ARCADE_PAVING}},
        {'id': 'master/japan/base/plaza-water', 'package': '/Game/Japan/Materials/M_PlazaWater',
         'builder': 'plaza_water', 'reads': [], 'inputs': [], 'arguments': {'pond': False}},
        {'id': 'master/japan/base/pond-water', 'package': '/Game/Japan/Materials/M_PondWater',
         'builder': 'plaza_water', 'reads': [], 'inputs': [], 'arguments': {'pond': True}},
        {'id': 'master/japan/base/sailboat-cloth', 'package': '/Game/Japan/Materials/M_SailboatCloth',
         'builder': 'sailboat_material', 'reads': [], 'inputs': [], 'arguments': {'wake': False}},
        {'id': 'master/japan/base/sailboat-wake', 'package': '/Game/Japan/Materials/M_SailboatWake',
         'builder': 'sailboat_material', 'reads': [], 'inputs': [], 'arguments': {'wake': True}},
        {'id': 'master/japan/base/zeppelin-fabric', 'package': '/Game/Japan/Materials/M_ZeppelinFabric',
         'builder': 'fabric_material', 'reads': [], 'inputs': [], 'arguments': {}},
        {'id': 'master/japan/base/forest-lake-water', 'package': '/Game/Japan/Materials/M_ForestLakeWater',
         'builder': 'forest_lake_water', 'reads': [], 'inputs': [], 'arguments': {}},
        {'id': 'master/japan/base/village-resident', 'package': '/Game/Japan/Materials/M_VillageResident',
         'builder': 'village_resident', 'reads': [], 'inputs': [], 'arguments': {}},
        {'id': 'master/japan/base/cloud-shadow', 'package': '/Game/Japan/Materials/M_CloudShadow',
         'builder': 'cloud_shadow', 'reads': [_CLOUD_MASK], 'inputs': ['texture/japan/cloudmask'],
         'arguments': {'texture': _CLOUD_MASK}},
    ],
}
