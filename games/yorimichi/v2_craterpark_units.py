"""Cold CraterPark FileSet exports and per-package native owners, without generated host scans."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code, _output as texture_output

GAME = 'games/yorimichi'
BODY = GAME + '/world/craterpark_members_v2.py'
FINISH = GAME + '/world/craterpark_finish_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_craterpark.py'
PLANNER = GAME + '/world/regions/craterpark/v2/plan_asset.py'
CATALOGUE = GAME + '/assets/craterpark/materials.json'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
ROOT = '/Game/CraterPark'
KINDS = ('Textured', 'Lacquer', 'World', 'Flat', 'Steel')


def _call(root, name, defaults):
    spec = importlib.util.spec_from_file_location('craterpark_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    function = getattr(module, name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _incoming(slot, owner, item):
    return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}}


def token(kind, *, follower=None, item='asset'):
    return {'derived_items': {'root': 'build/v2-derived/craterpark/' + kind, 'templates': [
        {'producer': 'world.craterpark.members.' + kind, 'group': 'members',
         'unit_prefix': 'world.craterpark.selected.' + kind, 'item': item,
         **({'follower': follower} if follower is not None else {})}]}}


def attach_followers(geometry, *, rows, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] craterpark-cold-selected-native-owners
    Membership MUST come from actual source_inputs/restyle Items, verified before
    FileSet publication. Raw/finish MUST consume expanded selected child Items,
    preserve original material/mesh policy and own one package with all sidecars.
    The original source library's runtime/report/FBX products MUST retain a real
    assembler owner: source_join is a required provider join, never a success alias.
    Generated host inventory, old native receipts and whole import main MUST NOT run.
    """
    root = Path(checkout).resolve(); by_id = {row['id']: row for row in rows}
    source = by_id.get('world.craterpark.inputs'); importer = by_id.get('unreal.craterpark')
    if (not source or len(source['products']) != 1
            or source['products'][0] != {'id': 'craterpark.source_inputs', 'paths': ['build/yorimichi/craterpark-inputs'], 'optional_paths': []}
            or not importer or len(importer['commands']) != 1
            or importer['commands'][0].get('kind') != 'UnrealScript'
            or importer['commands'][0].get('script') != {'path': ORIGINAL}):
        raise Unsupported('CraterPark requires its original canonical source Product and native script')
    restyle = by_id.get('world.craterpark_restyle')
    if not restyle or restyle['outputs'] != ['build/yorimichi/craterpark/textures']:
        raise Unsupported('CraterPark restyle must own its complete textures ROOT')
    original_source = by_id.get('world.craterpark')
    if not original_source or not any(p['id'] == 'craterpark.library' and p['paths'] == [
            'build/yorimichi/craterpark/fbx', 'build/yorimichi/craterpark/build.json', 'build/yorimichi/craterpark/park.json']
            and not p['optional_paths'] for p in original_source['products']):
        raise Unsupported('CraterPark complete source library ownership differs')
    imports = (root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions')
    scanner = ImportScanner()
    def closure(paths):
        result = set(paths)
        for path in paths:
            result.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / path, imports))
        return sorted(result)
    recipe_code = closure([BODY, RECIPE, PLANNER])
    native_code = sorted(set(_code(root)) | set(closure([FINISH, BODY])) | {ORIGINAL, GAME + '/world/regions/megapark/verify_import.py'})
    result = {'geometry': deepcopy(geometry), 'units': [], 'staged_inputs': {}, 'content_slots': {},
              'packages': {}, 'aliases': {}, 'module_requirements': {}, 'templates': [], 'groups': {}}
    units, packages = result['units'], result['packages']
    modules = _modules(root, [])[0]
    def add(unit, inputs):
        unit['inputs'] = inputs; units.append(unit)
        result['staged_inputs'][unit['id']] = {i['name']: ('inputs/catalogue/materials.json' if i['name'] == 'catalogue' else 'inputs/' + i['name']) for i in inputs}
        result['content_slots'].update({i['name']: False for i in inputs})
        if unit['op']['kind'].startswith('unreal.'):
            result['module_requirements'][unit['id']] = modules
    def reference(package, owner, item, dependencies=()):
        packages[package] = {'unit': owner, 'item': item, 'package': package, 'dependencies': deepcopy(list(dependencies))}
    for kind in ('render', 'collision', 'seed', 'textures'):
        producer = 'world.craterpark.members.' + kind; folder = 'generated/craterpark/' + kind
        texture = kind == 'textures'; archive = 'outputs/0.tree.tar' if texture else 'products/0-0.tree.tar'
        owner, item = ('world.craterpark_restyle', 'output0') if texture else ('world.craterpark.inputs', 'product0')
        incoming = _incoming('source', owner, item)
        incoming['whole'] = 'The complete canonical inventory and all consumed packet/pixel digests validate before membership selection.'
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': 'CraterPark_' + kind, 'encoding': 'file_set',
                    'class': 'Data', 'logical_namespace': '/Internal/CraterPark/' + kind, **LIMITS}
        add({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code,
             'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': {'source': 'inputs/source/' + archive},
                'verify': None, 'commands': [_call(root, 'project', (root / 'source', root / folder, kind))],
                'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                'file_group': {'source': folder, 'parent': 'CraterPark_' + kind, 'extensions': ['.png' if texture else '.npz']}}},
             'outputs': [{'id': 'archive', 'logical_path': '/Internal/CraterPark/' + kind, 'class': 'Data',
                          'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
             'output_groups': [contract]}, [incoming])
        result['groups'][producer] = {'contract': contract, 'source': folder}
    texture_token = token('textures', follower=1, item='texture')
    raw_texture = '/Game/_Raw/CraterPark/Textures/T_CP_$piece'; texture = ROOT + '/Textures/T_CP_$piece'
    raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
           'inputs': [_incoming('source', '$export', 'asset')], 'params': {'op': 'raw_import', 'kind': 'texture',
               'source': 'source', 'source_member': '$piece.png', 'destination': raw_texture,
               'input_roots': {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}},
           'outputs': [texture_output(raw_texture, raw=True)]}
    finished = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': _code(root),
        'inputs': [_incoming('raw', '$previous', 'raw_texture')],
        'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': texture,
                   'properties': {'srgb': True, 'compression_settings': {'unreal_enum': 'TextureCompressionSettings.TC_DEFAULT'},
                                  'address_x': {'unreal_enum': 'TextureAddress.TA_WRAP'}, 'address_y': {'unreal_enum': 'TextureAddress.TA_WRAP'}}},
        'outputs': [texture_output(texture, raw=False)]}
    def template(kind, outputs, command, followers):
        prefix = 'world.craterpark.selected.' + kind
        value = {'producer': 'world.craterpark.members.' + kind, 'group': 'members', 'unit_prefix': prefix,
            'op': {'kind': 'recipe.blender' if kind != 'textures' else 'recipe.python', 'version': '1'},
            'script': RECIPE, 'code': recipe_code, 'derive_payload': False, 'payload_slot': 'selected',
            'staged_path': 'inputs/selected', 'output_class': 'Data', 'logical_namespace': '/Internal/CraterPark/Selected/' + kind,
            'files': [{'path': path + '.tree.tar', 'required': True} for path in outputs],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/selected'}, 'verify': None,
                'commands': [command], 'outputs': [{'kind': 'tree', 'path': path, 'file': path + '.tree.tar', 'required': True} for path in outputs]}},
            'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}} for unit in followers]}
        result['templates'].append(value); result['module_requirements'][prefix] = modules
    template('textures', ('member',), _call(root, 'select_texture', (root / 'selected', root / 'member', '$piece')), [raw, finished])
    parents = {}
    for kind in KINDS:
        owner = 'unreal.craterpark.parent.' + kind; package = ROOT + '/Materials/M_CP_' + kind
        add({'id': owner, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': native_code,
             'params': {'args': {'action': 'parent', 'kind': kind}, 'settings': []}, 'outputs': [_output('asset', package, 'Material')]}, [])
        reference(package, owner, 'asset'); parents[kind] = packages[package]
    specs = json.loads((root / CATALOGUE).read_bytes())
    if not isinstance(specs, list) or len({s['id'] for s in specs}) != len(specs):
        raise Unsupported('CraterPark committed material roster is invalid')
    material_slots = {}
    for spec in [*specs, {'id': 'coping_steel'}]:
        coping = spec['id'] == 'coping_steel'; package = ROOT + '/Materials/MI_CP_' + spec['id']
        owner = 'unreal.craterpark.material.' + spec['id']
        incoming = [_incoming('parent' + kind, ref['unit'], ref['item']) for kind, ref in parents.items()]
        if not coping:
            incoming += [_incoming('restyle', 'world.craterpark_restyle', 'output0'),
                         {'role': 'content', 'name': 'catalogue', 'source': {'kind': 'file', 'path': CATALOGUE}}]
        add({'id': owner, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': native_code,
             'params': {'args': {'action': 'instance', 'spec': spec, 'coping': coping,
                 'parents': {k: 'parent' + k for k in KINDS}, 'textures': deepcopy(texture_token)}, 'settings': [],
                 **({} if coping else {'input_roots': {'restyle': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}}})},
             'outputs': [_output('asset', package, 'MaterialInstance')]}, incoming)
        reference(package, owner, 'asset', parents.values()); packages[package]['derived_dependencies'] = {'textures': deepcopy(texture_token)}
        material_slots[spec['id']] = 'material' + str(len(material_slots))
    native_inputs = []; seen = set()
    def dependency(ref):
        key = (ref['unit'], ref['item'])
        if key in seen:
            return
        seen.add(key)
        for child in ref.get('dependencies', []):
            dependency(child)
        slot = material_slots.get(ref['package'].rsplit('MI_CP_', 1)[-1], 'native' + str(len(native_inputs)))
        native_inputs.append(_incoming(slot, ref['unit'], ref['item']))
    for path, ref in {**(natives or {}), **packages}.items():
        if path.startswith(ROOT + '/Materials/'):
            dependency(ref)
    for kind in ('render', 'collision', 'seed'):
        followers = []
        if kind != 'seed':
            collision = kind == 'collision'; raw_package = '/Game/_Raw/CraterPark/Meshes/$piece'; package = ROOT + '/Meshes/$piece'
            raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
                'inputs': [_incoming('source', '$export', 'asset')], 'params': {'op': 'raw_import', 'kind': 'static_mesh',
                    'source': 'source', 'source_member': '$piece.fbx', 'destination': raw_package,
                    'input_roots': {'source': {'archive_member': 'export.tree.tar', 'name': 'export'}},
                    'fbx': {'remove_degenerates': False, 'vertex_color_import_option':
                            {'unreal_enum': 'VertexColorImportOption.' + ('IGNORE' if collision else 'REPLACE')}},
                    'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
                'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]}
            finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH, 'code': native_code,
                'inputs': [_incoming('raw', '$previous', 'raw'), *[_incoming(slot, '$export', 'asset') for slot in ('source_export', 'payload', 'metadata')], *deepcopy(native_inputs)],
                'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                    'input_roots': {slot: {'archive_member': path + '.tree.tar', 'name': path} for slot, path in
                                    (('source_export', 'export'), ('payload', 'payload'), ('metadata', 'metadata'))},
                    'args': {'action': 'mesh', 'piece': '$piece', 'collision': collision, 'source_export': 'source_export',
                             'payload': 'payload', 'metadata': 'metadata', 'materials': dict(material_slots), 'textures': deepcopy(texture_token)},
                    'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                'outputs': [_output('asset', package, 'StaticMesh'), *[
                    {'id': label, 'logical_path': '/Internal/CraterPark/' + label + '/$piece', 'class': 'Data', 'destination': 'store',
                     'files': [{'path': 'data/' + folder + '/$piece.' + extension, 'required': True}]}
                    for label, folder, extension in (('geometry', 'geometry', 'bin'), ('report', 'reports', 'json'))]]}
            followers = [raw, finish]
        template(kind, ('export', 'payload', 'metadata'), _call(root, 'export_packet',
            (root / 'selected', root / 'export', root / 'payload', root / 'metadata', '$piece', root / PLANNER)), followers)
    library_index = next(i for i, product in enumerate(original_source['products']) if product['id'] == 'craterpark.library')
    folder = 'generated/craterpark/native-summary'
    gate = {'id': 'unreal.craterpark.complete', 'op': {'kind': 'recipe.python', 'version': '1'},
        'script': RECIPE, 'code': recipe_code,
        'params': {'recipe': {'version': 1, 'paths': {'build-library': 'inputs/library/products/' + str(library_index) + '-1.tree.tar'},
            'verify': None, 'commands': [_call(root, 'native_summary', (root / 'build-library',
                token('render', follower=1, item='report'), token('collision', follower=1, item='report'), root / folder))],
            'outputs': [{'kind': 'tree', 'path': folder, 'file': 'summary.tree.tar', 'required': True}]}},
        'outputs': [{'id': 'summary', 'logical_path': '/Internal/CraterPark/NativeSummary', 'class': 'Data', 'destination': 'store',
            'files': [{'path': 'summary.tree.tar', 'required': True}]}]}
    add(gate, [_incoming('library', 'world.craterpark', 'product' + str(library_index))])
    result['aliases']['unreal.craterpark'] = [gate['id'], *(unit['id'] for unit in units if unit['op']['kind'].startswith('unreal.'))]
    result['mesh_items'] = {kind: token(kind, follower=1) for kind in ('render', 'collision')}
    result['source_join'] = {'owner': 'world.craterpark', 'product': 'craterpark.library',
        'required': True, 'source': {'unit': 'world.craterpark.inputs', 'item': 'product0'},
        'selected_exports': {kind: token(kind) for kind in ('render', 'collision', 'seed')},
        'paths': ['build/yorimichi/craterpark/fbx', 'build/yorimichi/craterpark/build.json', 'build/yorimichi/craterpark/park.json'],
        'assembler': GAME + '/world/regions/craterpark/v2/assemble.py'}
    result['geometry']['templates'] = [t for t in result['geometry'].get('templates', [])
        if not t['producer'].startswith('world.craterpark.geometry.')]
    result['geometry']['templates'] += deepcopy(result['templates'])
    result['geometry'].setdefault('groups', {}).update(deepcopy(result['groups']))
    return result
