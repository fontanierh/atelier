"""Replace unreal.fox_hunter (Scripts/import_fox_hunter.py) by native units per /Game/FoxHunter package (world/fox_v2.py).

characters.fox_hunter's Product ``characters.fox_hunter.export`` is export.json with fbx/ and textures/; the committed
fox-hunter/manifest.json names the fifteen clips. From that whole Item (world/fox_members_v2.py):
- FileSet groups: ``images`` (each texture a material names; raw texture and finish), ``materials`` (each export
  material; the original loop body on its declared finished texture) and ``clips`` (each clip's FBX; a raw FBX
  animation on SK_FoxHunter_Skeleton and its finish with the shared compression);
- one body unit with the fixed owners' views: member/ (FoxHunter.fbx) and facts/facts.json;
- fixed units: the raw skeletal import, SK_FoxHunter with its Skeleton and PhysicsAsset, BS_FoxLocomotion,
  DA_FoxHunter and the record writing fox_hunter/unreal_import.json.
``natives = {compression: {unit, item, package}}``, the shared CharacterCompression owner.
"""
from copy import deepcopy
import json
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import CLIP_FBX, MESH_FBX, VERTEX_COLORS, _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/fox_v2.py'
BODY = GAME + '/world/fox_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_fox_hunter.py'
COMPRESSION_SCRIPT = GAME + '/unreal/Scripts/animation_compression.py'
CHARACTER = GAME + '/assets/characters/fox-hunter'
MANIFEST = CHARACTER + '/manifest.json'
EXPORTER = CHARACTER + '/export_unreal.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi/fox_hunter'
PRODUCT = 'characters.fox_hunter.export'
EXPORT_PATHS = (OUT + '/export.json', OUT + '/fbx', OUT + '/textures')
DEST = '/Game/FoxHunter'
RAW = '/Game/_Raw/FoxHunter'
REPORT_FILE = OUT + '/unreal_import.json'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
FOLLOWERS = {'images': (1, 'texture'), 'materials': (0, 'asset'), 'clips': (1, 'animation')}


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('fox_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _file(name, path):
    return {'role': 'content', 'name': name, 'source': {'kind': 'file', 'path': path}}


def token(kind):
    follower, item = FOLLOWERS[kind]
    return {'derived_items': {'root': f'build/v2-derived/fox_hunter/{kind}', 'templates': [
        {'producer': f'characters.fox_hunter.members.{kind}', 'group': 'members',
         'unit_prefix': f'unreal.fox_hunter.{kind}', 'follower': follower, 'item': item}]}}


def _check(by_id):
    importer, producer = by_id.get('unreal.fox_hunter'), by_id.get('characters.fox_hunter')
    commands = (importer or {}).get('commands') or [{}]
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL} or commands[0].get('marker') != 'FOX HUNTER IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or importer.get('products')):
        raise Unsupported('unreal.fox_hunter differs from the original import_fox_hunter.py target')
    script = (((producer or {}).get('commands') or [{}])[0]).get('script')
    if script != {'path': EXPORTER}:
        raise Unsupported('characters.fox_hunter differs from the original fox-hunter/export_unreal.py')
    found = [i for i, p in enumerate(producer.get('products', ())) if p['id'] == PRODUCT]
    if len(found) != 1 or [str(p) for p in producer['products'][found[0]]['paths']] != list(EXPORT_PATHS):
        raise Unsupported(f'{PRODUCT} must be exactly export.json, fbx/ and textures/')
    index = found[0]
    return producer['id'], f'product{index}', {path: f'products/{index}-{j}.tree.tar' for j, path in enumerate(EXPORT_PATHS)}


