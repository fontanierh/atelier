"""Replace Scripts/import_megapark.py (unreal.megapark) by native units per MegaPark package (world/megapark_v2.py).

The original imports, into /Game/MegaPark: one T_<tid> per map.json texture (the restyled image where
tools/megapark_textures.py replaces it) and four fallback pixels, the three M_Retail* parents, one MI_<key> per
generated material, every render/collision/seam mesh, and the SuperUltraMegaPark level placing the render and
collision meshes with the rails, spawn and lights. Here:
- attach_followers: one raw import + finish per piece of every megapark D2 export template (not the import seed),
  each consuming its own export, MeshIR payload and logical parent's metadata, plus the supplied MI closure;
- megapark_units: textures, parents, instances and the level. The material roster is generated (plan_asset over
  the npz geometry), so it MUST arrive as keyed ``members['materials'] = {key: {alpha, textures: {role: tid}}}``,
  otherwise DynamicMembership; the restyled images need ``natives['restyle'] = {unit, item, root?}``.
"""
import ast
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

from v2_character_units import DynamicMembership, _modules, _output
from v2_texture_units import OPS, SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/megapark_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_megapark.py'
SOURCE = GAME + '/assets/megapark'
TEXTURES_TOOL = GAME + '/tools/megapark_textures.py'
BUILD = 'build/yorimichi/megapark'
ROOT = '/Game/MegaPark'
RAW = '/Game/_Raw/MegaPark'
LEVEL = ROOT + '/Maps/SuperUltraMegaPark'
PARENTS = ('M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent')
ROLES = ('diffuse', 'decal', 'macrooverlay', 'lightmap', 'normal', 'detail', 'specular', 'transparent')
# import_megapark.materials' fallback pixels: (file, linear, normal).
DEFAULTS = {'T_DefaultWhite': ('white.png', False, False), 'T_DefaultLinear': ('white.png', True, False),
            'T_DefaultBlack': ('black.png', True, False), 'T_DefaultNormal': ('normal.png', False, True)}
# import_megapark._source_mesh's FBX options. vertex_color_import_option is left at the editor's static-mesh
# default (BaseEditorPerProjectUserSettings: Ignore), which the raw op would otherwise turn into Replace.
FBX = {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False,
       'convert_scene': True, 'convert_scene_unit': True, 'import_uniform_scale': 1., 'build_nanite': False,
       'remove_degenerates': False,
       'normal_import_method': {'unreal_enum': 'FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS'},
       'vertex_color_import_option': {'unreal_enum': 'VertexColorImportOption.IGNORE'}}
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0,'
            'r.GenerateMeshDistanceFields=0,r.MeshCardRepresentation=0']


