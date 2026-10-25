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



def _family_module(checkout, name):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('joined_' + name,
        Path(checkout) / 'games/yorimichi' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    import sys
    previous = list(sys.path)
    try:
        sys.path.insert(0, str(Path(checkout) / 'games/yorimichi'))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = previous
    return module


def _family_source_reference(rows, unit_id, suffix, member):
    """Resolve the actual required directory ROOT and original archive index."""
    matches = [row for row in rows if row['id'] == unit_id]
    if len(matches) != 1:
        raise ValueError(unit_id + ': missing or ambiguous source producer')
    row = matches[0]
    candidates = []
    for product_index, product in enumerate(row['products']):
        paths = [*product['paths'], *product['optional_paths']]
        for path_index, path in enumerate(paths):
            if path.endswith('/' + suffix) and path in product['paths']:
                candidates.append({'unit': unit_id, 'item': product.get('native_item', 'product' + str(product_index)),
                    'file': f'products/{product_index}-{path_index}.tree.tar', 'member': member})
    for output_index, path in enumerate(row['outputs']):
        if path.endswith('/' + suffix):
            candidates.append({'unit': unit_id, 'item': 'output' + str(output_index),
                               'file': f'outputs/{output_index}.tree.tar', 'member': member})
    if len(candidates) != 1:
        raise ValueError(unit_id + ': requires one complete directory ROOT for ' + suffix
                         + '; a metadata JSON output or pool_roots is insufficient')
    return candidates[0]


def _append_family(native, family):
    native['units'].extend(family['units'])
    native['staged_inputs'].update(family['staged_inputs'])
    native['content_slots'].update(family['content_slots'])
    native['packages'].update(family['packages'])


def _join_native_families(native, rows, geometry, selected, *, checkout):
    """@cc [owner:fontanierh,label:correctness] real-native-family-composition
    Family source refs MUST resolve actual required directory outputs/products and
    their real archive indices. Metadata-only outputs and pool roots MUST NOT imply
    PNG ownership. Missing hero/material/source/membership roles MUST remain explicit;
    an incomplete family MUST NOT replace an old importer through an alias.
    This composition MUST NOT execute producers, native jobs or generated scans.
    """
    gaps = list(native.get('missing_roles', ()))
    geometry = deepcopy(native.get('geometry', geometry))
    if 'unreal.treehouse' in selected:
        sources = {}
        for role, producer, suffix, member in (
            ('palette', 'world.treehouse_textures', 'treehouse/textures', 'textures.json'),
            ('props', 'world.treehouse_props', 'treehouse/props', 'props.json'),
            ('trees', 'world.treehouse_trees', 'treehouse/trees', 'trees.json')):
            try:
                sources[role] = _family_source_reference(rows, producer, suffix, member)
            except ValueError as error:
                gaps.append('treehouse.' + role + ': ' + str(error))
        if len(sources) == 3:
            try:
                material = _family_module(checkout, 'v2_treehouse_material_units').author_units(
                    sources, _package_dependencies(native), checkout=checkout)
            except ValueError as error:
                gaps.append('treehouse.materials: ' + str(error))
            else:
                _append_family(native, material)
        followers = _family_module(checkout, 'v2_treehouse_native_units').attach_followers(
            geometry, native['packages'], native['units'], checkout=checkout)
        geometry = followers['geometry']
        gaps.extend('treehouse.material:' + package for package in followers['missing_material_packages'])
        gaps.extend('treehouse.geometry:' + parent for parent in followers['unrepresented_parents'])
        # Per-piece ownership does not yet prove the original combined retirement,
        # runtime roster and every selected follower's completion target.
        gaps.append('treehouse.complete_native_membership_and_selection')
    if 'unreal.brinecove' in selected:
        material = _family_module(checkout, 'v2_brinecove_material_units').author_units(
            native['packages'], checkout=checkout)
        _append_family(native, material)
        gaps.extend('brinecove.' + role for role in material['missing_roles'])
        followers = _family_module(checkout, 'v2_brinecove_native_units').attach_followers(
            geometry, native['packages'], native['units'], checkout=checkout)
        geometry = followers['geometry']
        gaps.extend('brinecove.material:' + package for package in followers['missing_material_packages'])
        if not any(t['unit_prefix'].startswith('world.brinecove.export.') for t in geometry['templates']):
            gaps.append('brinecove.geometry_templates')
        gaps.append('brinecove.complete_native_membership_and_selection')
    native['geometry'] = geometry
    native['missing_roles'] = sorted(set(gaps))
    return native



def _join_audio(native, rows, geometry, *, checkout):
    """Replace the six original sound imports with per-WAV owners and typed footsteps."""
    import ast
    from pathlib import Path
    from copy import deepcopy
    audio = _family_module(checkout, 'v2_audio_templates').audio_templates(rows, checkout=checkout)
    if {row['id'] for row in rows} & set(_family_module(checkout, 'v2_audio_units').ROSTER) != set(
            _family_module(checkout, 'v2_audio_units').ROSTER):
        raise ValueError('native sounds require all six original audio producers')
    waves = {key.removeprefix('audio.footsteps.files.'): value for key, value in audio['packages'].items()
             if key.startswith('audio.footsteps.files.')}
    footsteps = _family_module(checkout, 'v2_footstep_units').author_units(checkout=checkout, waves=waves)
    native['units'].extend(audio['units'])
    native['staged_inputs'].update(audio['staged_inputs'])
    native['content_slots'].update(audio['content_slots'])
    _append_family(native, footsteps)
    native.setdefault('module_requirements', {}).update(footsteps['module_requirements'])
    geometry = deepcopy(geometry)
    geometry['templates'].extend(audio['templates'])
    geometry['groups'].update(audio['groups'])
    native['geometry'] = geometry
    native.setdefault('derived_packages', {}).update(audio['packages'])
    # This pure completed-roster consumer selects EVERY cue's finished children,
    # including those outside the FootstepSet. Optional unreal.music is a distinct
    # original target and is not part of unreal.sounds.
    script = 'games/yorimichi/world/audio_index_v2.py'
    line = next(node.lineno for node in ast.parse((Path(checkout) / script).read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'write_index')
    templates = {template['producer']: template for template in audio['templates']}
    families = {producer: {'destination': templates[producer]['followers'][0]['unit']['params']['destination'],
                           'members': deepcopy(token)} for producer, token in audio['packages'].items()}
    output = 'build/yorimichi/audio-native.json'
    index = {'id': 'unreal.sounds.complete', 'op': {'kind': 'recipe.python', 'version': '1'},
        'script': 'platform/studio/atelier/build_v2/recipe_job.py',
        'code': [script, 'platform/studio/atelier/build_v2/recipe_job.py'],
        'inputs': [{'role': 'content', 'name': 'footsteps', 'source': {
            'kind': 'item', 'unit': 'unreal.footsteps.library', 'item': 'asset'}}],
        'params': {'recipe': {'version': 1, 'paths': {}, 'verify': None,
            'commands': [{'kind': 'call', 'call': {'source': script, 'qualname': 'write_index', 'line': line,
                'captures': [], 'defaults': [families, {'path': output}], 'kwdefaults': {}}}],
            'outputs': [{'path': output, 'kind': 'file', 'file': 'audio-native.tree.tar', 'required': True}]}},
        'outputs': [{'id': 'roster', 'logical_path': '/Build/Audio/NativeRoster', 'class': 'Data',
            'destination': 'store', 'files': [{'path': 'audio-native.tree.tar', 'required': True}]}]}
    native['units'].append(index)
    native['staged_inputs'][index['id']] = {'footsteps': 'inputs/footsteps'}
    native['content_slots']['footsteps'] = False
    native['aliases']['unreal.sounds'] = (index['id'],)
    return native

def lower(rows, geometry, *, checkout):
    """Game-authored replacements; unknown native families remain compiler refusals."""
    selected = {row['id'] for row in rows}
    if 'unreal.island' in selected:
        native = island(rows, geometry, checkout=checkout)
        native['aliases'] = {'unreal.island': ('unreal.island.map',)}
    elif 'unreal.materials' in selected:
        native = shared_materials(rows, checkout=checkout)
        native['aliases'] = {}
    elif selected & {'unreal.treehouse', 'unreal.brinecove', 'unreal.sounds', 'unreal.crater_cloud', 'unreal.skate_board', 'unreal.fx'}:
        native = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {},
                  'targets': (), 'aliases': {}, 'missing_roles': []}
        if 'unreal.treehouse' in selected:
            try:
                shared = shared_materials(rows, checkout=checkout)
            except ValueError as error:
                native['missing_roles'].append('treehouse.shared_materials: ' + str(error))
            else:
                _append_family(native, shared)
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
    for original, constructor in (('unreal.crater_cloud', 'v2_cloud_units'),
                                  ('unreal.skate_board', 'v2_board_units'), ('unreal.fx', 'v2_fx_units')):
        if original in selected:
            family = _family_module(checkout, constructor).author_units(rows, checkout=checkout)
            _append_family(native, family)
            native['aliases'].update(family['aliases'])
    if 'unreal.sounds' in selected:
        native = _join_audio(native, rows, native.get('geometry', geometry), checkout=checkout)
    if selected & {'unreal.treehouse', 'unreal.brinecove'}:
        native = _join_native_families(native, rows, geometry, selected, checkout=checkout)
    return native
