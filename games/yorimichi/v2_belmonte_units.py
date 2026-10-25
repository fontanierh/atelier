"""Belmonte selected encoded-GLB followers and separate whole-hull owners."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from atelier.source_imports import ImportScanner
from atelier.build import Call, Step
from atelier.build_v2.recipe_dependencies import extract
from atelier.build_v2.recipe_compiler import _binding
from v2_geometry_templates import LIMITS
from v2_character_units import _modules, _output
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
BODY = GAME + '/world/belmonte_v2.py'
MEMBERS = GAME + '/world/belmonte_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_belmonte.py'
ROOT = '/Game/Belmonte'
FAMILIES = ('belmonte_models', 'belmonte_ground', 'belmonte_north')


def incoming(slot, unit, item):
    return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': unit, 'item': item}}


def selected(template, piece):
    return {'derived_items': {'root': 'build/v2-derived/belmonte-hulls', 'templates': [{
        'producer': template['producer'], 'group': template['group'], 'unit_prefix': template['unit_prefix'],
        'piece': piece, 'item': 'asset'}]}}


def attach_followers(geometry, *, rows, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] belmonte-per-package-native-owners
    All actual model, ground and north parents MUST use their original encoded
    exports. Render-only projection MUST prevent hull dependency cycles. Each
    whole hull MUST have one independent final package owner. Materials and their
    native closure MUST have explicit per-package owners; original first-placement bindings,
    current source validation and original mesh policy MUST survive. No generated
    scan, guessed child ID, old importer main or native execution is permitted.
    """
    root = Path(checkout).resolve(); by_id = {row['id']: row for row in rows}
    importer = by_id.get('unreal.belmonte')
    if (not importer or len(importer['commands']) != 1
            or importer['commands'][0].get('script') != {'path': ORIGINAL}
            or importer['commands'][0].get('kind') != 'UnrealScript'):
        raise Unsupported('Belmonte requires its original native importer row')
    source = json.loads((root / GAME / 'assets/belmonte/source.json').read_bytes())
    originals = {row['name']: row for row in source['meshes']}
    expected = {**{name: 'belmonte_ground' if name.startswith('SM_BM_BT_Terrain_') else 'belmonte_models'
                  for name in originals}, 'SM_BM_NorthApron': 'belmonte_north', 'SM_BM_NorthCountry': 'belmonte_north'}
    defaults = {}
    for placement in source['placements']:
        defaults.setdefault(placement['asset'], placement['materials'])
    scanner = ImportScanner()
    imports = (root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions', root / GAME / 'unreal/Scripts')
    def closure(path):
        return sorted({path, *(p.relative_to(root).as_posix() for p in scanner.local_imports(root / path, imports))})
    native_code = sorted(set(_code(root)) | set(closure(BODY)) | set(closure(GAME + '/unreal/Scripts/atmosphere.py')) | {ORIGINAL, GAME + '/unreal/Scripts/racing_tv_material.py', GAME + '/unreal/Scripts/atmosphere.py', GAME + '/unreal/Scripts/ground_grain.py'})
    result = {'geometry': deepcopy(geometry), 'units': [], 'staged_inputs': {}, 'content_slots': {},
              'packages': {}, 'aliases': {}, 'module_requirements': {}, 'templates': [], 'groups': {}}
    modules = _modules(root, [])[0]
    def add(unit):
        result['units'].append(unit)
        result['staged_inputs'][unit['id']] = {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}
        result['content_slots'].update({i['name']: False for i in unit['inputs']})
        if unit['op']['kind'].startswith('unreal.'):
            result['module_requirements'][unit['id']] = modules
    def call(name, defaults):
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location('belmonte_declaration', root / MEMBERS)
        module = importlib.util.module_from_spec(spec)
        previous = list(sys.path)
        try:
            sys.path[:0] = [str(path) for path in imports]
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = previous
        function = getattr(module, name); function.__defaults__ = tuple(defaults)
        row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build', import_roots=imports)[0]
        return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}
    def token(kind, *, piece=None, follower=None, item='asset'):
        return {'derived_items': {'root': 'build/v2-derived/belmonte-' + kind, 'templates': [{
            'producer': 'world.belmonte.members.' + kind, 'group': 'members',
            'unit_prefix': 'world.belmonte.selected.' + kind, 'item': item,
            **({'piece': piece} if piece is not None else {}), **({'follower': follower} if follower is not None else {})}]}}
    material_row = by_id.get('world.belmonte.meshes'); assembly = by_id.get('world.belmonte')
    def product(row, name, paths):
        selected = [(i,p) for i,p in enumerate(row['products']) if p['id'] == name] if row else []
        if len(selected) != 1 or selected[0][1]['paths'] != paths or selected[0][1]['optional_paths']:
            raise Unsupported('Belmonte original product differs: ' + name)
        return selected[0][0]
    material_index = product(material_row, 'belmonte.materials', ['build/yorimichi/products/belmonte/materials.json'])
    geometry_index = product(material_row, 'belmonte.geometry', ['build/yorimichi/products/belmonte/geometry.json'])
    runtime_index = product(material_row, 'belmonte.runtime', ['build/yorimichi/products/belmonte/runtime.json'])
    pixels_index = product(assembly, 'belmonte.assembled_textures', ['build/yorimichi/belmonte/textures'])
    recipe_script = 'platform/studio/atelier/build_v2/recipe_job.py'
    recipe_code = sorted(set(closure(MEMBERS)) | set(closure(recipe_script)))
    for kind in ('materials', 'textures'):
        producer = 'world.belmonte.members.' + kind; folder = 'generated/belmonte/' + kind
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
            'adapter_version': 'd2.file-set/1', 'parent': 'Belmonte_' + kind, 'encoding': 'file_set',
            'class': 'Data', 'logical_namespace': '/Internal/Belmonte/' + kind, **LIMITS}
        add({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': recipe_script,
            'code': recipe_code, 'inputs': [incoming('materials', material_row['id'], 'product' + str(material_index)),
                incoming('pixels', assembly['id'], 'product' + str(pixels_index))],
            'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': {
                'material-view': 'inputs/materials/products/' + str(material_index) + '-0.tree.tar',
                'pixels': 'inputs/pixels/products/' + str(pixels_index) + '-0.tree.tar'}, 'verify': None,
                'commands': [call('project_materials', (root / 'material-view', root / 'pixels', root / folder, kind))],
                'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                'file_group': {'source': folder, 'parent': 'Belmonte_' + kind, 'extensions': ['.json' if kind == 'materials' else '.png']}}},
            'outputs': [{'id': 'archive', 'logical_path': '/Internal/Belmonte/' + kind, 'class': 'Data',
                'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}], 'output_groups': [contract]})
        result['groups'][producer] = {'contract': contract, 'source': folder}
        template = {'producer': producer, 'group': 'members', 'unit_prefix': 'world.belmonte.selected.' + kind,
            'op': {'kind': 'py_data', 'version': '1'}, 'script': MEMBERS, 'code': closure(MEMBERS),
            'derive_payload': False, 'payload_slot': 'selected', 'staged_path': 'inputs/selected', 'output_class': 'Data',
            'logical_namespace': '/Internal/Belmonte/Selected/' + kind,
            'files': [{'path': '$piece' + ('.json' if kind == 'materials' else '.png'), 'required': True}],
            'params': {'action': 'select', 'piece': '$piece', 'extension': '.json' if kind == 'materials' else '.png'}}
        if kind == 'textures':
            raw_package = '/Game/_Raw/Belmonte/Textures/$piece'; package = ROOT + '/Textures/$piece'
            from v2_texture_units import _output as texture_output
            raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
                'code': _code(root), 'inputs': [incoming('source', '$export', 'asset')],
                'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'source_member': '$piece.png', 'destination': raw_package},
                'outputs': [texture_output(raw_package, raw=True)]}
            finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS,
                'code': _code(root), 'inputs': [incoming('raw', '$previous', 'raw_texture')],
                'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                    'package_sources': {'raw': raw_package}, 'properties': {'srgb': True, 'max_texture_size': 1024,
                    'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}}},
                'outputs': [texture_output(package, raw=False)]}
            template['followers'] = [{'unit': u, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in u['inputs']}} for u in (raw, finish)]
            result['module_requirements'][template['unit_prefix']] = modules
        result['templates'].append(template)
    def author(owner, package, action, args, inputs):
        add({'id': owner, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': BODY, 'code': native_code,
            'inputs': inputs, 'params': {'args': {'action': action, **args}},
            'outputs': [_output('asset', package, 'MaterialInstance' if action == 'instance' else 'Material')]})
        ref = {'unit': owner, 'item': 'asset', 'package': package}
        result['packages'][package] = ref
        return ref
    parent_ref = author('unreal.belmonte.parent', ROOT + '/Materials/M_Belmonte', 'parent', {}, [])
    ground_texture = None
    def texture_name(path, descriptor):
        texture = descriptor['textures'].get('BaseColor') or descriptor['textures'].get('DryColor')
        if not texture: return None
        atlas = 'SalonPosters' in path or '/Atelier/' in path
        key = ('tuscan-ground' if 'terrain_' in path else texture) + (':atlas' if atlas else ':detail')
        return 'T_BM_' + hashlib.sha256(key.encode()).hexdigest()[:12]
    for path, descriptor in source['materials'].items():
        if 'terrain_' in path:
            value = texture_name(path, descriptor)
            if value:
                if ground_texture is not None and ground_texture != value: raise Unsupported('Ambiguous Belmonte ground texture')
                ground_texture = value
    if ground_texture is None: raise Unsupported('Missing original Belmonte ground texture')
    join_ref = author('unreal.belmonte.join_parent', ROOT + '/Materials/M_BelmonteJoin', 'join_parent',
        {'texture': token('textures', piece=ground_texture, follower=1, item='texture')}, [])
    join_ref['derived_dependencies'] = [token('textures', piece=ground_texture, follower=1, item='texture')]
    specs = [(path, 'MI_BM_' + hashlib.sha256(path.encode()).hexdigest()[:12], texture_name(path, descriptor))
             for path, descriptor in source['materials'].items() if not path.endswith('MI_B_foliage')]
    specs.append(('Ground', 'MI_BM_Ground', None))
    for source_name, name, texture in specs:
        base = join_ref if source_name == 'Ground' else parent_ref
        ref = author('unreal.belmonte.material.' + name, ROOT + '/Materials/' + name, 'instance',
            {'name': name, 'source_name': source_name, 'spec': token('materials', piece=name),
             'texture': token('textures', piece=texture, follower=1, item='texture') if texture else None,
             'parent_package': base['package'], 'parent_dependencies': deepcopy(base.get('derived_dependencies', []))}, [incoming('parent', base['unit'], base['item'])])
        ref['dependencies'] = [base]
        ref['derived_dependencies'] = [token('textures', piece=texture, follower=1, item='texture')] if texture else []
    tv_ref = author('unreal.belmonte.racing_tv', '/Game/Racing/M_RacingTv', 'tv', {}, [])
    supplied = dict(natives or {}); supplied.update(result['packages']); natives = supplied
    def dependencies(paths):
        found = {}; packages = {}
        def visit(package, supplied=None):
            ref = natives.get(package) if supplied is None else supplied
            if (not isinstance(ref, dict) or ref.get('package') != package
                    or any(not isinstance(ref.get(k), str) or not ref[k] for k in ('unit', 'item'))):
                raise Unsupported('Missing exact supplied Belmonte native dependency: ' + package)
            key = ref['unit'], ref['item']
            if key in found:
                if found[key][1]['package'] != package:
                    raise Unsupported('Belmonte native Item aliases different packages')
                return
            if package in packages and packages[package] != key:
                raise Unsupported('Belmonte package has multiple native owners')
            packages[package] = key; found[key] = ('native' + str(len(found)), ref)
            for child in ref.get('dependencies', ()):
                visit(child if isinstance(child, str) else child['package'], None if isinstance(child, str) else child)
        for path in sorted(set(paths)):
            visit(path)
        return list(found.values())
    def report_output(piece):
        return {'id': 'report', 'logical_path': '/Internal/Belmonte/NativeReport/' + piece, 'class': 'Data', 'destination': 'store',
                'files': [{'path': 'data/reports/' + piece + '.json', 'required': True}]}
    seen = set()
    for template in result['geometry']['templates']:
        family = next((f for f in FAMILIES if template['unit_prefix'].startswith('world.' + f + '.export.')), None)
        if family is None:
            continue
        parent = template['unit_prefix'].removeprefix('world.' + family + '.export.')
        producer = 'world.' + family + '.geometry.' + parent
        row = by_id.get(producer)
        if (expected.get(parent) != family or parent in seen or template['producer'] != producer
                or template['group'] != 'geometry' or template['op'] != {'kind': 'encoded_export_piece', 'version': '1'}
                or template['files'] != [{'path': '$piece.glb'}, {'path': 'export.json'}] or template.get('followers')
                or not row or len(row['products']) != 1 or row['products'][0]['optional_paths']):
            raise Unsupported('Belmonte requires every unmodified original encoded parent exactly once')
        group = geometry['groups'].get(producer)
        if (not group or group['contract']['parent'] != parent or group['contract']['encoding'] != 'encoded_glb'
                or row['products'][0]['paths'] != [group['source']]):
            raise Unsupported('Belmonte original planner Product differs')
        seen.add(parent)
        original = originals.get(parent)
        paths = ([ROOT + '/Materials/MI_BM_Ground'] if original is None else [
            ROOT + '/Materials/MI_BM_' + hashlib.sha256(path.encode()).hexdigest()[:12]
            for path in defaults[original['source_asset']]])
        if original is not None:
            from atelier.gltf import glb_parts
            doc, _ = glb_parts((root / GAME / 'assets/belmonte' / original['path']).read_bytes())
            used = [int(m['name'].split('_')[1]) for m in doc['materials']]
            bindings = {str(i): paths[i] for i in used}
            paths = list(bindings.values())
        else:
            bindings = {'0': paths[0]}
        hull = original.get('collision') if original else None
        refs = dependencies([*paths, *([ROOT + '/Materials/MI_BM_Ground'] if hull else [])])
        native = {slot: ref['package'] for slot, ref in refs}
        extra = []
        for _, ref in refs:
            for descriptor in ref.get('derived_dependencies', []):
                if descriptor not in extra: extra.append(descriptor)
        native_inputs = [incoming(slot, ref['unit'], ref['item']) for slot, ref in refs]
        hull_ref = None
        if hull:
            piece = parent + '_Collision'; raw_id = 'unreal.belmonte.hull.raw.' + parent
            finish_id = 'unreal.belmonte.hull.finish.' + parent
            raw_package = '/Game/_Raw/Belmonte/' + piece; package = ROOT + '/Meshes/' + piece
            hull_token = selected(template, piece)
            add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': BODY, 'code': native_code,
                 'inputs': [], 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': hull_token,
                 'destination': raw_package}, 'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]})
            hull_refs = dependencies([ROOT + '/Materials/MI_BM_Ground'])
            hull_native = {slot: ref['package'] for slot, ref in hull_refs}
            hull_extra = [descriptor for _, ref in hull_refs for descriptor in ref.get('derived_dependencies', [])]
            add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': BODY, 'code': native_code,
                 'inputs': [incoming('raw', raw_id, 'raw'), *[incoming(slot, ref['unit'], ref['item']) for slot, ref in hull_refs]],
                 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                     'package_sources': {'raw': raw_package}, 'args': {'piece': piece, 'parent': parent,
                     'source_export': hull_token, 'hull': True, 'native_inputs': hull_native, 'native_extra': hull_extra, 'bindings': {}, 'collision': None}},
                 'outputs': [_output('asset', package, 'StaticMesh'), report_output(piece)]})
            hull_ref = {'unit': finish_id, 'item': 'asset', 'package': package}
            result['packages'][package] = hull_ref
        projection = 'world.belmonte.render.' + parent
        contract = dict(group['contract'], root='geometry', root_param='geometry_root')
        add({'id': projection, 'op': {'kind': 'py_data', 'version': '1'}, 'script': MEMBERS, 'code': closure(MEMBERS),
             'inputs': [incoming('source', producer, 'product0')],
             'params': {'parent': parent, 'geometry_root': 'geometry'}, 'outputs': [], 'output_groups': [contract]})
        result['groups'][projection] = {'contract': contract, 'source': 'geometry', 'format': 'glb'}
        render = deepcopy(template); render['producer'] = projection
        render['unit_prefix'] = 'world.belmonte.render_export.' + parent
        raw_package = '/Game/_Raw/Belmonte/$piece'; package = ROOT + '/Meshes/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': _code(root),
               'inputs': [incoming('source', '$export', 'asset')],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package},
               'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]}
        inputs = [incoming('raw', '$previous', 'raw'), incoming('source_export', '$export', 'asset'),
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': projection, 'group': 'geometry', 'piece': '$piece'}},
                  *deepcopy(native_inputs)]
        if hull_ref:
            inputs.append(incoming('collision', hull_ref['unit'], hull_ref['item']))
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': BODY, 'code': native_code,
                  'inputs': inputs, 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                  'package_sources': {'raw': raw_package}, 'args': {'piece': '$piece', 'parent': parent, 'source_export': 'source_export',
                  'payload': 'payload', 'hull': False, 'native_inputs': native, 'native_extra': deepcopy(extra), 'bindings': bindings,
                  'collision': hull_ref['package'] if hull_ref else None}}, 'outputs': [_output('asset', package, 'StaticMesh'), report_output('$piece')]}
        render['followers'] = [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}} for unit in (raw, finish)]
        result['templates'].append(render); result['module_requirements'][render['unit_prefix']] = modules
    if seen != set(expected):
        raise Unsupported('Belmonte actual complete parent roster differs')
    render_templates = [t for t in result['templates'] if t['unit_prefix'].startswith('world.belmonte.render_export.')]
    def mesh_token(item):
        return {'derived_items': {'root': 'build/v2-derived/belmonte-native-' + item, 'templates': [
            {'producer': t['producer'], 'group': t['group'], 'unit_prefix': t['unit_prefix'], 'follower': 1, 'item': item} for t in render_templates]}}
    hulls = [u for u in result['units'] if u['id'].startswith('unreal.belmonte.hull.finish.')]
    material_refs = [ref for package, ref in result['packages'].items() if package.startswith(ROOT + '/Materials/')]
    paths = {'geometry': 'inputs/geometry/products/' + str(geometry_index) + '-0.tree.tar',
             'runtime': 'inputs/runtime/products/' + str(runtime_index) + '-0.tree.tar',
             'material-view': 'inputs/material_view/products/' + str(material_index) + '-0.tree.tar', 'tv': 'inputs/tv'}
    gate_inputs = [incoming('geometry', material_row['id'], 'product' + str(geometry_index)),
        incoming('runtime', material_row['id'], 'product' + str(runtime_index)),
        incoming('material_view', material_row['id'], 'product' + str(material_index)), incoming('tv', tv_ref['unit'], 'asset')]
    hull_paths = {}; material_paths = {}
    for index, unit in enumerate(hulls):
        name = unit['params']['args']['piece']; slot = 'hull' + str(index); report = slot + 'report'
        gate_inputs += [incoming(slot, unit['id'], 'asset'), incoming(report, unit['id'], 'report')]
        paths[slot] = 'inputs/' + slot; paths[report] = 'inputs/' + report
        hull_paths[name] = (root / slot, root / report)
    for index, ref in enumerate(material_refs):
        name = ref['package'].rsplit('/', 1)[-1]; slot = 'material' + str(index)
        gate_inputs.append(incoming(slot, ref['unit'], ref['item'])); paths[slot] = 'inputs/' + slot; material_paths[name] = root / slot
    folder = 'generated/belmonte/native-summary'
    add({'id': 'unreal.belmonte.complete', 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': recipe_script,
        'code': recipe_code, 'inputs': gate_inputs, 'params': {'recipe': {'version': 1, 'paths': paths, 'verify': None,
            'commands': [call('complete', (root / 'geometry', root / 'runtime', mesh_token('report'), hull_paths,
                material_paths, token('textures', follower=1, item='texture'), root / 'tv', root / folder, mesh_token('asset'), root / 'material-view'))],
            'outputs': [{'kind': 'tree', 'path': folder, 'file': 'summary.tree.tar', 'required': True}]}},
        'outputs': [{'id': 'summary', 'logical_path': '/Internal/Belmonte/NativeSummary', 'class': 'Data', 'destination': 'store',
            'files': [{'path': 'summary.tree.tar', 'required': True}]}]})
    result['geometry']['templates'] += deepcopy(result['templates'])
    result['geometry']['groups'].update(deepcopy(result['groups']))
    result['aliases']['unreal.belmonte'] = ['unreal.belmonte.complete']
    result['source_join'] = {'owner': 'world.belmonte', 'required': True, 'retained': True,
        'native_templates': [t['unit_prefix'] for t in result['templates']],
        'products': ['belmonte.assembled_models', 'belmonte.assembled_textures', 'belmonte.assembled_queries', 'belmonte.assembled_metadata']}
    return result
