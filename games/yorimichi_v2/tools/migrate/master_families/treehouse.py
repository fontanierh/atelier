"""The Tree House masters: M_TreeHouse and M_TH_Light, owned by adopted/japan/treehouse/generator.

The adopted record retains its pinned Tree House region generator sources and becomes a generator record; its five
material-instance dependents re-point their input_dependencies at the master they parent to.
"""
WOOD_PLANK = '/Game/Japan/Treehouse/Textures/T_TH_wood_plank'
SEE_THROUGH = '/Game/SeeThrough/MPC_SeeThrough'

FAMILY = {
    'name': 'treehouse',
    'adopted': 'adopted/japan/treehouse/generator',
    'owner': 'shared/japan/treehouse/generator',
    'license': 'owner-published (docs/DECISIONS.md D05 group 1)',
    'builder': 'treehouse_masters.py',
    'donor': 'games/yorimichi/unreal/Scripts/import_treehouse.py and see_through.py',
    'donor_lines': {
        'treehouse_surface': 'import_treehouse.py 49-99; see_through.py 381-435, 463-475',
        'treehouse_light': 'import_treehouse.py 129-166',
    },
    'generator': True,
    'fallback': 'master/treehouse/surface',
    'masters': [
        {'id': 'master/treehouse/surface', 'package': '/Game/Japan/Treehouse/Materials/M_TreeHouse',
         'builder': 'treehouse_surface', 'reads': [WOOD_PLANK, SEE_THROUGH],
         'inputs': ['adopted/japan/treehouse/surface-wood-plank', 'material/seethrough/collection'],
         'arguments': {'texture': WOOD_PLANK, 'see_through': SEE_THROUGH}},
        {'id': 'master/treehouse/light', 'package': '/Game/Japan/Treehouse/Materials/M_TH_Light',
         'builder': 'treehouse_light', 'reads': [], 'inputs': [], 'arguments': {}},
    ],
}
