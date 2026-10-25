"""C3 owners for unreal.bike: each Bike part's exported child imported and finished on M_Bike, then the report.

Scripts/import_bike.py imports the eleven independent Bike parts from the combined world.bike library onto M_Bike,
checks each against its construction report, persists the complete steering group's bounds on its four children
and writes bike/import-report.json. Here each part's existing vehicle_bike D2 export template (one per committed
vehicle_sources.FAMILIES['bike'] builder) gains two followers: a store-only raw static-mesh import of the child's FBX
with mesh_import's legacy options, and a finish to /Game/Japan/Assets/<part> on M_Bike with the original checks
against the part's own construction report (vehicle_bike.report.<part>) and export receipt. The four steering parts
are mutated jointly (their group bounds), so one steering unit owns their four packages as four Items, from their
raw imports and export children (derived tokens over their templates).
M_Bike is the original bike_material.material, called through the native author body unless a caller supplies its
sole owner. One record unit writes the report from the finished parts.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
FINISH = GAME + '/world/bike_finish_v2.py'
AUTHOR = GAME + '/world/native_author_call_v2.py'
SOURCE = GAME + '/unreal/Scripts/bike_material.py'
ORIGINAL = GAME + '/unreal/Scripts/import_bike.py'
PRODUCTS = GAME + '/bike_atomic_products.py'
MATERIAL = '/Game/Japan/Materials/M_Bike'
MATERIAL_UNIT = 'unreal.bike.material.M_Bike'
RECORD_UNIT = 'unreal.bike.record'
STEERING_UNIT = 'unreal.bike.steering'
RECORD = 'data/import-report.json'
DEST = '/Game/Japan/Assets'
RAW = '/Game/_Raw/Bike'
REGION = 'vehicle_bike'
REPORT_OUT = 'build/yorimichi/bike/import-report.json'
# mesh_import.import_mesh's legacy FBX static-mesh options, which import_bike.py uses.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}
# import_bike.py runs `Interchange.FeatureFlags.Import.FBX 0` and `Editor.AsyncStaticMeshCompilation 0` first.
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def roster(checkout):
    """bike_atomic_products' committed PARTS and STEERING, checked against vehicle_sources' bike builders."""
    import ast
    root = Path(checkout)
    tree = ast.parse((root / PRODUCTS).read_bytes(), filename=PRODUCTS)
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) in ('STEERING', 'OTHER'):
            names[node.targets[0].id] = ast.literal_eval(node.value)
    sources = _load(root, GAME + '/world/vehicle_sources.py', 'bike_source_roster')
    steering, other = names.get('STEERING'), names.get('OTHER')
    if (not isinstance(steering, tuple) or not isinstance(other, tuple) or len(steering) != 4
            or set(steering) | set(other) != set(sources.FAMILIES['bike']['builders']) or set(steering) & set(other)):
        raise Unsupported('bike_atomic_products roster differs from the committed bike builders')
    return (*other, *steering), steering


def _files(package, *, store):
    stem = package.removeprefix('/Game/')
    rows = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = GAME + '/unreal/Content/' + stem + suffix
        rows.append(row)
    return rows


def _item(name, unit, item):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item}}


def _check(rows, parts):
    """The original unreal.bike row with its three Products, and each part's construction report Product."""
    by_id = {row['id']: row for row in rows}
    row = by_id.get('unreal.bike')
    commands = (row or {}).get('commands') or [{}]
    if (row is None or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL} or commands[0].get('marker') != 'BIKE IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or row.get('outputs')):
        raise Unsupported('unreal.bike differs from the original Bike import')
    products = {p['id']: p for p in row.get('products', ())}
    meshes = [f'{GAME}/unreal/Content/Japan/Assets/{key}.uasset' for key in parts]
    if (set(products) != {'bike.native_meshes', 'bike.native_material', 'bike.native_report'}
            or sorted(products['bike.native_meshes']['paths']) != sorted(meshes)
            or products['bike.native_material']['paths'] != [f'{GAME}/unreal/Content/Japan/Materials/M_Bike.uasset']
            or products['bike.native_report']['paths'] != [REPORT_OUT]):
        raise Unsupported('unreal.bike Products differ from the original eleven parts, M_Bike and report')
    reports = {}
    for key in parts:
        producer = by_id.get(f'world.{REGION}.geometry.{key}')
        found = [i for i, p in enumerate((producer or {}).get('products', ())) if p['id'] == f'{REGION}.report.{key}']
        if len(found) != 1 or len(producer['products'][found[0]]['paths']) != 1:
            raise Unsupported(key + ': construction report Product is not its one file')
        reports[key] = (producer['id'], f'product{found[0]}', f'products/{found[0]}-0.tree.tar')
    return reports


