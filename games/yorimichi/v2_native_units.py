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
    """Preserve explicit finished partners; raw import packages are private intermediates."""
    classes = {'Texture', 'StaticMesh', 'SkeletalMesh', 'Skeleton', 'PhysicsAsset',
               'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Map', 'Sound', 'Animation', 'DataAsset', 'BlendSpace1D', 'AdventureMoveSet', 'AnimBoneCompressionSettings',
               'WandererDefinition', 'SoundAttenuation'}
    by_id = {unit['id']: unit for unit in native['units']}
    result = {}
    for package, reference in native['packages'].items():
        if not package.startswith('/Game/') or reference['unit'] not in by_id:
            continue
        unit = by_id[reference['unit']]
        deps = [value['package'] if isinstance(value, dict) else value
                for value in reference.get('dependencies', ())]
        for incoming in unit['inputs']:
            source = incoming['source']
            owner = by_id.get(source.get('unit')) if source['kind'] == 'item' else None
            if owner:
                deps.extend(item['logical_path'] for item in owner['outputs']
                            if item['id'] == source['item'] and item['class'] in classes
                            and not item['logical_path'].startswith('/Game/_Raw/'))
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
    native.setdefault('module_requirements', {}).update(family.get('module_requirements', {}))
    native.setdefault('plugin_requirements', {}).update(family.get('plugin_requirements', {}))


def _stage_native_closure(family, unit, slot, reference):
    source = {'kind': 'item', 'unit': reference['unit'], 'item': reference['item']}
    if not any(incoming['source'] == source for incoming in unit['inputs']):
        if any(incoming['name'] == slot for incoming in unit['inputs']):
            raise ValueError('Native dependency closure aliases an existing input: ' + slot)
        unit['inputs'].append({'role': 'content', 'name': slot, 'source': source})
        family['staged_inputs'][unit['id']][slot] = 'inputs/' + slot
        family.setdefault('content_slots', {})[slot] = False


