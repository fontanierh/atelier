"""Material-to-UV surface scales used by geometry and texture preparation."""

# material key -> (base surface, metres per tile)
MATERIAL_SURFACE = {
    'plaster': ('plaster', 2.8), 'cream': ('plaster', 2.8), 'ochre': ('plaster', 2.8),
    'coral': ('plaster', 2.8), 'sage_wall': ('plaster', 2.8), 'teal_wall': ('plaster', 2.8),
    'azure_wall': ('plaster', 2.8), 'lime_wall': ('plaster', 2.8), 'rose_wall': ('plaster', 2.8),
    'yellow_wall': ('plaster', 2.8), 'peach_wall': ('plaster', 2.8),
    'roof_terra': ('roof', 1.9), 'roof_terra_light': ('roof', 1.9), 'roof_teal': ('roof', 1.9),
    'roof_slate': ('roof', 1.9), 'roof_straw': ('thatch', 1.6),
    'stone': ('stone', 3.2), 'stone_light': ('stone', 3.2), 'stone_dark': ('stone', 3.2),
    'cobble': ('cobble', 2.0), 'cobble_dark': ('cobble', 2.0),
    'wood': ('wood', 1.5), 'wood_dark': ('wood', 1.5), 'wood_light': ('wood', 1.5),
    'sail': ('canvas', 2.2), 'canvas': ('canvas', 2.2), 'canvas_red': ('canvas', 2.2),
    'sail_dark': ('canvas', 2.2),
    'canvas_teal': ('canvas', 2.2), 'canvas_gold': ('canvas', 2.2), 'canvas_blue': ('canvas', 2.2),
    'canvas_green': ('canvas', 2.2),
    'metal': ('iron', 1.0), 'gold': ('iron', 1.0),
    'water': ('water', 26.0), 'water_shallow': ('water', 18.0), 'water_mid': ('water', 22.0),
    'rock': ('cliff_block', 22.0), 'rock_light': ('cliff_block', 22.0),
    'rock_dark': ('cliff_block', 22.0), 'rock_strata': ('cliff_strata', 9.0), 'moss': ('moss_rock', 5.0),
    'planks': ('planks', 1.5),
    'hull': ('hull_planks', 2.0), 'deck_planks': ('hull_planks', 1.8),
    'sand': ('sand', 4.5), 'earth': ('sand', 4.5),
    'jungle': ('foliage', 3.0), 'jungle_light': ('foliage', 3.0), 'jungle_dark': ('foliage', 3.0),
    'palm': ('foliage', 3.0), 'palm_light': ('foliage', 3.0),
    'autumn_rust': ('foliage', 3.0), 'autumn_gold': ('foliage', 3.0),
    'autumn_olive': ('foliage', 3.0),
}