def _load(checkout, relative, name):
    spec = importlib.util.spec_from_file_location(name, Path(checkout) / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def restyled(checkout):
    """{tid: png} megapark_textures.finish writes: painted surfaces, recolours, and signs whose paintings exist."""
    import sys
    root = Path(checkout)
    sys.path[:0] = [str(root / GAME / 'world'), str(root / GAME / 'world/regions')]
    try:
        # Its tables only; importing it builds nothing (finish/main never run).
        tool = _load(root, TEXTURES_TOOL, 'v2_megapark_textures')
    finally:
        del sys.path[:2]
    painted = Path(tool.PAINTED)
    if painted != root / SOURCE / 'restyle':
        raise Unsupported('megapark_textures paints from another folder')
    tids = [tid for slug, (tid, _, _) in tool.SURFACES.items() if (painted / f'{slug}.jpg').is_file()]
    tids += list(tool.RECOLOUR)
    tids += [tid for tid, (slug, how) in tool.SIGNS.items()
             if all((painted / f'{n}.jpg').is_file() for n in [slug] + (['waves'] if how != 'fit' else []))]
    if len(set(tids)) != len(tids):
        raise Unsupported('a texture is restyled twice')
    return {tid: tid[2:] + '.png' for tid in tids}


def catalogue(checkout):
    """(textures {tid: png}, placed render parents, placed collision parents, seam parents) from committed sources."""
    root = Path(checkout)
    source = json.loads((root / SOURCE / 'map.json').read_text())
    atomic = _load(root, GAME + '/megapark_atomic_build.py', 'v2_megapark_atomic')
    import sys
    sys.path[:0] = [str(root / GAME / 'world'), str(root / GAME / 'world/regions')]
    try:
        _source, models = atomic.catalogue()
    finally:
        del sys.path[:2]
    render = ['SM_MP_' + m['asset_id'][2:] for m in models]
    collision = ['UC_MP_' + s['id'] for s in source['collision']]
    return {tid: t['png'] for tid, t in source['textures'].items()}, render, collision, ['SM_MP_Seam', 'UC_MP_Seam']


def _check_original(checkout, rows):
    tree = ast.parse((Path(checkout) / ORIGINAL).read_bytes())
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    by_id = {row['id']: row for row in rows}
    importer = by_id.get('unreal.megapark')
    commands = importer and importer['commands']
    if (not importer or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}):
        raise Unsupported('unreal.megapark differs from the original import_megapark.py target')
    if not {'material', '_finish_mesh', 'ue', 'texture'} <= defined:
        raise Unsupported('import_megapark.py no longer defines its native functions')
    return by_id


def _product(row, product_id):
    index = [i for i, p in enumerate(row['products']) if p['id'] == product_id]
    if len(index) != 1 or row['products'][index[0]]['optional_paths']:
        raise Unsupported(f'{row["id"]} must own exactly one complete {product_id} product')
    return f'product{index[0]}', {str(path): f'products/{index[0]}-{j}.tree.tar'
                                  for j, path in enumerate(row['products'][index[0]]['paths'])}


def _code_closure(checkout):
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    found = {p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
        root / SCRIPT, (root / GAME / 'world', root / GAME / 'unreal/Scripts', root / 'platform/studio'))}
    return sorted({*_code(root), SCRIPT, ORIGINAL, *found})


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _native(ref):
    return _item('native_' + ref['package'].removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])


def level_token(render, collision):
    """The finished placed pieces (render then collision parents), as the derived_items token the provider expands."""
    return {'derived_items': {'templates': [{'producer': 'world.megapark.geometry.' + parent, 'group': 'geometry',
                                             'unit_prefix': 'world.megapark.export.' + parent, 'follower': 1, 'item': 'asset'}
                                            for parent in (*render, *collision)],
                              'root': 'build/v2-derived/megapark/level'}}


