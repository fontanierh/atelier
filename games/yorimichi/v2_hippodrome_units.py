"""C3 owners for unreal.hippodrome (Scripts/import_hippodrome.py) on the actual hippodrome export templates.

The region's ten logical parents (regions/hippodrome/atomic: the six SURFACES and layout.STRUCTURES) are
world.hippodrome.export.<parent> encoded-GLB templates; each exported child is one SM_HD_<child>. Here:
- the original materials: T_Grass and T_Dirt from world.hippodrome.textures (raw import, then the original texture
  settings), M_HD_Structure and M_HD_<Surface> by the original functions;
- a FileSet ``paints`` over the whole assembled region (world/hippodrome_members_v2.py): one member per structure
  child with its glTF base-colour map, each followed by a raw texture, its finish and the restyled instance on
  M_HD_Structure (the original imported that glTF material and map and restyled the instance);
- each export child gains a raw GLB import and a finish to /Game/Hippodrome/<child>: a surface child on the four
  surface materials (its receipt names which), a structure child on its own paint instance (exact piece join);
- Content/Data/hippodrome/hippodrome.json from the region data, and hippodrome/import-report.json from the meshes.
"""
import ast
from copy import deepcopy
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/hippodrome_v2.py'
BODY = GAME + '/world/hippodrome_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_hippodrome.py'
REGION_DIR = GAME + '/world/regions/hippodrome'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi'
REGION = OUT + '/hippodrome/region'
TEXTURES = OUT + '/hippodrome_textures'
DATA_FILE = GAME + '/unreal/Content/Data/hippodrome/hippodrome.json'
REPORT_FILE = OUT + '/hippodrome/import-report.json'
ROOT = '/Game/Hippodrome'
RAW = '/Game/_Raw/Hippodrome'
PREFIX = 'world.hippodrome.export.'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
STRUCTURE = ROOT + '/Materials/M_HD_Structure'


def _literal(path, name):
    tree = ast.parse(Path(path).read_bytes(), filename=str(path))
    found = [n.value for n in tree.body if isinstance(n, ast.Assign) and [getattr(t, 'id', None) for t in n.targets] == [name]]
    if len(found) != 1:
        raise Unsupported(f'{path}: no single {name}')
    return found[0]


def parents(checkout):
    """(surface parents, structure parents): atomic.SURFACES and layout.STRUCTURES' SM_HD_* names, read statically."""
    root = Path(checkout)
    surfaces = ast.literal_eval(_literal(root / REGION_DIR / 'atomic.py', 'SURFACES'))
    structures = _literal(root / REGION_DIR / 'layout.py', 'STRUCTURES')
    if not isinstance(structures, ast.Dict) or any(not isinstance(k, ast.Constant) for k in structures.keys):
        raise Unsupported('layout.STRUCTURES is not one literal mapping')
    slugs = [k.value for k in structures.keys]
    return (['SM_HD_' + s for s in surfaces], ['SM_HD_' + ''.join(p.title() for p in slug.split('_')) for slug in slugs])


def surface_specs(checkout):
    """import_hippodrome.SURFACES: {key: (map file or RGB, roughness, two-sided)}."""
    specs = ast.literal_eval(_literal(Path(checkout) / ORIGINAL, 'SURFACES'))
    if not specs or any(not k.startswith('HD_') for k in specs):
        raise Unsupported('import_hippodrome SURFACES differ from HD_* surfaces')
    return specs


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('hippodrome_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _product(by_id, unit, product, paths):
    row = by_id.get(unit)
    found = [i for i, p in enumerate((row or {}).get('products', ())) if p['id'] == product]
    if len(found) != 1 or [str(p) for p in row['products'][found[0]]['paths']] != paths:
        raise Unsupported(f'{unit} must own its {product} Product')
    return f'product{found[0]}', f'products/{found[0]}-0.tree.tar'


def paint_token():
    """The selected child's own restyled instance: the paints child of the same piece."""
    return {'derived_items': {'root': 'build/v2-derived/hippodrome/paints', 'templates': [
        {'producer': 'hippodrome.members.paints', 'group': 'members', 'unit_prefix': 'unreal.hippodrome.paints',
         'follower': 2, 'item': 'asset', 'piece': '$piece'}]}}


def meshes_token(prefixes):
    return {'derived_items': {'root': 'build/v2-derived/hippodrome/meshes', 'templates': [
        {'producer': 'world.hippodrome.geometry.' + p.removeprefix(PREFIX), 'group': 'geometry', 'unit_prefix': p,
         'follower': 1, 'item': 'mesh'} for p in prefixes]}}


def _check(by_id):
    importer = by_id.get('unreal.hippodrome')
    commands = (importer or {}).get('commands') or [{}]
    products = (importer or {}).get('products') or []
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL} or commands[0].get('marker') != 'HIPPODROME IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or [str(o) for o in importer['outputs']] != [DATA_FILE]
            or [(p['id'], [str(x) for x in p['paths']]) for p in products]
            != [('hippodrome.native', [GAME + '/unreal/Content/Hippodrome', REPORT_FILE])]):
        raise Unsupported('unreal.hippodrome differs from the original import_hippodrome.py target')


