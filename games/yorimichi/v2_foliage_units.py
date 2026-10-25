"""Author C3 foliage RawImport, crown and Finish units for the 18 fixed foliage owners.

The static LOD roster comes from each owner's committed spec through the original
``foliage_source_products.definition_rows`` (mesh levels and the far crown; the seed
export is only an obsolete import slot template). Each raw import consumes its exact
``world.foliage.export.<key>`` Item (one FBX plus its public export receipt) and stays
store-only; the raw FBX options equal ``Scripts/mesh_import.py``. One keyed
``world/foliage_finish_v2.py`` Finish per owner consumes every raw LOD Item, the
assembled ``world.foliage.<owner>`` manifest Item, the shared ``MI_<slot>`` palette and,
for trees, its far crown MaterialInstance, and owns the base and LOD packages.
Shared native packages (``MI_<slot>``, ``M_Painted``, ``T_white``) are other units'
Items; callers pass them as ``natives`` {package: {unit, item}}.
"""
import importlib.util
import json
from pathlib import Path
import sys

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
EXPORTS = 'build/yorimichi/exports/world.foliage.export'
FINISH = GAME + '/world/foliage_finish_v2.py'
HELPERS = GAME + '/unreal/Scripts/foliage_material.py'
PARENT, WHITE = '/Game/Japan/Materials/M_Painted', '/Game/Japan/Textures/T_white'


