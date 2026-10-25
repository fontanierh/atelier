"""Cold-graph adventure move-set membership through existing FileSet templates (world/moveset_members_v2.py).

Per import_adventure_moveset.py target unreal.<k>_adventure, the generated roster of characters.<k>_adventure's
export Item becomes FileSet groups written by one projector each: ``clips`` (the merged library's clips, at
adventure/bake.py FPS) and, on every character but the donor, ``own`` (the donor's [donor] clips and gestures
retargeted onto it, at the donor's rate). The donor plays its own imported clips (natives['donor']) and declares
no own group. Each selected child unpacks its own member (FBX plus receipt, and its clip metadata); followers import it on the
character's skeleton at the group's committed rate and finish it with the shared compression, each consuming only
its own member, never the whole export. The three speed blends, the merged definition and
the move record are the fixed units of v2_moveset_units, on the derived clip and own Items.
``natives = {reference: {skeleton, glide, equipment, record, export}, <id>: {skeleton, base}, donor: {package: ref}}``.
"""
import ast
from copy import deepcopy
import json
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_geometry_templates import LIMITS
from v2_moveset_units import (BLENDS, COMPRESSION, COMPRESSION_UNIT, FBX, ORIGINAL, SCRIPT, Unsupported, _Inputs, _check,
                              _code_closure, _data_ref, _definition, _files, _modules, _native, compression_unit)
from v2_texture_units import OPS, _code

BODY = 'games/yorimichi/world/moveset_members_v2.py'
BAKE = 'games/yorimichi/assets/characters/adventure/bake.py'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('moveset_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / 'games/yorimichi/world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def bake_fps(root):
    """adventure/bake.py FPS, the rate retarget.py exports every merged clip at."""
    found = [n.value.value for n in ast.parse((root / BAKE).read_bytes()).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'FPS' for t in n.targets) and isinstance(n.value, ast.Constant)]
    if len(found) != 1 or type(found[0]) is not int or found[0] <= 0:
        raise Unsupported('adventure/bake.py no longer defines a literal FPS')
    return found[0]


def _export(row, k, output):
    paths = [f'{OUT}/{output}/adventure/{name}' for name in ('export.json', 'fbx')]
    found = [i for i, p in enumerate(row['products']) if p['id'] == f'characters.{k}_adventure.export']
    if len(found) != 1 or [str(p) for p in row['products'][found[0]]['paths']] != paths or row['products'][found[0]]['optional_paths']:
        raise Unsupported(f'characters.{k}_adventure must own its complete adventure export Product (export.json, fbx)')
    index = found[0]
    return f'product{index}', {'export.json': f'products/{index}-0.tree.tar', 'fbx': f'products/{index}-1.tree.tar'}


def token(k, kind):
    return {'derived_items': {'root': f'build/v2-derived/moveset/{k}/{kind}', 'templates': [
        {'producer': f'characters.{k}_adventure.members.{kind}', 'group': 'members',
         'unit_prefix': f'unreal.moveset.{k}.{kind}', 'follower': 1, 'item': 'animation'}]}}