def _material(root, natives):
    """The sole M_Bike owner: the caller's, or the original bike_material.material via the native author body."""
    supplied = (natives or {}).get('M_Bike')
    if supplied is not None:
        if (not isinstance(supplied, dict) or set(supplied) != {'unit', 'item', 'package'} or supplied['package'] != MATERIAL
                or any(not isinstance(supplied[k], str) or not supplied[k] for k in ('unit', 'item'))):
            raise Unsupported('supplied M_Bike must be its exact finished owner reference')
        return None, dict(supplied)
    from atelier.source_imports import ImportScanner
    roots = (root / GAME / 'unreal/Scripts', root / GAME / 'world', root / GAME, root / 'platform/studio')
    code = {*_code(root), AUTHOR, SOURCE}
    for source in (AUTHOR, SOURCE):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / source, roots))
    for relative in code:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise Unsupported('missing or linked M_Bike keyed source: ' + relative)
    unit = {'id': MATERIAL_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': AUTHOR, 'code': sorted(code),
            'inputs': [], 'params': {'args': {'module': SOURCE, 'function': 'material', 'arguments': [],
                                              'keyword_arguments': {}, 'expected_package': MATERIAL}, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': MATERIAL, 'class': 'Material', 'destination': 'checkout',
                         'files': _files(MATERIAL, store=False)}]}
    return unit, {'unit': MATERIAL_UNIT, 'item': 'asset', 'package': MATERIAL}


def token(parts, *, follower, item, root):
    """The derived roster of the given parts' followers, or (follower None) their export children, resolved by the
    controller after expansion."""
    return {'derived_items': {'root': root, 'templates': [
        {'producer': f'world.{REGION}.geometry.{key}', 'group': 'geometry', 'unit_prefix': f'world.{REGION}.export.{key}',
         **({} if follower is None else {'follower': follower}), 'item': item} for key in parts]}}


