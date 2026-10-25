"""Compose native replacement owners over the ordinary source producer declarations."""
from copy import deepcopy


def shared_materials(rows, *, checkout):
    """Return independent texture/graph owners; no old native task or cache runs."""
    import importlib.util
    from pathlib import Path
    def load(name):
        spec = importlib.util.spec_from_file_location('native_' + name,
            Path(checkout) / 'games/yorimichi' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    texture = load('v2_texture_units')
    materials_source = load('v2_material_units')
    textures = texture.texture_units(rows, checkout=checkout)
    if len(textures['textures']) != 22:
        raise ValueError('Shared material library requires all 22 original texture producers')
    materials = materials_source.author_units(textures['textures'], checkout=checkout)
    native_code = texture._code(checkout)
    units = deepcopy(textures['units']) + deepcopy(materials['units'])
    for unit in units:
        unit['code'] = sorted(set(unit['code']) | set(native_code))
    return {'units': units,
            'staged_inputs': {**textures['staged'], **materials['staged_inputs']},
            'content_slots': {**textures['slots'], **materials['content_slots']},
            'packages': {**{row['package']: row for row in textures['textures'].values()},
                         **materials['packages']},
            'targets': tuple(unit['id'] for unit in materials['units'])}


def island(rows, geometry, *, checkout):
    """Compose the seven authored terrain families, shaders and their Slice map."""
    import importlib.util
    from pathlib import Path
    root = Path(checkout)
    def load(name):
        spec = importlib.util.spec_from_file_location('island_' + name,
            root / 'games/yorimichi' / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    native = shared_materials(rows, checkout=root)
    rock = load('v2_texture_units').coast_rock_units(checkout=root)
    native['units'].extend(rock['units'])
    native['staged_inputs'].update(rock['staged'])
    native['content_slots'].update(rock['slots'])
    native['packages'].update({row['package']: row for row in rock['textures'].values()})
    references = {**native['packages'], 'north_snow': {
        'unit': 'world.hidamari.north_masks', 'item': 'product0', 'file': 'products/0-1.tree.tar'}}
    materials = load('v2_island_material_units').author_units(references, checkout=root)
    native_code = load('v2_texture_units')._code(root)
    for unit in materials['units']:
        unit['code'] = sorted(set(unit['code']) | set(native_code))
    native['units'].extend(materials['units'])
    native['staged_inputs'].update(materials['staged_inputs'])
    native['content_slots'].update(materials['content_slots'])
    native['packages'].update(materials['packages'])
    geometry = load('v2_island_units').attach_followers(geometry, native['packages'],
                                                     native['units'], checkout=root)
    terrain = {}
    for template in geometry['templates']:
        if template['unit_prefix'].startswith('world.island.export.'):
            parent = template['producer'].rsplit('.', 1)[-1]
            terrain[parent] = {'derived_items': {'root': 'build/v2-derived/native-island/' + parent,
                'templates': [{key: template[key] for key in ('producer', 'group', 'unit_prefix')}
                              | {'follower': 1, 'item': 'asset'}]}}
    map_units = load('v2_map_units').author_units(
        world={'unit': 'world.layout', 'item': 'output0', 'file': 'outputs/0.tree.tar'},
        terrain=terrain, painterly=native['packages']['/Game/Japan/Materials/M_Painterly'],
        checkout=root)
    for unit in map_units['units']:
        unit['code'] = sorted(set(unit['code']) | set(native_code))
    native['units'].extend(map_units['units'])
    native['staged_inputs'].update(map_units['staged_inputs'])
    native['content_slots'].update(map_units['content_slots'])
    native['packages'].update(map_units['packages'])
    native['targets'] = ('unreal.island.map',)
    native['geometry'] = geometry
    return native


def _package_dependencies(native):
    classes = {'Texture', 'StaticMesh', 'SkeletalMesh', 'Skeleton', 'PhysicsAsset',
               'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Map', 'Sound', 'Animation'}
    by_id = {unit['id']: unit for unit in native['units']}
    result = {}
    for package, reference in native['packages'].items():
        if not package.startswith('/Game/') or reference['unit'] not in by_id:
            continue
        unit = by_id[reference['unit']]
        deps = []
        for incoming in unit['inputs']:
            source = incoming['source']
            owner = by_id.get(source.get('unit')) if source['kind'] == 'item' else None
            if owner:
                deps.extend(item['logical_path'] for item in owner['outputs']
                            if item['id'] == source['item'] and item['class'] in classes)
        result[package] = {'unit': reference['unit'], 'item': reference['item'],
                           'package': package, 'dependencies': sorted(set(deps))}
    return result


def lower(rows, geometry, *, checkout):
    """Game-authored replacements; unknown native families remain compiler refusals."""
    selected = {row['id'] for row in rows}
    if 'unreal.island' in selected:
        native = island(rows, geometry, checkout=checkout)
        native['aliases'] = {'unreal.island': ('unreal.island.map',)}
    elif 'unreal.materials' in selected:
        native = shared_materials(rows, checkout=checkout)
        native['aliases'] = {}
    else:
        return None
    native['aliases']['unreal.materials'] = tuple(unit['id'] for unit in native['units']
                                                if unit['id'].startswith('unreal.materials.'))
    foliage_ids = [name for name in selected if name.startswith('unreal.foliage.')]
    if foliage_ids:
        import importlib.util
        from pathlib import Path
        path = Path(checkout) / 'games/yorimichi/v2_foliage_units.py'
        spec = importlib.util.spec_from_file_location('native_foliage_units', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        foliage = module.foliage_units(rows, checkout=checkout, natives=_package_dependencies(native))
        native['units'].extend(foliage['units'])
        native['staged_inputs'].update(foliage['staged'])
        native['content_slots'].update(foliage['slots'])
        native['packages'].update(foliage['packages'])
        for name in foliage_ids:
            owner = name.removeprefix('unreal.foliage.')
            native['aliases'][name] = ('unreal.foliage.finish.' + owner,)
    return native
