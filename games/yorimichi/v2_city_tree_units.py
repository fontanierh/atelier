"""C3 owners for unreal.city_tree_lods (Scripts/import_city_tree_atomic.py) on the actual city tree templates.

The three committed tree parents (regions/hidamari/tree_policy.TREES) are city surface parents: each exported child
<P><sfx> of world.hidamari.export.<P> is finished by the city followers (v2_city_units) at
/Game/Experiments/CitySurfaces/v1_128m/<P><sfx>. Their bounded lower levels are the children <P>_LOD<n><sfx> of
world.city_tree_lods.export.<P>_LOD<n>. Here:
- each lower-level child gains a store-only raw import of its FBX and a finish to
  /Game/Experiments/CityTrees/v4/lods/<P>_LOD<n><sfx> on the parent's original material, checked against its own
  export receipt (triangles, bounds within 0.2 cm) with full-precision UVs and no collision;
- each city tree child gains a third follower: /Game/Experiments/CityTrees/v4/<P><sfx>_v4, a fresh duplicate of
  its city-finished original ($previous) with its two finished lower levels (a derived token whose piece maps
  <P> to <P>_LOD<n>), the original's LOD, material, bounds, collision and screen-size checks;
- one record writes city_tree_lods/v4/import-report.json from the finished trees.
``natives`` {package: {unit, item, dependencies?}} supplies the parents' original material and its closure.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/city_tree_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_city_tree_atomic.py'
EMPTY = GAME + '/unreal/Scripts/import_city_surface_tiles.py'
POLICY = GAME + '/world/regions/hidamari/tree_policy.py'
SURFACES = '/Game/Experiments/CitySurfaces/v1_128m'
DEST = '/Game/Experiments/CityTrees/v4'
REPORT = 'build/yorimichi/city_tree_lods/v4/import-report.json'
RECORD_UNIT = 'unreal.city_tree_lods.record'
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}
# import_city_tree_atomic.py runs both console commands before importing.
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def policy(checkout):
    """tree_policy's committed TREES and SCREEN_SIZES."""
    module = _load(Path(checkout), POLICY, 'city_tree_v2_policy')
    if len(module.TREES) != 3 or len(module.SCREEN_SIZES) != 3:
        raise Unsupported('City tree policy differs from three parents with three screen sizes')
    return tuple(module.TREES), list(module.SCREEN_SIZES)


def _files(package, *, store):
    stem = package.removeprefix('/Game/')
    rows = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = GAME + '/unreal/Content/' + stem + suffix
        rows.append(row)
    return rows


def _output(item, package, cls, *, store=False):
    return {'id': item, 'logical_path': package, 'class': cls, 'destination': 'store' if store else 'checkout',
            'files': _files(package, store=store)}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def lod_token(parent, level):
    """The finished lower level of the selected base piece: the LOD template's child <parent>_LOD<level><sfx>."""
    key = f'{parent}_LOD{level}'
    return {'derived_items': {'root': f'build/v2-derived/city_trees/{parent}/lod{level}', 'templates': [
        {'producer': f'world.city_tree_lods.geometry.{key}', 'group': 'geometry',
         'unit_prefix': f'world.city_tree_lods.export.{key}', 'follower': 1, 'item': 'mesh',
         'piece': {'value': '$piece', 'replace_prefix': {'from': parent, 'to': key}}}]}}