def attach_followers(geometry, *, rows, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] bike-part-native-followers
    Each committed Bike part MUST be finished from its own existing vehicle_bike
    export child: a store-only raw import with mesh_import's legacy FBX options,
    then exactly /Game/Japan/Assets/<part> on the sole M_Bike owner with
    import_bike.py's checks against its own construction report and receipt.
    The four steering packages MUST have one joint owner with four Items. It MUST NOT read the combined world.bike library or run import_bike.py
    main, inventory or retirement. unreal.bike is replaced only by the complete
    eleven parts, M_Bike and the report.
    """
    root = Path(checkout)
    parts, steering = roster(root)
    reports = _check(rows, parts)
    if natives is not None and (not isinstance(natives, dict) or set(natives) - {'M_Bike'}):
        raise Unsupported('Bike accepts only the M_Bike native owner')
    result = deepcopy(geometry)
    templates = {t['unit_prefix']: t for t in result['templates'] if t['unit_prefix'].startswith(f'world.{REGION}.export.')}
    expected = {f'world.{REGION}.export.{key}': key for key in parts}
    if sorted(templates) != sorted(expected):
        raise Unsupported('Bike export templates differ from the committed part roster')
    material_unit, material = _material(root, natives)
    native_code = _code(root)
    finish_code = sorted({*native_code, FINISH})
    descriptor = json.loads((root / GAME / 'unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')}
               for m in descriptor['Modules']]
    requirements = dict(result.get('module_requirements', {}))
    packages = {}
    for prefix, key in expected.items():
        template = templates[prefix]
        if (template['producer'] != f'world.{REGION}.geometry.{key}' or template['group'] != 'geometry'
                or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'] != {'format': 'fbx', 'options': {}}
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise Unsupported(key + ': export template differs from the FBX export child')
        raw_package, package = f'{RAW}/{key}', f'{DEST}/{key}'
        producer, report_item, report_archive = reports[key]
        raw = {'id': f'unreal.bike.raw.{key}', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
               'code': native_code, 'inputs': [_item('source', '$export', 'asset')],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                          'fbx': dict(FBX), 'settings': list(SETTINGS)},
               'outputs': [{'id': 'raw_static_mesh', 'logical_path': raw_package, 'class': 'RawStaticMesh',
                            'destination': 'store', 'files': _files(raw_package, store=True)}]}
        requirements[prefix] = modules
        if key in steering:
            # The four jointly mutated steering packages have one owner (the steering unit below).
            template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}}]
            continue
        args = {'action': 'part', 'part': key, 'piece': '$piece', 'export': 'export', 'report': 'report', 'material': 'material'}
        finish = {'id': f'unreal.bike.{key}', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': finish_code,
                  'inputs': [_item('raw', '$previous', 'raw_static_mesh'), _item('export', '$export', 'asset'),
                             _item('report', producer, report_item), _item('material', material['unit'], material['item'])],
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package, 'args': args,
                             'input_roots': {'report': {'archive_member': report_archive, 'name': 'report.json'}},
                             'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [{'id': 'mesh', 'logical_path': package, 'class': 'StaticMesh', 'destination': 'checkout',
                               'files': _files(package, store=False)}]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in finish['inputs']}}]
        packages[package] = {'unit': finish['id'], 'item': 'mesh', 'package': package, 'dependencies': [dict(material)]}
    ordinary = [key for key in parts if key not in steering]
    joint_inputs = [*(_item('report_' + key, reports[key][0], reports[key][1]) for key in steering),
                    _item('material', material['unit'], material['item'])]
    joint = {'id': STEERING_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': finish_code,
             'inputs': joint_inputs,
             'params': {'args': {'action': 'steering', 'material': 'material', 'reports': {key: 'report_' + key for key in steering},
                                 'raws': token(steering, follower=0, item='raw_static_mesh', root='build/v2-derived/bike/steering/raw'),
                                 'exports': token(steering, follower=None, item='asset', root='build/v2-derived/bike/steering/export')},
                        'input_roots': {'report_' + key: {'archive_member': reports[key][2], 'name': 'report.json'} for key in steering},
                        'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
             'outputs': [{'id': key, 'logical_path': f'{DEST}/{key}', 'class': 'StaticMesh', 'destination': 'checkout',
                          'files': _files(f'{DEST}/{key}', store=False)} for key in steering]}
    requirements[STEERING_UNIT] = modules
    for key in steering:
        packages[f'{DEST}/{key}'] = {'unit': STEERING_UNIT, 'item': key, 'package': f'{DEST}/{key}', 'dependencies': [dict(material)]}
    record_inputs = [*(_item('report_' + key, reports[key][0], reports[key][1]) for key in parts),
                     *(_item('steering_' + key, STEERING_UNIT, key) for key in steering)]
    record = {'id': RECORD_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': FINISH, 'code': finish_code,
              'inputs': record_inputs,
              'params': {'args': {'action': 'record', 'reports': {key: 'report_' + key for key in parts},
                                  'parts': token(ordinary, follower=1, item='mesh', root='build/v2-derived/bike/parts'),
                                  'steering': {key: 'steering_' + key for key in steering}},
                         'input_roots': {'report_' + key: {'archive_member': reports[key][2], 'name': 'report.json'}
                                         for key in parts},
                         'settings': []},
              'outputs': [{'id': 'record', 'logical_path': '/Internal/Bike/Report', 'class': 'JsonData', 'destination': 'store',
                           'files': [{'path': RECORD, 'required': True}]}]}
    requirements[RECORD_UNIT] = modules
    units = [*([material_unit] if material_unit else []), joint, record]
    if material_unit:
        packages[MATERIAL] = dict(material)
    packages[REPORT_OUT] = {'unit': RECORD_UNIT, 'item': 'record'}
    result['module_requirements'] = requirements
    return {'geometry': result, 'units': units,
            'staged_inputs': {unit['id']: {i['name']: 'inputs/' + i['name'] for i in unit['inputs']} for unit in units},
            'content_slots': {'source': False, 'raw': False, 'export': False, 'report': False, 'material': False,
                              **{i['name']: False for unit in units for i in unit['inputs']}},
            'packages': packages,
            'aliases': {'unreal.bike': tuple([*(u['id'] for u in units), *(f'unreal.bike.{key}' for key in ordinary)])}}
