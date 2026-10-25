"""Cold-graph character membership through existing FileSet templates (world/character_members_v2.py).

Per import_character.py target unreal.<k>, the generated roster of characters.<k>'s export Item becomes FileSet groups
written by one projector per group: ``materials`` (<M>.json), ``textures`` (the exported images) and ``clips_<rate>``
(the clip FBX bytes, one group per sample rate the committed source exports). Each selected child packages its one
member; followers import and finish it (texture), author it (material) or import and finish it on the character's
Skeleton with the shared compression (clip). The fixed units are the raw body import from the export's fbx/, the
skeletal finish binding the derived materials, and DA_<Name>Base on the derived clips. Cloth is decided by the
committed export hooks and the clip rates by the committed manifest; the projector refuses an export that differs.
``natives = {compression: {unit, item, package}, see_through: {unit, item, package}}`` (the shared MPC_SeeThrough,
for characters whose character.toml names see_through material prefixes).
"""
import ast
from copy import deepcopy
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import (CLIP_FBX, COMPRESSION, MESH_FBX, SCRIPT, SKELETON_MUTATION, VERTEX_COLORS, Unsupported,
                                _check, _code_closure, _definition, _modules, _output)
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, _code

BODY = 'games/yorimichi/world/character_members_v2.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi'
EXTENSIONS = {'materials': ['.json'], 'textures': ['.jpg', '.png'], 'clips': ['.fbx']}
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
SEE_THROUGH = '/Game/SeeThrough/MPC_SeeThrough'


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('character_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / 'games/yorimichi/world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def cloth(character):
    """Whether the committed export hooks report a cloth (pipeline/export.py export_hooks.body)."""
    hooks = character.folder / 'export_hooks.py'
    if not hooks.is_file():
        return False
    for node in ast.walk(ast.parse(hooks.read_bytes())):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'report'
                        and isinstance(target.slice, ast.Constant) and target.slice.value == 'cloth'):
                    return True
    return False


def rates(character):
    """The sample rates of the clips pipeline/export.py exports, from the committed manifest roles, [export] clips
    and the donor's taken clips: per action the largest role export_sample_rate, else the character's fps."""
    manifest = character.manifest() if callable(character.manifest) else character.manifest
    roles = manifest.get('roles', [])
    by_action = {}
    for role in roles:
        by_action.setdefault(role['clip'], role['role'])
    by_action.update(character.export['clips'])
    wanted = character.donor and character.donor['clips'] + character.donor['gestures']
    return sorted({max((r.get('export_sample_rate', character.fps) for r in roles if r['clip'] == action),
                       default=character.fps) for action, name in by_action.items() if not wanted or name in wanted})


def _export(row, k, output):
    paths = [f'{OUT}/{output}/{name}' for name in ('export.json', 'fbx', 'textures')]
    found = [i for i, p in enumerate(row['products']) if p['id'] == f'characters.{k}.export']
    if (len(found) != 1 or [str(p) for p in row['products'][found[0]]['paths']] != paths
            or row['products'][found[0]]['optional_paths']):
        raise Unsupported(f'characters.{k} must own its complete export Product (export.json, fbx, textures)')
    index = found[0]
    return f'product{index}', {name: f'products/{index}-{j}.tree.tar' for j, name in enumerate(('export.json', 'fbx', 'textures'))}


def token(k, kind, templates):
    return {'derived_items': {'root': f'build/v2-derived/characters/{k}/{kind}', 'templates': [
        {'producer': f'characters.{k}.members.{group}', 'group': 'members', 'unit_prefix': prefix, 'follower': follower,
         'item': item} for group, prefix, follower, item in templates]}}


