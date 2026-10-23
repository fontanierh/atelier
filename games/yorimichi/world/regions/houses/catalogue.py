"""Explicit logical assets and frozen original color-stream positions.

Offsets were measured against the original eight-asset authoring order and
validated with complete corner/material/UV/color/collision equality. Keeping
each position explicit prevents an edited sibling from reshuffling its colors.
"""
ASSETS = {
    'House_A': ('house_a', 'house_a', 'model', 0),
    'House_B': ('house_b', 'house_b', 'model', 171),
    'House_C': ('house_c', 'house_c', 'model', 312),
    'HouseLot_1': ('lots', 'lot_mesh', 'lot', 511),
    'HouseLot_2': ('lots', 'lot_mesh', 'lot', 1564),
    'HouseLot_3': ('lots', 'lot_mesh', 'lot', 2305),
    'HouseLot_4': ('lots', 'lot_mesh', 'lot', 3024),
    'HouseLot_5': ('lots', 'lot_mesh', 'lot', 4084),
}
