"""The skatepark pier masters: the adopted record adopted/skatepark/materials, seven M_Pier_<key> surfaces built by the
per-key builder (unreal/Scripts/material_masters/skatepark_masters.py). Inventory: docs/inventory/master-sources.md, section 2.

Each master reads the three texture records of its key (albedo, normal, roughness; the mural has only an albedo), and the
metallic argument is the donor's: steel 1, every other key 0 (donor tools/pier_texture_finish.py lines 69-75; `painted` is
the steel maps at metallic 0, donor import_skatepark.py line 134).
"""
DONOR = 'games/yorimichi/unreal/Scripts/import_skatepark.py'


def _pier(key, roles=('albedo', 'normal', 'roughness'), metallic=0.0):
    return {'id': f'master/skatepark/pier-{key}', 'package': f'/Game/SkatePark/Materials/M_Pier_{key}',
            'builder': 'pier_material',
            'reads': [f'/Game/SkatePark/Textures/T_Pier_{key}_{role}' for role in roles],
            'inputs': [f'texture/skatepark/pier-{key}-{role}' for role in roles],
            'arguments': {'key': key, 'metallic': metallic}}


FAMILY = {
    'name': 'skatepark',
    'adopted': 'adopted/skatepark/materials',
    'owner': 'shared/skatepark/materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'skatepark_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': DONOR,
    'donor_lines': {'pier_material': '132-174'},
    # 16 of the 17 records that reference adopted/skatepark/materials name Pier_concrete in their slot_map (the pier's
    # default surface); the one that does not (skate-park-features-piecedf883a6e8f7c7b66) names only Pier_ceramic and gets its
    # own ceramic master from its recipe. Concrete is the fallback for any record that names no master.
    'fallback': 'master/skatepark/pier-concrete',
    'masters': [
        _pier('basalt'),
        _pier('ceramic'),
        _pier('concrete'),
        _pier('mural', roles=('albedo',)),
        _pier('painted', metallic=0.0),
        _pier('steel', metallic=1.0),
        _pier('wood'),
    ],
}
