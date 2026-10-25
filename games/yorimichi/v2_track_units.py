"""Cold train-track source Items and per-package native owners; root supplies existing Belmonte owners."""
from copy import deepcopy
import importlib.util
import sys
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/track_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_belmonte_track.py'
OUT = 'build/yorimichi/belmonte-track'
DEST = '/Game/BelmonteTrack'
PARENT = '/Game/Belmonte/Materials/M_Belmonte'
GLOW = DEST + '/Materials/M_TK_Glow'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
SETTINGS = ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0,Editor.AsyncStaticMeshCompilation=0']
KINDS = ('materials', 'glow_materials', 'mesh1', 'mesh2', 'mesh3', 'record')


def _item(slot, unit, item):
    return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': unit, 'item': item}}


def _call(root, function, defaults):
    spec = importlib.util.spec_from_file_location('track_v2_declaration', root / SCRIPT)
    module = importlib.util.module_from_spec(spec)
    previous = list(sys.path)
    try:
        sys.path.insert(0, str(root / GAME / 'world'))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    fn = getattr(module, function); fn.__defaults__ = tuple(defaults)
    row = extract([Step('track.body', [Call(function, fn)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def token(kind, follower, item):
    return {'derived_items': {'root': 'build/v2-derived/track/' + kind, 'templates': [
        {'producer': 'track.members.' + kind, 'group': 'members', 'unit_prefix': 'unreal.belmonte_track.' + kind,
         'follower': follower, 'item': item}]}}


def combined(kinds):
    return {'derived_items': {'root': 'build/v2-derived/track/combined_' + '_'.join(k for k, _, _ in kinds), 'templates': [
        token(kind, follower, item)['derived_items']['templates'][0] for kind, follower, item in kinds]}}


def _product(rows, unit, product, expected):
    row = rows.get(unit)
    found = [(i, p) for i, p in enumerate((row or {}).get('products', ())) if p['id'] == product]
    if len(found) != 1 or found[0][1]['optional_paths'] or found[0][1]['paths'] != [expected]:
        raise Unsupported('Track requires the actual complete Product: ' + product)
    index, _ = found[0]
    return _item(product.replace('.', '_'), unit, f'product{index}'), f'products/{index}-0.tree.tar'


def _sources(rows):
    by_id = {r['id']: r for r in rows}; row = by_id.get('unreal.belmonte_track')
    commands = (row or {}).get('commands') or [{}]
    if (not row or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('marker') != 'BELMONTE TRACK IMPORT COMPLETE'
            or commands[0].get('args') != ['-ForceDPCVars=r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0']
            or commands[0].get('env') or row.get('products')
            or row['outputs'] != [GAME + '/unreal/Content/Data/belmonte_track/track.json', OUT + '/runtime/import-report.json']
            or {r['product'] for r in row['reads']} != {'belmonte.materials', 'belmonte.native_materials'}):
        raise Unsupported('unreal.belmonte_track differs from the selected original importer')
    specs = [('world.belmonte_track', 'belmonte_track.library', OUT + '/atomic'),
             ('world.belmonte_track_data', 'belmonte_track.runtime', OUT + '/runtime/track.json'),
             ('world.belmonte.meshes', 'belmonte.materials', 'build/yorimichi/products/belmonte/materials.json')]
    inputs, paths = [], {}
    for unit, product, path in specs:
        incoming, archive = _product(by_id, unit, product, path)
        incoming['whole'] = 'Validate complete declared railway membership before exposing selected package sources.'
        inputs.append(incoming); paths[path] = 'inputs/' + incoming['name'] + '/' + archive
    return inputs, paths


def _natives(natives):
    """Actual supplied package/Item ownership only; recursively retain exact texture tokens and native partners."""
    if not isinstance(natives, dict) or PARENT not in natives:
        raise Unsupported('Track needs the existing M_Belmonte owner and original Belmonte material owners')
    refs = {p: deepcopy(r) for p, r in natives.items() if p.startswith('/Game/Belmonte/Materials/')}
    def closure(selected, prefix):
        inputs, slots, derived, seen, visiting = [], {}, [], set(), set()
        def visit(ref):
            if isinstance(ref, str):
                if ref not in natives: raise Unsupported('Missing transitive Belmonte package owner: ' + ref)
                ref = natives[ref]
            if (not isinstance(ref, dict) or not {'unit', 'item', 'package'} <= set(ref)
                    or any(not isinstance(ref[k], str) or not ref[k] for k in ('unit', 'item', 'package'))
                    or not ref['package'].startswith('/Game/')):
                raise Unsupported('Invalid supplied Belmonte native reference')
            key = (ref['unit'], ref['item'], ref['package'])
            if key in visiting: raise Unsupported('Cyclic supplied Belmonte native dependency')
            if key in seen: return
            visiting.add(key)
            for dependency in ref.get('dependencies', ()): visit(dependency)
            visiting.remove(key); seen.add(key)
            slot = prefix + str(len(inputs)); inputs.append(_item(slot, ref['unit'], ref['item'])); slots[ref['package']] = slot
            tokens = ref.get('derived_dependencies', [])
            if isinstance(tokens, dict): tokens = list(tokens.values())
            for value in tokens:
                if not isinstance(value, dict) or set(value) != {'derived_items'}:
                    raise Unsupported('Belmonte derived closure must retain its actual declared texture token')
                if value not in derived: derived.append(deepcopy(value))
        for package in selected:
            ref = refs[package]
            if ref.get('package') != package: raise Unsupported('Supplied Belmonte package key differs from reference')
            visit(ref)
        return inputs, slots, derived
    parent = closure([PARENT], 'base_')
    materials = [p for p in refs if p != PARENT and '/MI_' in p]
    if not materials: raise Unsupported('Track cannot replace Belmonte materials with a missing-owner fallback')
    all_materials = closure([PARENT, *materials], 'belmonte_')
    return parent, all_materials, materials


def track_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-track-native-declarations
    Actual track library/runtime/Belmonte material-view Items MUST feed keyed
    FileSets and selected native packages. Existing Belmonte owners and their exact
    texture/native closure MUST be supplied, never guessed from future IDs or Content.
    Every author MUST emit one package or one JSON; LOD finishes own one final mesh.
    """
    root = Path(checkout).resolve(); source_inputs, paths = _sources(rows)
    parent, existing, material_packages = _natives(natives)
    roots = (root / 'platform/studio', root / GAME / 'world', root / GAME / 'unreal/Scripts')
    code = {SCRIPT, GAME + '/world/train_v2.py'}
    for path in (SCRIPT, RECIPE, EMITTER):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / path, roots))
    recipe_code = sorted(code); native_code = sorted({*_code(root), SCRIPT, GAME + '/world/train_v2.py', ORIGINAL})
    units, staged, packages, templates, groups = [], {}, {}, [], {}
    def add(unit):
        units.append(unit); staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}
    for kind in KINDS:
        producer, folder = 'track.members.' + kind, 'generated/track/' + kind
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
            'adapter_version': 'd2.file-set/1', 'parent': 'Track_' + kind, 'encoding': 'file_set', 'class': 'Data',
            'logical_namespace': '/Internal/Track/' + kind, **LIMITS}
        add({'id': producer, 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code,
             'inputs': deepcopy(source_inputs), 'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': dict(paths),
                'verify': None, 'commands': [_call(root, 'project', (root / OUT, root / 'build/yorimichi/products/belmonte/materials.json', root / folder, kind))],
                'outputs': [{'kind': 'tree', 'path': folder, 'file': 'members.tree.tar', 'required': True}],
                'file_group': {'source': folder, 'parent': 'Track_' + kind, 'extensions': ['.json']}}},
             'outputs': [{'id': 'archive', 'logical_path': '/Internal/Track/' + kind, 'class': 'Data', 'destination': 'store',
                          'files': [{'path': 'members.tree.tar', 'required': True}]}], 'output_groups': [contract]})
        groups[producer] = {'contract': contract, 'source': folder}
    selected = {'archive_member': 'selected.tree.tar', 'name': 'selected'}
    def template(kind, followers):
        templates.append({'producer': 'track.members.' + kind, 'group': 'members', 'unit_prefix': 'unreal.belmonte_track.' + kind,
            'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code, 'derive_payload': False,
            'payload_slot': 'payload', 'staged_path': 'inputs/payload', 'output_class': 'Data',
            'logical_namespace': '/Internal/Track/Selected/' + kind, 'files': [{'path': 'selected.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece'))],
                'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'selected.tree.tar', 'required': True}]}},
            'followers': [{'unit': u, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in u['inputs']}} for u in followers]})
    glow_id = 'unreal.belmonte_track.glow'
    add({'id': glow_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': native_code,
         'inputs': [], 'params': {'args': {'action': 'glow'}, 'settings': SETTINGS}, 'outputs': [_output('asset', GLOW, 'Material')]})
    packages[GLOW] = {'unit': glow_id, 'item': 'asset', 'package': GLOW}
    for kind, use_glow in [('materials', False), ('glow_materials', True)]:
        inputs, slots, closure = ([_item('glow', glow_id, 'asset')], {GLOW: 'glow'}, []) if use_glow else parent
        template(kind, [{'id': '$export.author', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
            'code': native_code, 'inputs': [_item('meta', '$export', 'asset'), *deepcopy(inputs)],
            'params': {'input_roots': {'meta': dict(selected)}, 'args': {'action': 'material', 'name': '$piece', 'meta': 'meta',
                'parent': slots[GLOW if use_glow else PARENT], 'closure': deepcopy(closure)}, 'settings': SETTINGS},
            'outputs': [_output('asset', DEST + '/Materials/$piece', 'MaterialInstance')]}])
    track_materials = combined([('materials', 0, 'asset'), ('glow_materials', 0, 'asset')])
    for count in (1, 2, 3):
        kind = 'mesh' + str(count); followers = []
        for level in range(count):
            raw = '/Game/_Raw/BelmonteTrack/$piece_LOD' + str(level)
            followers.append({'id': '$export.raw' + str(level), 'op': {'kind': 'unreal.raw_import', 'version': '1'},
                'script': OPS, 'code': _code(root), 'inputs': [_item('source', '$export', 'asset')],
                'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw,
                    'source_member': f'level{level}/source.glb', 'input_roots': {'source': dict(selected)}, 'settings': SETTINGS},
                'outputs': [_output('raw_mesh', raw, 'RawStaticMesh', store=True)]})
        inputs, slots, closure = existing
        followers.append({'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
            'code': native_code, 'inputs': [_item('meta', '$export', 'asset'),
                *(_item(f'level{i}', '$export.raw' + str(i), 'raw_mesh') for i in range(count)), *deepcopy(inputs),
                _item('glow_parent', glow_id, 'asset')],
            'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'level0', 'destination': DEST + '/$piece',
                'input_roots': {'meta': dict(selected)}, 'settings': SETTINGS, 'args': {'action': 'mesh', 'name': '$piece', 'meta': 'meta',
                    'levels': ['level' + str(i) for i in range(count)], 'materials': deepcopy(track_materials),
                    'belmonte': [slots[p] for p in material_packages], 'closure': deepcopy(closure)}},
            'outputs': [_output('mesh', DEST + '/$piece', 'StaticMesh')]})
        template(kind, followers)
    add({'id': 'track.record.selected', 'op': {'kind': 'recipe.python', 'version': '1'}, 'script': RECIPE, 'code': recipe_code,
         'inputs': [{'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': 'track.members.record', 'group': 'members', 'piece': 'Record'}}],
         'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
            'commands': [_call(root, 'select', (root / 'selected', root / 'member', 'Record'))],
            'outputs': [{'kind': 'tree', 'path': 'member', 'file': 'selected.tree.tar', 'required': True}]}},
         'outputs': [{'id': 'selected', 'logical_path': '/Internal/Track/RecordSource', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': 'selected.tree.tar', 'required': True}]}]})
    for field, filename, install in [('runtime', 'track.json', GAME + '/unreal/Content/Data/belmonte_track/track.json'),
                                     ('report', 'import-report.json', None)]:
        inputs, slots, closure = existing; unit_id = 'unreal.belmonte_track.' + field
        output = {'id': field, 'logical_path': '/Game/_Data/belmonte_track/track' if install else '/Internal/Track/Report',
            'class': 'JsonData', 'destination': 'checkout' if install else 'store',
            'files': [{'path': 'data/' + filename, 'required': True, **({'install_path': install} if install else {})}]}
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': native_code,
             'inputs': [_item('meta', 'track.record.selected', 'selected'), *deepcopy(inputs),
                        _item('glow_parent', glow_id, 'asset')],
             'params': {'input_roots': {'meta': dict(selected)}, 'settings': SETTINGS, 'args': {'action': 'record', 'field': field,
                'meta': 'meta', 'meshes': combined([('mesh' + str(i), i, 'mesh') for i in (1, 2, 3)]),
                'materials': deepcopy(track_materials), 'belmonte': [slots[p] for p in material_packages],
                'closure': deepcopy(closure)}}, 'outputs': [output]})
        packages[install or OUT + '/runtime/import-report.json'] = {'unit': unit_id, 'item': field}
    return {'units': units, 'staged_inputs': staged,
        'content_slots': {i['name']: False for u in units for i in u['inputs']} | {'source': False, 'meta': False,
            'level0': False, 'level1': False, 'level2': False}, 'packages': packages,
        'aliases': {'unreal.belmonte_track': ('unreal.belmonte_track.runtime', 'unreal.belmonte_track.report')},
        'module_requirements': {}, 'templates': templates, 'groups': groups}