def _check(rows):
    row = {r['id']: r for r in rows}.get('unreal.city_tree_lods')
    commands = (row or {}).get('commands') or [{}]
    if (row is None or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('marker') != 'CITY ATOMIC TREE LODS IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or row.get('outputs')):
        raise Unsupported('unreal.city_tree_lods differs from the original import_city_tree_atomic.py target')
    products = {p['id']: p['paths'] for p in row.get('products', ())}
    if products != {'city.native_tree_lods': [GAME + '/unreal/Content/Experiments/CityTrees/v4'],
                    'city.native_tree_report': [REPORT]}:
        raise Unsupported('unreal.city_tree_lods Products differ from its folder and report')


def _closure(natives, package):
    """The native material's Item and its transitive dependencies, as staged consumer inputs."""
    order, seen, stack = [], set(), [package]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        ref = (natives or {}).get(current)
        if (not isinstance(ref, dict) or not {'unit', 'item'} <= set(ref) or ref.get('package', current) != current
                or not all(isinstance(ref[k], str) and ref[k] for k in ('unit', 'item'))):
            raise Unsupported('missing exact native Item for ' + current)
        order.append((current, ref))
        stack.extend(d if isinstance(d, str) else d['package'] for d in ref.get('dependencies', ()))
    return order


def attach_followers(geometry, *, rows, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] city-tree-lod-native-followers
    Every lower-level tree child MUST be finished from its own export child on the
    parent's original material at its own lods/ package. Every city tree child MUST
    own exactly its <piece>_v4 package as a fresh duplicate of its city-finished
    original with its own two finished lower levels and the original's checks.
    Natives stay read-only; no namespace inventory, protected-file scan, original
    main or retirement MAY run, and no sibling is keyed by an invented ID.
    """
    root = Path(checkout).resolve()
    _check(rows)
    trees, sizes = policy(root)
    city = _load(root, GAME + '/city_atomic_products.py', 'city_tree_v2_city')
    if city.DESTINATION != SURFACES:
        raise Unsupported('City surface destination differs')
    from atelier.source_imports import ImportScanner
    scanner = ImportScanner()
    code = {*_code(root), SCRIPT, EMPTY}
    code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
        root / SCRIPT, (root / 'platform/studio', root / GAME / 'world')))
    code = sorted(code)
    ops_code = list(_code(root))
    descriptor = json.loads((root / GAME / 'unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry)
    requirements = dict(result.get('module_requirements', {}))
    templates = {t['unit_prefix']: t for t in result['templates']}
    tokens = []
    for parent in trees:
        (material,) = city.piece_material_paths(parent, ['Palette']).values()
        closure = _closure(natives, material)
        native_inputs = [_item('native_' + p.removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])
                         for p, ref in closure]
        material_slot = native_inputs[0]['name']
        for level in (1, 2):
            prefix = f'world.city_tree_lods.export.{parent}_LOD{level}'
            template = templates.get(prefix)
            if (template is None or template['producer'] != f'world.city_tree_lods.geometry.{parent}_LOD{level}'
                    or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                    or template['params'] != {'format': 'fbx', 'options': {}}
                    or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
                raise Unsupported(prefix + ': lower-level template differs from the FBX export child')
            raw_package, package = '/Game/_Raw/CityTrees/$piece', f'{DEST}/lods/$piece'
            raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                   'inputs': [_item('source', '$export', 'asset')],
                   'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                              'fbx': dict(FBX), 'settings': list(SETTINGS)},
                   'outputs': [_output('raw_static_mesh', raw_package, 'RawStaticMesh', store=True)]}
            inputs = [_item('raw', '$previous', 'raw_static_mesh'), _item('export', '$export', 'asset'), *deepcopy(native_inputs)]
            finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                      'inputs': inputs,
                      'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                                 'args': {'action': 'lod', 'parent': parent, 'level': level, 'piece': '$piece',
                                          'export': 'export', 'material': material_slot},
                                 'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                      'outputs': [_output('mesh', package, 'StaticMesh')]}
            template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                     {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
            requirements[prefix] = modules
        prefix = f'world.hidamari.export.{parent}'
        template = templates.get(prefix)
        followers = (template or {}).get('followers') or []
        if (len(followers) != 2 or [f['unit']['id'] for f in followers] != ['$export.raw', '$export.finish']
                or followers[1]['unit']['outputs'][0]['id'] != 'asset'
                or followers[1]['unit']['outputs'][0]['logical_path'] != SURFACES + '/$piece'):
            raise Unsupported(prefix + ': the city tree parent must carry exactly the city raw and finish followers')
        package = f'{DEST}/$piece_v4'
        inputs = [_item('original', '$previous', 'asset'), _item('export', '$export', 'asset'),
                  _item('parent', f'unreal.city.parent.{parent}', 'parent'), *deepcopy(native_inputs)]
        base = {'id': '$export.tree', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                'inputs': inputs,
                'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'original', 'destination': package,
                           'args': {'action': 'base', 'parent': parent, 'piece': '$piece', 'export': 'export',
                                    'facts': 'parent', 'material': material_slot, 'screen_sizes': list(sizes),
                                    'lods': {'1': lod_token(parent, 1), '2': lod_token(parent, 2)}},
                           'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                'outputs': [_output('mesh', package, 'StaticMesh')]}
        template['followers'] = [*followers, {'unit': base, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        tokens.append({'producer': f'world.hidamari.geometry.{parent}', 'group': 'geometry', 'unit_prefix': prefix,
                       'follower': 2, 'item': 'mesh'})
    record = {'id': RECORD_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code, 'inputs': [],
              'params': {'args': {'action': 'record', 'screen_sizes': list(sizes),
                                  'trees': {'derived_items': {'root': 'build/v2-derived/city_trees/record', 'templates': tokens}}},
                         'settings': []},
              'outputs': [{'id': 'record', 'logical_path': '/Internal/CityTrees/Report', 'class': 'JsonData', 'destination': 'store',
                           'files': [{'path': 'data/import-report.json', 'required': True}]}]}
    requirements[RECORD_UNIT] = modules
    result['module_requirements'] = requirements
    return {'geometry': result, 'units': [record], 'staged_inputs': {RECORD_UNIT: {}},
            'content_slots': {name: False for name in ('source', 'raw', 'export', 'original', 'parent')},
            'packages': {REPORT: {'unit': RECORD_UNIT, 'item': 'record'}},
            'aliases': {'unreal.city_tree_lods': (RECORD_UNIT,)}}
