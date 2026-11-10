"""The skateboard dissolve master: the adopted record adopted/skatepark/board, one M_BoardDissolve built by the module body of
the donor wrapped in one function (unreal/Scripts/material_masters/skatepark_board_masters.py). Inventory: master-sources.md,
section 2 and section 4.

It has no texture input and no per-master argument: the donor's constants are in the builder, and the Dissolve parameter's
default (0) is the donor's.
"""
DONOR = 'games/yorimichi/unreal/Scripts/board_dissolve_material.py'

FAMILY = {
    'name': 'skatepark_board',
    'adopted': 'adopted/skatepark/board',
    'owner': 'shared/skatepark/board',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'skatepark_board_masters.py',   # unreal/Scripts/material_masters/, copied into the record's src/
    'donor': DONOR,
    'donor_lines': {'board_dissolve': '1-95'},
    # No record in the tree references adopted/skatepark/board: the skateboard's parts (skate-deck, skate-truck, skate-wheel)
    # reference the Japan base materials, and M_BoardDissolve is read by the game's skate settings at run time, not by a
    # record. The fallback is therefore the family's only master.
    'fallback': 'master/skatepark/board-dissolve',
    'masters': [
        {'id': 'master/skatepark/board-dissolve', 'package': '/Game/SkatePark/Board/M_BoardDissolve',
         'builder': 'board_dissolve', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