def _module(name, path):
    spec = importlib.util.spec_from_file_location('v2_foliage_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def roster(checkout):
    """{owner: {chain: [(key, level)], materials, crown}} from committed specs only."""
    world = str(Path(checkout) / GAME / 'world')
    sys.path.insert(0, world)
    try:
        catalog = _module('catalog', Path(world) / 'asset_catalog.py')
        materials = _module('materials', Path(world) / 'material_specs.py')
        products = _module('products', Path(checkout) / GAME / 'foliage_source_products.py')
    finally:
        sys.path.remove(world)
    result = {}
    for owner in catalog.FOLIAGE:
        spec = json.loads((catalog.SPEC_ROOT / (owner + '.json')).read_text())
        rows, policy = products.definition_rows(owner, spec, materials.MATERIALS)
        chain = policy['levels']
        if (len(chain) != len(policy['screen_sizes']) or policy['keys'] != chain + [owner + '_Seed']
                or [rows[key]['mode'] for key in chain] != ['mesh'] * len(spec['screen_sizes'])
                + ['crown'] * policy['crown']):
            raise Unsupported(f'{owner}: unexpected foliage source rows')
        result[owner] = {'chain': [(key, level) for level, key in enumerate(chain)],
                         'materials': list(rows[owner]['material_order']), 'crown': policy['crown']}
    return result


def _output(item, package, cls, *, store):
    stem = package.removeprefix('/Game/')
    files = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = GAME + '/unreal/Content/' + stem + suffix
        files.append(row)
    return {'id': item, 'logical_path': package, 'class': cls, 'destination': 'store' if store else 'checkout',
            'files': files}


def _row(rows, unit, path, script):
    row = rows.get(unit)
    if row is None:
        raise Unsupported(f'missing source row {unit}')
    products = row['products']
    if len(products) != 1 or products[0]['optional_paths'] or products[0]['paths'] != [path]:
        raise Unsupported(f'{unit}: source must own exactly its single folder ROOT')
    commands = row['commands']
    if len(commands) != 1 or commands[0].get('script') != {'path': script}:
        raise Unsupported(f'{unit}: command differs from the original declared body')
    return row


def _native(natives, package):
    ref = natives.get(package)
    if not isinstance(ref, dict) or set(ref) != {'unit', 'item'} or not all(
            isinstance(ref[key], str) and ref[key] for key in ref):
        raise Unsupported(f'missing exact native Item for {package}')
    return {'kind': 'item', **ref}


def _root(owner):
    return {'manifest': {'archive_member': 'products/0-0.tree.tar', 'name': owner}}


def foliage_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] authored-c3-foliage-units
    Every fixed mesh LOD and far crown of every foliage owner MUST become one
    independent store-only RawImport consuming its exact export Item with the
    original FBX options. One keyed Finish per owner MUST consume exactly its raw LOD
    Items, its assembled manifest Item, its shared MI_<slot> palette and its crown
    MaterialInstance, and own the stable base and LOD packages. The roster MUST come
    from committed source specs, never a generated-folder scan; a missing native
    Item or reshaped source row refuses.
    """
    by_id = {row['id']: row for row in rows}
    if len(by_id) != len(rows):
        raise Unsupported('duplicate source row')
    owners = roster(checkout)
    code = _code(checkout)
    body = sorted({*code, FINISH, HELPERS})
    units, staged, slots, packages = [], {}, {}, {}
    def add(unit, inputs):
        units.append(unit)
        staged[unit['id']] = {name: 'inputs/' + name for name in inputs}
        slots.update({name: False for name in inputs})
    for owner, entry in owners.items():
        manifest_row = _row(by_id, 'world.foliage.' + owner, f'build/yorimichi/foliage/{owner}',
                            GAME + '/foliage_source_products.py')
        if manifest_row['products'][0]['id'] != f'foliage.{owner}.source':
            raise Unsupported(f'{owner}: assembled foliage product differs')
        manifest = {'role': 'content', 'name': 'manifest',
                    'source': {'kind': 'item', 'unit': manifest_row['id'], 'item': 'product0'}}
        folder = '/Game/Japan/FoliageLODs/' + owner
        base = '/Game/Japan/Assets/' + owner
        raws = []
        for key, level in entry['chain']:
            row = _row(by_id, 'world.foliage.export.' + key, f'{EXPORTS}/{key}', GAME + '/world/export_foliage_piece.py')
            command = row['commands'][0]
            if command.get('kind') != 'blender' or command.get('args', [])[-2:] != ['--format', '.fbx']:
                raise Unsupported(f'{key}: export command differs from the original FBX body')
            unit_id = 'unreal.foliage.raw.' + key
            package = f'/Game/_Raw/Foliage/{owner}/{key}'
            add({'id': unit_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': list(code),
                 'inputs': [{'role': 'content', 'name': 'source',
                             'source': {'kind': 'item', 'unit': row['id'], 'item': 'product0'}}],
                 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': package,
                            'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar', 'name': key}}},
                 'outputs': [_output('raw_static_mesh', package, 'RawStaticMesh', store=True)]}, ['source'])
            packages[package] = {'unit': unit_id, 'item': 'raw_static_mesh', 'owner': owner, 'key': key, 'level': level}
            raws.append((unit_id, level))
        inputs = [manifest]
        inputs += [{'role': 'content', 'name': f'lod{level}',
                    'source': {'kind': 'item', 'unit': unit_id, 'item': 'raw_static_mesh'}} for unit_id, level in raws]
        materials = {}
        for key in entry['materials']:
            inputs.append({'role': 'content', 'name': 'material_' + key,
                           'source': _native(natives, '/Game/Japan/Materials/MI_' + key)})
            materials[key] = 'material_' + key
        crown = None
        if entry['crown']:
            crown_id, crown = 'unreal.foliage.crown.' + owner, 'crown'
            crown_package = f'{folder}/MI_{owner}_Crown'
            crown_inputs = [manifest, {'role': 'content', 'name': 'parent', 'source': _native(natives, PARENT)},
                            {'role': 'content', 'name': 'white', 'source': _native(natives, WHITE)}]
            add({'id': crown_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': body,
                 'inputs': crown_inputs,
                 'params': {'op': 'crown', 'input_roots': _root(owner),
                            'args': {'owner': owner, 'manifest': 'manifest', 'parent': 'parent', 'white': 'white'}},
                 'outputs': [_output('material', crown_package, 'MaterialInstance', store=False)]},
                [item['name'] for item in crown_inputs])
            packages[crown_package] = {'unit': crown_id, 'item': 'material', 'owner': owner}
            inputs.append({'role': 'content', 'name': 'crown',
                           'source': {'kind': 'item', 'unit': crown_id, 'item': 'material'}})
        finish_id = 'unreal.foliage.finish.' + owner
        outputs = [_output('static_mesh', base, 'StaticMesh', store=False)]
        outputs += [_output(f'lod{level}', f'{folder}/{owner}_LOD{level}', 'StaticMesh', store=False)
                    for _, level in raws[1:]]
        add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH, 'code': body,
             'inputs': inputs,
             'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'lod0', 'destination': base,
                        'input_roots': _root(owner),
                        'args': {'owner': owner, 'manifest': 'manifest', 'levels': [f'lod{level}' for _, level in raws],
                                 'materials': materials, 'crown': crown}},
             'outputs': outputs}, [item['name'] for item in inputs])
        for output in outputs:
            packages[output['logical_path']] = {'unit': finish_id, 'item': output['id'], 'owner': owner}
    return {'units': units, 'staged': staged, 'slots': slots, 'packages': packages}
