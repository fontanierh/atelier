"""Individual original Treehouse texture and material owners over finished Data Items."""
from pathlib import Path

SCRIPT = 'games/yorimichi/world/treehouse_materials_v2.py'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_treehouse.py'
MAT = '/Game/Japan/Treehouse/Materials/'
TEX = '/Game/Japan/Treehouse/Textures/'


def author_units(sources, packages, *, checkout):
    """@cc [owner:fontanierh,label:correctness] treehouse-palette-item-owners
    Every original palette/prop/recolour texture and material MUST have an individual
    declared owner. Gain/glow MUST come from actual finished Data Items, not cold
    generated reads or generic defaults. Native parents/collections MUST be explicit
    dependencies. No old importer top-level/main/cache/receiving action MAY run.
    """
    from atelier.source_imports import ImportScanner
    from importlib.util import module_from_spec, spec_from_file_location
    root = Path(checkout).resolve()
    def load(path, name):
        spec = spec_from_file_location(name, root / path)
        module = module_from_spec(spec); spec.loader.exec_module(module)
        return module
    family = load('games/yorimichi/v2_treehouse_native_units.py', 'treehouse_native_palette')
    texture = load('games/yorimichi/v2_texture_units.py', 'treehouse_texture_palette')
    def relative(value):
        if not isinstance(value, str) or not value or '\\' in value or value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
            raise ValueError('Treehouse source selection must be canonical relative')
        return value
    for role in ('palette', 'props', 'trees'):
        ref = sources.get(role)
        if not isinstance(ref, dict) or any(not isinstance(ref.get(k), str) or not ref[k] for k in ('unit', 'item', 'file', 'member')):
            raise ValueError('Missing finished Treehouse source role: ' + role)
        relative(ref['file']); relative(ref['member'])
    scanner = ImportScanner()
    code = set(texture._code(root)) | {SCRIPT, ORIGINAL}
    for helper in (SCRIPT, 'games/yorimichi/unreal/Scripts/see_through.py'):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root / helper,
            (root / 'platform/studio', root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts')))
    units, staged, slots, refs = [], {}, {}, dict(packages)
    dependencies_by_package = {path: list(ref.get('dependencies', ())) for path, ref in packages.items()}
    def incoming(role):
        ref = sources[role]
        return {'role': 'content', 'name': role, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
    def append(unit):
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}
        slots.update({i['name']: False for i in unit['inputs']})
    def image(role, filename, package, *, canopy=False):
        name = package.rsplit('/', 1)[-1]
        raw_id, finish_id = 'unreal.treehouse.texture.raw.' + name, 'unreal.treehouse.texture.finish.' + name
        raw_package = '/Game/_Raw/TreehouseTextures/' + name
        member = str(Path(sources[role]['member']).parent / filename)
        raw = {'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': texture.OPS,
               'code': texture._code(root), 'inputs': [incoming(role)],
               'params': {'op': 'raw_import', 'kind': 'texture', 'source': role, 'destination': raw_package, 'source_member': member,
                          'input_roots': {role: {'archive_member': sources[role]['file'], 'name': role}}},
               'outputs': [texture._output(raw_package, raw=True)]}
        properties = ({'do_scale_mips_for_alpha_coverage': True,
                       'alpha_coverage_thresholds': {'unreal_type': 'Vector4', 'args': [0, 0, 0, .4]},
                       'mip_gen_settings': {'unreal_enum': 'TextureMipGenSettings.TMGS_SIMPLE_AVERAGE'}} if canopy else
                      {'srgb': True, 'max_texture_size': 1024,
                       'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}})
        finish = {'id': finish_id, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': texture.OPS,
                  'code': texture._code(root), 'inputs': [{'role': 'content', 'name': 'raw',
                    'source': {'kind': 'item', 'unit': raw_id, 'item': 'raw_texture'}}],
                  'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                             'package_sources': {'raw': raw_package}, 'properties': properties},
                  'outputs': [texture._output(package, raw=False)]}
        append(raw); append(finish)
        refs[package] = {'unit': finish_id, 'item': 'texture', 'package': package}
    palette = [slot for slot in family._palette(root) if slot != 'pane']
    for slug in palette:
        image('palette', slug + '.png', TEX + 'T_TH_' + slug)
    for prop in family.PROPS:
        image('props', prop + '.png', TEX + 'T_' + prop)
    for colour in ('crimson', 'amber'):
        image('trees', 'T_leaf_' + colour + '.png', '/Game/Japan/Textures/T_leaf_' + colour, canopy=True)
    def material(name, factory, dependencies, *, data=None, extra=None, package=None):
        package = package or MAT + name
        native = {}
        inputs = []
        complete = []
        def add(path):
            if path in complete:
                return
            complete.append(path)
            for dependency in dependencies_by_package.get(path, ()):
                add(dependency)
        for dependency in dependencies:
            add(dependency)
        for index, path in enumerate(complete):
            if path not in refs:
                raise ValueError('Missing finished Treehouse native material role: ' + path)
            slot = 'native' + str(index); native[slot] = path
            inputs.append({'role': 'content', 'name': slot, 'source': {'kind': 'item',
                'unit': refs[path]['unit'], 'item': refs[path]['item']}})
        args = {'asset': name, 'package': package, 'factory': factory, 'inputs': native, **(extra or {})}
        if data:
            inputs.append(incoming(data))
            args['data'] = {'slot': data, 'file': sources[data]['file'], 'member': sources[data]['member']}
        row = texture._output(package, raw=False)
        row.update(id='asset', **{'class': 'Material' if factory in ('parent', 'light_parent') else 'MaterialInstance'})
        unit = {'id': 'unreal.treehouse.material.' + name, 'op': {'kind': 'unreal.author', 'version': '1'},
                'script': SCRIPT, 'code': sorted(code), 'inputs': inputs,
                'params': {'args': args, 'settings': []}, 'outputs': [row]}
        append(unit)
        refs[package] = {'unit': unit['id'], 'item': 'asset', 'package': package}
        dependencies_by_package[package] = list(dependencies)
    material('M_TreeHouse', 'parent', [TEX + 'T_TH_wood_plank', '/Game/SeeThrough/MPC_SeeThrough'])
    for slug in palette:
        material('MI_TH_' + slug, 'palette', [MAT + 'M_TreeHouse', TEX + 'T_TH_' + slug],
                 data='palette', extra={'key': slug})
    material('MI_TH_trunk', 'trunk', [MAT + 'M_TreeHouse', TEX + 'T_TH_bark'], data='palette', extra={'key': 'bark'})
    material('M_TH_Light', 'light_parent', [])
    material('MI_TH_pane', 'pane', [MAT + 'M_TH_Light'])
    for prop in family.PROPS:
        material('MI_' + prop, 'prop', [MAT + 'M_TreeHouse', TEX + 'T_' + prop], data='props', extra={'key': prop})
    for colour in ('Crimson', 'Amber'):
        material('MI_Leaf' + colour, 'foliage', ['/Game/Japan/Materials/M_Foliage', '/Game/Japan/Textures/T_leaf_' + colour.lower()],
                 package='/Game/Japan/Materials/MI_Leaf' + colour)
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots,
            'packages': {key: value for key, value in refs.items() if key not in packages or value != packages[key]}}