def megapark_units(rows, *, checkout, members=None, natives=None):
    """@cc [owner:fontanierh,label:correctness] authored-c3-megapark-library
    import_megapark.py's library MUST become one unit per package: a raw import +
    finish per map texture and fallback pixel (the restyled image where the
    committed restyle tables replace it), the three original parents, one
    instance per supplied keyed material member and the level over the finished
    placed pieces. Generated membership MUST be supplied or refused; generated
    content is never scanned and the original never runs.
    """
    checkout = Path(checkout)
    by_id = _check_original(checkout, rows)
    if not isinstance(members, dict) or set(members) != {'materials'} or not isinstance(members['materials'], dict) \
            or not members['materials']:
        raise DynamicMembership('MegaPark material instances need the generated roster as keyed members')
    textures, render, collision, _seam = catalogue(checkout)
    restyle = restyled(checkout)
    if set(restyle) - set(textures):
        raise Unsupported('a restyled texture is not a map texture')
    roles = {}
    for key, spec in members['materials'].items():
        if (not isinstance(key, str) or not key.startswith('0x') or not isinstance(spec, dict) or set(spec) != {'alpha', 'textures'}
                or spec['alpha'] not in (0, 1, 2) or not isinstance(spec['textures'], dict)
                or set(spec['textures']) - set(ROLES) or set(spec['textures'].values()) - set(textures)):
            raise Unsupported(f'noncanonical MegaPark material member {key!r}')
        for role, tid in spec['textures'].items():
            roles.setdefault(tid, set()).add(role)
    restyle_ref = (natives or {}).get('restyle')
    if restyle and (not isinstance(restyle_ref, dict) or not {'unit', 'item'} <= set(restyle_ref) <= {'unit', 'item', 'root'}):
        raise Unsupported('restyled MegaPark images need the declared restyle textures Item (natives["restyle"])')
    library_item, library_roots = _product(by_id['world.megapark'], 'megapark.library')
    restyle_row = by_id['world.megapark_restyle']
    if str(restyle_row['outputs'][0]) != BUILD + '/textures/textures.json':
        raise Unsupported('world.megapark_restyle no longer publishes textures.json first')
    code, ops_code = _code_closure(checkout), list(_code(checkout))
    editor = _modules(checkout, [])[0]
    units, staged, owned, requirements = [], {}, {}, {}

    def add(unit, inputs, roots=None, *, package=None, item_id='asset', dependencies=()):
        if roots:
            unit['params']['input_roots'] = roots
        unit['inputs'] = inputs
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'unreal.raw_import':
            requirements[unit['id']] = editor
            owned[package] = {'unit': unit['id'], 'item': item_id, 'package': package,
                              'dependencies': [deepcopy(owned[p]) for p in dependencies]}

    def texture(name, source, roots, member, *, linear, normal, clamp):
        raw_package, package = f'{RAW}/Textures/{name}', f'{ROOT}/Textures/{name}'
        raw_id = f'unreal.megapark.texture.raw.{name}'
        params = {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package}
        if member:
            params['source_member'] = member
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': params, 'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]}, [source], roots)
        properties = {'srgb': not linear and not normal, 'compression_settings': {'unreal_enum':
                      'TextureCompressionSettings.' + ('TC_NORMALMAP' if normal else 'TC_DEFAULT')}}
        if clamp:
            properties.update(address_x={'unreal_enum': 'TextureAddress.TA_CLAMP'}, address_y={'unreal_enum': 'TextureAddress.TA_CLAMP'})
        add({'id': f'unreal.megapark.texture.{name}', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS,
             'code': ops_code, 'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                                          'package_sources': {'raw': raw_package}, 'properties': properties},
             'outputs': [_output('texture', package, 'Texture')]}, [_item('raw', raw_id, 'raw_texture')],
            package=package, item_id='texture')

    for tid, png in textures.items():
        used = roles.get(tid, set())
        flags = dict(linear=bool(used & {'lightmap', 'normal', 'detail', 'specular'}), normal=bool(used & {'normal', 'detail'}),
                     clamp='lightmap' in used)
        if tid in restyle:
            source = _item('source', restyle_ref['unit'], restyle_ref['item'])
            roots = {'source': dict(restyle_ref['root'])} if 'root' in restyle_ref else None
            texture('T_' + tid[2:], source, roots, restyle[tid], **flags)
        else:
            source = {'role': 'content', 'name': 'source', 'source': {'kind': 'file', 'path': f'{SOURCE}/{png}'}}
            texture('T_' + tid[2:], source, None, None, **flags)
    for name, (png, linear, normal) in DEFAULTS.items():
        source = _item('source', 'world.megapark', library_item)
        texture(name, source, {'source': {'archive_member': library_roots[f'{BUILD}/{png}'], 'name': png}}, None,
                linear=linear, normal=normal, clamp=False)
    defaults = [f'{ROOT}/Textures/{name}' for name in DEFAULTS]
    for alpha, name in enumerate(PARENTS):
        add({'id': f'unreal.megapark.material.{name}', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
             'code': code, 'params': {'args': {'action': 'parent', 'alpha': alpha,
                                               'defaults': {n: _native(owned[p])['name'] for n, p in zip(DEFAULTS, defaults)}},
                                      'settings': []},
             'outputs': [_output('asset', f'{ROOT}/Materials/{name}', 'Material')]},
            [_native(owned[p]) for p in defaults], package=f'{ROOT}/Materials/{name}', dependencies=defaults)
    build_json = _item('build', 'world.megapark', library_item)
    build_root = {'build': {'archive_member': library_roots[f'{BUILD}/build.json'], 'name': 'build.json'}}
    lightmaps = _item('restyle', restyle_row['id'], 'output0')
    lightmap_root = {'restyle': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures.json'}}
    for key, spec in sorted(members['materials'].items()):
        parent = f'{ROOT}/Materials/{PARENTS[spec["alpha"]]}'
        maps = sorted({f'{ROOT}/Textures/T_{tid[2:]}' for tid in spec['textures'].values()})
        closure = [parent, *maps, *defaults]
        package = f'{ROOT}/Materials/MI_{key[2:]}'
        add({'id': f'unreal.megapark.instance.{key[2:]}', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
             'code': code, 'params': {'args': {
                 'action': 'instance', 'key': key, 'alpha': spec['alpha'], 'parent': _native(owned[parent])['name'],
                 'textures': {role: _native(owned[f'{ROOT}/Textures/T_{tid[2:]}'])['name'] for role, tid in spec['textures'].items()},
                 'defaults': {n: _native(owned[p])['name'] for n, p in zip(DEFAULTS, defaults)},
                 'build': 'build', 'restyle': 'restyle'}, 'settings': []},
             'outputs': [_output('asset', package, 'MaterialInstanceConstant')]},
            [*(_native(owned[p]) for p in dict.fromkeys(closure)), dict(build_json), dict(lightmaps)],
            {**build_root, **lightmap_root}, package=package, dependencies=closure)
    add({'id': 'unreal.megapark.level', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
         'params': {'args': {'action': 'level', 'build': 'build', 'render': render, 'collision': collision,
                             'pieces': level_token(render, collision)}, 'settings': list(SETTINGS)},
         'outputs': [{'id': 'asset', 'logical_path': LEVEL, 'class': 'Map', 'destination': 'checkout', 'files': [
             {'path': 'content' + LEVEL + suffix, 'install_path': GAME + '/unreal/Content' + LEVEL.removeprefix('/Game') + suffix,
              'required': suffix == '.umap'} for suffix in ('.umap', *SIDECARS)]}]},
        [dict(build_json)], dict(build_root), package=LEVEL)
    owned[LEVEL]['derived_dependencies'] = {'pieces': level_token(render, collision)}
    return {'units': units, 'staged_inputs': staged, 'packages': owned, 'module_requirements': requirements}


def attach_followers(geometry, natives, *, rows, checkout):
    """@cc [owner:fontanierh,label:correctness] original-megapark-native-followers
    Every megapark D2 parent except the import seed MUST receive independent
    per-piece raw and finish owners at /Game/MegaPark/Meshes/<piece>. Finish MUST
    consume its own export, MeshIR payload and logical-parent metadata and the
    supplied MI closure; nothing is discovered or duplicated. All pieces MUST be
    complex-as-simple with the original UV precision/degenerate/distance-field
    LOD settings; UC_ pieces are double-sided unless one-sided, SM_ pieces bind
    their MeshIR slots by name.
    """
    checkout = Path(checkout).resolve()
    _textures, render, collision, seam = catalogue(checkout)
    parents = {*render, *collision, *seam}
    if not isinstance(natives, dict) or not natives:
        raise Unsupported('MegaPark pieces need the supplied MI roster')
    instances = sorted(p for p in natives if p.startswith(ROOT + '/Materials/MI_'))
    if not instances:
        raise Unsupported('MegaPark pieces need at least one supplied MI_ instance')
    dependencies = {}

    def dependency(ref):
        if (not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('unit', 'item', 'package'))
                or not ref['package'].startswith('/Game/') or set(ref) - {'unit', 'item', 'package', 'dependencies'}):
            raise Unsupported('MegaPark material dependency must name its actual finished native Item')
        key = ref['unit'], ref['item']
        if key in dependencies:
            if dependencies[key][1]['package'] != ref['package']:
                raise Unsupported('MegaPark material Item aliases distinct native packages')
            return dependencies[key][0]
        slot = 'native' + str(len(dependencies)); dependencies[key] = slot, ref
        for child in ref.get('dependencies', ()):
            if isinstance(child, str):
                if child not in natives:
                    raise Unsupported('Missing supplied MegaPark transitive input: ' + child)
                child = natives[child]
            dependency(child)
        return slot

    materials = {}
    for package in instances:
        if natives[package].get('package') != package:
            raise Unsupported('MegaPark instance ref names another package: ' + package)
        materials['0x' + package.rsplit('/MI_', 1)[1]] = dependency(natives[package])
    by_id = {row['id']: row for row in rows}
    texture = _load(checkout, GAME + '/v2_texture_units.py', 'v2_megapark_texture')
    island = _load(checkout, GAME + '/v2_island_units.py', 'v2_megapark_items')
    code = _code_closure(checkout)
    editor = _modules(checkout, [])[0]
    result = deepcopy(geometry); seen = set(); requirements = dict(result.get('module_requirements', {}))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.megapark.export.'):
            continue
        parent = template['unit_prefix'].removeprefix('world.megapark.export.')
        if parent == 'SM_MP_ImportSeed':
            continue
        if (parent not in parents or parent in seen or template['producer'] != 'world.megapark.geometry.' + parent
                or template['group'] != 'geometry' or template['op'] != {'kind': 'blender_export_piece', 'version': '1'}
                or template['params'].get('format') != 'fbx'
                or template['files'] != [{'path': '$piece.fbx'}, {'path': 'export.json'}] or template.get('followers')):
            raise Unsupported('MegaPark native followers require every original FBX D2 parent exactly once')
        seen.add(parent)
        producer = by_id.get(template['producer'])
        if producer is None:
            raise Unsupported('MegaPark follower needs its actual geometry row: ' + template['producer'])
        metadata_item, metadata_roots = _product(producer, 'megapark.metadata.' + parent)
        (metadata_path, metadata_member), = metadata_roots.items()
        raw_package, destination = RAW + '/Meshes/$piece', ROOT + '/Meshes/$piece'
        raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(checkout), 'inputs': [{'role': 'content', 'name': 'source',
                   'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}}],
               'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                          'fbx': dict(FBX), 'settings': list(SETTINGS)},
               'outputs': [island._item(raw_package, raw=True)]}
        inputs = [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                  {'role': 'content', 'name': 'source_export', 'source': {'kind': 'item', 'unit': '$export', 'item': 'asset'}},
                  {'role': 'content', 'name': 'payload', 'source': {'kind': 'group_member', 'unit': template['producer'],
                                                                    'group': 'geometry', 'piece': '$piece'}},
                  _item('metadata', template['producer'], metadata_item),
                  *({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
                    for slot, ref in dependencies.values())]
        finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
                  'code': code, 'inputs': inputs,
                  'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                             'package_sources': {'raw': raw_package},
                             'input_roots': {'metadata': {'archive_member': metadata_member, 'name': parent + '.json'}},
                             'args': {'action': 'mesh', 'parent': parent, 'collision': parent.startswith('UC_'),
                                      'payload': 'payload', 'source_export': 'source_export', 'metadata': 'metadata',
                                      'materials': materials,
                                      'native_inputs': {slot: ref['package'] for slot, ref in dependencies.values()}},
                             'settings': list(SETTINGS)},
                  'outputs': [island._item(destination, raw=False)]}
        template['followers'] = [{'unit': raw, 'staged_inputs': {'source': 'inputs/source'}},
                                 {'unit': finish, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in inputs}}]
        requirements[template['unit_prefix']] = editor
    if seen != parents:
        raise Unsupported('MegaPark native followers require the complete render/collision/seam family')
    result['module_requirements'] = requirements
    return result
