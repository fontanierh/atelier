"""The hippodrome masters: the importer pilot (docs/inventory/master-sources.md, section 5). Imported under MASTERHD."""
TEXTURE_GRASS = '/Game/Hippodrome/Textures/T_Grass'
TEXTURE_DIRT = '/Game/Hippodrome/Textures/T_Dirt'
ENGINE_WHITE = '/Engine/EngineResources/WhiteSquareTexture'

FAMILY = {
    'name': 'hippodrome',
    'adopted': 'adopted/hippodrome/materials',
    'owner': 'shared/hippodrome/materials',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'hippodrome_masters.py',   # unreal/Scripts/material_masters/, copied into each record's src/
    'donor': 'games/yorimichi/unreal/Scripts/import_hippodrome.py',
    'donor_lines': {'surface': '36-55', 'structure_material': '59-78'},
    # A record that references the adopted record but names no master package slots a loose mesh's own instance
    # (owned by adopted/hippodrome/meshes), whose parent is M_HD_Structure.
    'fallback': 'master/hippodrome/structure',
    # `arguments` are the builder's keyword arguments; `reads` the packages the builder receives.
    'masters': [
        {'id': 'master/hippodrome/structure', 'package': '/Game/Hippodrome/Materials/M_HD_Structure',
         'builder': 'structure_material', 'reads': [ENGINE_WHITE], 'inputs': [],
         'arguments': {'texture': ENGINE_WHITE}},
        {'id': 'master/hippodrome/grass', 'package': '/Game/Hippodrome/Materials/M_HD_Grass',
         'builder': 'surface', 'reads': [TEXTURE_GRASS], 'inputs': ['texture/hippodrome/grass'],
         'arguments': {'texture': TEXTURE_GRASS, 'roughness': 0.95, 'two_sided': False}},
        {'id': 'master/hippodrome/dirt', 'package': '/Game/Hippodrome/Materials/M_HD_Dirt',
         'builder': 'surface', 'reads': [TEXTURE_DIRT], 'inputs': ['texture/hippodrome/dirt'],
         'arguments': {'texture': TEXTURE_DIRT, 'roughness': 0.95, 'two_sided': False}},
        {'id': 'master/hippodrome/stone', 'package': '/Game/Hippodrome/Materials/M_HD_Stone',
         'builder': 'surface', 'reads': [], 'inputs': [],
         'arguments': {'colour_r': 0.36, 'colour_g': 0.35, 'colour_b': 0.32, 'roughness': 0.9, 'two_sided': True}},
        {'id': 'master/hippodrome/rail', 'package': '/Game/Hippodrome/Materials/M_HD_Rail',
         'builder': 'surface', 'reads': [], 'inputs': [],
         'arguments': {'colour_r': 0.86, 'colour_g': 0.85, 'colour_b': 0.80, 'roughness': 0.6, 'two_sided': False}},
    ],
}
