"""Complete coastal native family over actual original library FileSet members."""
from copy import deepcopy
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, _code, _output
import v2_brinecove_material_units as material
from v2_brinecove_native_units import FINISH, _load

BODY = 'games/yorimichi/world/brinecove_members_v2.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
SOURCE = 'build/yorimichi/brinecove'
KINDS = ('materials', 'textures', 'meshes')
PARENTS = ('M_Brinecove', 'M_BrinecoveMasked', 'M_BrinecoveSpray', 'M_BrinecoveTerrain')


def _call(root, name, defaults):
    function = getattr(_load(root, BODY, 'brinecove_callback_' + name), name)
    function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / 'games/yorimichi/world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def token(kind, follower, item):
    return {'derived_items': {'root': 'build/v2-derived/brinecove/' + kind,
        'templates': [{'producer': 'world.brinecove.members.' + kind, 'group': 'members',
            'unit_prefix': 'world.brinecove.selected.' + kind, 'follower': follower, 'item': item}]}}


def _input(name, owner, item):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': owner, 'item': item}}


def attach_followers(geometry, *, rows, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] complete-brinecove-source-family
    The complete original library Product MUST own the finite generated roster.
    Each source descriptor/image/mesh MUST select independently before native work;
    actual derived native Items and full parent/texture closure MUST be explicit.
    Completion MUST compare original runtime/report membership with actual native
    Items. Preserve original source ownership, geometry bytes and finishing policy;
    no generated scan, fabricated child ID, fallback material or native reuse claim.
    """
    root = Path(checkout).resolve(); by_id = {row['id']: row for row in rows}
    original = by_id.get('unreal.brinecove'); producer = by_id.get('world.brinecove')
    if (not original or len(original['commands']) != 1 or original['commands'][0].get('kind') != 'UnrealScript'
            or original['commands'][0].get('script') != {'path': material.ORIGINAL}):
        raise ValueError('Brinecove requires its actual original importer declaration')
    products = [(i, p) for i, p in enumerate(producer['products']) if p['id'] == 'brinecove.library'] if producer else []
    paths = [SOURCE + '/' + p for p in ('glb', 'textures', 'runtime.json', 'build-report.json')]
    if len(products) != 1 or products[0][1]['paths'] != paths or products[0][1]['optional_paths']:
        raise ValueError('Brinecove requires the actual complete original library Product')
    index = products[0][0]; item = 'product' + str(index)
    imports = (root / 'platform/studio', root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts')
    def closure(files):
        result = set(files)
        for path in files: result.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / path, imports))
        return sorted(result)
    code = closure([BODY, RECIPE, EMITTER]); native_code = closure([material.SCRIPT, FINISH])
    native_code = sorted(set(native_code) | set(_code(root)) | {material.ORIGINAL})
    result = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {}, 'aliases': {},
        'module_requirements': {}, 'templates': [], 'groups': {}, 'geometry': deepcopy(geometry), 'missing_roles': []}
    modules = _modules(root, [])[0]
    def add(unit):
        result['units'].append(unit)
        result['staged_inputs'][unit['id']] = {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}
        result['content_slots'].update({i['name']: False for i in unit['inputs']})
        if unit['op']['kind'].startswith('unreal.'): result['module_requirements'][unit['id']] = modules
    def wrap(unit): return {'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
    def data(name, path, file):
        return {'id': name, 'logical_path': path, 'class': 'Data', 'destination': 'store', 'files': [{'path': file, 'required': True}]}
    for name, blend in zip(PARENTS, ('opaque', 'masked', 'translucent', 'terrain')):
        package = material.ROOT + '/Materials/' + name; owner = 'unreal.brinecove.material.' + name
        output = _output(package, raw=False); output.update(id='asset', **{'class': 'Material'})
        add({'id': owner, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': material.SCRIPT, 'code': native_code,
            'inputs': [], 'params': {'args': {'asset': name, 'package': package, 'factory': 'terrain_parent' if blend == 'terrain' else 'parent',
                'inputs': {}, 'blend': blend}, 'settings': []}, 'outputs': [output]})
        result['packages'][package] = {'unit': owner, 'item': 'asset', 'package': package}
    parents = [_input('parent' + str(i), 'unreal.brinecove.material.' + name, 'asset') for i, name in enumerate(PARENTS)]
    parent_slots = {name: 'parent' + str(i) for i, name in enumerate(PARENTS)}
    textures = token('textures', 1, 'texture'); materials = token('materials', 0, 'asset')
    source_paths = {path: 'inputs/library/products/' + str(index) + '-' + str(i) + '.tree.tar' for i, path in enumerate(paths)}
    incoming = _input('library', 'world.brinecove', item)
    incoming['whole'] = 'The complete original report/runtime/texture/mesh membership validates before finite selected children.'
    for kind in KINDS:
        owner = 'world.brinecove.members.' + kind; folder = 'generated/brinecove/' + kind
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
            'adapter_version': 'd2.file-set/1', 'parent': 'Brinecove_' + kind, 'encoding': 'file_set', 'class': 'Data',
            'logical_namespace': '/Internal/Brinecove/' + kind, **LIMITS}
        add({'id': owner, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': code, 'inputs': [deepcopy(incoming)],
            'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(source_paths), 'verify': None,
                'commands': [_call(root, 'project', (root / paths[3], root / paths[2], root / paths[1], root / paths[0], root / folder, kind))],
                'outputs': [{'path': folder, 'file': 'members.tree.tar', 'required': True}],
                'file_group': {'source': folder, 'parent': 'Brinecove_' + kind, 'extensions': ['.mesh'] if kind == 'meshes' else ['.png', '.jpg'] if kind == 'textures' else ['.json']}}},
            'outputs': [data('archive', '/Internal/Brinecove/' + kind, 'members.tree.tar')], 'output_groups': [contract]})
        result['groups'][owner] = {'contract': contract, 'source': folder}
        selected = {'archive_member': 'member.tree.tar', 'name': 'member'}
        followers = []
        if kind == 'materials':
            output = _output(material.ROOT + '/Materials/$piece', raw=False); output.update(id='asset', **{'class': 'MaterialInstance'})
            followers = [{'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': material.SCRIPT, 'code': native_code,
                'inputs': [_input('spec', '$export', 'asset'), *deepcopy(parents)],
                'params': {'input_roots': {'spec': selected}, 'args': {'factory': 'selected_instance', 'piece': '$piece',
                    'parents': dict(parent_slots), 'textures': deepcopy(textures)}, 'settings': []}, 'outputs': [output]}]
        else:
            mesh = kind == 'meshes'; raw = '/Game/_Raw/Brinecove/' + ('Meshes/' if mesh else 'Textures/') + '$piece'
            dest = material.ROOT + ('/Meshes/' if mesh else '/Textures/') + '$piece'
            raw_output = _output(raw, raw=True)
            if mesh: raw_output.update(id='raw', **{'class': 'RawStaticMesh'})
            finish_output = _output(dest, raw=False)
            if mesh: finish_output.update(id='asset', **{'class': 'StaticMesh'})
            followers.append({'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
                'inputs': [_input('source', '$export', 'asset')], 'params': {'op': 'raw_import', 'kind': 'static_mesh' if mesh else 'texture',
                    'source': 'source', 'destination': raw, 'input_roots': {'source': selected}}, 'outputs': [raw_output]})
            inputs = [_input('raw', '$previous', 'raw' if mesh else 'raw_texture')]
            params = {'op': 'finish', 'kind': 'static_mesh' if mesh else 'texture', 'source': 'raw', 'destination': dest, 'package_sources': {'raw': raw}}
            if mesh:
                inputs += [_input('source_export', '$export', 'asset'), {'role': 'content', 'name': 'payload',
                    'source': {'kind': 'group_member', 'unit': owner, 'group': 'members', 'piece': '$piece'}}, *deepcopy(parents)]
                params.update(input_roots={'source_export': selected}, args={'materials': deepcopy(materials), 'source_export': 'source_export', 'payload': 'payload'},
                    partners=deepcopy(textures))
            else:
                # The selected piece name determines the original normal-map policy.
                params['args'] = {'texture_piece': '$piece'}
            followers.append({'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH if mesh else material.SCRIPT,
                'code': native_code, 'inputs': inputs, 'params': params, 'outputs': [finish_output, *([data('report', '/Internal/Brinecove/Reports/$piece', 'data/reports/$piece.json')] if mesh else [])]})
        template = {'producer': owner, 'group': 'members', 'unit_prefix': 'world.brinecove.selected.' + kind,
            'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': code, 'derive_payload': False,
            'payload_slot': 'selected', 'staged_path': 'inputs/selected', 'output_class': 'Data',
            'logical_namespace': '/Internal/Brinecove/Selected/' + kind, 'files': [{'path': 'member.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/selected'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece', kind))],
                'outputs': [{'path': 'member', 'file': 'member.tree.tar', 'required': True}]}}, 'followers': [wrap(u) for u in followers]}
        result['templates'].append(template); result['module_requirements'][template['unit_prefix']] = modules
    folder = 'generated/brinecove/complete'
    gate = {'id': 'unreal.brinecove.complete', 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': code,
        'inputs': [deepcopy(incoming)], 'params': {'recipe': {'version': 1, 'paths': dict(source_paths), 'verify': None,
            'commands': [_call(root, 'complete', (root / paths[3], root / paths[2], root / paths[1], token('meshes', 1, 'asset'),
                deepcopy(materials), deepcopy(textures), token('meshes', 1, 'report'), root / folder))],
            'outputs': [{'path': folder, 'file': 'complete.tree.tar', 'required': True}]}},
        'outputs': [data('summary', '/Internal/Brinecove/Complete', 'complete.tree.tar')]}
    add(gate); result['aliases']['unreal.brinecove'] = (gate['id'],)
    result['geometry'].setdefault('templates', []).extend(deepcopy(result['templates']))
    result['geometry'].setdefault('groups', {}).update(deepcopy(result['groups']))
    result['runtime_data'] = {'unit': 'world.brinecove', 'item': item,
        'root': {'archive_member': 'products/' + str(index) + '-2.tree.tar', 'name': 'runtime.json'}}
    result['source_join'] = {'owner': 'world.brinecove', 'retained': True, 'products': ['brinecove.library'], 'runtime_data': deepcopy(result['runtime_data'])}
    result['native_report'] = {'unit': gate['id'], 'item': 'summary', 'root': {'archive_member': 'complete.tree.tar', 'name': 'complete'}, 'member': 'import-report.json'}
    result['material_items'] = materials; result['texture_items'] = textures; result['mesh_items'] = token('meshes', 1, 'asset')
    return result