def moveset_templates(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-adventure-generated-native-members
    Each character's actual complete adventure export Product MUST author FileSet
    members before keys, in clip/own groups fixed by committed rates and the
    committed donor roster; the donor declares no own group. Every member has one
    selected child and its original raw/finish followers on the shared compression.
    Blends, definition and record MUST bind actual derived Items, never invented
    IDs or keyed rosters. Generated content is never scanned; the original never runs.
    """
    root = Path(checkout).resolve()
    definition = _definition(root)
    by_id = {row['id']: row for row in rows}
    targets = {row['id']: row for row in rows if any(c.get('script') == {'path': ORIGINAL} for c in row['commands'])}
    characters = [c for c in definition.movers() if f'unreal.{c.id.replace("-", "_")}_adventure' in targets]
    if len(characters) != len(targets):
        raise Unsupported('move-set targets without an adventure definition')
    for character in characters:
        _check(targets[f'unreal.{character.id.replace("-", "_")}_adventure'], character)
    recipe_code = set()
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / source, (root / 'platform/studio', root / 'games/yorimichi/world')))
    recipe_code = sorted(recipe_code | {BODY})
    code, ops_code, modules = _code_closure(root), list(_code(root)), _modules(root)
    donor_id, donor_spec = definition.movers()[0].id, definition.movers()[0].donor
    fps = bake_fps(root)
    reference = (natives or {}).get('reference') or {}
    units, staged, slots, packages, aliases, requirements = [compression_unit(checkout=root, code=code)], {}, {}, {}, {}, {}
    packages[COMPRESSION] = {'unit': COMPRESSION_UNIT, 'item': 'asset', 'package': COMPRESSION}
    templates, groups, tokens = [], {}, {}

    def add(unit, inputs, module=None):
        unit['inputs'] = inputs.items
        if inputs.roots:
            unit['params']['input_roots'] = dict(inputs.roots)
        units.append(unit)
        staged[unit['id']] = {item['name']: 'inputs/' + item['name'] for item in inputs.items}
        slots.update({item['name']: False for item in inputs.items})
        if module:
            requirements[unit['id']] = [dict(modules[module])]

    def author(unit_id, args, cls, package, inputs, module=None, json_file=None):
        output = {'id': 'record' if json_file else 'asset', 'logical_path': package, 'class': cls, 'destination': 'checkout',
                  'files': _files(package, json_file=json_file)}
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}, 'outputs': [output]}, inputs, module)

    for character in characters:
        k, spec = character.id.replace('-', '_'), character.adventure
        is_donor = character.id == donor_id
        producer = by_id.get(f'characters.{k}_adventure')
        if not producer:
            raise Unsupported(f'missing the actual characters.{k}_adventure export row')
        export_item, archives = _export(producer, k, character.output)
        own_refs = (natives or {}).get(character.id) or {}
        skeleton = _native(own_refs.get('skeleton'), f'{character.id} skeleton')
        base = _native(own_refs.get('base'), f'{character.id} base definition', spec['base'])
        export = {'unit': producer['id'], 'item': export_item, 'root': {'archive_member': archives['export.json'], 'name': 'export.json'}}
        reference_export = _data_ref(reference.get('export'), 'adventure/export.json')
        roster = _data_ref(reference.get('record'), 'Data/adventure/reference.json')
        rates = {'clips': fps, **({} if is_donor else {'own': int(donor_spec['fps'])})}
        name, dest = spec['mesh'].rsplit('/SK_', 1)[1], spec['dest']
        base_out = f'{OUT}/{character.output}/adventure'
        paths = {f'{base_out}/export.json': 'inputs/export/' + archives['export.json'], f'{base_out}/fbx': 'inputs/export/' + archives['fbx']}
        own_ids = []
        for kind, rate in rates.items():
            folder, parent, producer_id = f'generated/moveset/{k}/{kind}', f'{name}_adventure_{kind}', f'characters.{k}_adventure.members.{kind}'
            contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                        'adapter_version': 'd2.file-set/1', 'parent': parent, 'encoding': 'file_set', 'class': 'Data',
                        'logical_namespace': f'/Internal/Moveset/{k}/{kind}', **LIMITS}
            inputs = _Inputs()
            inputs.item('export', producer['id'], export_item)
            inputs.items[-1]['whole'] = 'The complete adventure export validates every rate and FBX before selecting members.'
            add({'id': producer_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
                 'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths), 'verify': None,
                     'commands': [_call(root, 'project', (root / base_out / 'export.json', root / base_out / 'fbx', root / folder,
                                                          kind, dict(rates)))],
                     'outputs': [{'path': folder, 'file': 'members.tree.tar', 'required': True}],
                     'file_group': {'source': folder, 'parent': parent, 'extensions': ['.json']}}},
                 'outputs': [{'id': 'members', 'logical_path': f'/Internal/Moveset/{k}/{kind}', 'class': 'Data',
                              'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
                 'output_groups': [contract]}, inputs)
            groups[producer_id] = {'contract': contract, 'source': folder}
            own_ids.append(producer_id)
            prefix, raw_package = f'unreal.moveset.{k}.{kind}', f'/Game/_Raw/Moveset/{k}/A_$piece'
            package = f'{dest}/A_$piece'
            raw = _Inputs(); raw.item('source', '$export', 'asset'); raw.native('skeleton', skeleton)
            finish = _Inputs(); finish.item('raw', '$previous', 'raw_animation'); finish.native('skeleton', skeleton)
            finish.item('compression', COMPRESSION_UNIT, 'asset'); finish.item('meta', '$export', 'asset')
            followers = [
                {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'inputs': raw.items,
                 'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_package,
                            'skeleton': 'skeleton', 'fbx': {**FBX, 'custom_sample_rate': rate},
                            'input_roots': {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}},
                 'outputs': [{'id': 'raw_animation', 'logical_path': raw_package, 'class': 'RawAnimation',
                              'destination': 'store', 'files': _files(raw_package, store=True)}]},
                {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'inputs': finish.items,
                 'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': package,
                            'input_roots': {'meta': {'archive_member': 'meta.tree.tar', 'name': 'meta'}},
                            'args': {'action': 'clip', 'name': '$piece', 'kind': kind, 'fps': rate, 'meta': 'meta',
                                     'skeleton': 'skeleton', 'compression': 'compression'}},
                 'outputs': [{'id': 'animation', 'logical_path': package, 'class': 'Animation',
                              'destination': 'checkout', 'files': _files(package)}]}]
            templates.append({'producer': producer_id, 'group': 'members', 'unit_prefix': prefix, 'op': dict(RECIPE_OP),
                'script': RECIPE, 'code': recipe_code, 'derive_payload': False, 'payload_slot': 'payload',
                'staged_path': 'inputs/payload', 'output_class': 'Data', 'logical_namespace': f'/Internal/Moveset/{k}/Selected/{kind}',
                'files': [{'path': 'member.tree.tar', 'required': True}, {'path': 'meta.tree.tar', 'required': True}],
                'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                    'commands': [_call(root, 'select', (root / 'selected', root / 'member', root / 'meta', '$piece'))],
                    'outputs': [{'path': 'member', 'file': 'member.tree.tar', 'required': True},
                                {'path': 'meta', 'file': 'meta.tree.tar', 'required': True}]}},
                'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                              for unit in followers]})
        clips, own = token(k, 'clips'), (token(k, 'own') if 'own' in rates else {})
        tokens[character.id] = {'clips': clips, **({'own': own} if own else {})}
        donor = {}
        if is_donor:
            needed = {donor_spec['double_jump'], *(t['clip'] for t in donor_spec['actions'].values())}
            for clip_name in sorted(needed):
                package = f"{donor_spec['folder']}/A_{clip_name}"
                donor[clip_name] = _native(((natives or {}).get('donor') or {}).get(package), 'donor clip', package)
        def common(inputs):
            return {'export': inputs.data('export', export), 'reference_export': inputs.data('reference_export', reference_export)}
        def rosters():
            return {'clips': deepcopy(clips), 'own': deepcopy(own)}
        blends = {}
        for kind, title in BLENDS:
            blend_name = f'BS_{name}Adventure{title}'
            package = f'{dest}/{blend_name}'
            inputs = _Inputs()
            args = {'action': 'blend', 'kind': kind, 'name': blend_name, 'dest': dest,
                    'skeleton': inputs.native('skeleton', skeleton), **common(inputs), 'clips': deepcopy(clips)}
            unit_id = f'unreal.moveset.{k}.blend.{title}'
            author(unit_id, args, 'BlendSpace1D', package, inputs, 'YorimichiImport')
            packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package,
                                 'derived_dependencies': {'clips': deepcopy(clips)}}
            blends[kind] = unit_id
        def donor_inputs(inputs):
            return {clip_name: inputs.native('donor_' + clip_name, ref) for clip_name, ref in donor.items()}
        timing = {'donor_spec': {'double_jump': donor_spec['double_jump'], 'gestures': list(donor_spec['gestures']),
                                 'actions': {a: dict(t) for a, t in donor_spec['actions'].items()}}, 'is_donor': is_donor}
        inputs = _Inputs()
        args = {'action': 'moveset', 'target': spec['definition'], 'base_package': spec['base'],
                'base': inputs.native('base', base), 'keep_base_actions': bool(spec['keep_base_actions']),
                'blends': {kind: inputs.item('blend_' + kind, unit_id, 'asset') for kind, unit_id in blends.items()},
                **common(inputs), 'roster': inputs.data('roster', roster), **rosters(), 'donor': donor_inputs(inputs), **timing}
        moveset_id = f'unreal.moveset.{k}.definition'
        author(moveset_id, args, 'AdventureMoveSet', spec['definition'], inputs, 'Yorimichi')
        packages[spec['definition']] = {'unit': moveset_id, 'item': 'asset', 'package': spec['definition'],
                                        'derived_dependencies': rosters()}
        inputs = _Inputs()
        equipment = [inputs.native(f'equipment_{index}', _native(ref, 'reference equipment mesh'))
                     for index, ref in enumerate(reference.get('equipment') or ())]
        if not equipment:
            raise Unsupported('missing exact native Items for the reference equipment meshes')
        args = {'action': 'record', 'character': character.id, **common(inputs), 'roster': inputs.data('roster', roster),
                'skeleton': inputs.native('skeleton', skeleton),
                'reference_skeleton': inputs.native('reference_skeleton', _native(reference.get('skeleton'), 'reference skeleton')),
                'reference_glide': inputs.native('reference_glide', _native(reference.get('glide'), 'reference glide clip')),
                'equipment': equipment, **rosters(), 'donor': donor_inputs(inputs),
                'fit': json.loads(json.dumps(spec.get('fit', {}))), **timing}
        record_file = f'games/yorimichi/unreal/Content/Data/{character.id}/adventure.json'
        record_id = f'unreal.moveset.{k}.record'
        author(record_id, args, 'JsonData', f'/Game/_Data/{character.id}/adventure', inputs, json_file=record_file)
        packages[record_file] = {'unit': record_id, 'item': 'record'}
        aliases[f'unreal.{k}_adventure'] = (*own_ids, *(u['id'] for u in units if u['id'].startswith(f'unreal.moveset.{k}.')))
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages, 'aliases': aliases,
            'module_requirements': requirements, 'templates': templates, 'groups': groups, 'tokens': tokens}