def fox_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-fox-hunter-native-units
    unreal.fox_hunter MUST become one unit per /Game/FoxHunter package and its
    record, from the whole declared characters.fox_hunter export Product and the
    committed clip manifest: generated images, materials and clips as FileSet
    members whose owners consume only their own member view; the body bundle,
    blend space and definition as fixed owners on the finished skeleton; clips
    with the shared compression owner. Consumers MUST bind actual derived Items,
    never invented IDs; the original top level and its texture imports never run.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    producer_id, product, archives = _check(by_id)
    fps = json.loads((root / MANIFEST).read_bytes())['fps']
    if type(fps) is not int or fps <= 0:
        raise Unsupported('fox-hunter/manifest.json has no integer fps')
    compression = (natives or {}).get('compression')
    if not isinstance(compression, dict) or not {'unit', 'item', 'package'} <= set(compression) or compression['package'] != COMPRESSION:
        raise Unsupported('missing the shared CharacterCompression owner Item')
    scanner = ImportScanner()
    recipe_code = {BODY}
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world')))
    recipe_code = sorted(recipe_code)
    code = {*_code(root), SCRIPT, ORIGINAL, COMPRESSION_SCRIPT}
    code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
        root / COMPRESSION_SCRIPT, (root / GAME / 'world', root / GAME / 'unreal/Scripts', root / 'platform/studio')))
    code = sorted(code)
    ops_code, editor = list(_code(root)), _modules(root, [])[0]
    units, staged, packages, requirements, templates, groups = [], {}, {}, {}, [], {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor

    sources = [_item('export', producer_id, product), _file('manifest', MANIFEST)]
    sources[0]['whole'] = 'The complete fox export checks against the committed clip roster before any member is selected.'
    paths = {**{path: 'inputs/export/' + archive for path, archive in archives.items()}, MANIFEST: 'inputs/manifest'}
    args = (*(root / path for path in EXPORT_PATHS), root / MANIFEST)
    for kind in FOLLOWERS:
        generated, unit_id = f'generated/fox_hunter/{kind}', f'characters.fox_hunter.members.{kind}'
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': f'FoxHunter_{kind}', 'encoding': 'file_set',
                    'class': 'Data', 'logical_namespace': f'/Internal/FoxHunter/{kind}', **LIMITS}
        add({'id': unit_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
             'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                 'commands': [_call(root, 'project', (*args, root / generated, kind))],
                 'outputs': [{'path': generated, 'kind': 'tree', 'file': 'members.tree.tar', 'required': True}],
                 'file_group': {'source': generated, 'parent': f'FoxHunter_{kind}', 'extensions': ['.json']}}},
             'outputs': [{'id': 'archive', 'logical_path': f'/Internal/FoxHunter/{kind}', 'class': 'Data',
                          'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
             'output_groups': [contract]}, deepcopy(sources))
        groups[unit_id] = {'contract': contract, 'source': generated}
    body_id = 'characters.fox_hunter.body'
    add({'id': body_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
             'commands': [_call(root, 'body', (*args, root / 'generated/fox_hunter/member', root / 'generated/fox_hunter/facts'))],
             'outputs': [{'path': f'generated/fox_hunter/{f}', 'kind': 'tree', 'file': f + '.tree.tar', 'required': True}
                         for f in ('member', 'facts')]}},
         'outputs': [{'id': 'body', 'logical_path': '/Internal/FoxHunter/Body', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': f + '.tree.tar', 'required': True} for f in ('member', 'facts')]}]}, deepcopy(sources))
    member_root = {'archive_member': 'member.tree.tar', 'name': 'member'}
    meta_root = {'archive_member': 'meta.tree.tar', 'name': 'meta'}
    facts_root = {'archive_member': 'facts.tree.tar', 'name': 'facts'}
    mesh_id = 'unreal.fox_hunter.mesh'
    mesh, skeleton, physics = f'{DEST}/SK_FoxHunter', f'{DEST}/SK_FoxHunter_Skeleton', f'{DEST}/SK_FoxHunter_PhysicsAsset'

    def template(kind, followers, files=('member', 'meta')):
        templates.append({'producer': f'characters.fox_hunter.members.{kind}', 'group': 'members',
            'unit_prefix': f'unreal.fox_hunter.{kind}', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
            'derive_payload': False, 'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
            'logical_namespace': f'/Internal/FoxHunter/Selected/{kind}',
            'files': [{'path': f + '.tree.tar', 'required': True} for f in files],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', root / 'meta', '$piece'))],
                'outputs': [{'path': f, 'kind': 'tree', 'file': f + '.tree.tar', 'required': True} for f in files]}},
            'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                          for unit in followers]})
    raw_texture = f'{RAW}/Textures/$piece'
    template('images', [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('source', '$export', 'asset')],
         'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_texture,
                    'input_roots': {'source': dict(member_root)}},
         'outputs': [_output('raw_texture', raw_texture, 'RawTexture', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('raw', '$previous', 'raw_texture')],
         'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': f'{DEST}/Textures/$piece',
                    'package_sources': {'raw': raw_texture}, 'properties': {}},
         'outputs': [_output('texture', f'{DEST}/Textures/$piece', 'Texture')]}])
    template('materials', [
        {'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'inputs': [_item('meta', '$export', 'asset')],
         'params': {'input_roots': {'meta': dict(meta_root)}, 'settings': [],
                    'args': {'action': 'material', 'name': '$piece', 'meta': 'meta', 'images': token('images')}},
         'outputs': [_output('asset', f'{DEST}/$piece', 'Material')]}], files=('meta',))
    raw_clip = f'{RAW}/A_Fox$piece'
    template('clips', [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('source', '$export', 'asset'), _item('skeleton', mesh_id, 'skeleton')],
         'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_clip, 'skeleton': 'skeleton',
                    'fbx': {**CLIP_FBX, 'custom_sample_rate': fps, 'delete_existing_morph_target_curves': True,
                            'do_not_import_curve_with_zero': False},
                    'input_roots': {'source': dict(member_root)}},
         'outputs': [_output('raw_animation', raw_clip, 'RawAnimation', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'inputs': [_item('raw', '$previous', 'raw_animation'), _item('skeleton', mesh_id, 'skeleton'),
                    _item('compression', compression['unit'], compression['item']), _item('meta', '$export', 'asset')],
         'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': f'{DEST}/A_Fox$piece',
                    'input_roots': {'meta': dict(meta_root)},
                    'args': {'action': 'clip', 'name': '$piece', 'meta': 'meta', 'skeleton': 'skeleton',
                             'compression': 'compression'}},
         'outputs': [_output('animation', f'{DEST}/A_Fox$piece', 'Animation')]}])
    raw_id, raw_mesh = 'unreal.fox_hunter.raw', f'{RAW}/SK_FoxHunter'
    add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw_mesh,
                    'create_physics_asset': True, 'fbx': {**MESH_FBX, **VERTEX_COLORS, 'import_morph_targets': False}},
         'outputs': [_output('raw_mesh', raw_mesh, 'RawSkeletalMesh', store=True),
                     _output('raw_skeleton', raw_mesh + '_Skeleton', 'Skeleton', store=True),
                     _output('raw_physics_asset', raw_mesh + '_PhysicsAsset', 'PhysicsAsset', store=True)]},
        [_item('source', body_id, 'body')], {'source': dict(member_root)})
    add({'id': mesh_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh,
                    'partners': {'skeleton': skeleton, 'physics_asset': physics},
                    'args': {'action': 'mesh', 'facts': 'facts', 'materials': token('materials')}},
         'outputs': [_output('mesh', mesh, 'SkeletalMesh'), _output('skeleton', skeleton, 'Skeleton'),
                     _output('physics_asset', physics, 'PhysicsAsset')]},
        [_item('raw', raw_id, 'raw_mesh'), _item('raw_skeleton', raw_id, 'raw_skeleton'),
         _item('raw_physics_asset', raw_id, 'raw_physics_asset'), _item('facts', body_id, 'body')], {'facts': dict(facts_root)})
    bundle = [{'unit': mesh_id, 'item': i, 'package': p} for i, p in (('skeleton', skeleton), ('physics_asset', physics))]
    packages[mesh] = {'unit': mesh_id, 'item': 'mesh', 'package': mesh, 'dependencies': deepcopy(bundle),
                      'derived_dependencies': {'materials': token('materials'), 'images': token('images')}}
    for row in bundle:
        packages[row['package']] = dict(row)
    blend_id, blend = 'unreal.fox_hunter.locomotion', f'{DEST}/BS_FoxLocomotion'
    add({'id': blend_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'blend', 'facts': 'facts', 'skeleton': 'skeleton', 'clips': token('clips')},
                    'settings': []},
         'outputs': [_output('asset', blend, 'BlendSpace1D')]},
        [_item('facts', body_id, 'body'), _item('skeleton', mesh_id, 'skeleton')], {'facts': dict(facts_root)})
    packages[blend] = {'unit': blend_id, 'item': 'asset', 'package': blend,
                       'dependencies': [dict(bundle[0])], 'derived_dependencies': {'clips': token('clips')}}
    definition_id, definition = 'unreal.fox_hunter.definition', f'{DEST}/DA_FoxHunter'
    add({'id': definition_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'definition', 'facts': 'facts', 'mesh': 'mesh', 'blend': 'blend', 'clips': token('clips')},
                    'settings': []},
         'outputs': [_output('asset', definition, 'DataAsset')]},   # the generic class of the FoxHunterDefinition the body builds
        [_item('facts', body_id, 'body'), _item('mesh', mesh_id, 'mesh'), _item('blend', blend_id, 'asset')],
        {'facts': dict(facts_root)})
    requirements[definition_id] = _modules(root, ['Yorimichi'])[0]
    packages[definition] = {'unit': definition_id, 'item': 'asset', 'package': definition,
                            'dependencies': [{'unit': mesh_id, 'item': 'mesh', 'package': mesh},
                                             {'unit': blend_id, 'item': 'asset', 'package': blend}],
                            'derived_dependencies': {'clips': token('clips')}}
    record_id = 'unreal.fox_hunter.record'
    add({'id': record_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'record', 'facts': 'facts', 'mesh': 'mesh', 'skeleton': 'skeleton',
                             'definition': 'definition', 'clips': token('clips')}, 'settings': []},
         'outputs': [{'id': 'report', 'logical_path': '/Internal/FoxHunter/Report', 'class': 'JsonData', 'destination': 'store',
                      'files': [{'path': 'data/unreal_import.json', 'required': True}]}]},
        [_item('facts', body_id, 'body'), _item('mesh', mesh_id, 'mesh'), _item('skeleton', mesh_id, 'skeleton'),
         _item('definition', definition_id, 'asset')], {'facts': dict(facts_root)})
    packages[REPORT_FILE] = {'unit': record_id, 'item': 'report'}
    return {'units': units, 'staged_inputs': staged, 'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'aliases': {'unreal.fox_hunter': tuple(u['id'] for u in units)},
            'module_requirements': requirements, 'templates': templates, 'groups': groups,
            'tokens': {kind: token(kind) for kind in FOLLOWERS}}