def _transport_preflight(native, family, rows, name, *, checkout):
    """@cc [owner:fontanierh,label:correctness] transport-source-before-native-owners
    Each transport native owner MUST depend on successful execution of the original
    service validator and Ferry cut check over the original declared source/read
    closure. Removing the original monolithic importer MUST NOT drop these checks.
    No prior report or ambient generated file MAY stand in for this produced Item.
    """
    from pathlib import Path
    from atelier.build import Call, Step
    from atelier.build_v2.recipe_dependencies import extract
    root = Path(checkout)
    original, = [row for row in rows if row['id'] == 'unreal.' + name]
    source = root / 'games/yorimichi/world/transport_preflight_v2.py'
    body = _family_module(checkout, 'world/transport_preflight_v2')
    out = root / 'build/yorimichi'
    report = out / 'native-checks' / (name + '.json')
    cut = None
    if name == 'ferry':
        cuts = {tuple(product['paths']) for row in rows for product in row['products']
                if product['id'] == 'hidamari.harbor_cut' and not product['optional_paths']}
        if len(cuts) != 1 or len(next(iter(cuts))) != 1:
            raise ValueError('Ferry requires its actual independently produced Harbor cut')
        cut = root / next(iter(cuts))[0]
    function = getattr(body, name)
    function.__defaults__ = ((out / 'ferry/service/service.json', cut, out, report)
                            if name == 'ferry' else (out / 'gondola/runtime.json', out, report))
    gate_id = 'unreal.' + name + '.preflight'
    authored, = extract([Step(gate_id, [Call(name + ' source preflight', function)])],
        checkout=root, build_root=root / 'build',
        import_roots=(root / 'platform/studio', root / 'games/yorimichi/world', root / 'games/yorimichi/world/regions'))
    gate = deepcopy(original)
    gate.update(id=gate_id, commands=authored['commands'], products=[],
                outputs=[report.relative_to(root).as_posix()], verify=None,
                code=sorted(set(original['code']) | set(authored['code']) | {source.relative_to(root).as_posix()}))
    required = [out / 'ferry/service/service.json', cut] if name == 'ferry' else [out / 'gondola/runtime.json']
    for path in required:
        incoming = {'path': path.relative_to(root).as_posix(), 'root': 'checkout', 'optional': False}
        if incoming not in gate['inputs']:
            gate['inputs'].append(incoming)
    native.setdefault('rows', []).append(gate)
    family.setdefault('content_slots', {})['transport_preflight'] = False
    for unit in family['units']:
        slot = 'transport_preflight'
        if any(incoming['name'] == slot for incoming in unit['inputs']):
            raise ValueError('transport preflight input aliases a native role')
        unit['inputs'].append({'role': 'content', 'name': slot,
            'source': {'kind': 'item', 'unit': gate_id, 'item': 'output0'},
            'whole': 'The original current source service and cut checks must pass before native asset mutation.'})
        family['staged_inputs'][unit['id']][slot] = 'inputs/' + slot
    return gate_id


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
        # Exact UCX vertex readback is provided by the produced Yorimichi module.
        import json
        from pathlib import Path
        descriptor = json.loads((Path(checkout) / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
        modules = [{'name': module['Name'], 'kind': module['Type'],
                    'loading_phase': module.get('LoadingPhase', 'Default')}
                   for module in descriptor['Modules'] if module['Name'] == 'Yorimichi']
        if not modules:
            raise ValueError('Treehouse collision readback requires the declared Yorimichi module')
        native.setdefault('follower_module_requirements', {}).update({
            template['unit_prefix']: modules for template in geometry['templates']
            if template['unit_prefix'].startswith(('world.treehouse_trees.export.',
                'world.treehouse_props.export.', 'world.treehouse_surfaces.export.'))
            and template.get('followers')})
        gaps.extend('treehouse.material:' + package for package in followers['missing_material_packages'])
        gaps.extend('treehouse.geometry:' + parent for parent in followers['unrepresented_parents'])
        if (len(sources) == 3 and not followers['missing_material_packages']
                and not followers['unrepresented_parents']):
            _complete_mesh_family(native, geometry, family='treehouse', export_prefixes=(
                'world.treehouse_trees.export.', 'world.treehouse_props.export.',
                'world.treehouse_surfaces.export.'), checkout=checkout)
        else:
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


def _complete_mesh_family(native, geometry, *, family, export_prefixes, checkout, fixed=None, prerequisites=()):
    """Select the full finished roster through existing before-key follower expansion."""
    import ast
    from pathlib import Path
    script = 'games/yorimichi/world/native_roster_v2.py'
    line = next(node.lineno for node in ast.parse((Path(checkout) / script).read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'write_index')
    families = {}
    for template in geometry['templates']:
        if not template['unit_prefix'].startswith(export_prefixes):
            continue
        if len(template.get('followers', ())) != 2:
            raise ValueError(family + ' completion requires every raw/finish chain')
        parent = template['unit_prefix'].rsplit('.', 1)[-1]
        families[parent] = {'destination': template['followers'][1]['unit']['params']['destination'],
            'members': {'derived_items': {'root': 'build/v2-derived/native-' + family + '/' + parent,
                'templates': [{key: template[key] for key in ('producer', 'group', 'unit_prefix')}
                              | {'follower': 1, 'item': template['followers'][1]['unit']['outputs'][0]['id']}]}}}
    if fixed is None:
        static = {unit['id'] for unit in native['units']}
        fixed = {package: reference for package, reference in native['packages'].items()
                 if reference['unit'].startswith('unreal.' + family + '.') and reference['unit'] in static}
    inputs = [{'role': 'content', 'name': 'fixed' + str(index), 'source': {
        'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
        for index, ref in enumerate(fixed.values())]
    inputs.extend({'role': 'content', 'name': 'required' + str(index), 'source': {
        'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
        for index, ref in enumerate(prerequisites))
    for incoming in inputs:
        incoming['whole'] = 'The complete finished Item is required to certify this family roster and runtime data.'
    output = 'build/yorimichi/' + family + '/import-report.json'
    unit = {'id': 'unreal.' + family + '.complete', 'op': {'kind': 'recipe.python', 'version': '1'},
        'script': 'platform/studio/atelier/build_v2/recipe_job.py',
        'code': [script, 'platform/studio/atelier/build_v2/recipe_job.py'], 'inputs': inputs,
        'params': {'recipe': {'version': 1, 'paths': {}, 'verify': None,
            'commands': [{'kind': 'call', 'call': {'source': script, 'qualname': 'write_index', 'line': line,
                'captures': [], 'defaults': [families, sorted(fixed), {'path': output}], 'kwdefaults': {}}}],
            'outputs': [{'path': output, 'kind': 'file', 'file': 'native-roster.tree.tar', 'required': True}]}},
        'outputs': [{'id': 'roster', 'logical_path': '/Build/' + family + '/NativeRoster', 'class': 'Data',
            'destination': 'store', 'files': [{'path': 'native-roster.tree.tar', 'required': True}]}]}
    native['units'].append(unit)
    native['staged_inputs'][unit['id']] = {row['name']: 'inputs/' + row['name'] for row in inputs}
    native['content_slots'].update({row['name']: False for row in inputs})
    native['aliases']['unreal.' + family] = (unit['id'],)



def _join_world_parts(native, rows, geometry, *, checkout):
    """Compose the actual World asset owners; completion waits for every callback family."""
    existing = {unit['id'] for unit in native['units']}
    resident_package = '/Game/Japan/Materials/M_VillageResident'
    if resident_package not in native['packages']:
        resident = deepcopy(next(unit for unit in native['units'] if unit['id'] == 'unreal.village.material.M_Village'))
        resident['id'] = 'unreal.village.material.M_VillageResident'
        resident['params']['args'].update(function='resident_material', expected_package=resident_package)
        resident['outputs'][0].update(logical_path=resident_package,
            files=_family_module(checkout, 'v2_kei_units')._files(resident_package, store=False))
        native['units'].append(resident)
        native['staged_inputs'][resident['id']] = {}
        native['packages'][resident_package] = {'unit': resident['id'], 'item': 'asset', 'package': resident_package}
    source = _family_source_reference(rows, 'characters.wanderer', 'wanderer', 'build.json')
    compression = _family_module(checkout, 'v2_moveset_units').compression_unit(checkout=checkout)
    if not any(unit['id'] == compression['id'] for unit in native['units']):
        native['units'].append(compression)
        native['staged_inputs'][compression['id']] = {}
        native['packages'][compression['outputs'][0]['logical_path']] = {
            'unit': compression['id'], 'item': 'asset', 'package': compression['outputs'][0]['logical_path']}
    wanderer = _family_module(checkout, 'v2_wanderer_units').wanderer_units(rows, checkout=checkout,
        natives={'wanderer': {'unit': source['unit'], 'item': source['item'],
            'root': {'archive_member': source['file'], 'name': 'wanderer'}},
            'compression': {'unit': compression['id'], 'item': 'asset',
                'package': compression['outputs'][0]['logical_path']}})
    wanderer['content_slots'] = {incoming['name']: False for unit in wanderer['units']
                                  for incoming in unit['inputs']}
    _append_family(native, wanderer)
    for family in ('props', 'sailboat', 'zeppelin', 'hidamari'):
        extended = _family_module(checkout, 'v2_' + family + '_units').attach_followers(
            geometry, _package_dependencies(native), checkout=checkout)
        if 'units' in extended:
            _append_family(native, {key: extended.pop(key) for key in
                ('units', 'staged_inputs', 'content_slots', 'packages')})
        native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
        geometry = extended
    native['geometry'] = geometry
    assembly = next(row for row in rows if row['id'] == 'world.hidamari_props')
    prerequisites = [{'unit': assembly['id'], 'item': product.get('native_item', 'product' + str(index))}
                     for index, product in enumerate(assembly['products'])]
    if not prerequisites:
        raise ValueError('World requires the complete original Hidamari prop assembly products')
    prerequisites.extend({'unit': unit['id'], 'item': output['id']} for unit in native['units']
                         for output in unit['outputs'] if output['class'] == 'Map')
    fixed = {package: ref for package, ref in native['packages'].items()
             if ref['unit'] not in existing or package in (
                 '/Game/Japan/Materials/M_Village', resident_package)}
    _complete_mesh_family(native, geometry, family='world', export_prefixes=(
        'world.props.export.', 'world.vehicle_sailboat.export.', 'world.zeppelin.export.',
        'world.hidamari_props.export.'), checkout=checkout, fixed=fixed, prerequisites=prerequisites)
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
        'inputs': [{'role': 'content', 'name': 'footsteps',
            'whole': 'The complete finished FootstepSet is part of the selected sound library.', 'source': {
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
    elif selected & {'unreal.treehouse', 'unreal.brinecove', 'unreal.sounds', 'unreal.crater_cloud', 'unreal.skate_board', 'unreal.fx', 'unreal.skate_data', 'unreal.kei', 'unreal.village', 'unreal.lake', 'unreal.houses', 'unreal.southwest', 'unreal.mega', 'unreal.swordcamp', 'unreal.kart', 'unreal.world', 'unreal.gondola', 'unreal.ferry', 'unreal.north', 'unreal.megapark', 'unreal.desktop', 'unreal.adventure', 'data.stage'}:
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
    if 'data.stage' in selected:
        runtime = _family_module(checkout, 'v2_runtime_data_units').lower(rows, checkout=checkout)
        native.setdefault('rows', []).extend(runtime['rows'])
        native['aliases'].update(runtime['aliases'])
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
                                  ('unreal.skate_board', 'v2_board_units'), ('unreal.fx', 'v2_fx_units'),
                                  ('unreal.skate_data', 'v2_skate_data_units')):
        if original in selected:
            family = _family_module(checkout, constructor).author_units(rows, checkout=checkout)
            _append_family(native, family)
            native['aliases'].update(family['aliases'])
    for name in ('gondola', 'ferry'):
        if 'unreal.' + name not in selected:
            continue
        family = getattr(_family_module(checkout, 'v2_' + name + '_units'), name + '_units')(rows, checkout=checkout)
        family['content_slots'] = {incoming['name']: False for unit in family['units']
                                   for incoming in unit['inputs']}
        gate = _transport_preflight(native, family, rows, name, checkout=checkout)
        _append_family(native, family)
        native['aliases']['unreal.' + name] = (gate, *sorted({ref['unit'] for ref in family['packages'].values()}))
    if 'unreal.sounds' in selected:
        native = _join_audio(native, rows, native.get('geometry', geometry), checkout=checkout)
    if selected & {'unreal.kei', 'unreal.village', 'unreal.lake', 'unreal.houses', 'unreal.southwest', 'unreal.mega', 'unreal.world'}:
        package = '/Game/Japan/Materials/M_Village'
        kei_module = _family_module(checkout, 'v2_kei_units')
        if 'unreal.kei' in selected:
            kei = kei_module.attach_followers(native.get('geometry', geometry), rows=rows, checkout=checkout)
            _append_family(native, kei)
            native['geometry'] = kei['geometry']
            _complete_mesh_family(native, native['geometry'], family='kei',
                export_prefixes=('world.vehicle_kei.export.',), checkout=checkout,
                fixed={package: native['packages'][package]})
        else:
            # Village and Lake share this same original material owner without
            # requiring the unrelated four-car source graph.
            from pathlib import Path
            unit, reference = kei_module._material(Path(checkout), None)
            native['units'].append(unit)
            native['staged_inputs'][unit['id']] = {}
            native['packages'][package] = reference
        if 'unreal.village' in selected:
            resident = deepcopy(next(unit for unit in native['units']
                                     if unit['id'] == 'unreal.village.material.M_Village'))
            resident_package = '/Game/Japan/Materials/M_VillageResident'
            resident['id'] = 'unreal.village.material.M_VillageResident'
            resident['params']['args'].update(function='resident_material', expected_package=resident_package)
            resident['outputs'][0].update(logical_path=resident_package,
                files=kei_module._files(resident_package, store=False))
            native['units'].append(resident)
            native['staged_inputs'][resident['id']] = {}
            native['packages'][resident_package] = {'unit': resident['id'], 'item': 'asset', 'package': resident_package}
            extended = _family_module(checkout, 'v2_village_units').attach_followers(
                native.get('geometry', geometry), _package_dependencies(native), checkout=checkout)
            native['geometry'] = extended
            native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
            _complete_mesh_family(native, extended, family='village', export_prefixes=('world.village.export.',),
                checkout=checkout, fixed={path: native['packages'][path] for path in (package, resident_package)})
        if 'unreal.lake' in selected:
            extended = _family_module(checkout, 'v2_lake_units').attach_followers(
                native.get('geometry', geometry), _package_dependencies(native), checkout=checkout)
            _append_family(native, {key: extended.pop(key) for key in
                ('units', 'staged_inputs', 'content_slots', 'packages')})
            native['geometry'] = extended
            native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
            _complete_mesh_family(native, extended, family='lake', export_prefixes=('world.lake.export.',),
                checkout=checkout, fixed={path: native['packages'][path] for path in
                    (package, '/Game/Japan/Materials/M_ForestLakeWater')})
    for family in ('houses', 'southwest', 'mega'):
        if 'unreal.' + family not in selected:
            continue
        extended = _family_module(checkout, 'v2_' + family + '_units').attach_followers(
            native.get('geometry', geometry), _package_dependencies(native), checkout=checkout)
        native['geometry'] = extended
        native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
        required = ['/Game/Japan/Materials/M_Village']
        if family == 'houses': required.append('/Game/Japan/Materials/MI_Ground')
        _complete_mesh_family(native, extended, family=family, export_prefixes=('world.' + family + '.export.',),
            checkout=checkout, fixed={path: native['packages'][path] for path in required})
    if 'unreal.swordcamp' in selected:
        module = _family_module(checkout, 'v2_swordcamp_units')
        family = module.author_units(rows, checkout=checkout)
        _append_family(native, family)
        extended = module.attach_followers(native.get('geometry', geometry),
            _package_dependencies(native), checkout=checkout)
        native['geometry'] = extended
        native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
        _complete_mesh_family(native, extended, family='swordcamp',
            export_prefixes=('world.swordcamp.export.',), checkout=checkout, fixed=family['packages'])
    if 'unreal.kart' in selected:
        extended = _family_module(checkout, 'v2_kart_units').attach_followers(
            native.get('geometry', geometry), _package_dependencies(native), checkout=checkout)
        family = {key: extended.pop(key) for key in ('units', 'staged_inputs', 'content_slots', 'packages')}
        _append_family(native, family)
        native['geometry'] = extended
        native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
        data = [{'unit': unit['id'], 'item': output['id']} for unit in family['units']
                if unit['id'] in extended['data_targets'] for output in unit['outputs']]
        _complete_mesh_family(native, extended, family='kart',
            export_prefixes=('world.vehicle_kart.export.',), checkout=checkout,
            fixed=family['packages'], prerequisites=data)
    if 'unreal.world' in selected:
        native = _join_world_parts(native, rows, native.get('geometry', geometry), checkout=checkout)
    if 'unreal.north' in selected:
        family = _family_module(checkout, 'v2_north_units').north_units(
            rows, checkout=checkout, natives=_package_dependencies(native))
        family['content_slots'] = {incoming['name']: False for unit in family['units']
                                   for incoming in unit['inputs']}
        _append_family(native, family)
        native['aliases']['unreal.north'] = tuple(sorted({ref['unit'] for ref in family['packages'].values()}))
    if 'unreal.megapark' in selected:
        family = _family_module(checkout, 'v2_megapark_templates').megapark_templates(
            rows, checkout=checkout, natives=_package_dependencies(native))
        _append_family(native, family)
        current = deepcopy(native.get('geometry', geometry))
        current['groups'].update(family['groups'])
        current['templates'].extend(family['templates'])
        extended = _family_module(checkout, 'v2_megapark_units').attach_followers(
            current, {**family['packages'], 'material_items': family['material_items']},
            rows=rows, checkout=checkout)
        native.setdefault('follower_module_requirements', {}).update(family.get('module_requirements', {}))
        native['follower_module_requirements'].update(extended.pop('module_requirements', {}))
        native['geometry'] = extended
        native['aliases']['unreal.megapark'] = tuple(family['required_targets'])
    if 'unreal.desktop' in selected and '/Game/Japan/Materials/M_NorthMountains' in native['packages']:
        extended = _family_module(checkout, 'v2_city_units').attach_followers(
            native.get('geometry', geometry), _package_dependencies(native), checkout=checkout)
        _append_family(native, {key: extended.pop(key, {}) for key in
            ('units', 'staged_inputs', 'content_slots', 'packages')})
        native.setdefault('follower_module_requirements', {}).update(extended.pop('module_requirements', {}))
        native['geometry'] = extended
        _complete_mesh_family(native, extended, family='desktop', export_prefixes=('world.hidamari.export.',),
            checkout=checkout, fixed={}, prerequisites=({'unit': 'unreal.world.complete', 'item': 'roster'},))
    characters = [row for row in rows if any(command.get('script') == {
        'path': 'games/yorimichi/unreal/Scripts/import_character.py'} for command in row['commands'])]
    if characters:
        moveset = _family_module(checkout, 'v2_moveset_units')
        if not any(unit['id'] == moveset.COMPRESSION_UNIT for unit in native['units']):
            compression = moveset.compression_unit(checkout=checkout)
            native['units'].append(compression)
            native['staged_inputs'][compression['id']] = {}
            native['packages'][moveset.COMPRESSION] = {'unit': compression['id'], 'item': 'asset', 'package': moveset.COMPRESSION}
        refs = _package_dependencies(native)
        character_module = _family_module(checkout, 'v2_character_templates')
        family = character_module.character_templates(rows, checkout=checkout, natives={
            'compression': refs[moveset.COMPRESSION],
            'see_through': refs.get('/Game/SeeThrough/MPC_SeeThrough')})
        definitions = character_module._definition(checkout)
        by_key = {character.id.replace('-', '_'): character for character in definitions.movers()}
        for unit in family['units']:
            if unit['op']['kind'].startswith('unreal.') and unit['params'].get('args', {}).get('action') in ('mesh', 'base'):
                key = unit['id'].split('.')[2]
                if by_key[key].toml.get('see_through'):
                    _stage_native_closure(family, unit, 'closure_see_through', refs['/Game/SeeThrough/MPC_SeeThrough'])
                if unit['params']['args']['action'] == 'base' and 'clips' in family['tokens'][by_key[key].id]:
                    _stage_native_closure(family, unit, 'closure_compression', refs[moveset.COMPRESSION])
        for template in family['templates']:
            key = template['unit_prefix'].split('.')[2]
            if by_key[key].toml.get('see_through') and '.clips_' in template['unit_prefix']:
                follower = template['followers'][1]
                temporary = {'staged_inputs': {follower['unit']['id']: follower['staged_inputs']}}
                _stage_native_closure(temporary, follower['unit'], 'closure_see_through', refs['/Game/SeeThrough/MPC_SeeThrough'])
        _append_family(native, family)
        current = deepcopy(native.get('geometry', geometry))
        current['groups'].update(family['groups'])
        current['templates'].extend(family['templates'])
        native['geometry'] = current
        native['aliases'].update(family['aliases'])
        native['character_tokens'] = family['tokens']
        definitions = character_module._definition(checkout)
        by_key = {character.id.replace('-', '_'): character for character in definitions.movers()}
        for template in family['templates']:
            prefix = template['unit_prefix']
            if any(follower['unit']['op']['kind'] == 'unreal.finish'
                   and follower['unit']['params'].get('kind') == 'animation'
                   for follower in template.get('followers', ())):
                key = prefix.split('.')[2]
                modules, _plugins = character_module._modules(checkout, list(by_key[key].unreal['modules']))
                native.setdefault('follower_module_requirements', {})[prefix] = modules
        if 'unreal.see_through' in selected:
            native['aliases']['unreal.see_through'] = tuple(dict.fromkeys(
                target for key, character in by_key.items() if character.toml.get('see_through')
                for target in family['aliases'].get('unreal.' + key, ())))
    if 'unreal.adventure' in selected:
        moveset = _family_module(checkout, 'v2_moveset_units')
        if not any(unit['id'] == moveset.COMPRESSION_UNIT for unit in native['units']):
            compression = moveset.compression_unit(checkout=checkout)
            native['units'].append(compression)
            native['staged_inputs'][compression['id']] = {}
            native['packages'][moveset.COMPRESSION] = {'unit': compression['id'], 'item': 'asset', 'package': moveset.COMPRESSION}
        reference = _family_module(checkout, 'v2_reference_units').reference_units(rows,
            checkout=checkout, natives={'compression': native['packages'][moveset.COMPRESSION]})
        masters = [ref for package, ref in reference['packages'].items()
                   if package in ('/Game/Adventure/M_AdventureCharacter', '/Game/Adventure/M_AdventureCharacterMasked')]
        for unit in reference['units']:
            action = unit['params'].get('args', {}).get('action')
            if action in ('mesh', 'prop', 'record'):
                unit['params']['args']['closure'] = {'images': deepcopy(reference['tokens']['images'])}
                for index, ref in enumerate(masters):
                    _stage_native_closure(reference, unit, 'closure_master_' + str(index), ref)
            if action == 'record':
                _stage_native_closure(reference, unit, 'closure_compression', native['packages'][moveset.COMPRESSION])
        _append_family(native, reference)
        current = deepcopy(native.get('geometry', geometry))
        current['groups'].update(reference['groups'])
        current['templates'].extend(reference['templates'])
        native['geometry'] = current
        native['aliases'].update(reference['aliases'])
        native['reference'] = reference['reference']
    if any(command.get('script') == {'path': 'games/yorimichi/unreal/Scripts/import_adventure_moveset.py'}
           for row in rows for command in row['commands']):
        module = _family_module(checkout, 'v2_moveset_templates')
        definitions = module._definition(checkout)
        refs = _package_dependencies(native)
        def concrete(package, seen=frozenset()):
            if package in seen:
                raise ValueError('Cyclic declared native item closure: ' + package)
            reference = deepcopy(refs[package])
            reference['dependencies'] = [concrete(value, seen | {package}) for value in reference.get('dependencies', ())]
            return reference
        reference = deepcopy(native['reference'])
        reference['equipment'] = [{key: value for key, value in ref.items() if key in
            ('unit', 'item', 'package', 'dependencies')} for ref in reference['equipment']]
        supplied = {'reference': reference, 'donor': {}}
        for character in definitions.movers():
            supplied[character.id] = {
                'skeleton': concrete(character.unreal_path + '/SK_' + character.name + '_Skeleton'),
                'base': concrete(character.adventure['base'])}
        donor = definitions.movers()[0]
        spec = donor.donor
        for piece in {spec['double_jump'], *(entry['clip'] for entry in spec['actions'].values())}:
            package = spec['folder'] + '/A_' + piece
            supplied['donor'][package] = {'derived': native['character_tokens'][donor.id]['clips'],
                                         'piece': piece, 'package': package}
        family = module.moveset_templates(rows, checkout=checkout, natives=supplied)
        existing = {unit['id']: unit for unit in native['units']}
        character_by_key = {character.id.replace('-', '_'): character for character in definitions.movers()}
        for unit in family['units']:
            if unit['id'].startswith('unreal.moveset.'):
                character = character_by_key[unit['id'].split('.')[2]]
                unit['params']['args']['closure'] = {'character': deepcopy(native['character_tokens'][character.id])}
                _stage_native_closure(family, unit, 'closure_compression', refs[module.COMPRESSION])
                if character.toml.get('see_through'):
                    _stage_native_closure(family, unit, 'closure_see_through', refs['/Game/SeeThrough/MPC_SeeThrough'])
        family['units'] = [unit for unit in family['units'] if unit['id'] not in existing]
        family['staged_inputs'] = {name: paths for name, paths in family['staged_inputs'].items() if name not in existing}
        _append_family(native, family)
        current = deepcopy(native['geometry'])
        current['groups'].update(family['groups'])
        current['templates'].extend(family['templates'])
        native['geometry'] = current
        native['aliases'].update(family['aliases'])
        native['moveset_tokens'] = family['tokens']
    if any(row['id'].endswith('_pawn') for row in rows):
        refs = _package_dependencies(native)
        refs.update({name: ref for name, ref in native['packages'].items() if name.startswith('games/')})
        family = _family_module(checkout, 'v2_pawn_units').author_units(rows, checkout=checkout, natives=refs)
        definitions = _family_module(checkout, 'v2_moveset_units')._definition(checkout)
        for unit in family['units']:
            character = next(value for value in definitions.movers() if value.id == unit['params']['args']['character'])
            unit['params']['args']['closure'] = {'character': deepcopy(native['character_tokens'][character.id]),
                                               'moveset': deepcopy(native['moveset_tokens'][character.id])}
            _stage_native_closure(family, unit, 'closure_compression', refs['/Game/Japan/Animation/CharacterCompression'])
            if character.toml.get('see_through'):
                _stage_native_closure(family, unit, 'closure_see_through', refs['/Game/SeeThrough/MPC_SeeThrough'])
        _append_family(native, family)
        native.setdefault('rows', []).extend(family['rows'])
        native['aliases'].update(family['aliases'])
    if selected & {'unreal.treehouse', 'unreal.brinecove'}:
        native = _join_native_families(native, rows, geometry, selected, checkout=checkout)
    return native
