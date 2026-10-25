"""C3 owners for unreal.fx: the five combat sprite textures and the seven /Game/FX materials.

Scripts/import_combat_fx.py imports build/yorimichi/combat_fx/T_FX_*.png (written by assets/fx/gen_textures.py)
and builds M_FX_Additive, M_FX_Dust, M_FX_Trail and their instances at import time. Here each image is a
raw_import from the fx.textures product ROOT (member T_FX_<name>.png) plus a finish carrying the original
texture settings, and each saved material graph is one author unit whose body runs the original definitions.
The sprite roster comes from the generator's committed save() calls, never from a generated folder.
"""
import ast
from pathlib import Path

from v2_texture_units import OPS, Unsupported, _code, _output

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/fx_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_combat_fx.py'
GENERATOR = GAME + '/assets/fx/gen_textures.py'
SOURCE_ROOT = 'build/yorimichi/combat_fx'
DEST = '/Game/FX'
TEXTURES = DEST + '/Textures/'
# Original saved graphs: sprite material -> (blend, default sprite); instance -> (parent, sprite).
SPRITES = {'M_FX_Additive': ('BLEND_ADDITIVE', 'Glow'), 'M_FX_Dust': ('BLEND_TRANSLUCENT', 'Dust')}
INSTANCES = {'MI_FX_Glow': ('M_FX_Additive', 'Glow'), 'MI_FX_Spark': ('M_FX_Additive', 'Spark'),
             'MI_FX_Ring': ('M_FX_Additive', 'Ring'), 'MI_FX_Dust': ('M_FX_Dust', 'Dust')}
TRAIL = ('M_FX_Trail', 'Trail')
TEXTURE_PROPERTIES = {'srgb': False, 'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_EFFECTS'}}


def sprites(checkout):
    """T_FX_<name> for every save('T_FX_<name>', ...) call in the committed generator."""
    tree = ast.parse((Path(checkout) / GENERATOR).read_bytes(), filename=GENERATOR)
    names = [node.args[0].value for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'save'
             and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)]
    if not names or len(set(names)) != len(names) or any(not n.startswith('T_FX_') or not n[5:].isalpha() for n in names):
        raise Unsupported('fx generator sprite declarations differ from the original T_FX_<name> roster')
    return sorted(name.removeprefix('T_FX_') for name in names)


def _check(rows):
    by_id = {row['id']: row for row in rows if row['id'] in ('fx.textures', 'unreal.fx')}
    if sorted(by_id) != ['fx.textures', 'unreal.fx']:
        raise Unsupported('unreal.fx needs its exact fx.textures and unreal.fx rows')
    producer, importer = by_id['fx.textures'], by_id['unreal.fx']
    commands = importer['commands']
    if (len(commands) != 1 or commands[0]['kind'] != 'UnrealScript' or commands[0]['script'] != {'path': ORIGINAL}
            or commands[0]['marker'] != 'COMBAT FX IMPORT COMPLETE' or commands[0]['args'] or commands[0]['env']
            or importer['outputs'] or importer['products'] or importer['needs'] != ['fx.textures']):
        raise Unsupported('unreal.fx differs from the original combat FX import')
    if ([c.get('script') for c in producer['commands']] != [{'path': GENERATOR}]
            or [(p['paths'], p['optional_paths']) for p in producer['products']] != [([SOURCE_ROOT], [])]):
        raise Unsupported('fx.textures must own its complete combat_fx ROOT as its one product')
    return producer


def author_units(rows, *, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] combat-fx-owners
    Every original combat sprite MUST be one raw import from the complete fx.textures
    ROOT member plus a finish with the original texture settings. Every saved FX
    material graph MUST be one author unit binding only its declared finished inputs
    and running import_combat_fx.py's own definitions and trail statements. Nothing
    MAY scan generated sprites, run the original top level or write its report.
    """
    if natives not in (None, {}):
        raise Unsupported('unreal.fx has no external native inputs')
    root = Path(checkout)
    producer = _check(rows)
    roster = sprites(root)
    needed = {texture for _, texture in SPRITES.values()} | {texture for _, texture in INSTANCES.values()} | {TRAIL[1]}
    if not needed <= set(roster):
        raise Unsupported('original FX materials name sprites the generator does not declare')
    native_code = _code(root)
    from atelier.source_imports import ImportScanner
    found = ImportScanner().local_imports(root / SCRIPT, (root / 'platform/studio', root / GAME / 'world'))
    code = sorted({*native_code, SCRIPT, ORIGINAL, *(p.relative_to(root).as_posix() for p in found)})
    units, staged, slots, packages, refs = [], {}, {}, {}, {}
    def append(unit):
        units.append(unit)
        staged[unit['id']] = {row['name']: 'inputs/' + row['name'] for row in unit['inputs']}
        slots.update({row['name']: False for row in unit['inputs']})
    def item(name, unit, item_id):
        return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}
    for sprite in roster:
        name = 'T_FX_' + sprite
        raw_package, package = '/Game/_Raw/FX/Textures/' + name, TEXTURES + name
        raw_id, finish_id = 'unreal.fx.texture.raw.' + name, 'unreal.fx.texture.' + name
        append({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': native_code,
                'inputs': [item('source', producer['id'], 'product0')],
                'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package,
                           'source_member': name + '.png',
                           'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar', 'name': 'source'}}},
                'outputs': [_output(raw_package, raw=True)]})
        append({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': native_code,
                'inputs': [item('raw', raw_id, 'raw_texture')],
                'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                           'package_sources': {'raw': raw_package}, 'properties': dict(TEXTURE_PROPERTIES)},
                'outputs': [_output(package, raw=False)]})
        refs[package] = packages[package] = {'unit': finish_id, 'item': 'texture', 'package': package}
    def material(name, cls, args, dependencies):
        package = DEST + '/' + name
        closure = []
        for dependency in dependencies:
            for row in [*packages[dependency].get('dependencies', ()), dict(refs[dependency])]:
                if row not in closure:
                    closure.append(row)
        inputs, bound = [], {}
        for index, row in enumerate(closure):
            slot = 'native' + str(index)
            inputs.append(item(slot, row['unit'], row['item']))
            bound[slot] = row['package']
        output = _output(package, raw=False)
        output.update(id='asset', **{'class': cls})
        unit_id = 'unreal.fx.material.' + name
        append({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
                'inputs': inputs, 'params': {'args': {**args, 'name': name, 'inputs': bound}, 'settings': []},
                'outputs': [output]})
        refs[package] = {'unit': unit_id, 'item': 'asset', 'package': package}
        packages[package] = {**refs[package], 'dependencies': closure}
    for name, (blend, sprite) in SPRITES.items():
        material(name, 'Material', {'action': 'sprite', 'blend': blend, 'texture': TEXTURES + 'T_FX_' + sprite},
                 [TEXTURES + 'T_FX_' + sprite])
    material(TRAIL[0], 'Material', {'action': 'trail', 'texture': TEXTURES + 'T_FX_' + TRAIL[1]},
             [TEXTURES + 'T_FX_' + TRAIL[1]])
    for name, (parent, sprite) in INSTANCES.items():
        material(name, 'MaterialInstance', {'action': 'instance', 'parent': DEST + '/' + parent,
                                            'texture': TEXTURES + 'T_FX_' + sprite},
                 [DEST + '/' + parent, TEXTURES + 'T_FX_' + sprite])
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': {'unreal.fx': tuple(unit['id'] for unit in units)}}
