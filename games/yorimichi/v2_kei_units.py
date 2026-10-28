"""C3 owners for unreal.kei: each Kei car's exported child imported and finished on M_Village.

Scripts/import_kei.py imports the four Mega Park kei cars from the combined world.kei library onto M_Village and
checks their scale and box collision. Here each car's existing vehicle_kei D2 export template (one per committed
vehicle_sources.FAMILIES['kei'] builder) gains two followers per exported child: a raw static-mesh import of the
child's FBX and a finish to /Game/Japan/Assets/<car> on M_Village, checked against the child's own export.json.
M_Village is the original import_village.material, called through the existing native author body unless a
caller supplies its sole owner.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
FINISH = GAME + '/world/kei_finish_v2.py'
AUTHOR = GAME + '/world/native_author_call_v2.py'
VILLAGE = GAME + '/unreal/Scripts/import_village.py'
ORIGINAL = GAME + '/unreal/Scripts/import_kei.py'
SOURCES = GAME + '/world/vehicle_sources.py'
MATERIAL = '/Game/Japan/Materials/M_Village'
MATERIAL_UNIT = 'unreal.village.material.M_Village'
DEST = '/Game/Japan/Assets'
RAW = '/Game/_Raw/Kei'
REGION = 'vehicle_kei'
# mesh_import.import_mesh's legacy FBX static-mesh options, which import_kei.py uses through import_village.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}
# import_kei.py runs `Interchange.FeatureFlags.Import.FBX 0` before importing.
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false']


def cars(checkout):
    """The committed Kei roster: vehicle_sources.FAMILIES['kei']['builders'] keys, read without running it."""
    import ast
    tree = ast.parse((Path(checkout) / SOURCES).read_bytes(), filename=SOURCES)
    families = [node.value for node in tree.body if isinstance(node, ast.Assign)
                and [getattr(t, 'id', None) for t in node.targets] == ['FAMILIES']]
    if len(families) != 1 or not isinstance(families[0], ast.Dict):
        raise Unsupported('vehicle_sources.FAMILIES is not one literal mapping')
    for key, value in zip(families[0].keys, families[0].values):
        if isinstance(key, ast.Constant) and key.value == 'kei':
            fields = {field.arg: field.value for field in value.keywords} if isinstance(value, ast.Call) else {}
            builders = ast.literal_eval(fields['builders']) if 'builders' in fields else None
            if not isinstance(builders, dict) or not builders or any(not k.startswith('SM_Kei_') for k in builders):
                raise Unsupported('Kei builders are not the original SM_Kei_* roster')
            return sorted(builders)
    raise Unsupported('vehicle_sources declares no kei family')


def _files(package, *, store):
    stem = package.removeprefix('/Game/')
    rows = []
    for suffix in SIDECARS:
        row = {'path': 'content/Game/' + stem + suffix, 'required': suffix == '.uasset'}
        if not store:
            row['install_path'] = GAME + '/unreal/Content/' + stem + suffix
        rows.append(row)
    return rows


def _check(rows):
    selected = [row for row in rows if row['id'] == 'unreal.kei']
    if len(selected) != 1:
        raise Unsupported('unreal.kei needs its one original import row')
    row = selected[0]
    commands = row['commands']
    if (len(commands) != 1 or commands[0]['kind'] != 'UnrealScript' or commands[0]['script'] != {'path': ORIGINAL}
            or commands[0]['marker'] != 'KEI IMPORT COMPLETE' or commands[0]['args'] or commands[0]['env']
            or row['outputs'] or row['products'] or sorted(row['needs']) != ['unreal.world', 'world.kei']):
        raise Unsupported('unreal.kei differs from the original Kei import')


def _material(root, natives):
    """The sole M_Village owner: the caller's, or the original import_village.material via the native author body."""
    supplied = (natives or {}).get('M_Village')
    if supplied is not None:
        if (not isinstance(supplied, dict) or set(supplied) != {'unit', 'item', 'package'} or supplied['package'] != MATERIAL
                or any(not isinstance(supplied[k], str) or not supplied[k] for k in ('unit', 'item'))):
            raise Unsupported('supplied M_Village must be its exact finished owner reference')
        return None, dict(supplied)
    from atelier.source_imports import ImportScanner
    roots = (root / GAME / 'unreal/Scripts', root / GAME / 'world', root / GAME, root / 'platform/studio')
    code = {*_code(root), AUTHOR, VILLAGE}
    for source in (AUTHOR, VILLAGE):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / source, roots))
    for relative in code:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise Unsupported('missing or linked M_Village keyed source: ' + relative)
    unit = {'id': MATERIAL_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': AUTHOR, 'code': sorted(code),
            'inputs': [], 'params': {'args': {'module': VILLAGE, 'function': 'material', 'arguments': [],
                                              'keyword_arguments': {}, 'expected_package': MATERIAL}, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': MATERIAL, 'class': 'Material', 'destination': 'checkout',
                         'files': _files(MATERIAL, store=False)}]}
    return unit, {'unit': MATERIAL_UNIT, 'item': 'asset', 'package': MATERIAL}


