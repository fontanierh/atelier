"""Replace unreal.forest (Scripts/import_forest.py) by native units per forest package (world/forest_v2.py).

The forest roster is committed: eight assets/forest/export-parameters species, five authored levels each, and the four
Tuscan leaves forest_atomic_build.native_products names. From the actual source Items:
- each existing world.forest.export.<key> template (one per level) gains a store-only raw import of its FBX child with
  mesh_import's legacy options;
- ``forest.species`` splits world.forest's trees.json into one entry per species, ``forest.leaves`` the
  world.forest_textures library into one PNG per leaf (world/forest_members_v2.py);
- textures: T_<leaf>, T_ForestNormalDefault (the Cypress normal atlas) and each species' T_<n>_colour/normal from its
  own impostor bake, with the original properties;
- materials: MI_<leaf>, M_ForestImpostor, MI_<n>_Impostor and FoliageLODs/MI_<n>_Crown;
- one owner per species owning its base and four FoliageLODs/<n>_LOD<i> packages, from its five raws (a derived
  token over its templates), and the record writing forest/import-report.json and forest/native/import.json.
Shared native packages (M_Foliage, M_Painted, T_white, each bark MI and any non-Tuscan leaf MI) are other units'
Items: ``natives`` {package: {unit, item, dependencies?}}, every consumer staging their closure.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _modules
from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/forest_v2.py'
BODY = GAME + '/world/forest_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_forest.py'
SCRIPTS = GAME + '/unreal/Scripts'
HELPERS = [SCRIPTS + '/' + n for n in ('import_foliage_lods.py', 'forest_native.py', 'forest_impostor_material.py',
                                       'foliage_material.py')]
PARAMETERS = GAME + '/assets/forest/export-parameters'
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
OUT = 'build/yorimichi'
MATERIALS, TEXTURES = '/Game/Japan/Materials', '/Game/Japan/Textures'
ASSETS, LODS = '/Game/Japan/Assets', '/Game/Japan/FoliageLODs'
FOLIAGE, PAINTED, WHITE = MATERIALS + '/M_Foliage', MATERIALS + '/M_Painted', TEXTURES + '/T_white'
LEAVES = ('LeafOlive', 'LeafOak', 'LeafCypress', 'LeafStonePine')
REPORT, NATIVE_REPORT = OUT + '/forest/import-report.json', OUT + '/forest/native/import.json'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1.0, 'build_nanite': False,
       'one_convex_hull_per_ucx': True,
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.REPLACE'},
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'}}
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false']
LEAF_TEXTURE = {'srgb': True, 'max_texture_size': 1024, 'do_scale_mips_for_alpha_coverage': True,
                'alpha_coverage_thresholds': {'unreal_type': 'Vector4', 'args': [0, 0, 0, .4]}}
NORMAL_TEXTURE = {'srgb': False,
                  'compression_settings': {'unreal_enum': 'TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP'}}
ATLAS = {'colour': {'srgb': True, 'max_texture_size': 512, 'do_scale_mips_for_alpha_coverage': True,
                    'alpha_coverage_thresholds': {'unreal_type': 'Vector4', 'args': [0, 0, 0, .4]}},
         'normal': {'srgb': False, 'max_texture_size': 512,
                    'compression_settings': {'unreal_enum': 'TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP'}}}


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def roster(checkout):
    """{species: {leaf, bark}} from the committed export parameters, as forest_atomic_build reads them."""
    root = Path(checkout)
    params = _load(root, GAME + '/world/forest_parameters.py', 'forest_v2_parameters')
    files = sorted((root / PARAMETERS).glob('*.json'))
    result = {}
    for file in files:
        name, spec = params.load(file)
        bark = 'BarkOlive' if spec[0] == 'olive' else 'BarkTuscan' if name.startswith('Tree_Tuscan_') else 'Bark'
        result[name] = {'leaf': spec[-1], 'bark': bark}
    if len(result) != 8:
        raise Unsupported('Forest requires the complete eight-species source inventory')
    return result


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


def _native(natives, package):
    ref = (natives or {}).get(package)
    if (not isinstance(ref, dict) or not {'unit', 'item'} <= set(ref) <= {'unit', 'item', 'package', 'dependencies'}
            or not all(isinstance(ref[k], str) and ref[k] for k in ('unit', 'item')) or ref.get('package', package) != package
            or not isinstance(ref.get('dependencies', []), list)):
        raise Unsupported('missing exact native Item for ' + package)
    return ref


def _closure(natives, roots):
    seen, order, stack = set(roots), [], list(reversed(roots))
    while stack:
        package = stack.pop()
        for dependency in _native(natives, package).get('dependencies', []):
            if not isinstance(dependency, str) or not dependency.startswith('/Game/'):
                raise Unsupported('invalid native dependency of ' + package)
            if dependency not in seen:
                seen.add(dependency); order.append(dependency); stack.append(dependency)
    return order


def _call(root, name, defaults):
    spec = importlib.util.spec_from_file_location('forest_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    function = getattr(module, name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _product(by_id, unit, product, paths):
    row = by_id.get(unit)
    found = [i for i, p in enumerate((row or {}).get('products', ())) if p['id'] == product]
    if len(found) != 1 or row['products'][found[0]]['paths'] != paths:
        raise Unsupported(f'{unit} must own its {product} Product')
    return f'product{found[0]}', f'products/{found[0]}-0.tree.tar'


def _check(by_id, species):
    importer = by_id.get('unreal.forest')
    commands = (importer or {}).get('commands') or [{}]
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL} or commands[0].get('marker') != 'FOREST IMPORT COMPLETE'
            or commands[0].get('args') or commands[0].get('env') or importer.get('outputs')):
        raise Unsupported('unreal.forest differs from the original import_forest.py target')
    products = {p['id']: p for p in importer.get('products', ())}
    content = GAME + '/unreal/Content/'
    expected = [content + p for p in ('Japan/Textures/T_ForestNormalDefault.uasset', 'Japan/Materials/M_ForestImpostor.uasset')]
    for leaf in LEAVES:
        expected += [content + f'Japan/Textures/T_{leaf}.uasset', content + f'Japan/Materials/MI_{leaf}.uasset']
    for name in species:
        expected += [content + f'Japan/Assets/{name}.uasset', content + f'Japan/Materials/MI_{name}_Impostor.uasset',
                     content + f'Japan/FoliageLODs/MI_{name}_Crown.uasset',
                     *(content + f'Japan/Textures/T_{name}_{kind}.uasset' for kind in ('colour', 'normal')),
                     *(content + f'Japan/FoliageLODs/{name}_LOD{i}.uasset' for i in range(1, 5))]
    if (set(products) != {'forest.native_assets', 'forest.native_reports'}
            or sorted(products['forest.native_assets']['paths']) != sorted(expected)
            or products['forest.native_reports']['paths'] != [REPORT, NATIVE_REPORT]):
        raise Unsupported('unreal.forest Products differ from the complete original package and report roster')


def forest_units(geometry, *, rows, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-forest-native-units
    unreal.forest MUST become one unit per forest package and its record from the
    actual Items: every committed species level a store-only raw import of its own
    export child, narrow per-species and per-leaf views of the whole manifest and
    texture library, the original texture properties and material bindings, and
    one finish per species owning its base and four source LODs with the original
    LOD, impostor, crown, height, collision and screen-size checks. Shared natives
    are supplied Items; the original top level, inventory and retirement never run.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    species = roster(root)
    _check(by_id, species)
    catalog = _load(root, GAME + '/world/asset_catalog.py', 'forest_v2_catalog')
    catalog.check_material_namespace(LEAVES, 'forest')
    scanner = ImportScanner()
    recipe_code = sorted({BODY, *(p.relative_to(root).as_posix() for p in scanner.local_imports(
        root / RECIPE, (root / 'platform/studio',))), RECIPE})
    code = {*_code(root), SCRIPT, ORIGINAL, *HELPERS}
    for source in HELPERS:
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(
            root / source, (root / SCRIPTS, root / GAME / 'world', root / 'platform/studio')))
    code = sorted(code)
    ops_code, editor = list(_code(root)), _modules(root, [])[0]
    result = deepcopy(geometry)
    units, staged, packages, requirements = [], {}, {}, dict(result.get('module_requirements', {}))

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor

    def native_inputs(roots):
        refs = []
        for package in [*roots, *_closure(natives, roots)]:
            ref = _native(natives, package)
            refs.append((package, _item('native_' + package.removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])))
        return refs

    def texture(name, source, member, properties, roots):
        raw_id, unit_id = f'unreal.forest.texture.raw.{name}', f'unreal.forest.texture.{name}'
        raw_package, package = f'/Game/_Raw/Forest/Textures/{name}', f'{TEXTURES}/{name}'
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package,
                        'source_member': member},
             'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]}, [source], roots)
        add({'id': unit_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                        'package_sources': {'raw': raw_package}, 'properties': deepcopy(properties)},
             'outputs': [_output('texture', package, 'Texture')]}, [_item('raw', raw_id, 'raw_texture')])
        packages[package] = {'unit': unit_id, 'item': 'texture', 'package': package}
        return unit_id

    # Narrow views of the two whole source libraries.
    manifest_item, manifest_archive = _product(by_id, 'world.forest', 'forest.manifest', [OUT + '/forest/trees.json'])
    textures_item, textures_archive = _product(by_id, 'world.forest_textures', 'forest.textures', [OUT + '/forest/textures'])
    whole = _item('manifest', 'world.forest', manifest_item)
    whole['whole'] = 'The complete assembled forest manifest checks every committed species before any is selected.'
    add({'id': 'forest.species', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'recipe': {'version': 1, 'verify': None,
             'paths': {OUT + '/forest/trees.json': 'inputs/manifest/' + manifest_archive},
             'commands': [_call(root, 'species', (root / OUT / 'forest/trees.json', root / 'generated/forest/species', sorted(species)))],
             'outputs': [{'path': f'generated/forest/species/{name}.json', 'kind': 'file', 'file': f'{name}.json', 'required': True}
                         for name in sorted(species)]}},
         'outputs': [{'id': name, 'logical_path': f'/Internal/Forest/Species/{name}', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': f'{name}.json', 'required': True}]} for name in sorted(species)]}, [whole])
    library = _item('library', 'world.forest_textures', textures_item)
    library['whole'] = 'The complete forest texture library checks every committed leaf before any is selected.'
    add({'id': 'forest.leaves', 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
         'params': {'recipe': {'version': 1, 'verify': None,
             'paths': {OUT + '/forest/textures': 'inputs/library/' + textures_archive},
             'commands': [_call(root, 'leaves', (root / OUT / 'forest/textures', root / 'generated/forest/leaves', list(LEAVES)))],
             'outputs': [{'path': f'generated/forest/leaves/T_{leaf}.png', 'kind': 'file', 'file': f'T_{leaf}.png', 'required': True}
                         for leaf in LEAVES]}},
         'outputs': [{'id': leaf, 'logical_path': f'/Internal/Forest/Leaves/{leaf}', 'class': 'Data', 'destination': 'store',
                      'files': [{'path': f'T_{leaf}.png', 'required': True}]} for leaf in LEAVES]}, [library])

    # Leaf textures and instances; the impostor master and its default normal (the Cypress atlas, as the original).
    foliage = native_inputs([FOLIAGE])
    leaf_mis = {}
    for leaf in LEAVES:
        texture_id = texture(f'T_{leaf}', _item('source', 'forest.leaves', leaf), f'T_{leaf}.png', LEAF_TEXTURE, None)
        unit_id, package = f'unreal.forest.material.MI_{leaf}', f'{MATERIALS}/MI_{leaf}'
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'leaf', 'slot': leaf, 'parent': foliage[0][1]['name'], 'texture': 'texture'},
                        'settings': []},
             'outputs': [_output('asset', package, 'MaterialInstance')]},
            [_item('texture', texture_id, 'texture'), *(i for _, i in foliage)])
        packages[package] = {'unit': unit_id, 'item': 'asset', 'package': package,
                             'dependencies': [{'unit': texture_id, 'item': 'texture', 'package': f'{TEXTURES}/T_{leaf}'},
                                              {**_native(natives, FOLIAGE), 'package': FOLIAGE}]}
        leaf_mis[leaf] = (unit_id, package)
    bakes = {}
    for name in species:
        bakes[name] = (f'world.forest.impostor.{name}',
                       *_product(by_id, f'world.forest.impostor.{name}', f'forest.impostor.{name}', [f'{OUT}/forest-bakes/{name}']))
    cypress, cypress_item, cypress_archive = bakes['Tree_Tuscan_Cypress']
    normal_id = texture('T_ForestNormalDefault', _item('source', cypress, cypress_item), 'Tree_Tuscan_Cypress_normal.png',
                        NORMAL_TEXTURE, {'source': {'archive_member': cypress_archive, 'name': 'Tree_Tuscan_Cypress'}})
    master_id = 'unreal.forest.material.M_ForestImpostor'
    add({'id': master_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'master', 'normal': 'normal'}, 'settings': []},
         'outputs': [_output('asset', MATERIALS + '/M_ForestImpostor', 'Material')]}, [_item('normal', normal_id, 'texture')])
    packages[MATERIALS + '/M_ForestImpostor'] = {'unit': master_id, 'item': 'asset', 'package': MATERIALS + '/M_ForestImpostor'}

    templates = {t['unit_prefix']: t for t in result['templates'] if t['unit_prefix'].startswith('world.forest.export.')}
    keys = {f'world.forest.export.{name}' + ('' if level == 0 else f'_LOD{level}'): (name, level)
            for name in species for level in range(5)}
    if sorted(templates) != sorted(keys):
        raise Unsupported('Forest export templates differ from the committed species levels')
    for prefix, (name, level) in keys.items():
        template = templates[prefix]
        key = prefix.removeprefix('world.forest.export.')
        if (template['producer'] != f'world.forest.geometry.{key}' or template['group'] != 'geometry'
                or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'] != {'format': 'fbx', 'options': {}}
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise Unsupported(key + ': export template differs from the FBX export child')
        raw_package = f'/Game/_Raw/Forest/{name}/{key}'
        template['followers'] = [{'unit': {
            'id': f'unreal.forest.raw.{key}', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS,
            'code': ops_code, 'inputs': [_item('source', '$export', 'asset')],
            'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                       'fbx': dict(FBX), 'settings': list(SETTINGS)},
            'outputs': [_output('raw_static_mesh', raw_package, 'RawStaticMesh', store=True)]},
            'staged_inputs': {'source': 'inputs/source'}}]
        requirements[prefix] = editor

    record_species = {}
    record_inputs = []
    painted = native_inputs([PAINTED, WHITE])
    for name, entry in species.items():
        species_input = _item('entry', 'forest.species', name)
        bake, bake_item, bake_archive = bakes[name]
        atlases = {kind: texture(f'T_{name}_{kind}', _item('source', bake, bake_item), f'{name}_{kind}.png', ATLAS[kind],
                                 {'source': {'archive_member': bake_archive, 'name': name}}) for kind in ('colour', 'normal')}
        impostor_id, impostor = f'unreal.forest.material.MI_{name}_Impostor', f'{MATERIALS}/MI_{name}_Impostor'
        add({'id': impostor_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'impostor', 'name': name, 'entry': 'entry', 'master': 'master',
                                 'colour': 'colour', 'normal': 'normal'}, 'settings': []},
             'outputs': [_output('asset', impostor, 'MaterialInstance')]},
            [deepcopy(species_input), _item('master', master_id, 'asset'),
             *(_item(kind, unit_id, 'texture') for kind, unit_id in atlases.items()), _item('master_normal', normal_id, 'texture')])
        packages[impostor] = {'unit': impostor_id, 'item': 'asset', 'package': impostor}
        crown_id, crown = f'unreal.forest.material.MI_{name}_Crown', f'{LODS}/MI_{name}_Crown'
        add({'id': crown_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'crown', 'name': name, 'entry': 'entry', 'parent': painted[0][1]['name'],
                                 'white': painted[1][1]['name']}, 'settings': []},
             'outputs': [_output('asset', crown, 'MaterialInstance')]},
            [deepcopy(species_input), *(deepcopy(i) for _, i in painted)])
        packages[crown] = {'unit': crown_id, 'item': 'asset', 'package': crown,
                          'dependencies': [{**_native(natives, p), 'package': p} for p in (PAINTED, WHITE)]}
        # The species palette: its leaf and bark (owned here or supplied), its impostor and its crown.
        materials, inputs = {}, [deepcopy(species_input)]
        for key in (entry['leaf'], entry['bark']):
            if key in leaf_mis:
                unit_id, package = leaf_mis[key]
                inputs.append(_item('material_' + key, unit_id, 'asset'))
                inputs += [deepcopy(i) for _, i in native_inputs([FOLIAGE])]
            else:
                ref = _native(natives, f'{MATERIALS}/MI_{key}')
                inputs.append(_item('material_' + key, ref['unit'], ref['item']))
                inputs += [i for _, i in native_inputs(_closure(natives, [f'{MATERIALS}/MI_{key}']))]
            materials[key] = 'material_' + key
        inputs += [_item('material_' + name + '_Impostor', impostor_id, 'asset'),
                   _item('material_' + name + '_Crown', crown_id, 'asset'), *(deepcopy(i) for _, i in painted)]
        materials[name + '_Impostor'], materials[name + '_Crown'] = 'material_' + name + '_Impostor', 'material_' + name + '_Crown'
        inputs = list({i['name']: i for i in inputs}.values())
        levels = {'derived_items': {'root': f'build/v2-derived/forest/{name}', 'templates': [
            {'producer': f'world.forest.geometry.{key}', 'group': 'geometry', 'unit_prefix': f'world.forest.export.{key}',
             'follower': 0, 'item': 'raw_static_mesh'} for key in [name, *(f'{name}_LOD{i}' for i in range(1, 5))]]}}
        finish_id, base = f'unreal.forest.finish.{name}', f'{ASSETS}/{name}'
        outputs = [_output('static_mesh', base, 'StaticMesh'),
                   *(_output(f'lod{i}', f'{LODS}/{name}_LOD{i}', 'StaticMesh') for i in range(1, 5))]
        # Five jointly assembled packages (the base reads its four saved LOD sources): one author owning five Items.
        add({'id': finish_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'species', 'name': name, 'entry': 'entry', 'levels': levels, 'materials': materials},
                        'settings': ['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},
             'outputs': outputs}, inputs)
        for output in outputs:
            packages[output['logical_path']] = {'unit': finish_id, 'item': output['id'], 'package': output['logical_path']}
        record_inputs += [_item('entry_' + name, 'forest.species', name), _item('base_' + name, finish_id, 'static_mesh')]
        record_species[name] = {'entry': 'entry_' + name, 'base': 'base_' + name}
    record_id = 'unreal.forest.record'
    add({'id': record_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'record', 'species': record_species}, 'settings': []},
         'outputs': [{'id': 'report', 'logical_path': '/Internal/Forest/Report', 'class': 'JsonData', 'destination': 'store',
                      'files': [{'path': 'data/import-report.json', 'required': True}]},
                     {'id': 'native_report', 'logical_path': '/Internal/Forest/NativeReport', 'class': 'JsonData',
                      'destination': 'store', 'files': [{'path': 'data/native-import.json', 'required': True}]}]},
        record_inputs)
    packages[REPORT] = {'unit': record_id, 'item': 'report'}
    packages[NATIVE_REPORT] = {'unit': record_id, 'item': 'native_report'}
    result['module_requirements'] = requirements
    return {'geometry': result, 'units': units, 'staged_inputs': staged,
            'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'module_requirements': requirements,
            'aliases': {'unreal.forest': (record_id,)}}
