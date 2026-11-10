"""The Mega Park retail masters: M_RetailOpaque, M_RetailMasked and M_RetailTranslucent, owned by adopted/megapark/base-materials
(donor import_megapark.py, material(alpha, defaults)). Imported under MASTERMEGAPARK."""
SHARED_TEXTURES = 'adopted/megapark/shared-textures-common'
TEXTURE_WHITE = '/Game/MegaPark/Textures/T_DefaultWhite'
TEXTURE_LINEAR = '/Game/MegaPark/Textures/T_DefaultLinear'
TEXTURE_BLACK = '/Game/MegaPark/Textures/T_DefaultBlack'
TEXTURE_NORMAL = '/Game/MegaPark/Textures/T_DefaultNormal'
DEFAULT_TEXTURES = [TEXTURE_WHITE, TEXTURE_LINEAR, TEXTURE_BLACK, TEXTURE_NORMAL]

FAMILY = {
    'name': 'megapark',
    'adopted': 'adopted/megapark/base-materials',
    'owner': 'shared/megapark/base-materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'megapark_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts/import_megapark.py',
    'donor_lines': {'retail_material': '68-163'},
    # The fallback is the opaque retail parent. The 22 cell records each own material instances that parent to all three retail
    # parents (their meshes are mostly opaque, 21 cells have masked meshes and 3 have translucent ones), and the seam and shared
    # instance records name M_RetailOpaque. No single master is exact for a cell; the planner's one-master fallback is the gap the
    # owner must decide (see the report). The default textures are not masters' outputs, so they come from shared-textures-common.
    'fallback': 'master/megapark/opaque',
    # `reads` are the four default textures every retail parent is built on (the donor's `defaults`), owned by shared-textures-common.
    # `arguments` carry the donor's alpha: 0 opaque, 1 masked, 2 translucent (blend mode, two-sided and the opacity pin all follow it).
    'masters': [
        {'id': 'master/megapark/opaque', 'package': '/Game/MegaPark/Materials/M_RetailOpaque',
         'builder': 'retail_material', 'reads': DEFAULT_TEXTURES, 'inputs': [SHARED_TEXTURES],
         'arguments': {'alpha': 0}},
        {'id': 'master/megapark/masked', 'package': '/Game/MegaPark/Materials/M_RetailMasked',
         'builder': 'retail_material', 'reads': DEFAULT_TEXTURES, 'inputs': [SHARED_TEXTURES],
         'arguments': {'alpha': 1}},
        {'id': 'master/megapark/translucent', 'package': '/Game/MegaPark/Materials/M_RetailTranslucent',
         'builder': 'retail_material', 'reads': DEFAULT_TEXTURES, 'inputs': [SHARED_TEXTURES],
         'arguments': {'alpha': 2}},
    ],
}
