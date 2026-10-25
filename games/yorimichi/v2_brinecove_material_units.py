"""Individual original Brinecove shader and texture owners, without receiver execution."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path

SCRIPT = 'games/yorimichi/world/brinecove_material_v2.py'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_brinecove.py'
ROOT = '/Game/Brinecove'


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def static_materials(checkout):
    """Run only original pure descriptor functions over committed source tables/files."""
    root = Path(checkout)
    colors = None
    for node in ast.parse((root / 'games/yorimichi/world/regions/brinecove/layout.py').read_bytes()).body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'COLORS' for n in node.targets):
            colors = ast.literal_eval(node.value)
    if not isinstance(colors, dict):
        raise ValueError('Missing original Brinecove palette')
    source = root / 'games/yorimichi/world/regions/brinecove/runtime_data.py'
    tree = ast.parse(source.read_bytes())
    constants = {'MASKED', 'TERRAIN', 'TRANSLUCENT', 'EMISSIVE', 'PAN_CM_S', 'MOTION', 'TEXTURE', 'TERRAIN_LAYERS', 'ROCK_TINT'}
    namespace = {'L': type('Palette', (), {'COLORS': colors}), 'TEXTURES': root / 'games/yorimichi/assets/brinecove/textures'}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants:
            namespace[node.targets[0].id] = ast.literal_eval(node.value)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('kind', 'srgb_to_linear', 'material_report')]
    if len(functions) != 3 or not constants <= set(namespace):
        raise ValueError('Original Brinecove descriptor helpers missing')
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['material_report']({*colors, 'terrain'})


def author_units(packages=None, *, checkout, hero_materials=None, textures=None):
    """@cc [owner:fontanierh,label:correctness] brinecove-original-material-owners
    Static descriptors MUST use original keyed pure functions and committed source
    textures. Hero descriptors/textures MUST be actual supplied semantic inputs;
    missing roles MUST remain explicit, never become grey/white fallback instances.
    Each parent, instance and texture MUST own one original native package, using
    original shader/atmosphere/motion/terrain/colour properties without old main.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    texture = _load(root, 'games/yorimichi/v2_texture_units.py', 'brinecove_texture_owner')
    descriptors, source_files = static_materials(root)
    body = _load(root, SCRIPT, 'brinecove_material_descriptor_check')
    missing = []
    if hero_materials is None:
        missing.append('hero_material_descriptors')
    else:
        for key, value in hero_materials.items():
            if key in descriptors or not key.startswith('hero_') or not isinstance(value, dict):
                raise ValueError('Hero material must have its original distinct descriptor')
            descriptors[key] = deepcopy(value)
    refs = dict(packages or {})
    supplied_textures = dict(textures or {})
    code = set(texture._code(root)) | {SCRIPT, ORIGINAL}
    for helper in (SCRIPT, 'games/yorimichi/unreal/Scripts/atmosphere.py'):
        code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(root / helper,
            (root / 'platform/studio', root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts')))
    units, staged, slots = [], {}, {}
    def append(unit):
        units.append(unit)
        staged[unit['id']] = {row['name']: 'inputs/' + row['name'] for row in unit['inputs']}
        slots.update({row['name']: False for row in unit['inputs']})
    files = set()
    for row in descriptors.values():
        body.descriptor(row)
        if row.get('texture'): files.add(row['texture'])
        files.update(value for table in ('layers', 'normals') for value in row.get(table, {}).values() if value)
    for filename in sorted(files):
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.startswith('T_BC_') or Path(filename).suffix not in ('.png', '.jpg'):
            raise ValueError('Invalid original Brinecove texture filename')
        package = ROOT + '/Textures/' + Path(filename).stem
        if filename in supplied_textures and 'package' in supplied_textures[filename]:
            ref = supplied_textures[filename]
            if ref['package'] != package or not ref.get('unit') or not ref.get('item'):
                raise ValueError('Supplied Brinecove texture differs from its native package')
            refs[package] = dict(ref); continue
        params = {'op': 'raw_import', 'kind': 'texture', 'source': 'source',
                  'destination': '/Game/_Raw/BrinecoveTextures/' + Path(filename).stem}
        if filename in source_files:
            path = source_files[filename]
            if path.is_symlink() or not path.is_file() or path.resolve() != path:
                raise ValueError('Brinecove source texture is missing or aliased')
            source = {'kind': 'file', 'path': path.relative_to(root).as_posix()}
        elif filename in supplied_textures:
            ref = supplied_textures[filename]
            if any(not isinstance(ref.get(k), str) or not ref[k] for k in ('unit', 'item', 'file', 'member')):
                raise ValueError('Hero texture needs its actual finished Data Item and exact PNG member')
            source = {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}
            params.update(input_roots={'source': {'archive_member': ref['file'], 'name': 'source'}}, source_member=ref['member'])
        else:
            missing.append('texture:' + filename); continue
        raw_id, finish_id = 'unreal.brinecove.texture.raw.' + Path(filename).stem, 'unreal.brinecove.texture.finish.' + Path(filename).stem
        append({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
            'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'source', 'source': source}],
            'params': params, 'outputs': [texture._output(params['destination'], raw=True)]})
        append({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': texture.OPS,
            'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': raw_id, 'item': 'raw_texture'}}],
            'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                'package_sources': {'raw': params['destination']}, 'properties': {
                    'srgb': not Path(filename).stem.endswith('_n'), 'max_texture_size': 1024,
                    'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}}},
            'outputs': [texture._output(package, raw=False)]})
        refs[package] = {'unit': finish_id, 'item': 'texture', 'package': package}
    parent_names = {'opaque': 'M_Brinecove', 'emissive': 'M_Brinecove', 'masked': 'M_BrinecoveMasked',
                    'translucent': 'M_BrinecoveSpray', 'terrain': 'M_BrinecoveTerrain'}
    def material(name, factory, args, dependencies):
        package = ROOT + '/Materials/' + name
        incoming, native = [], {}
        for index, path in enumerate(dict.fromkeys(dependencies)):
            slot = 'native' + str(index); ref = refs[path]; native[slot] = path
            incoming.append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}})
        row = texture._output(package, raw=False); row.update(id='asset', **{'class': 'MaterialInstance' if factory == 'instance' else 'Material'})
        unit_id = 'unreal.brinecove.material.' + name
        append({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': sorted(code),
                'inputs': incoming, 'params': {'args': {'asset': name, 'package': package, 'factory': factory,
                    'inputs': native, **args}, 'settings': []}, 'outputs': [row]})
        refs[package] = {'unit': unit_id, 'item': 'asset', 'package': package}
    for kind in ('opaque', 'masked', 'translucent', 'terrain'):
        material(parent_names[kind], 'terrain_parent' if kind == 'terrain' else 'parent', {'blend': kind}, [])
    for key, descriptor in sorted(descriptors.items()):
        kind = descriptor.get('kind')
        if kind not in parent_names or descriptor.get('name') != 'MI_BC_' + key:
            raise ValueError('Brinecove descriptor differs from original material identity/kind')
        required_files = [descriptor['texture']] if descriptor.get('texture') else []
        required_files += [value for table in ('layers', 'normals') for value in descriptor.get(table, {}).values()]
        if any(not value or ROOT + '/Textures/' + Path(value).stem not in refs for value in required_files):
            missing.append('material_textures:' + key); continue
        parent = ROOT + '/Materials/' + parent_names[kind]
        material(descriptor['name'], 'instance', {'descriptor': descriptor},
                 [parent, *(ROOT + '/Textures/' + Path(value).stem for value in required_files)])
        refs[ROOT + '/Materials/' + descriptor['name']]['material_kind'] = kind
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots,
            'packages': {key: ref for key, ref in refs.items() if key not in (packages or {}) or ref != packages[key]},
            'missing_roles': sorted(set(missing))}
