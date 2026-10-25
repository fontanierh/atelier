"""Replace Scripts/import_ferry.py by one unit per native Ferry package (world/ferry_v2.py).

The original authors M_Ferry (Tint/Roughness/Metallic parameters), M_FerryWake and FY_Wake (the engine plane with
the wake material and no collision), one MaterialInstanceConstant per palette entry (the ship's FY_ palette, then
the terminals' palette, which is the ship's extended by FT_), and imports the ship meshes into /Game/Ferry/Ship and
the terminal meshes into /Game/Ferry/Terminals. Here each package has its own author unit or raw import + finish,
consuming exact roots of the actual ferry.ship, ferry_ship.collision_data and ferry.terminals Products. The mesh
roster is the actual unreal.ferry row's declared packages; the palette is the committed MATERIALS literals.
"""
import ast
import importlib.util
from pathlib import Path, PurePosixPath

from v2_character_units import _modules, _output
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/ferry_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_ferry.py'
NATIVE = GAME + '/unreal/Scripts/ferry_native.py'
SHIP_SOURCE = GAME + '/assets/vehicles/ferry/build.py'
TERMINAL_SOURCE = GAME + '/assets/vehicles/ferry/terminals/build.py'
BUILD = 'build/yorimichi/ferry'
CONTENT = GAME + '/unreal/Content/Ferry'
RAW = '/Game/_Raw/Ferry'
MATERIALS = '/Game/Ferry/Materials/'
FUNCTIONS = ('material_parent', 'wake_material', 'wake_mesh', 'materials')
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']


