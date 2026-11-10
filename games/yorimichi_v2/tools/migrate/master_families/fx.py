"""The FX masters: M_FX_Additive, M_FX_Dust and M_FX_Trail, owned by adopted/fx (donor import_combat_fx.py). Imported under MASTERFX."""
TEXTURE_GLOW = '/Game/FX/Textures/T_FX_Glow'
TEXTURE_DUST = '/Game/FX/Textures/T_FX_Dust'
TEXTURE_TRAIL = '/Game/FX/Textures/T_FX_Trail'

FAMILY = {
    'name': 'fx',
    'adopted': 'adopted/fx',
    'owner': 'shared/fx',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'fx_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts/import_combat_fx.py',
    'donor_lines': {'sprite_material': '52-69', 'trail': '87-96'},
    # The one referencing record, material/fx-instances, parents three of its four instances to M_FX_Additive (Glow, Ring, Spark)
    # and one to M_FX_Dust. Its recipe names both parents, so the planner maps it by recipe; this fallback is for a record that
    # names no master and is the additive one, the master most of the family's instances parent to.
    'fallback': 'master/fx/additive',
    # `arguments` are the builder's keyword arguments; `reads` the packages the builder receives.
    'masters': [
        {'id': 'master/fx/additive', 'package': '/Game/FX/M_FX_Additive',
         'builder': 'sprite_material', 'reads': [TEXTURE_GLOW], 'inputs': ['texture/fx/glow'],
         'arguments': {'blend': 'additive', 'texture': TEXTURE_GLOW}},
        {'id': 'master/fx/dust', 'package': '/Game/FX/M_FX_Dust',
         'builder': 'sprite_material', 'reads': [TEXTURE_DUST], 'inputs': ['texture/fx/dust'],
         'arguments': {'blend': 'translucent', 'texture': TEXTURE_DUST}},
        {'id': 'master/fx/trail', 'package': '/Game/FX/M_FX_Trail',
         'builder': 'trail', 'reads': [TEXTURE_TRAIL], 'inputs': ['texture/fx/trail'],
         'arguments': {'texture': TEXTURE_TRAIL, 'intensity': 4.0}},
    ],
}
