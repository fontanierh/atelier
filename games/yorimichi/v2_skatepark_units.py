"""Sunset Pier native owners over existing validated park/board D2 templates."""
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
from v2_mega_units import FBX
from v2_texture_units import OPS, Unsupported, _code, _output as texture_output

GAME = 'games/yorimichi'
BODY = GAME + '/world/skatepark_members_v2.py'
FINISH = GAME + '/world/skatepark_finish_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_skatepark.py'
LOGICAL = GAME + '/world/regions/skatepark/park.json'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
ROOT = '/Game/SkatePark'
VILLAGE = '/Game/Japan/Materials/M_Village'
PARK = ('SM_SkatePier', 'SM_SkatePierPilings', 'SM_SkateParkFeatures', 'SM_SkatePath',
        'SM_SkateParkFurniture', 'SM_SkateParkPlanting', 'SM_SkateParkDecals')
BOARD = ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel')
ROLES = ('albedo', 'normal', 'roughness')


def _call(root, name, defaults):
    spec = importlib.util.spec_from_file_location('skatepark_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fn = getattr(module, name); fn.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, fn)])], checkout=root, build_root=root / 'build',
        import_roots=(root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _input(slot, owner, item):
    return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}}


def token(kind, *, follower=0, item='asset'):
    return {'derived_items': {'root': 'build/v2-derived/skatepark/' + kind, 'templates': [
        {'producer': 'world.skatepark.members.' + kind, 'group': 'members',
         'unit_prefix': 'world.skatepark.selected.' + kind, 'follower': follower, 'item': item}]}}


