"""Replace Scripts/import_gondola.py by one unit per native ropeway package (world/gondola_v2.py).

The original imports the complete kit (params.asset_names() from build/yorimichi/gondola/assets) into
/Game/Gondola/Kit, the fitted world meshes (site.json exports without rope _LOD1/_LOD2) into /Game/Gondola/World,
the GD_<name> materials (params.MATERIALS, values from the kit manifest) into /Game/Gondola/Materials and their
timber textures into /Game/Gondola/Textures. Here every package has its own raw import and finish (textures,
meshes) or author (materials) unit, and every source is an exact root of an actual producer Item:
world.gondola_kit (manifest.json, assets), world.gondola_kit.textures (one PNG per root) and world.gondola_site
(site.json and one FBX per output). The roster is the actual unreal.gondola row's declared packages.
"""
import importlib.util
from pathlib import Path, PurePosixPath

from v2_character_units import _modules, _output
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/gondola_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_gondola.py'
KIT = GAME + '/assets/vehicles/gondola'
BUILD = 'build/yorimichi/gondola'
CONTENT = GAME + '/unreal/Content/Gondola'
HELPERS = ('material_assets.py', 'mesh_materials.py')
RAW = '/Game/_Raw/Gondola'


def _load(checkout, relative, name):
    spec = importlib.util.spec_from_file_location(name, Path(checkout) / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _rows(rows):
    by_id = {row['id']: row for row in rows}
    needed = ('world.gondola_kit', 'world.gondola_kit.textures', 'world.gondola_site', 'unreal.gondola')
    missing = [name for name in needed if name not in by_id]
    if missing:
        raise Unsupported('Gondola needs the actual rows: ' + ', '.join(missing))
    return by_id


def _product(row, product_id):
    """(item, {path: archive member}) of one declared product of an actual row."""
    index = [i for i, p in enumerate(row['products']) if p['id'] == product_id]
    if len(index) != 1:
        raise Unsupported(f'{row["id"]} must own exactly one {product_id} product')
    product = row['products'][index[0]]
    if product['optional_paths']:
        raise Unsupported(f'{product_id} has optional roots')
    return f'product{index[0]}', {str(path): f'products/{index[0]}-{j}.tree.tar' for j, path in enumerate(product['paths'])}


def roster(rows, checkout):
    """The original's package closure, from the actual unreal.gondola row and cross-checked with its committed source."""
    by_id = _rows(rows)
    importer = by_id['unreal.gondola']
    commands = importer['commands']
    if (len(commands) != 1 or commands[0].get('kind') != 'UnrealScript' or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('args') or importer['products']):
        raise Unsupported('unreal.gondola differs from the original import_gondola.py target')
    declared = {}
    for path in importer['outputs'][1:]:
        relative = PurePosixPath(str(path))
        if not str(relative).startswith(CONTENT + '/') or relative.suffix != '.uasset' or len(relative.parts) != len(PurePosixPath(CONTENT).parts) + 2:
            raise Unsupported('unreal.gondola declares an output outside its four package folders: ' + str(path))
        declared.setdefault(relative.parent.name, []).append(relative.stem)
    if str(importer['outputs'][0]) != BUILD + '/import-report.json' or set(declared) != {'Kit', 'World', 'Materials', 'Textures'}:
        raise Unsupported('unreal.gondola outputs differ from the original four package folders')
    parameters = _load(checkout, KIT + '/params.py', 'v2_gondola_parameters')
    names = _site_names(by_id['world.gondola_site'])
    textures = {name: [f'GD_{key}_{kind}' for kind in ('color', 'rough')] for name, key in parameters.TEXTURED.items()}
    expected = {'Kit': list(parameters.asset_names()), 'World': [n for n in names if not n.endswith(('_LOD1', '_LOD2'))],
                'Materials': list(parameters.MATERIALS),
                'Textures': [PurePosixPath(f).stem for f in parameters.product_files() if f.startswith('textures/')]}
    if (any(sorted(declared[k]) != sorted(v) for k, v in expected.items())
            or sorted(t for pair in textures.values() for t in pair) != sorted(expected['Textures'])):
        raise Unsupported('unreal.gondola packages differ from params.py and the fitted site roster')
    lods = {n: [f'{n[:-1]}{level}' for level in (1, 2)] for n in expected['World'] if n.endswith('_Rope_LOD0')}
    if any(lod not in names for pair in lods.values() for lod in pair) or len(names) != len(expected['World']) + 2 * len(lods):
        raise Unsupported('Gondola rope detail levels differ from the fitted site')
    return {**expected, 'textured': textures, 'lods': lods}


def _site_names(row):
    commands = row['commands']
    if (len(commands) != 1 or commands[0].get('kind') != 'blender'
            or commands[0].get('script') != {'path': GAME + '/world/regions/gondola/site.py'} or row['products']
            or str(row['outputs'][0]) != BUILD + '/world/site.json'):
        raise Unsupported('world.gondola_site differs from the original fitted site export')
    names = []
    for path in row['outputs'][1:]:
        path = PurePosixPath(str(path))
        if str(path.parent) != BUILD + '/world/assets' or path.suffix != '.fbx':
            raise Unsupported('world.gondola_site declares a non-mesh output: ' + str(path))
        names.append(path.stem)
    return names


def gondola_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] authored-c3-gondola
    import_gondola.py MUST become one unit per native package of the actual
    unreal.gondola row: a raw import and finish per texture and mesh and an author
    per GD material, each consuming only exact roots of the actual kit, texture
    and fitted-site Items. Finishes MUST keep the original collision, slot,
    distance-field and rope detail-level policy. Generated content is never
    scanned and the original never runs.
    """
    checkout = Path(checkout)
    by_id = _rows(rows)
    packages = roster(rows, checkout)
    kit_item, kit_roots = _product(by_id['world.gondola_kit'], 'gondola.kit')
    texture_item, texture_roots = _product(by_id['world.gondola_kit.textures'], 'gondola_kit.textures')
    if set(kit_roots) != {BUILD + '/manifest.json', BUILD + '/atomic-manifest.json', BUILD + '/assets'}:
        raise Unsupported('gondola.kit roots differ from the complete file-only kit')
    if set(texture_roots) != {f'{BUILD}/textures/{stem}.png' for stem in packages['Textures']}:
        raise Unsupported('gondola_kit.textures roots differ from the declared texture packages')
    site = by_id['world.gondola_site']
    site_outputs = {PurePosixPath(str(path)).stem: (f'output{i}', f'outputs/{i}.tree.tar')
                    for i, path in enumerate(site['outputs'])}
    from atelier.source_imports import ImportScanner
    found = set()
    for helper in HELPERS:
        found |= {p.relative_to(checkout).as_posix() for p in ImportScanner().local_imports(
            checkout / GAME / 'unreal/Scripts' / helper, (checkout / GAME / 'unreal/Scripts', checkout / 'platform/studio'))}
    code, ops_code = sorted({*_code(checkout), SCRIPT, *found}), list(_code(checkout))
    editor = _modules(checkout, [])[0]
    units, staged, owned = [], {}, {}

    def item(name, unit, item_id):
        return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}

    def root(name, unit, item_id, member, basename):
        return item(name, unit, item_id), {name: {'archive_member': member, 'name': basename}}

    def add(unit, inputs, roots=None):
        if roots:
            unit['params']['input_roots'] = roots
        unit['inputs'] = inputs
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'unreal.raw_import':
            requirements[unit['id']] = editor

    requirements = {}
    for stem in packages['Textures']:
        raw_package, package = f'{RAW}/Textures/{stem}', f'/Game/Gondola/Textures/{stem}'
        raw_id, finish_id = f'unreal.gondola.texture.raw.{stem}', f'unreal.gondola.texture.{stem}'
        source, roots = root('source', 'world.gondola_kit.textures', texture_item,
                             texture_roots[f'{BUILD}/textures/{stem}.png'], stem + '.png')
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package},
             'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]}, [source], roots)
        add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                        'package_sources': {'raw': raw_package},
                        # import_gondola.material: roughness maps are linear.
                        'properties': {'srgb': False} if stem.endswith('_rough') else {}},
             'outputs': [_output('texture', package, 'Texture')]}, [item('raw', raw_id, 'raw_texture')])
        owned[package] = {'unit': finish_id, 'item': 'texture', 'package': package}

    def native(package):
        ref = owned[package]
        return item('native_' + package.removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])

    manifest, manifest_roots = root('manifest', 'world.gondola_kit', kit_item, kit_roots[BUILD + '/manifest.json'], 'manifest.json')
    for name in packages['Materials']:
        package = f'/Game/Gondola/Materials/{name}'
        unit_id = f'unreal.gondola.material.{name}'
        maps = [f'/Game/Gondola/Textures/{stem}' for stem in packages['textured'].get(name, ())]
        args = {'action': 'material', 'name': name, 'manifest': 'manifest'}
        if maps:
            args.update(color=native(maps[0])['name'], rough=native(maps[1])['name'])
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}, 'outputs': [_output('asset', package, 'Material')]},
            [dict(manifest), *(native(p) for p in maps)], dict(manifest_roots))
        owned[package] = {'unit': unit_id, 'item': 'asset', 'package': package,
                          'dependencies': [dict(owned[p]) for p in maps]}

    palette = [f'/Game/Gondola/Materials/{name}' for name in packages['Materials']]
    closure = [*palette, *(f'/Game/Gondola/Textures/{stem}' for stem in packages['Textures'])]
    materials = {name: native(f'/Game/Gondola/Materials/{name}')['name'] for name in packages['Materials']}
    for folder in ('Kit', 'World'):
        for name in packages[folder]:
            raw_package, package = f'{RAW}/{folder}/{name}', f'/Game/Gondola/{folder}/{name}'
            raw_id, finish_id = f'unreal.gondola.mesh.raw.{name}', f'unreal.gondola.mesh.{name}'
            if folder == 'Kit':
                source, roots = root('source', 'world.gondola_kit', kit_item, kit_roots[BUILD + '/assets'], 'assets')
                params = {'source_member': name + '.fbx'}
            else:
                output, member = site_outputs[name]
                source, roots = root('source', 'world.gondola_site', output, member, name + '.fbx')
                params = {}
            add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package, **params,
                            'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
                 'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]}, [source], roots)
            inputs, roots = [item('raw', raw_id, 'raw'), *(native(p) for p in closure)], {}
            lods = {}
            for level, lod in enumerate(packages['lods'].get(name, ()), start=1):
                output, member = site_outputs[lod]
                slot, binding = root(f'lod{level}', 'world.gondola_site', output, member, lod + '.fbx')
                inputs.append(slot); roots.update(binding); lods[str(level)] = slot['name']
            add({'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
                 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                            'package_sources': {'raw': raw_package},
                            'args': {'action': 'mesh', 'name': name, 'folder': folder, 'materials': materials, 'lods': lods},
                            'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},
                 'outputs': [_output('asset', package, 'StaticMesh')]}, inputs, roots)
            owned[package] = {'unit': finish_id, 'item': 'asset', 'package': package,
                              'dependencies': [dict(owned[p]) for p in closure]}
    return {'units': units, 'staged_inputs': staged, 'packages': owned, 'module_requirements': requirements}