def _load(checkout, relative, name):
    spec = importlib.util.spec_from_file_location(name, Path(checkout) / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def palettes(checkout):
    """(ship palette names, terminal-only palette names) from the committed MATERIALS literals."""
    sources = _load(checkout, GAME + '/world/regions/ferry/ship_sources.py', 'v2_ferry_ship_sources')
    ship = list(sources.palette((Path(checkout) / SHIP_SOURCE).read_text()))
    terminal = list(sources.palette((Path(checkout) / TERMINAL_SOURCE).read_text()))
    text = (Path(checkout) / TERMINAL_SOURCE).read_text()
    if 'F.MATERIALS.update(MATERIALS)' not in text or set(ship) & set(terminal) or not ship or not terminal:
        raise Unsupported('the terminal palette no longer extends the ship palette with distinct names')
    return ship, terminal


def _check_original(checkout):
    tree = ast.parse((Path(checkout) / ORIGINAL).read_bytes())
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if set(FUNCTIONS) - defined:
        raise Unsupported('import_ferry.py no longer defines ' + ', '.join(sorted(set(FUNCTIONS) - defined)))
    text = ast.unparse(tree)
    for expected in ("names += ['FY_Collision'] if folder == ROOT else ['FT_HD_Collision', 'FT_BC_Collision']",
                     "collision = name.endswith(('_Collision', '_Brow'))"):
        if expected not in text:
            raise Unsupported('import_ferry.py mesh policy changed: ' + expected)


def _product(row, product_id):
    index = [i for i, p in enumerate(row['products']) if p['id'] == product_id]
    if len(index) != 1 or row['products'][index[0]]['optional_paths']:
        raise Unsupported(f'{row["id"]} must own exactly one complete {product_id} product')
    paths = row['products'][index[0]]['paths']
    return f'product{index[0]}', {str(path): f'products/{index[0]}-{j}.tree.tar' for j, path in enumerate(paths)}


def roster(rows):
    by_id = {row['id']: row for row in rows}
    importer = by_id.get('unreal.ferry')
    if importer is None:
        raise Unsupported('Ferry needs the actual unreal.ferry row')
    commands = importer['commands']
    if (len(commands) != 1 or commands[0].get('kind') != 'UnrealScript' or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('args') or str(importer['outputs'][0]) != BUILD + '/import-report.json'):
        raise Unsupported('unreal.ferry differs from the original import_ferry.py target')
    folders = {'Ship': [], 'Terminals': []}
    for path in importer['outputs'][1:]:
        path = PurePosixPath(str(path))
        if str(path.parent) not in (CONTENT + '/Ship', CONTENT + '/Terminals') or path.suffix != '.uasset':
            raise Unsupported('unreal.ferry declares a package outside Ship/Terminals: ' + str(path))
        folders[path.parent.name].append(path.stem)
    if ('FY_Collision' not in folders['Ship'] or not {'FT_HD_Collision', 'FT_BC_Collision'} <= set(folders['Terminals'])
            or any(not n.startswith('FY_') for n in folders['Ship']) or any(not n.startswith('FT_') for n in folders['Terminals'])
            or 'FY_Wake' in folders['Ship']):
        raise Unsupported('unreal.ferry mesh packages differ from the original ship/terminal rosters')
    return folders


def ferry_units(rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] authored-c3-ferry
    import_ferry.py MUST become one unit per native package: M_Ferry, M_FerryWake,
    FY_Wake, one instance per committed palette entry and a raw import + finish
    per declared ship and terminal mesh, each consuming only exact roots of the
    actual ferry Products. Finishes MUST keep the original slot binding, simple-
    as-complex UCX policy and ferry_native current-source validation. Generated
    content is never scanned; the original top level, service gate and
    retirement never run.
    """
    checkout = Path(checkout)
    _check_original(checkout)
    meshes = roster(rows)
    ship_palette, terminal_palette = palettes(checkout)
    by_id = {row['id']: row for row in rows}
    for name in ('world.ferry_ship', 'world.ferry_ship.audit', 'world.ferry_terminals'):
        if name not in by_id:
            raise Unsupported('Ferry needs the actual row ' + name)
    ship_item, ship_roots = _product(by_id['world.ferry_ship'], 'ferry.ship')
    data_item, data_roots = _product(by_id['world.ferry_ship.audit'], 'ferry_ship.collision_data')
    terminal_item, terminal_roots = _product(by_id['world.ferry_terminals'], 'ferry.terminals')
    if (not {BUILD + '/manifest.json', BUILD + '/atomic-manifest.json', BUILD + '/atomic-assets'} <= set(ship_roots)
            or set(data_roots) != {BUILD + '/ship-collision-data.json'}
            or set(terminal_roots) != {f'{BUILD}/terminals/{n}' for n in ('manifest.json', 'atomic-manifest.json', 'atomic-assets')}):
        raise Unsupported('ferry Products differ from the complete file-only assemblies')
    ship_sources = _load(checkout, GAME + '/world/regions/ferry/ship_sources.py', 'v2_ferry_ship_parents')
    tree = ast.parse((checkout / GAME / 'ferry_terminal_atomic_build.py').read_bytes())
    models = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'MODELS' for t in n.targets))
    from atelier.source_imports import ImportScanner
    found = set()
    for helper in (NATIVE, ORIGINAL.replace('import_ferry.py', 'mesh_materials.py')):
        found |= {p.relative_to(checkout).as_posix() for p in ImportScanner().local_imports(
            checkout / helper, (checkout / GAME / 'unreal/Scripts', checkout / GAME / 'world', checkout / 'platform/studio'))}
    code, ops_code = sorted({*_code(checkout), SCRIPT, ORIGINAL, *found}), list(_code(checkout))
    editor = _modules(checkout, [])[0]
    units, staged, owned, requirements = [], {}, {}, {}

    def item(name, unit, item_id):
        return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}

    def root(name, unit, item_id, member, basename):
        return item(name, unit, item_id), {name: {'archive_member': member, 'name': basename}}

    def native(package):
        ref = owned[package]
        return item('native_' + package.removeprefix('/Game/').replace('/', '_'), ref['unit'], ref['item'])

    def add(unit, inputs, roots=None, *, cls, package, item_id='asset', dependencies=()):
        if roots:
            unit['params']['input_roots'] = roots
        unit['inputs'] = inputs
        unit.setdefault('outputs', [_output(item_id, package, cls)])
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'unreal.raw_import':
            requirements[unit['id']] = editor
            owned[package] = {'unit': unit['id'], 'item': item_id, 'package': package,
                              'dependencies': [dict(owned[p]) for p in dependencies]}

    def author(unit_id, args, inputs, roots, cls, package, dependencies=()):
        add({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': args, 'settings': []}}, inputs, roots, cls=cls, package=package, dependencies=dependencies)

    parent, wake = MATERIALS + 'M_Ferry', MATERIALS + 'M_FerryWake'
    author('unreal.ferry.material.M_Ferry', {'action': 'parent'}, [], None, 'Material', parent)
    author('unreal.ferry.material.M_FerryWake', {'action': 'wake_material'}, [], None, 'Material', wake)
    author('unreal.ferry.mesh.FY_Wake', {'action': 'wake_mesh', 'material': native(wake)['name']}, [native(wake)], None,
           'StaticMesh', '/Game/Ferry/Ship/FY_Wake', [wake])
    ship_manifest = root('ship_manifest', 'world.ferry_ship', ship_item, ship_roots[BUILD + '/manifest.json'], 'manifest.json')
    terminal_manifest = root('terminal_manifest', 'world.ferry_terminals', terminal_item,
                             terminal_roots[BUILD + '/terminals/manifest.json'], 'manifest.json')
    for name in (*ship_palette, *terminal_palette):
        # The original writes each FY_ instance from the ship pass, then again from the terminal pass: both manifests
        # must give it the same values. FT_ instances exist only in the terminal pass.
        manifests = [ship_manifest, terminal_manifest] if name in ship_palette else [terminal_manifest]
        inputs, roots = [native(parent)], {}
        for slot, binding in manifests:
            inputs.append(dict(slot)); roots.update(binding)
        author(f'unreal.ferry.instance.{name}', {'action': 'instance', 'name': name, 'parent': native(parent)['name'],
                                                 'manifests': [slot['name'] for slot, _ in manifests]},
               inputs, roots, 'MaterialInstanceConstant', MATERIALS + name, [parent])
    passes = (('Ship', 'world.ferry_ship', ship_item, ship_roots, BUILD, ship_palette, list(ship_sources.BUILDERS)),
              ('Terminals', 'world.ferry_terminals', terminal_item, terminal_roots, BUILD + '/terminals',
               [*ship_palette, *terminal_palette], list(models)))
    for folder, unit_of, product, roots_of, base, palette, parents in passes:
        closure = [parent, *(MATERIALS + name for name in palette)]
        manifest_slot, manifest_root = root('manifest', unit_of, product, roots_of[base + '/manifest.json'], 'manifest.json')
        atomic_slot, atomic_root = root('atomic', unit_of, product, roots_of[base + '/atomic-manifest.json'], 'atomic-manifest.json')
        for name in meshes[folder]:
            raw_package, package = f'{RAW}/{folder}/{name}', f'/Game/Ferry/{folder}/{name}'
            raw_id = f'unreal.ferry.mesh.raw.{name}'
            source, source_root = root('source', unit_of, product, roots_of[base + '/atomic-assets'], 'atomic-assets')
            add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
                 'params': {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': raw_package,
                            'source_member': name + '.fbx', 'settings': list(SETTINGS)},
                 'outputs': [_output('raw', raw_package, 'RawStaticMesh', store=True)]},
                [source], source_root, cls='RawStaticMesh', package=raw_package)
            inputs = [item('raw', raw_id, 'raw'), dict(manifest_slot), dict(atomic_slot), *(native(p) for p in closure)]
            roots = {**manifest_root, **atomic_root}
            args = {'action': 'mesh', 'name': name, 'folder': folder, 'parents': parents,
                    'materials': {n: native(MATERIALS + n)['name'] for n in palette},
                    'manifest': 'manifest', 'atomic': 'atomic'}
            if name == 'FY_Collision':
                slot, binding = root('collision_data', 'world.ferry_ship.audit', data_item,
                                     data_roots[BUILD + '/ship-collision-data.json'], 'ship-collision-data.json')
                inputs.append(slot); roots.update(binding); args['collision_data'] = 'collision_data'
            add({'id': f'unreal.ferry.mesh.{name}', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT,
                 'code': code, 'params': {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': package,
                                          'package_sources': {'raw': raw_package}, 'args': args, 'settings': list(SETTINGS)}},
                inputs, roots, cls='StaticMesh', package=package, dependencies=closure)
    return {'units': units, 'staged_inputs': staged, 'packages': owned, 'module_requirements': requirements,
            'palettes': {'ship': ship_palette, 'terminal': terminal_palette}}
