"""One original skateboard dissolve Material owner using the recorded native call body."""
from pathlib import Path

from v2_texture_units import SIDECARS, Unsupported, _code

SCRIPT = 'games/yorimichi/world/native_author_call_v2.py'
ORIGINAL = 'games/yorimichi/unreal/Scripts/board_dissolve_material.py'
PACKAGE = '/Game/SkatePark/Board/M_BoardDissolve'
UNIT = 'unreal.skate_board.material.M_BoardDissolve'


def author_units(rows, *, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] original-board-material-owner
    The exact original unreal.skate_board row MUST map to one Material owner with
    complete keyed source and checkout sidecars before publishing its alias. Its
    named original build MUST run through the existing native author call ABI,
    with no native dependencies, generated discovery or original main execution.
    """
    result = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {}, 'aliases': {}}
    selected = [row for row in rows if row['id'] == 'unreal.skate_board']
    if not selected:
        return result
    if len(selected) != 1:
        raise Unsupported('duplicate skateboard dissolve producer')
    row = selected[0]
    stem = PACKAGE.removeprefix('/Game/')
    primary = 'games/yorimichi/unreal/Content/' + stem + '.uasset'
    commands = row['commands']
    if (row['outputs'] != [primary] or len(commands) != 1
            or commands[0].get('kind') != 'UnrealScript' or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('marker') != 'BOARD DISSOLVE MATERIAL COMPLETE'
            or commands[0].get('null_rhi') is not False or commands[0].get('env') not in ([], ())
            or commands[0].get('args') not in ([], ()) or commands[0].get('modules') not in ([], ())):
        raise Unsupported('board dissolve must match its exact original command and package')
    root = Path(checkout)
    from atelier.source_imports import ImportScanner
    code = {*_code(root), SCRIPT, ORIGINAL}
    for source in (SCRIPT, ORIGINAL):
        code.update(path.relative_to(root).as_posix() for path in ImportScanner().local_imports(
            root / source, (root / 'platform/studio', root / 'games/yorimichi/unreal/Scripts')))
    for relative in code:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise Unsupported('missing or linked board dissolve keyed source: ' + relative)
    unit = {'id': UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
            'code': sorted(code), 'inputs': [],
            'params': {'args': {'module': ORIGINAL, 'function': 'build', 'arguments': [],
                                'keyword_arguments': {}, 'expected_package': PACKAGE}, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': PACKAGE, 'class': 'Material', 'destination': 'checkout',
                         'files': [{'path': 'content/Game/' + stem + suffix,
                                    'install_path': 'games/yorimichi/unreal/Content/' + stem + suffix,
                                    'required': suffix == '.uasset'} for suffix in SIDECARS]}]}
    result['units'] = [unit]
    result['staged_inputs'] = {UNIT: {}}
    result['packages'] = {PACKAGE: {'unit': UNIT, 'item': 'asset', 'package': PACKAGE}}
    result['aliases'] = {'unreal.skate_board': [UNIT]}
    return result
