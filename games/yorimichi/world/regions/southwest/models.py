"""One explicitly selected Southwest constructor, independent of sibling execution."""
import importlib
import json
from pathlib import Path

from atelier.export_manifest import real_directory
from random_stream import positioned

MODELS = {
    'stand': ('stand', 'build', 'SW_CoconutStand'),
    'fisher_house_a': ('fishing', 'fisher_house_a', 'SW_FisherHouseA'),
    'fisher_house_b': ('fishing', 'fisher_house_b', 'SW_FisherHouseB'),
    'boat_shed': ('fishing', 'boat_shed', 'SW_BoatShed'),
    'stairs': ('fishing', 'stairs', 'SW_StoneStairs'),
    'dock': ('fishing', 'dock', 'SW_Dock'), 'boat': ('fishing', 'boat', 'SW_Boat'),
    'drying_rack': ('fishing', 'drying_rack', 'SW_DryingRack'),
    'temple': ('temple', 'temple', 'SW_Temple'), 'island': ('island', 'build', 'SW_Island'),
    'boulder_a': ('island', 'boulder_a', 'SW_Boulder_A'),
    'boulder_b': ('island', 'boulder_b', 'SW_Boulder_B'),
    'boulder_c': ('island', 'boulder_c', 'SW_Boulder_C'),
    'stone_wall': ('fishing', 'stone_wall', 'SW_StoneWall'),
    'pine_lean_a': ('island', 'pine_lean_a', 'Tree_PineLean_A'),
    'pine_lean_b': ('island', 'pine_lean_b', 'Tree_PineLean_B')}


def construct(model, context_path):
    if model not in MODELS:
        raise ValueError('Unknown Southwest logical model')
    module, function, asset = MODELS[model]
    path = Path(context_path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Southwest requires a regular selected constructor context')
    context = json.loads(path.read_text())
    if (set(context) != {'schema', 'model', 'asset', 'contexts'} or context['schema'] != 1
            or context['model'] != model or context['asset'] != asset
            or set(context['contexts']) != {'stand', 'fishing', 'temple', 'village'}):
        raise ValueError('Invalid Southwest constructor identity')
    # Import before restoration: neither a reused worker nor another builder's
    # import-time draws may supply the selected owner's geometry parameters.
    selected = importlib.import_module('southwest.' + module)
    modules = {module: selected} if module in ('stand', 'fishing', 'temple') else {}
    if module == 'fishing': modules['village'] = importlib.import_module('village.mesh')
    for key, selected_module in modules.items():
        value = context['contexts'][key]
        if not isinstance(value, dict) or set(value) != {'seed', 'prefix_words'}:
            raise ValueError('Invalid Southwest random stream context')
        selected_module.R.setstate(positioned(value['seed'], value['prefix_words']).getstate())
    source = (selected.MODELS[function]() if module == 'fishing' else getattr(selected, function)())
    if source.name != asset:
        raise ValueError('Southwest constructor returned a foreign logical asset')
    return source
