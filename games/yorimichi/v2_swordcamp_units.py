"""C3 owners for unreal.swordcamp: the atlas texture, the two original materials and per-piece mesh followers.

Scripts/import_swordcamp.py imports build/yorimichi/swordcamp/swordcamp_atlas.jpg as T_SwordCampAtlas, builds
M_SwordCamp (the equipment and camp props) and M_RoninBody (the runtime Ronin characters' skeletal material) over
it, then imports every swordcamp_build catalogue export into /Game/SwordCamp/Assets on M_SwordCamp, with simple and
complex collision for the four solid camp props and the default trace for the equipment.

``author_units`` owns the atlas raw/finish from the actual swordcamp.atlas product ROOT and the two materials,
each the original named function called through the existing native author body. ``attach_followers`` gives each
original catalogue parent's export template a raw import and a finish over its own export and MeshIR plus the
supplied M_SwordCamp closure (normally ``author_units(...)['packages']``).
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

GAME = 'games/yorimichi'
ORIGINAL = GAME + '/unreal/Scripts/import_swordcamp.py'
AUTHOR = GAME + '/world/native_author_call_v2.py'
FINISH = GAME + '/world/swordcamp_finish_v2.py'
CATALOGUE = GAME + '/world/regions/swordcamp/catalogue.py'
ATLAS = '/Game/SwordCamp/Textures/T_SwordCampAtlas'
RAW_ATLAS = '/Game/_Raw/SwordCamp/Textures/T_SwordCampAtlas'
MATERIALS = {'M_SwordCamp': 'build_material', 'M_RoninBody': 'build_ronin_body_material'}
MATERIAL = '/Game/SwordCamp/Materials/M_SwordCamp'
DESTINATION = '/Game/SwordCamp/Assets'
RAW = '/Game/_Raw/SwordCamp'
SOLID_PROPS = ('SM_CampBales', 'SM_CampFirePit', 'SM_CampJinmaku', 'SM_CampWeaponRack')
# import_atlas() settings.
ATLAS_PROPERTIES = {'srgb': True, 'max_texture_size': 2048, 'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}}
# mesh_import.import_mesh's legacy FBX static-mesh options, which import_swordcamp.py uses.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}


def _load(root, relative, name):
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _check(rows):
    by_id = {row['id']: row for row in rows if row['id'] in ('world.swordcamp_atlas', 'unreal.swordcamp')}
    if sorted(by_id) != ['unreal.swordcamp', 'world.swordcamp_atlas']:
        raise ValueError('SwordCamp needs its exact atlas producer and import rows')
    commands = by_id['unreal.swordcamp']['commands']
    if (len(commands) != 1 or commands[0]['kind'] != 'UnrealScript' or commands[0]['script'] != {'path': ORIGINAL}
            or commands[0]['marker'] != 'SWORDCAMP IMPORT COMPLETE' or commands[0]['args'] or commands[0]['env']):
        raise ValueError('unreal.swordcamp differs from the original SwordCamp import')
    products = [(i, p) for i, p in enumerate(by_id['world.swordcamp_atlas']['products']) if p['id'] == 'swordcamp.atlas']
    if (len(products) != 1 or products[0][1]['paths'] != ['build/yorimichi/swordcamp/swordcamp_atlas.jpg']
            or products[0][1]['optional_paths']):
        raise ValueError('SwordCamp atlas must be its actual singleton required product')
    return products[0][0]


def author_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-swordcamp-atlas-materials
    T_SwordCampAtlas MUST be one raw import of the actual swordcamp.atlas product
    ROOT plus a finish with import_atlas's sRGB/2048/World settings. M_SwordCamp
    and M_RoninBody MUST each be the original build_material or
    build_ronin_body_material called through the native author body over exactly
    that finished atlas; the importer's main, cache or report paths never run.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    index = _check(rows)
    texture = _load(root, GAME + '/v2_texture_units.py', 'v2_swordcamp_texture')
    native_code = texture._code(root)
    raw = {'id': 'unreal.swordcamp.texture.raw.T_SwordCampAtlas', 'op': {'kind': 'unreal.raw_import', 'version': '1'},
           'script': texture.OPS, 'code': native_code,
           'inputs': [{'role': 'content', 'name': 'source',
                       'source': {'kind': 'item', 'unit': 'world.swordcamp_atlas', 'item': 'product' + str(index)}}],
           'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': RAW_ATLAS,
                      'input_roots': {'source': {'archive_member': f'products/{index}-0.tree.tar', 'name': 'swordcamp_atlas.jpg'}}},
           'outputs': [texture._output(RAW_ATLAS, raw=True)]}
    finish = {'id': 'unreal.swordcamp.texture.T_SwordCampAtlas', 'op': {'kind': 'unreal.finish', 'version': '1'},
              'script': texture.OPS, 'code': native_code,
              'inputs': [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': raw['id'], 'item': 'raw_texture'}}],
              'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': ATLAS,
                         'package_sources': {'raw': RAW_ATLAS}, 'properties': dict(ATLAS_PROPERTIES)},
              'outputs': [texture._output(ATLAS, raw=False)]}
    atlas = {'unit': finish['id'], 'item': 'texture', 'package': ATLAS}
    roots = (root / GAME / 'unreal/Scripts', root / GAME / 'world', root / GAME, root / 'platform/studio')
    code = {*native_code, AUTHOR, ORIGINAL}
    for source in (AUTHOR, ORIGINAL):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / source, roots))
    for relative in code:
        if (root / relative).is_symlink() or not (root / relative).is_file():
            raise ValueError('missing or linked SwordCamp keyed source: ' + relative)
    units, packages = [raw, finish], {ATLAS: atlas}
    for name, function in MATERIALS.items():
        package = '/Game/SwordCamp/Materials/' + name
        output = texture._output(package, raw=False)
        output.update(id='asset', **{'class': 'Material'})
        units.append({'id': 'unreal.swordcamp.material.' + name, 'op': {'kind': 'unreal.author', 'version': '1'},
                      'script': AUTHOR, 'code': sorted(code),
                      'inputs': [{'role': 'content', 'name': 'atlas', 'source': {'kind': 'item', 'unit': atlas['unit'], 'item': atlas['item']}}],
                      'params': {'args': {'module': ORIGINAL, 'function': function, 'arguments': [{'native_input': 'atlas'}],
                                          'keyword_arguments': {}, 'expected_package': package}, 'settings': []},
                      'outputs': [output]})
        packages[package] = {'unit': units[-1]['id'], 'item': 'asset', 'package': package, 'dependencies': [ATLAS]}
    return {'units': units, 'staged_inputs': {u['id']: {i['name']: 'inputs/' + i['name'] for i in u['inputs']} for u in units},
            'content_slots': {'source': False, 'raw': False, 'atlas': False}, 'packages': packages}


def attach_followers(geometry, natives, *, checkout):
    """@cc [owner:fontanierh,label:correctness] original-swordcamp-native-followers
    Every original SwordCamp catalogue D2 parent MUST receive independent per-piece
    raw and finish owners at /Game/SwordCamp/Assets/<parent>. Finish MUST consume
    its own export and MeshIR payload and the supplied M_SwordCamp with its
    declared native closure; no material owner is duplicated and nothing is
    discovered. The four SOLID_PROPS MUST stay simple-and-complex, all other
    parents the default trace, with M_SwordCamp on slot 0.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    catalogue = _load(root, CATALOGUE, 'v2_swordcamp_catalogue')
    original = _load_solid(root)
    if set(original) != set(SOLID_PROPS) or not set(SOLID_PROPS) <= set(catalogue.ASSETS):
        raise ValueError('SwordCamp solid prop policy differs from the original importer')
    texture = _load(root, GAME + '/v2_texture_units.py', 'v2_swordcamp_followers_texture')
    island = _load(root, GAME + '/v2_island_units.py', 'v2_swordcamp_items')
    if not isinstance(natives, dict):
        raise ValueError('SwordCamp requires the supplied native material roster')
    dependencies = {}
    def dependency(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/') or set(ref) - {'unit', 'item', 'package', 'dependencies'}):
            raise ValueError('SwordCamp material dependency must name its actual finished native Item')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']:
                raise ValueError('SwordCamp material Item aliases distinct native packages')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives:
                    raise ValueError('Missing supplied SwordCamp transitive material input: ' + child)
                child = natives[child]
            dependency(child)
        return slot
    material = natives.get(MATERIAL)
    if not isinstance(material, dict) or material.get('package') != MATERIAL:
        raise ValueError('Missing exact supplied SwordCamp native material: ' + MATERIAL)
    material_slot = dependency(material)
    code = set(texture._code(root))
    for source in (FINISH, GAME + '/city_tile_products.py'):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / source,
            (root / 'platform/studio', root / GAME, root / GAME / 'world', root / GAME / 'world/regions')))
    descriptor = json.loads((root / GAME / 'unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m.get('LoadingPhase', 'Default')} for m in descriptor['Modules']]
    result = deepcopy(geometry); seen = set(); requirements = dict(result.get('module_requirements', {}))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.swordcamp.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.swordcamp.export.')
        if (parent not in catalogue.ASSETS or parent in seen or template['producer'] != 'world.swordcamp.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx'
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise ValueError('SwordCamp native followers require every original FBX D2 parent exactly once')
        seen.add(parent)
        raw_package, destination = RAW + '/$piece', DESTINATION + '/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                   'fbx': dict(FBX),
                   'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},
               'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'],
                                                                    'group': 'geometry', 'piece': '$piece'}},
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in dependencies.values())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': FINISH,
                  'code': sorted(code), 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                    'package_sources': {'raw': raw_package},
                    'args': {'parent': parent, 'collision': 'simple_and_complex' if parent in SOLID_PROPS else 'default',
                             'payload': 'payload', 'source_export': 'source_export', 'material': material_slot,
                             'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                    'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = modules
    if seen != set(catalogue.ASSETS):
        raise ValueError('SwordCamp native followers require the complete catalogue family')
    result['module_requirements'] = requirements
    return result


def _load_solid(root):
    """The original importer's SOLID_PROPS literal, read without importing it."""
    import ast
    tree = ast.parse((root / ORIGINAL).read_bytes(), filename=ORIGINAL)
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and [getattr(t, 'id', None) for t in node.targets] == ['SOLID_PROPS']]
    if len(values) != 1:
        raise ValueError('The original importer lacks SOLID_PROPS')
    return ast.literal_eval(values[0])
