"""The Sword Camp masters: M_SwordCamp (the camp and ronin props) and M_RoninBody (the skeletal Ronin body), owned by
adopted/swordcamp/materials (docs/inventory/master-sources.md, section 2 and section 9). Planned, not imported."""
ATLAS = '/Game/SwordCamp/Textures/T_SwordCampAtlas'

FAMILY = {
    'name': 'swordcamp',
    'adopted': 'adopted/swordcamp/materials',
    'owner': 'shared/swordcamp/materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'swordcamp_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts/import_swordcamp.py',   # blob sha256 86ce7b5e...
    'donor_lines': {'build_material': '46-113', 'build_ronin_body_material': '116-171'},
    # The 14 static-mesh props that reference adopted/swordcamp/materials each name M_SwordCamp in slot_materials, so the
    # fallback is the master they use. M_RoninBody has no referencing record in V2 (its skeletal mesh is not recovered), so
    # the fallback can only ever be M_SwordCamp.
    'fallback': 'master/swordcamp/camp',
    # `arguments` are the builder's keyword arguments; `reads` the packages the builder receives.
    'masters': [
        {'id': 'master/swordcamp/camp', 'package': '/Game/SwordCamp/Materials/M_SwordCamp',
         'builder': 'build_material', 'reads': [ATLAS], 'inputs': ['texture/swordcamp/atlas'],
         'arguments': {'texture': ATLAS}},
        {'id': 'master/swordcamp/ronin-body', 'package': '/Game/SwordCamp/Materials/M_RoninBody',
         'builder': 'build_ronin_body_material', 'reads': [ATLAS], 'inputs': ['texture/swordcamp/atlas'],
         'arguments': {'texture': ATLAS}},
    ],
}
