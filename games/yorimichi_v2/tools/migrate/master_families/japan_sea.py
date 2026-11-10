"""The japan sea masters: the open sea (M_Sea) and the Hidamari harbour water (M_HarborWater), two of the fourteen packages the
japan_base family left in adopted/japan/materials/base-materials (docs/inventory/master-sources.md, section 10). Both read
the donor's sea_look.py and the harbour rectangle from world/coast_water.py, copied into the builder module.
Builders: unreal/Scripts/material_masters/japan_sea_masters.py.
"""
FAMILY = {
    'name': 'japan_sea',
    'adopted': 'adopted/japan/materials/base-materials',
    'owner': 'shared/japan/materials/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'japan_sea_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts (one file per builder, see donor_lines); sea_look.py 38-150; '
             'games/yorimichi/world/coast_water.py 6',
    'donor_lines': {
        'sea_material': 'import_southwest.py 14-19, 32-70',
        'harbor_water': 'harbor_material.py 16-18, 39-142, 174-176',
    },
    # A referencing record that names neither package keeps its reference to the adopted record, which keeps the
    # other packages; the fallback is only for a dependency line naming neither.
    'fallback': 'master/japan/sea/open-sea',
    # The twelve packages that still have no recoverable builder (and MPC_Wind, which is not a Material).
    'keeps': [
        '/Game/Japan/Materials/MPC_Wind', '/Game/Japan/Materials/M_CoastRock', '/Game/Japan/Materials/M_Foliage',
        '/Game/Japan/Materials/M_ForestGround', '/Game/Japan/Materials/M_ForestImpostor', '/Game/Japan/Materials/M_Grass',
        '/Game/Japan/Materials/M_NorthGate', '/Game/Japan/Materials/M_NorthMountains', '/Game/Japan/Materials/M_Painted',
        '/Game/Japan/Materials/M_Painterly', '/Game/Japan/Materials/M_Sky', '/Game/Japan/Materials/M_Village',
    ],
    'masters': [
        {'id': 'master/japan/sea/open-sea', 'package': '/Game/Japan/Materials/M_Sea',
         'builder': 'sea_material', 'reads': [], 'inputs': [], 'arguments': {}},
        {'id': 'master/japan/sea/harbor-water', 'package': '/Game/Japan/Materials/M_HarborWater',
         'builder': 'harbor_water', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