def attach_followers(geometry, *, rows, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] kei-child-native-followers
    Each committed Kei car MUST be finished from its own existing vehicle_kei export
    child: a store-only raw import with mesh_import's FBX options, then exactly
    /Game/Japan/Assets/<car> on the sole M_Village owner, validated against that
    child's export.json bounds and collision hulls. It MUST NOT read the combined
    world.kei library or run import_kei.py/import_village main or purge paths.
    unreal.kei is replaced only when all four cars are finished here.
    """
    root = Path(checkout)
    _check(rows)
    roster = cars(root)
    if natives is not None and (not isinstance(natives, dict) or set(natives) - {'M_Village'}):
        raise Unsupported('Kei accepts only the M_Village native owner')
    result = deepcopy(geometry)
    templates = {template['unit_prefix']: template for template in result['templates']
                 if template['unit_prefix'].startswith(f'world.{REGION}.export.')}
    expected = {f'world.{REGION}.export.{car}': car for car in roster}
    if sorted(templates) != sorted(expected):
        raise Unsupported('Kei export templates differ from the committed car roster')
    material_unit, material = _material(root, natives)
    native_code = _code(root)
    finish_code = sorted({*native_code, FINISH})
    packages, finished = {}, []
    for prefix, car in sorted(expected.items()):
        template = templates[prefix]
        if (template['op'] != {'kind': 'blender_export_piece', 'version': '1'} or template['params'] != {'format': 'fbx', 'options': {}}
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise Unsupported(car + ': export template differs from the FBX export child')
        raw_package, package = f'{RAW}/{car}', f'{DEST}/{car}'
        raw = {'id': f'unreal.kei.raw.{car}', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
               'code': native_code, 'inputs': [{'role': 'content', 'name': 'source',
                                                'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                          'fbx': dict(FBX), 'settings': list(SETTINGS)},
               'outputs': [{'id': 'raw_static_mesh', 'logical_path': raw_package, 'class': 'RawStaticMesh',
                            'destination': 'store', 'files': _files(raw_package, store=True)}]}
        finish = {'id': f'unreal.kei.{car}', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': finish_code,
                  'inputs': [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw_static_mesh'}},
                             {'role': 'content', 'name': 'export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                             {'role': 'content', 'name': 'material', 'source': {'kind': 'item', 'unit': material['unit'], 'item': material['item']}}],
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                             'args': {'car': car, 'piece': '$piece', 'export': 'export', 'material': 'material'}},
                  'outputs': [{'id': 'mesh', 'logical_path': package, 'class': 'StaticMesh', 'destination': 'checkout',
                               'files': _files(package, store=False)}]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {name: 'inputs/' + name for name in ('raw', 'export', 'material')}}]
        packages[package] = {'unit': finish['id'], 'item': 'mesh', 'package': package, 'dependencies': [dict(material)]}
        finished.append(finish['id'])
    units = [material_unit] if material_unit else []
    if material_unit:
        packages[MATERIAL] = dict(material)
    return {'geometry': result, 'units': units,
            'staged_inputs': {unit['id']: {} for unit in units},
            'content_slots': {'source': False, 'raw': False, 'export': False, 'material': False},
            'packages': packages,
            'aliases': {'unreal.kei': tuple([*(u['id'] for u in units), *finished])}}