def attach_followers(geometry, *, rows, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] sunset-pier-original-native-owners
    All seven original park and three board parents MUST retain their validated
    template membership. Every finish MUST consume its own export/MeshIR and actual
    native material Items. Sunset Pier maps/specs MUST come from the complete produced
    texture ROOT. Board MUST bind the supplied finished M_Village with its closure.
    Runtime/build/source membership and native trees MUST precede alias completion;
    no old namespace scan, fallback material or importer top level MAY run.
    """
    root = Path(checkout).resolve(); by_id = {row['id']: row for row in rows}
    importer = by_id.get('unreal.skatepark')
    if (not importer or len(importer['commands']) != 1 or importer['commands'][0].get('kind') != 'UnrealScript'
            or importer['commands'][0].get('script') != {'path': ORIGINAL}):
        raise Unsupported('Sunset Pier requires its original targeted native script')
    def product(owner, name, paths):
        row = by_id.get(owner)
        if not row: raise Unsupported('Missing original Sunset Pier source owner: ' + owner)
        matches = [(i, p) for i, p in enumerate(row['products']) if p['id'] == name]
        if len(matches) != 1 or matches[0][1]['paths'] != paths or matches[0][1]['optional_paths']:
            raise Unsupported('Changed complete Sunset Pier source Product: ' + name)
        return matches[0][0]
    texture_index = product('world.skatepark_textures', 'skatepark.textures', ['build/yorimichi/skatepark/textures'])
    meshes_index = product('world.skatepark', 'skatepark.meshes', ['build/yorimichi/skatepark/assets',
        'build/yorimichi/skatepark/board', 'build/yorimichi/skatepark/build-report.json'])
    runtime_index = product('world.skatepark', 'skatepark.runtime', ['build/yorimichi/skatepark/runtime-park.json'])
    product('world.skatepark', 'skatepark.queries', ['build/yorimichi/skatepark/collision.json'])
    if not isinstance(natives, dict) or VILLAGE not in natives:
        raise Unsupported('Board requires its exact supplied finished M_Village Item')
    dependencies = {}
    def dependency(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/')):
            raise Unsupported('Sunset Pier native dependency must name its actual finished owner')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']: raise Unsupported('Aliased Sunset Pier native Item')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives: raise Unsupported('Missing supplied Sunset Pier transitive dependency')
                child = natives[child]
            dependency(child)
        return slot
    village = natives[VILLAGE]
    if village.get('package') != VILLAGE: raise Unsupported('Wrong supplied board material')
    material_slot = dependency(village)
    logical = json.loads((root / LOGICAL).read_bytes())
    blocks = {entry['name']: entry['blocks'] for entry in logical['meshes']}
    if set(blocks) != set(PARK) or any(type(v) is not bool for v in blocks.values()):
        raise Unsupported('Changed original Sunset Pier logical/collision contract')
    for name in logical.get('trees', {}):
        path = '/Game/Japan/Assets/' + name
        if path not in natives or natives[path].get('package') != path:
            raise Unsupported('Missing explicit Sunset Pier runtime tree owner: ' + path)
    imports = (root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions')
    scanner = ImportScanner()
    def closure(paths):
        value = set(paths)
        for source in paths: value.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / source, imports))
        return sorted(value)
    recipe_code = closure([BODY, RECIPE]); native_code = sorted(set(_code(root)) | set(closure([FINISH])) | {ORIGINAL})
    modules = _modules(root, [])[0]
    result = {'geometry': deepcopy(geometry), 'units': [], 'staged_inputs': {}, 'content_slots': {},
              'packages': {}, 'aliases': {}, 'module_requirements': {}, 'groups': {}, 'templates': []}
    def add(unit, incoming):
        unit['inputs'] = incoming; result['units'].append(unit)
        result['staged_inputs'][unit['id']] = {i['name']: 'inputs/' + i['name'] for i in incoming}
        result['content_slots'].update({i['name']: False for i in incoming})
    def wrap(unit):
        return {'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
    textures = {role: token(role, follower=1, item='texture') for role in ROLES}
    materials = token('materials')
    for kind in ('materials', *ROLES):
        producer = 'world.skatepark.members.' + kind; folder = 'generated/skatepark/' + kind
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
            'adapter_version': 'd2.file-set/1', 'parent': 'SkatePark_' + kind, 'encoding': 'file_set', 'class': 'Data',
            'logical_namespace': '/Internal/SkatePark/' + kind, **LIMITS}
        incoming = _input('textures', 'world.skatepark_textures', 'product' + str(texture_index))
        incoming['whole'] = 'The complete produced Sunset Pier texture roster and every PNG digest validate before member selection.'
        add({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code,
            'params': {'file_root': 'output/files', 'recipe': {'version': 1,
                'paths': {'textures': 'inputs/textures/products/' + str(texture_index) + '-0.tree.tar'}, 'verify': None,
                'commands': [_call(root, 'project', (root / 'textures', root / folder, kind))],
                'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                'file_group': {'source': folder, 'parent': 'SkatePark_' + kind, 'extensions': ['.json' if kind == 'materials' else '.png']}}},
            'outputs': [{'id': 'archive', 'logical_path': '/Internal/SkatePark/' + kind, 'class': 'Data', 'destination': 'store',
                'files': [{'path': 'members.tree.tar', 'required': True}]}], 'output_groups': [contract]}, [incoming])
        result['groups'][producer] = {'contract': contract, 'source': folder}
        followers = []
        if kind == 'materials':
            followers = [{'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': native_code,
                'inputs': [_input('spec', '$export', 'asset')], 'params': {'args': {'action': 'material', 'piece': '$piece', 'textures': deepcopy(textures)},
                    'input_roots': {'spec': {'archive_member': 'member.tree.tar', 'name': 'member'}}, 'settings': []},
                'outputs': [_output('asset', ROOT + '/Materials/M_Pier_$piece', 'Material')]}]
        else:
            raw_package = '/Game/_Raw/SkatePark/Textures/T_Pier_$piece'; dest = ROOT + '/Textures/T_Pier_$piece'
            followers = [
                {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
                 'inputs': [_input('source', '$export', 'asset')], 'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source',
                    'source_member': '$piece.png', 'destination': raw_package,
                    'input_roots': {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}},
                 'outputs': [texture_output(raw_package, raw=True)]},
                {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': _code(root),
                 'inputs': [_input('raw', '$previous', 'raw_texture')], 'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw',
                    'destination': dest, 'properties': {'srgb': kind == 'albedo',
                        'compression_settings': {'unreal_enum': 'TextureCompressionSettings.' + ('TC_NORMALMAP' if kind == 'normal' else 'TC_DEFAULT')}}},
                 'outputs': [texture_output(dest, raw=False)]}]
        template = {'producer': producer, 'group': 'members', 'unit_prefix': 'world.skatepark.selected.' + kind,
            'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code, 'derive_payload': False,
            'payload_slot': 'selected', 'staged_path': 'inputs/selected', 'output_class': 'Data',
            'logical_namespace': '/Internal/SkatePark/Selected/' + kind, 'files': [{'path': 'member.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/selected'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece', '.json' if kind == 'materials' else '.png'))],
                'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'member.tree.tar', 'required': True}]}},
            'followers': [wrap(unit) for unit in followers]}
        result['templates'].append(template); result['module_requirements'][template['unit_prefix']] = modules
    matched = {}; captures = {'park': [], 'board': []}
    for template in result['geometry'].get('templates', []):
        family = next((f for f in ('skatepark', 'skatepark_board') if template['unit_prefix'].startswith('world.' + f + '.export.')), None)
        if family is None: continue
        parent = template['unit_prefix'].removeprefix('world.' + family + '.export.')
        board = family == 'skatepark_board'
        if (parent not in (BOARD if board else PARK) or parent in matched or template.get('followers')
                or template['producer'] != 'world.' + family + '.geometry.' + parent or template['group'] != 'geometry'
                or template['op'] != {'kind': 'blender_export_piece', 'version': '1'} or template['params'].get('format') != 'fbx'):
            raise Unsupported('Sunset Pier native followers require the original complete D2 family')
        matched[parent] = template['unit_prefix']
        raw_package = '/Game/_Raw/SkatePark/$piece'; package = ROOT + ('/Board/' if board else '/') + '$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
            'inputs': [_input('source', '$export', 'asset')], 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source',
                'destination': raw_package, 'fbx': deepcopy(FBX),
                'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]}
        incoming = [_input('raw', '$previous', 'raw'), _input('source_export', '$export', 'asset'),
            {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'], 'group': 'geometry', 'piece': '$piece'}}]
        if board: incoming += [_input(slot, ref['unit'], ref['item']) for slot, ref in dependencies.values()]
        args = {'action': 'mesh', 'parent': parent, 'piece': '$piece', 'board': board, 'blocks': False if board else blocks[parent],
                **({'material': material_slot} if board else {'materials': deepcopy(materials), 'textures': deepcopy(textures)})}
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH, 'code': native_code,
            'inputs': incoming, 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                'package_sources': {'raw': raw_package}, 'args': args, 'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
            'outputs': [_output('asset', package, 'StaticMesh'), {'id': 'report', 'logical_path': '/Internal/SkatePark/Reports/$piece',
                'class': 'Data', 'destination': 'store', 'files': [{'path': 'data/reports/$piece.json', 'required': True}]}]}
        template['followers'] = [wrap(raw), wrap(finish)]; result['module_requirements'][template['unit_prefix']] = modules
        captures['board' if board else 'park'].append({'producer': template['producer'], 'group': 'geometry',
            'unit_prefix': template['unit_prefix'], 'follower': 1, 'item': 'report'})
    if set(matched) != set(PARK + BOARD): raise Unsupported('Sunset Pier requires all ten original source parents')
    folder = 'generated/skatepark/native-summary'; tree_inputs = []; tree_paths = {}
    for index, name in enumerate(logical.get('trees', {})):
        ref = natives['/Game/Japan/Assets/' + name]; slot = 'tree' + str(index)
        tree_inputs.append(_input(slot, ref['unit'], ref['item'])); tree_paths[name] = root / ('tree/' + name)
    paths = {'build': 'inputs/source/products/' + str(meshes_index) + '-2.tree.tar',
             'runtime': 'inputs/runtime/products/' + str(runtime_index) + '-0.tree.tar', LOGICAL: 'inputs/logical',
             **{'tree/' + name: 'inputs/tree' + str(i) for i, name in enumerate(logical.get('trees', {}))}}
    roster = lambda kind: {'derived_items': {'root': 'build/v2-derived/skatepark/native-' + kind, 'templates': captures[kind]}}
    gate = {'id': 'unreal.skatepark.complete', 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code,
        'params': {'recipe': {'version': 1, 'paths': paths, 'verify': None,
            'commands': [_call(root, 'complete', (root / 'build', root / 'runtime', root / LOGICAL, roster('park'), roster('board'), tree_paths, root / folder))],
            'outputs': [{'kind': 'tree', 'path': folder, 'file': 'summary.tree.tar', 'required': True}]}},
        'outputs': [{'id': 'summary', 'logical_path': '/Internal/SkatePark/NativeSummary', 'class': 'Data', 'destination': 'store',
            'files': [{'path': 'summary.tree.tar', 'required': True}]}]}
    add(gate, [_input('source', 'world.skatepark', 'product' + str(meshes_index)), _input('runtime', 'world.skatepark', 'product' + str(runtime_index)),
               {'role': 'content', 'name': 'logical', 'source': {'kind': 'file', 'path': LOGICAL}}, *tree_inputs])
    result['aliases']['unreal.skatepark'] = (gate['id'],)
    result['geometry']['templates'] += deepcopy(result['templates']); result['geometry'].setdefault('groups', {}).update(deepcopy(result['groups']))
    result['materials'] = materials; result['textures'] = textures
    result['mesh_items'] = {kind: {'derived_items': {'root': 'build/v2-derived/skatepark/meshes-' + kind,
        'templates': [{**capture, 'item': 'asset'} for capture in captures[kind]]}} for kind in ('park', 'board')}
    result['source_join'] = {'owner': 'world.skatepark', 'retained': True, 'products': ['skatepark.meshes', 'skatepark.runtime', 'skatepark.queries']}
    return result
