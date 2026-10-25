"""Cold Belmonte train Item -> finite source groups -> per-package native owners.

The library and service Items are bound from actual extracted recipe rows. No
completed build directory is inspected by this constructor. Sparse material and
texture dependencies currently use conservative explicit derived content closures;
this preserves correctness but does not claim selective material invalidation.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/train_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_belmonte_train.py'
BAKE = GAME + '/world/train/bake_manifest.py'
OUT = 'build/yorimichi/belmonte-train'
DEST = '/Game/BelmonteTrain'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
SETTINGS = ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0,Editor.AsyncStaticMeshCompilation=0']
KINDS = ('images', 'materials', 'vehicles', 'doors', 'furniture1', 'furniture2', 'record')


def _call(root, function, defaults):
    spec = importlib.util.spec_from_file_location('train_v2_declaration', root / SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fn = getattr(module, function); fn.__defaults__ = tuple(defaults)
    row = extract([Step('train.body', [Call(function, fn)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(slot, unit, item):
    return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': unit, 'item': item}}


def token(kind, follower, item):
    return {'derived_items': {'root': 'build/v2-derived/train/' + kind, 'templates': [
        {'producer': 'train.members.' + kind, 'group': 'members', 'unit_prefix': 'unreal.belmonte_train.' + kind,
         'follower': follower, 'item': item}]}}


def _sources(rows):
    by_id = {r['id']: r for r in rows}
    importer = by_id.get('unreal.belmonte_train')
    commands = (importer or {}).get('commands') or [{}]
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('marker') != 'BELMONTE TRAIN IMPORT COMPLETE'
            or commands[0].get('args') != ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0']
            or commands[0].get('env') or importer.get('products')
            or importer['outputs'] != [GAME + '/unreal/Content/Data/belmonte_train/service.json', OUT + '/service/import-report.json']):
        raise Unsupported('unreal.belmonte_train differs from the selected original importer')
    library = by_id.get('world.belmonte_train'); service = by_id.get('world.belmonte_train_service')
    bake = by_id.get('world.belmonte_train_furniture_lods')
    if not library or not service or not bake:
        raise Unsupported('Train requires actual library, service and furniture bake declarations')
    indices = [i for i, p in enumerate(library['products']) if p['id'] == 'belmonte_train.library']
    if len(indices) != 1: raise Unsupported('Train requires its actual library Product')
    index = indices[0]; product = library['products'][index]
    if product['optional_paths'] or not {OUT + '/manifest.json', OUT + '/furniture/canteen-pot.glb'} <= set(product['paths']):
        raise Unsupported('Train library lost required original sources')
    if service['outputs'] != [OUT + '/service/service.json', OUT + '/service/glb']:
        raise Unsupported('Train service outputs differ from original')
    if not bake['outputs'] or bake['outputs'][0] != OUT + '/furniture/lod/summary.json':
        raise Unsupported('Train bake must expose its summary and all baked levels')
    inputs = [_item('library', library['id'], f'product{index}')]
    inputs[0]['whole'] = 'Complete original train library is validated before narrow source members are published.'
    paths = {path: f'inputs/library/products/{index}-{j}.tree.tar' for j, path in enumerate(product['paths'])}
    for label, row in [('service', service), ('bake', bake)]:
        for j, path in enumerate(row['outputs']):
            slot = f'{label}{j}'; inputs.append(_item(slot, row['id'], f'output{j}'))
            paths[path] = f'inputs/{slot}/outputs/{j}.tree.tar'
    return inputs, paths


def train_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] cold-train-package-declarations
    Actual original library/service/bake Items MUST feed keyed pure projections.
    Every native saved package MUST have one declared owner; meshes, textures and
    materials MUST consume the validated selected member, never ambient Content or
    invented future child IDs. The original import main MUST NOT execute.
    """
    root = Path(checkout).resolve(); source_inputs, paths = _sources(rows)
    roots = (root / 'platform/studio', root / GAME / 'world', root / GAME / 'unreal/Scripts')
    scanner = ImportScanner()
    recipe_code = {SCRIPT, BAKE, GAME + '/world/train/budgets.py'}
    for path in (SCRIPT, BAKE, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / path, roots))
    native_code = sorted({*_code(root), SCRIPT, ORIGINAL})
    units, staged, groups, templates, packages, requirements = [], {}, {}, [], {}, {}
    editor = _modules(root, [])[0]
    def add(unit):
        units.append(unit); staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}
        # Only the vehicle finish calls the project's BelmonteTrainImportLibrary.
    for kind in KINDS:
        producer = 'train.members.' + kind; folder = 'generated/train/' + kind
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': 'Train_' + kind, 'encoding': 'file_set',
                    'class': 'Data', 'logical_namespace': '/Internal/Train/' + kind, **LIMITS}
        add({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': sorted(recipe_code),
             'inputs': deepcopy(source_inputs), 'params': {'file_root': 'output/files', 'recipe': {
                 'version': 1, 'paths': dict(paths), 'verify': None,
                 'commands': [_call(root, 'project', (root / OUT, root / BAKE, root / folder, kind))],
                 'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                 'file_group': {'source': folder, 'parent': 'Train_' + kind, 'extensions': ['.json']}}},
             'outputs': [{'id': 'archive', 'logical_path': '/Internal/Train/' + kind, 'class': 'Data', 'destination': 'store',
                          'files': [{'path': 'members.tree.tar', 'required': True}]}], 'output_groups': [contract]})
        groups[producer] = {'contract': contract, 'source': folder}
    def template(kind, followers):
        templates.append({'producer': 'train.members.' + kind, 'group': 'members',
            'unit_prefix': 'unreal.belmonte_train.' + kind, 'op': {'kind': 'recipe.python', 'version': '1'},
            'script': RECIPE, 'code': sorted(recipe_code), 'derive_payload': False,
            'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
            'logical_namespace': '/Internal/Train/Selected/' + kind, 'files': [{'path': 'selected.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece'))],
                'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'selected.tree.tar', 'required': True}]}},
            'followers': [{'unit': u, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in u['inputs']}} for u in followers]})
        if kind == 'vehicles':
            requirements['unreal.belmonte_train.' + kind] = editor
    selected = {'archive_member': 'selected.tree.tar', 'name': 'selected'}
    raw_texture, texture = '/Game/_Raw/BelmonteTrain/T_$piece', DEST + '/Textures/T_$piece'
    template('images', [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
         'inputs': [_item('source', '$export', 'asset')],
         'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_texture,
                    'source_member': 'image', 'input_roots': {'source': dict(selected)}, 'settings': SETTINGS}, 'outputs': [_output('raw_texture', raw_texture, 'RawTexture', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': native_code,
         'inputs': [_item('raw', '$previous', 'raw_texture'), _item('meta', '$export', 'asset')],
         'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': texture,
                    'input_roots': {'meta': dict(selected)}, 'args': {'action': 'texture', 'meta': 'meta'}, 'settings': SETTINGS},
         'outputs': [_output('texture', texture, 'Texture')]}])
    template('materials', [
        {'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': native_code,
         'inputs': [_item('meta', '$export', 'asset')],
         'params': {'input_roots': {'meta': dict(selected)}, 'args': {'action': 'material', 'name': '$piece', 'meta': 'meta',
                    'images': token('images', 1, 'texture')}, 'settings': SETTINGS},
         'outputs': [_output('asset', DEST + '/Materials/MI_$piece', 'MaterialInstance'),
                     _output('parent', DEST + '/Materials/M_$piece', 'Material')]}])
    for kind, folder, count in [('vehicles', '', 3), ('doors', '/Doors', 1), ('furniture1', '/Furniture', 1), ('furniture2', '/Furniture', 2)]:
        followers = []
        for level in range(count):
            raw = '/Game/_Raw/BelmonteTrain/' + kind + '/$piece_LOD' + str(level)
            followers.append({'id': '$export.raw' + str(level), 'op': {'kind': 'unreal.raw_import', 'version': '1'},
                'script': OPS, 'code': _code(root), 'inputs': [_item('source', '$export', 'asset')],
                'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw,
                           'source_member': f'level{level}/source.glb', 'input_roots': {'source': dict(selected)}, 'settings': SETTINGS},
                'outputs': [_output('raw_mesh', raw, 'RawStaticMesh', store=True)]})
        destination = DEST + folder + '/$piece'
        followers.append({'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
            'code': native_code, 'inputs': [_item('meta', '$export', 'asset'),
                *(_item(f'level{level}', '$export.raw' + str(level), 'raw_mesh') for level in range(count))],
            'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'level0', 'destination': destination,
                'input_roots': {'meta': dict(selected)}, 'args': {'action': 'mesh', 'name': '$piece', 'meta': 'meta',
                    'levels': ['level' + str(i) for i in range(count)], 'materials': token('materials', 0, 'asset'),
                    'parents': token('materials', 0, 'parent'), 'images': token('images', 1, 'texture')}, 'settings': SETTINGS},
            'outputs': [_output('mesh', destination, 'StaticMesh')]})
        template(kind, followers)
    board = 'unreal.belmonte_train.board'
    add({'id': board, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': native_code,
         'inputs': [], 'params': {'args': {'action': 'board'}, 'settings': SETTINGS},
         'outputs': [_output('asset', DEST + '/Materials/M_BT_BoardText', 'Material')]})
    packages[DEST + '/Materials/M_BT_BoardText'] = {'unit': board, 'item': 'asset', 'package': DEST + '/Materials/M_BT_BoardText'}
    mesh_tokens = {'derived_items': {'root': 'build/v2-derived/train/record', 'templates': [
        token(kind, count, 'mesh')['derived_items']['templates'][0]
        for kind, count in [('vehicles', 3), ('doors', 1), ('furniture1', 1), ('furniture2', 2)]]}}
    add({'id': 'train.record.selected', 'op': {'kind': 'recipe.python', 'version': '1'},
         'script': RECIPE, 'code': sorted(recipe_code),
         'inputs': [{'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member',
                     'unit': 'train.members.record', 'group': 'members', 'piece': 'Record'}}],
         'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                    'commands': [_call(root, 'select', (root / 'selected', root / 'member', 'Record'))],
                    'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'selected.tree.tar', 'required': True}]}},
         'outputs': [{'id': 'selected', 'logical_path': '/Internal/Train/RecordSource', 'class': 'Data',
                      'destination': 'store', 'files': [{'path': 'selected.tree.tar', 'required': True}]}]})
    record_unit = {'id': 'unreal.belmonte_train.record', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
        'code': native_code, 'inputs': [_item('meta', 'train.record.selected', 'selected'), _item('board', board, 'asset')],
        'params': {'input_roots': {'meta': dict(selected)}, 'args': {'action': 'record', 'meta': 'meta', 'meshes': mesh_tokens, 'materials': token('materials', 0, 'asset'),
                    'parents': token('materials', 0, 'parent'), 'images': token('images', 1, 'texture')}, 'settings': SETTINGS},
        'outputs': [{'id': 'service', 'logical_path': '/Game/_Data/belmonte_train/service', 'class': 'JsonData', 'destination': 'checkout',
                     'files': [{'path': 'data/service.json', 'install_path': GAME + '/unreal/Content/Data/belmonte_train/service.json', 'required': True}]},
                    {'id': 'report', 'logical_path': '/Internal/Train/Report', 'class': 'JsonData', 'destination': 'store',
                     'files': [{'path': 'data/import-report.json', 'required': True}]}]}
    service_unit = deepcopy(record_unit)
    service_unit['id'] = 'unreal.belmonte_train.service'
    service_unit['outputs'] = [record_unit['outputs'][0]]
    service_unit['params']['args']['field'] = 'service'
    record_unit['outputs'] = [record_unit['outputs'][1]]
    record_unit['params']['args']['field'] = 'report'
    add(service_unit); add(record_unit)
    packages[GAME + '/unreal/Content/Data/belmonte_train/service.json'] = {'unit': service_unit['id'], 'item': 'service'}
    packages[OUT + '/service/import-report.json'] = {'unit': record_unit['id'], 'item': 'report'}

    return {'units': units, 'staged_inputs': staged,
        'content_slots': {i['name']: False for u in units for i in u['inputs']} | {'source': False, 'raw': False, 'meta': False,
                         'level0': False, 'level1': False, 'level2': False, 'board': False},
        'packages': packages, 'aliases': {'unreal.belmonte_train': tuple([board, 'unreal.belmonte_train.service', 'unreal.belmonte_train.record'])},
        'module_requirements': requirements, 'templates': templates, 'groups': groups}