def attach_followers(geometry, *, rows, checkout):
    """@cc [owner:fontanierh,label:correctness] hippodrome-child-native-followers
    unreal.hippodrome MUST become one owner per /Game/Hippodrome package and its
    data: each exported child of the actual hippodrome templates finished from its
    own raw GLB import and receipt with the original checks, on the original
    surface materials or its own restyled paint (an exact piece join over the
    region's structure members); textures and materials by the original settings
    and functions. It MUST NOT run the original top level, its reuse bookkeeping,
    registry scans or retire, and MUST bind actual derived Items only.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    _check(by_id)
    surface_parents, structure_parents = parents(root)
    specs = surface_specs(root)
    result = deepcopy(geometry)
    templates = {t['unit_prefix']: t for t in result['templates'] if t['unit_prefix'].startswith(PREFIX)}
    if sorted(templates) != sorted(PREFIX + p for p in [*surface_parents, *structure_parents]):
        raise Unsupported('Hippodrome export templates differ from the committed surfaces and structures')
    for prefix, template in templates.items():
        if (template['op'] != {'kind': 'encoded_export_piece', 'version': '1'} or template.get('followers')
                or template['files'] != [{'path': '$piece.glb'}, {'path': 'export.json'}]):
            raise Unsupported(prefix + ': export template differs from the encoded GLB child')
    textures_item, textures_archive = _product(by_id, 'world.hippodrome.textures', 'hippodrome.textures', [TEXTURES])
    region_item, region_archive = _product(by_id, 'world.hippodrome', 'hippodrome.region', [REGION])
    scanner = ImportScanner()
    recipe_code = {BODY}
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world')))
    recipe_code = sorted(recipe_code)
    ops_code = list(_code(root))
    code = sorted({*ops_code, SCRIPT, ORIGINAL})
    editor = _modules(root, [])[0]
    units, staged, packages, requirements = [], {}, {}, {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor
    def stage(unit):
        return {'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}

    structure_id = 'unreal.hippodrome.material.M_HD_Structure'
    add({'id': structure_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'structure'}, 'settings': []},
         'outputs': [_output('asset', STRUCTURE, 'Material')]}, [])
    packages[STRUCTURE] = {'unit': structure_id, 'item': 'asset', 'package': STRUCTURE}
    surface_inputs = {}
    for key, (colour, _, _) in specs.items():
        inputs, args = [], {'action': 'surface', 'key': key}
        dependencies = []
        if isinstance(colour, str):
            name = 'T_' + key[3:]
            raw_package, package = f'{RAW}/Textures/{name}', f'{ROOT}/Textures/{name}'
            raw_id, texture_id = f'unreal.hippodrome.texture.raw.{name}', f'unreal.hippodrome.texture.{name}'
            add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package,
                            'source_member': colour},
                 'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]},
                [_item('source', 'world.hippodrome.textures', textures_item)],
                {'source': {'archive_member': textures_archive, 'name': 'hippodrome_textures'}})
            add({'id': texture_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                            'args': {'action': 'texture'}},
                 'outputs': [_output('texture', package, 'Texture')]}, [_item('raw', raw_id, 'raw_texture')])
            packages[package] = {'unit': texture_id, 'item': 'texture', 'package': package}
            inputs.append(_item('texture', texture_id, 'texture')); args['texture'] = 'texture'
            dependencies.append(dict(packages[package]))
        unit_id, package = f'unreal.hippodrome.material.M_{key}', f'{ROOT}/Materials/M_{key}'
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}, 'outputs': [_output('asset', package, 'Material')]}, inputs)
        packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package, 'dependencies': dependencies}
        surface_inputs[key] = unit_id
    # Structure paints: one member per structure child of the complete assembled region.
    whole = _item('region', 'world.hippodrome', region_item)
    whole['whole'] = 'The complete assembled region checks every child against its report before any paint is selected.'
    generated = 'generated/hippodrome/paints'
    contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                'adapter_version': 'd2.file-set/1', 'parent': 'Hippodrome_paints', 'encoding': 'file_set',
                'class': 'Data', 'logical_namespace': '/Internal/Hippodrome/paints', **LIMITS}
    add({'id': 'hippodrome.members.paints', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'paths': {REGION: 'inputs/region/' + region_archive},
             'verify': None, 'commands': [_call(root, 'project', (root / REGION, sorted(specs), root / generated))],
             'outputs': [{'path': generated, 'kind': 'tree', 'file': 'members.tree.tar', 'required': True}],
             'file_group': {'source': generated, 'parent': 'Hippodrome_paints', 'extensions': ['.json']}}},
         'outputs': [{'id': 'archive', 'logical_path': '/Internal/Hippodrome/paints', 'class': 'Data',
                      'destination': 'store', 'files': [{'path': 'members.tree.tar', 'required': True}]}],
         'output_groups': [contract]}, [whole])
    groups = {'hippodrome.members.paints': {'contract': contract, 'source': generated}}
    member_root = {'archive_member': 'member.tree.tar', 'name': 'member'}
    raw_paint, paint_texture = f'{RAW}/Paints/T_$piece', f'{ROOT}/Meshes/$piece/T_$piece'
    paint_units = [
        {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('source', '$export', 'asset')],
         'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_paint,
                    'input_roots': {'source': dict(member_root)}},
         'outputs': [_output('raw_texture', raw_paint, 'RawTexture', store=True)]},
        {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
         'inputs': [_item('raw', '$previous', 'raw_texture')],
         'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': paint_texture,
                    'package_sources': {'raw': raw_paint}, 'properties': {}},
         'outputs': [_output('texture', paint_texture, 'Texture')]},
        {'id': '$export.paint', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'inputs': [_item('texture', '$previous', 'texture'), _item('master', structure_id, 'asset')],
         'params': {'args': {'action': 'paint', 'name': '$piece', 'texture': 'texture', 'master': 'master'}, 'settings': []},
         'outputs': [_output('asset', f'{ROOT}/Meshes/$piece/MI_$piece', 'MaterialInstance')]}]
    paints = [{
        'producer': 'hippodrome.members.paints', 'group': 'members', 'unit_prefix': 'unreal.hippodrome.paints',
        'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code, 'derive_payload': False, 'payload_slot': 'payload',
        'staged_path': 'inputs/payload', 'output_class': 'Data', 'logical_namespace': '/Internal/Hippodrome/Selected/paints',
        'files': [{'path': 'member.tree.tar', 'required': True}],
        'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
            'commands': [_call(root, 'select', (root / 'selected', root / 'member', '$piece'))],
            'outputs': [{'path': 'member', 'kind': 'tree', 'file': 'member.tree.tar', 'required': True}]}},
        'followers': [stage(unit) for unit in paint_units]}]
    # Every exported child: its raw GLB import and its finished SM_HD_<child>.
    for prefix, template in sorted(templates.items()):
        parent = prefix.removeprefix(PREFIX)
        raw_mesh = f'{RAW}/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
               'inputs': [_item('source', '$export', 'asset')],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_mesh},
               'outputs': [_output('raw_static_mesh', raw_mesh, 'RawStaticMesh', store=True)]}
        inputs = [_item('raw', '$previous', 'raw_static_mesh'), _item('export', '$export', 'asset')]
        args = {'action': 'mesh', 'piece': '$piece', 'export': 'export'}
        if parent in surface_parents:
            inputs += [_item('surface_' + key, unit_id, 'asset') for key, unit_id in surface_inputs.items()]
            args['surfaces'] = {key: 'surface_' + key for key in surface_inputs}
        else:
            inputs.append(_item('master', structure_id, 'asset'))
            args.update(master='master', paint=paint_token(), surface_keys=sorted(specs))
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                  'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': f'{ROOT}/$piece', 'args': args},
                  'outputs': [_output('mesh', f'{ROOT}/$piece', 'StaticMesh')]}
        template['followers'] = [stage(raw), stage(finish)]
    region_root = {'region': {'archive_member': region_archive, 'name': 'region'}}
    data_id, report_id = 'unreal.hippodrome.data', 'unreal.hippodrome.record'
    add({'id': data_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'data', 'region': 'region'}, 'settings': []},
         'outputs': [{'id': 'data', 'logical_path': '/Game/_Data/hippodrome/hippodrome', 'class': 'JsonData',
                      'destination': 'checkout', 'files': [{'path': 'data/hippodrome.json', 'install_path': DATA_FILE, 'required': True}]}]},
        [_item('region', 'world.hippodrome', region_item)], deepcopy(region_root))
    add({'id': report_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'record', 'region': 'region', 'meshes': [meshes_token(sorted(templates))]}, 'settings': []},
         'outputs': [{'id': 'report', 'logical_path': '/Internal/Hippodrome/Report', 'class': 'JsonData', 'destination': 'store',
                      'files': [{'path': 'data/import-report.json', 'required': True}]}]},
        [_item('region', 'world.hippodrome', region_item)], deepcopy(region_root))
    packages[DATA_FILE] = {'unit': data_id, 'item': 'data'}
    packages[REPORT_FILE] = {'unit': report_id, 'item': 'report'}
    slots = {i['name']: False for u in units for i in u['inputs']}
    slots.update({i['name']: False for t in [*result['templates'], *paints] if t.get('followers')
                  for f in t['followers'] for i in f['unit']['inputs']})
    return {'geometry': result, 'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': {'unreal.hippodrome': tuple(u['id'] for u in units)}, 'module_requirements': requirements,
            'templates': paints, 'groups': groups, 'tokens': {'paint': paint_token(), 'meshes': meshes_token(sorted(templates))}}