def character_templates(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-character-generated-native-members
    Each character's actual complete export Product MUST author FileSet members
    before keys: material entries, exported images and clip FBX bytes in groups
    fixed by committed source. Every member has one selected child and its
    original texture/material/clip followers. The skeletal finish, base and clip
    closure MUST bind actual derived Items, never invented IDs or keyed rosters.
    Generated content is never scanned at declaration; the original never runs.
    """
    root = Path(checkout).resolve()
    definition = _definition(root)
    by_id = {row['id']: row for row in rows}
    targets = {row['id']: row for row in rows if any(c.get('script') == {'path': 'games/yorimichi/unreal/Scripts/import_character.py'}
                                                     for c in row['commands'])}
    characters = [c for c in definition.movers() if f"unreal.{c.id.replace('-', '_')}" in targets]
    if len(characters) != len(targets):
        raise Unsupported('character targets without a definition')
    compression = (natives or {}).get('compression')
    if (not isinstance(compression, dict) or not {'unit', 'item', 'package'} <= set(compression)
            or compression['package'] != COMPRESSION):
        raise Unsupported('missing the shared CharacterCompression owner Item')
    scanner, recipe_code = ImportScanner(), set()
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / 'platform/studio', root / 'games/yorimichi/world')))
    recipe_code = sorted(recipe_code | {BODY})
    code, ops_code = _code_closure(root), list(_code(root))
    units, staged, packages, aliases, requirements, plugins, effects = [], {}, {}, {}, {}, {}, []
    templates, groups, tokens = [], {}, {}

    def add(unit, inputs, roots=None, modules=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if modules:
            requirements[unit['id']], needed = modules
            if needed:
                plugins[unit['id']] = needed

    for character in characters:
        k, name, dest, settings = character.id.replace('-', '_'), character.name, character.unreal_path, character.unreal
        _check(targets[f'unreal.{k}'], character)
        producer = by_id.get(f'characters.{k}')
        if not producer or producer['commands'][0].get('script') != {'path': 'games/yorimichi/assets/characters/pipeline/export.py'}:
            raise Unsupported(f'characters.{k} differs from the original pipeline/export.py body export')
        export_item, archives = _export(producer, k, character.output)
        export = lambda slot='export': _item(slot, producer['id'], export_item)
        export_root = {'archive_member': archives['export.json'], 'name': 'export.json'}
        has_cloth, clip_rates, morphs = cloth(character), rates(character), bool(settings['morph_targets'])
        kinds = ['materials', 'textures', *(f'clips_{rate}' for rate in clip_rates)]
        base_out = f'{OUT}/{character.output}'
        paths = {f'{base_out}/{n}': 'inputs/export/' + archives[n] for n in ('export.json', 'fbx', 'textures')}
        own = []
        for kind in kinds:
            folder, parent = f'generated/characters/{k}/{kind}', f'{name}_{kind}'
            producer_id = f'characters.{k}.members.{kind}'
            contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                        'adapter_version': 'd2.file-set/1', 'parent': parent, 'encoding': 'file_set', 'class': 'Data',
                        'logical_namespace': f'/Internal/Characters/{k}/{kind}', **LIMITS}
            incoming = export()
            incoming['whole'] = 'The complete export Item validates its body, clips, textures and cloth before selecting members.'
            add({'id': producer_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
                 'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                     'commands': [_call(root, 'project', (root / base_out / 'export.json', root / base_out / 'fbx',
                                                          root / base_out / 'textures', root / folder, kind, name,
                                                          has_cloth, tuple(clip_rates)))],
                     'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                     'file_group': {'source': folder, 'parent': parent, 'extensions': EXTENSIONS[kind.split('_')[0]]}}},
                 'outputs': [{'id': 'archive', 'logical_path': f'/Internal/Characters/{k}/{kind}', 'class': 'Data',
                              'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
                 'output_groups': [contract]}, [incoming])
            groups[producer_id] = {'contract': contract, 'source': folder}
            own.append(producer_id)
        prefix = {kind: f'unreal.character.{k}.{kind}' for kind in kinds}
        textures = token(k, 'textures', [('textures', prefix['textures'], 1, 'texture')])
        materials = token(k, 'materials', [('materials', prefix['materials'], 0, 'asset')])
        clips = token(k, 'clips', [(kind, prefix[kind], 1, 'animation') for kind in kinds if kind.startswith('clips_')])
        tokens[character.id] = {'materials': materials, 'textures': textures, **({'clips': clips} if clip_rates else {})}
        raw_id, mesh_id = f'unreal.character.{k}.raw', f'unreal.character.{k}.mesh'
        raw_mesh, mesh_package = f'/Game/_Raw/Characters/{k}/SK_{name}', f'{dest}/SK_{name}'
        selected = {'archive_member': 'member.tree.tar', 'name': 'member'}

        def template(kind, followers):
            templates.append({'producer': f'characters.{k}.members.{kind}', 'group': 'members', 'unit_prefix': prefix[kind],
                'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code, 'derive_payload': False,
                'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
                'logical_namespace': f'/Internal/Characters/{k}/Selected/{kind}',
                'files': [{'path': 'member.tree.tar', 'required': True}],
                'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                    'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece'))],
                    'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'member.tree.tar', 'required': True}]}},
                'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                              for unit in followers]})

        texture_raw = f'/Game/_Raw/Characters/{k}/Textures/$piece'
        template('textures', [
            {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('source', '$export', 'asset')],
             'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': texture_raw,
                        'input_roots': {'source': dict(selected)}},
             'outputs': [_output('raw_texture', texture_raw, 'RawTexture', store=True)]},
            {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('raw', '$previous', 'raw_texture')],
             'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': f'{dest}/Textures/$piece',
                        'package_sources': {'raw': texture_raw}, 'properties': {}},
             'outputs': [_output('texture', f'{dest}/Textures/$piece', 'Texture')]}])
        material_inputs, material_args = [export()], {}
        prefixes = list(character.toml.get('see_through', ()))
        if prefixes:
            # unreal.see_through's patch, inside each matching material's own owner, on the shared collection.
            shared = (natives or {}).get('see_through')
            if not isinstance(shared, dict) or not {'unit', 'item', 'package'} <= set(shared) or shared['package'] != SEE_THROUGH:
                raise Unsupported(f'{character.id}: see-through materials need the shared {SEE_THROUGH} owner Item')
            material_inputs.append(_item('see_through', shared['unit'], shared['item']))
            material_args['see_through'] = {'prefixes': prefixes, 'collection': 'see_through'}
        template('materials', [
            {'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'inputs': material_inputs,
             'params': {'input_roots': {'export': dict(export_root)}, 'settings': [],
                        'args': {'action': 'material', 'name': '$piece', 'dest': dest, 'morphs': morphs, 'export': 'export',
                                 'textures': deepcopy(textures), **material_args}},
             'outputs': [_output('asset', f'{dest}/$piece', 'Material')]}])
        for rate in clip_rates:
            fbx = {**CLIP_FBX, 'custom_sample_rate': rate}
            if morphs:
                fbx.update(delete_existing_morph_target_curves=True, do_not_import_curve_with_zero=False)
            clip_raw = f'/Game/_Raw/Characters/{k}/A_$piece'
            template(f'clips_{rate}', [
                {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'inputs': [_item('source', '$export', 'asset'), _item('skeleton', mesh_id, 'skeleton')],
                 'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': clip_raw,
                            'skeleton': 'skeleton', 'fbx': fbx, 'input_roots': {'source': dict(selected)}},
                 'outputs': [_output('raw_animation', clip_raw, 'RawAnimation', store=True)]},
                {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'inputs': [_item('raw', '$previous', 'raw_animation'), _item('skeleton', mesh_id, 'skeleton'),
                            _item('mesh', mesh_id, 'mesh'), _item('compression', compression['unit'], compression['item']),
                            export()],
                 'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': f'{dest}/A_$piece',
                            'input_roots': {'export': dict(export_root)},
                            'args': {'action': 'clip', 'name': '$piece', 'export': 'export', 'skeleton': 'skeleton',
                                     'mesh': 'mesh', 'compression': 'compression',
                                     'closure': {'materials': deepcopy(materials), 'textures': deepcopy(textures)}}},
                 'outputs': [_output('animation', f'{dest}/A_$piece', 'Animation')]}])
            if morphs:
                effects.append({'unit_prefix': prefix[f'clips_{rate}'], 'follower': 0,
                                'input': f'{mesh_package}_Skeleton', 'refusal': SKELETON_MUTATION})
        fbx = dict(MESH_FBX)
        if morphs:
            fbx['import_morph_targets'] = True
        if settings['vertex_colors']:
            fbx.update(VERTEX_COLORS)
        physics = bool(settings['physics_asset'])
        raw_outputs = [_output('raw_mesh', raw_mesh, 'RawSkeletalMesh', store=True),
                       _output('raw_skeleton', raw_mesh + '_Skeleton', 'Skeleton', store=True)]
        if physics:
            raw_outputs.append(_output('raw_physics_asset', raw_mesh + '_PhysicsAsset', 'PhysicsAsset', store=True))
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'skeletal_mesh', 'source': 'source', 'destination': raw_mesh,
                        'create_physics_asset': physics, 'fbx': fbx, 'source_member': name + '.fbx'},
             'outputs': raw_outputs}, [export('source')], {'source': {'archive_member': archives['fbx'], 'name': 'fbx'}})
        inputs = [_item('raw', raw_id, 'raw_mesh'), _item('raw_skeleton', raw_id, 'raw_skeleton'), export()]
        if physics:
            inputs.append(_item('raw_physics_asset', raw_id, 'raw_physics_asset'))
        partners = {'skeleton': f'{mesh_package}_Skeleton'}
        outputs = [_output('mesh', mesh_package, 'SkeletalMesh'), _output('skeleton', partners['skeleton'], 'Skeleton')]
        if physics:
            partners['physics_asset'] = f'{mesh_package}_PhysicsAsset'
            outputs.append(_output('physics_asset', partners['physics_asset'], 'PhysicsAsset'))
        args = {'action': 'mesh', 'name': name, 'dest': dest, 'export': 'export', 'materials': deepcopy(materials),
                'closure': {'textures': deepcopy(textures)}, 'cpu_access': bool(settings['cpu_access']), 'morphs': morphs,
                'contact_morphs': list(settings['contact_morphs'])}
        if has_cloth:
            args['cloth_package'] = f'{dest}/PA_{name}_Cloth'
            outputs.append(_output('cloth', args['cloth_package'], 'PhysicsAsset'))
        add({'id': mesh_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'op': 'finish', 'kind': 'skeletal_mesh', 'source': 'raw', 'destination': mesh_package,
                        'partners': partners, 'args': args}, 'outputs': outputs},
            inputs, {'export': dict(export_root)}, _modules(root, list(settings['modules'])))
        for output in outputs[1:]:
            packages[output['logical_path']] = {'unit': mesh_id, 'item': output['id'], 'package': output['logical_path']}
        packages[mesh_package] = {'unit': mesh_id, 'item': 'mesh', 'package': mesh_package,
                                  'dependencies': [dict(packages[o['logical_path']]) for o in outputs[1:]],
                                  'derived_dependencies': {'materials': deepcopy(materials), 'textures': deepcopy(textures)}}
        base_package, base_id = f'{dest}/DA_{name}Base', f'unreal.character.{k}.base'
        add({'id': base_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'base', 'name': f'DA_{name}Base', 'dest': dest, 'export': 'export', 'mesh': 'mesh',
                                 'clips': deepcopy(clips) if clip_rates else {},
                                 'closure': {'materials': deepcopy(materials), 'textures': deepcopy(textures)},
                                 'camera_height': float(settings['camera_height'])}, 'settings': []},
             'outputs': [_output('asset', base_package, 'WandererDefinition')]},
            [_item('mesh', mesh_id, 'mesh'), export(),
             *(_item('native_' + p.removeprefix('/Game/').replace('/', '_'), mesh_id, packages[p]['item'])
               for p in (o['logical_path'] for o in outputs[1:]))],
            {'export': dict(export_root)}, _modules(root, ['Yorimichi']))
        packages[base_package] = {'unit': base_id, 'item': 'asset', 'package': base_package,
                                  'dependencies': [dict(packages[mesh_package])],
                                  'derived_dependencies': {'clips': deepcopy(clips)} if clip_rates else {}}
        aliases[f'unreal.{k}'] = (*own, raw_id, mesh_id, base_id)
    return {'units': units, 'staged_inputs': staged, 'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'aliases': aliases, 'module_requirements': requirements, 'plugin_requirements': plugins,
            'runtime_refusals': effects, 'templates': templates, 'groups': groups, 'tokens': tokens}
