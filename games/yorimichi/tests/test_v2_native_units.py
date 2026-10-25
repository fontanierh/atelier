"""Shared native constructor composition uses actual source texture declarations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'


def load(name):
    spec = importlib.util.spec_from_file_location(name, GAME / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows():
    return extract(load('build').texture_steps(SimpleNamespace(out=ROOT / 'build/yorimichi')),
                   checkout=ROOT, build_root=ROOT / 'build')


def test_real_shared_library_joins_individual_raw_finish_and_graph_owners():
    graph = load('v2_native_units').shared_materials(rows(), checkout=ROOT)
    units = {unit['id']: unit for unit in graph['units']}
    assert len(units) == 84 and len(graph['targets']) == 40
    assert len(graph['packages']) == 62
    assert all(units[name]['op']['kind'] == 'unreal.author' for name in graph['targets'])
    for unit in units.values():
        assert len(unit['outputs']) == 1
        assert unit['script'] in unit['code']
        assert 'platform/build-v2/unreal/AtelierBuildWorker/Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp' in unit['code']
        for incoming in unit['inputs']:
            owner = incoming['source']['unit']
            assert owner in units or owner.startswith('world.textures.')
            if owner in units:
                assert incoming['source']['item'] in {item['id'] for item in units[owner]['outputs']}
    assert units['unreal.materials.MI_LeafMaple']['inputs']
    assert any(row['source']['unit'] == 'unreal.texture.finish.leaf_maple'
               for row in units['unreal.materials.MI_LeafMaple']['inputs'])


def test_missing_texture_does_not_produce_an_incomplete_material_selection():
    with pytest.raises(ValueError, match='all 22'):
        load('v2_native_units').shared_materials(rows()[1:], checkout=ROOT)


def test_island_binds_the_actual_finish_follower_and_complete_native_material_inputs():
    parents = ('Terrain', 'Road', 'Lane', 'Guardrail', 'Wires', 'FarHills', 'Sea')
    geometry = {'templates': [dict(producer='world.island.geometry.' + parent, group='geometry',
        unit_prefix='world.island.export.' + parent,
        op={'kind': 'blender_export_piece', 'version': '1'}) for parent in parents]}
    graph = load('v2_native_units').island(rows(), geometry, checkout=ROOT)
    assert graph['targets'] == ('unreal.island.map',)
    assert all(len(template['followers']) == 2 for template in graph['geometry']['templates'])
    material_units = {unit['id']: unit for unit in graph['units']}
    for template in graph['geometry']['templates']:
        finish = template['followers'][1]['unit']
        assert finish['script'] == 'games/yorimichi/world/island_finish_v2.py'
        assert finish['inputs'][0]['source']['unit'] == '$previous'
        assert finish['inputs'][1]['source']['unit'] == '$export'
        assert all(incoming['source']['unit'] in material_units for incoming in finish['inputs'][2:])
        assert not any(incoming['source']['unit'].startswith('unreal.texture.raw.')
                       for incoming in finish['inputs'][2:])
    target = material_units['unreal.island.map']
    assert target['outputs'][0]['class'] == 'Map'
    assert target['params']['args']['world'] == {'file': 'outputs/0.tree.tar'}
    assert 'Sea' not in target['params']['args']['terrain']
    for value in target['params']['args']['terrain'].values():
        assert value['derived_items']['templates'][0]['follower'] == 1


def real_family_rows():
    """The original source factories, not generated plans or native products."""
    import ast
    recipe = load('build')
    ctx = SimpleNamespace(out=ROOT / 'build/yorimichi', uproject=GAME / 'unreal/Yorimichi.uproject')
    atomic = load('treehouse_atomic_build')
    source_steps = [*recipe.texture_steps(ctx), *atomic.canopy_steps(ctx),
                    *atomic.prop_steps(ctx), *atomic.surface_steps(ctx)]
    tree = ast.parse((GAME / 'build.py').read_text())
    def original_step(name):
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == 'Step' and node.args
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == name)
        return eval(compile(ast.Expression(call), str(GAME / 'build.py'), 'eval'),
                    {**vars(recipe), 'ctx': ctx, 'out': ctx.out, 'region': GAME / 'world/regions/brinecove'})
    source_steps += [original_step(name) for name in ('world.treehouse_textures', 'unreal.treehouse')]
    # This fixture exercises original declarations/product roles, not whole-game
    # dependency selection; the omitted Brine source frontier is checked by the
    # full-target compiler. Keep the selected factories' real products unchanged.
    for step in recipe.brinecove_steps(ctx.out):
        if step.name in ('world.brinecove', 'unreal.brinecove'):
            step.reads = []; step.needs = []; step.after = []
            source_steps.append(step)
    return extract(source_steps, checkout=ROOT, build_root=ROOT / 'build')


def test_joined_actual_rows_expose_all_family_gaps_without_incomplete_import_aliases():
    source_rows = real_family_rows()
    palette = next(row for row in source_rows if row['id'] == 'world.treehouse_textures')
    palette['outputs'] = ['build/yorimichi/treehouse/textures/textures.json']
    geometry = load('v2_geometry_templates').geometry_templates(source_rows, checkout=ROOT)
    result = load('v2_native_units').lower(source_rows, geometry, checkout=ROOT)
    assert 'unreal.treehouse' not in result['aliases']
    assert result['aliases']['unreal.brinecove'] == ('unreal.brinecove.complete',)
    assert any(role.startswith('treehouse.palette:') for role in result['missing_roles'])
    assert any('complete directory ROOT' in role for role in result['missing_roles'])
    assert 'treehouse.complete_native_membership_and_selection' in result['missing_roles']
    assert not any(role.startswith('brinecove.') for role in result['missing_roles'])
    assert any(unit['id'] == 'unreal.brinecove.material.M_Brinecove' for unit in result['units'])
    assert len([t for t in result['geometry']['templates']
                if t['unit_prefix'].startswith('world.brinecove.selected.')]) == 3
    assert all('world.brinecove.selected.' not in owner for owner in result['module_requirements'])
    assert all(result['follower_module_requirements'][t['unit_prefix']]
               for t in result['geometry']['templates'] if t['unit_prefix'].startswith('world.brinecove.selected.'))
    props = load('v2_native_units')._family_source_reference(source_rows, 'world.treehouse_props', 'treehouse/props', 'props.json')
    trees = load('v2_native_units')._family_source_reference(source_rows, 'world.treehouse_trees', 'treehouse/trees', 'trees.json')
    assert props == {'unit': 'world.treehouse_props', 'item': 'product0', 'file': 'products/0-0.tree.tar', 'member': 'props.json'}
    assert trees['item'] == 'product0' and trees['file'] == 'products/0-0.tree.tar'


def test_join_binds_actual_reordered_product_and_output_indices():
    native = load('v2_native_units')
    source_rows = real_family_rows()
    palette = next(row for row in source_rows if row['id'] == 'world.treehouse_textures')
    # Model the required whole-root source declaration correction explicitly. The
    # actual baseline's metadata-only output is checked as a gap above.
    palette['outputs'].insert(0, 'build/yorimichi/unrelated-source.json')
    palette['outputs'][1] = 'build/yorimichi/treehouse/textures'
    props = next(row for row in source_rows if row['id'] == 'world.treehouse_props')
    props['products'].insert(0, {'id': 'other.explicit.source', 'paths': ['build/yorimichi/other-source'], 'optional_paths': []})
    geometry = load('v2_geometry_templates').geometry_templates(source_rows, checkout=ROOT)
    result = native.lower(source_rows, geometry, checkout=ROOT)
    by_id = {unit['id']: unit for unit in result['units']}
    bark = by_id['unreal.treehouse.texture.raw.T_TH_bark']
    assert bark['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.treehouse_textures', 'item': 'output1'}
    assert bark['params']['input_roots']['palette']['archive_member'] == 'outputs/1.tree.tar'
    prop = by_id['unreal.treehouse.texture.raw.T_TH_P_barrel']
    assert prop['inputs'][0]['source']['item'] == 'product1'
    assert prop['params']['input_roots']['props']['archive_member'] == 'products/1-0.tree.tar'
    treehouse = [t for t in result['geometry']['templates'] if t['unit_prefix'].startswith('world.treehouse_')]
    assert len(treehouse) == 21 and all(len(t['followers']) == 2 for t in treehouse)
    assert result['aliases']['unreal.treehouse'] == ('unreal.treehouse.complete',)
    index = by_id['unreal.treehouse.complete']
    assert len(index['params']['recipe']['commands'][0]['call']['defaults'][0]) == 21
    assert index['inputs'] and all(i['source']['unit'].startswith('unreal.treehouse.') for i in index['inputs'])
    assert not any(role.startswith('treehouse.palette:') or role.startswith('treehouse.material:') for role in result['missing_roles'])


def test_actual_six_audio_factories_join_all_wave_templates_and_both_footstep_owners():
    import ast
    recipe = load('build')
    ctx = SimpleNamespace(out=ROOT / 'build/yorimichi')
    tree = ast.parse((GAME / 'build.py').read_text())
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'Step' and node.args
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == 'unreal.sounds')
    sound = eval(compile(ast.Expression(call), str(GAME / 'build.py'), 'eval'),
                 {**vars(recipe), 'ctx': ctx, 'out': ctx.out})
    source_rows = extract([*recipe.sound_effect_steps(ctx), sound], checkout=ROOT, build_root=ROOT / 'build')
    result = load('v2_native_units').lower(source_rows, {'groups': {}, 'templates': []}, checkout=ROOT)
    assert result['aliases']['unreal.sounds'] == ('unreal.sounds.complete',)
    assert len(result['geometry']['templates']) == 102
    units = {unit['id']: unit for unit in result['units']}
    assert len(units) == 105
    assert units['unreal.footsteps.attenuation']['outputs'][0]['class'] == 'SoundAttenuation'
    assert units['unreal.footsteps.library']['outputs'][0]['class'] == 'DataAsset'
    assert result['module_requirements']['unreal.footsteps.library']
    index = units['unreal.sounds.complete']
    families = index['params']['recipe']['commands'][0]['call']['defaults'][0]
    assert len(families) == 102
    for template in result['geometry']['templates']:
        family = families[template['producer']]
        token = family['members']['derived_items']['templates'][0]
        assert token['producer'] == template['producer'] and token['follower'] == 0 and token['item'] == 'sound'
        assert family['destination'] == template['followers'][0]['unit']['params']['destination']
    assert not any(unit['id'] == 'unreal.music' for unit in result['units'])


def test_completed_audio_index_executes_real_callback_with_resolved_native_items(tmp_path):
    from atelier.build_v2.recipe_job import bind
    from types import SimpleNamespace
    import ast
    import json
    import shutil
    script = 'games/yorimichi/world/audio_index_v2.py'
    path = tmp_path / script; path.parent.mkdir(parents=True); shutil.copyfile(ROOT / script, path)
    output = tmp_path / 'build/audio-native.json'; output.parent.mkdir()
    member = tmp_path / 'derived/Hit'; member.mkdir(parents=True)
    line = next(node.lineno for node in ast.parse(path.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'write_index')
    families = {'combat.hit': {'destination': '/Game/Audio/Combat/$piece', 'members': {
        'derived_items': {'root': 'derived', 'members': [{'piece': 'Hit', 'slot': 'derived_0', 'root': 'derived/Hit'}]}}}}
    callback = bind({'source': script, 'qualname': 'write_index', 'line': line, 'captures': [],
                     'defaults': [families, {'path': 'build/audio-native.json'}], 'kwdefaults': {}}, tmp_path)
    callback()
    assert json.loads(output.read_text()) == {'schema': 1, 'packages': ['/Game/Audio/Combat/Hit']}
    member.rmdir()
    with pytest.raises(ValueError, match='invalid completed member'):
        callback()


def test_treehouse_completed_index_requires_actual_finished_primary_and_preserves_cold_output(tmp_path):
    import json
    import hashlib
    script = 'games/yorimichi/world/native_roster_v2.py'
    spec = importlib.util.spec_from_file_location('treehouse_index_test', ROOT / script)
    body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
    member = tmp_path / 'member'; member.mkdir()
    asset = member / 'content/Game/Japan/Assets/Tree_Canopy_Maple.uasset'
    asset.parent.mkdir(parents=True); asset.write_bytes(b'actual native Item')
    source = SimpleNamespace(products=[SimpleNamespace(paths=(member,))])
    families = {'Tree_Canopy_Maple': {'destination': '/Game/Japan/Assets/$piece',
                                    'members': [(source, 'Tree_Canopy_Maple')]}}
    output = tmp_path / 'report.json'
    body.write_index(families, ['/Game/Japan/Treehouse/Materials/M_TreeHouse'], output)
    report = json.loads(output.read_text())
    assert report['meshes']['/Game/Japan/Assets/Tree_Canopy_Maple']['sha256'] == hashlib.sha256(asset.read_bytes()).hexdigest()
    families['Tree_Canopy_Maple']['destination'] = '/Game/Japan/Assets/Tree_Canopy_Maple'
    body.write_index(families, [], output)
    assert json.loads(output.read_text())['assets'] == ['/Game/Japan/Assets/Tree_Canopy_Maple']
    families['Tree_Canopy_Maple']['members'] = [(source, 'Foreign')]
    with pytest.raises(ValueError, match='single declared'):
        body.write_index(families, [], output)
    families['Tree_Canopy_Maple']['members'] = [(source, 'Tree_Canopy_Maple')]
    saved = output.read_bytes(); asset.unlink()
    with pytest.raises(ValueError, match='primary package'):
        body.write_index(families, [], output)
    assert output.read_bytes() == saved


def test_real_kei_village_lake_composition_has_one_palette_and_complete_dynamic_targets():
    import ast
    recipe = load('build')
    ctx = SimpleNamespace(out=ROOT / 'build/yorimichi', uproject=GAME / 'unreal/Yorimichi.uproject')
    steps = [*recipe.texture_steps(ctx), *load('vehicle_atomic_build').steps(ctx, 'kei'),
             *load('village_atomic_build').steps(ctx), *load('lake_atomic_build').steps(ctx)]
    tree = ast.parse((GAME / 'build.py').read_text())
    steps.append(recipe.foliage_build.unreal_steps(ctx, (), ())[0])
    for name in ('unreal.kei', 'unreal.village', 'unreal.lake'):
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == 'Step' and node.args
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == name)
        steps.append(eval(compile(ast.Expression(call), str(GAME / 'build.py'), 'eval'),
                          {**vars(recipe), 'ctx': ctx, 'out': ctx.out}))
    source_rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    geometry = load('v2_geometry_templates').geometry_templates(source_rows, checkout=ROOT)
    result = load('v2_native_units').lower(source_rows, geometry, checkout=ROOT)
    units = {unit['id']: unit for unit in result['units']}
    palette = '/Game/Japan/Materials/M_Village'
    assert sum(output['logical_path'] == palette for unit in units.values() for output in unit['outputs']) == 1
    assert units['unreal.village.material.M_VillageResident']['params']['args']['function'] == 'resident_material'
    assert len(result['follower_module_requirements']) == 17
    for family, count, item in (('kei', 4, 'mesh'), ('village', 12, 'asset'), ('lake', 5, 'asset')):
        assert result['aliases']['unreal.' + family] == ('unreal.' + family + '.complete',)
        index = units['unreal.' + family + '.complete']
        families = index['params']['recipe']['commands'][0]['call']['defaults'][0]
        assert len(families) == count
        assert all(row['members']['derived_items']['templates'][0]['follower'] == 1
                   and row['members']['derived_items']['templates'][0]['item'] == item for row in families.values())
        assert all(incoming['source']['unit'] in units for incoming in index['inputs'])
    for template in result['geometry']['templates']:
        assert len(template['followers']) == 2


def test_swordcamp_and_kart_completion_select_all_native_and_runtime_data_outputs():
    recipe = load('build')
    ctx = SimpleNamespace(out=ROOT / 'build/yorimichi', uproject=GAME / 'unreal/Yorimichi.uproject')
    selected = [step for step in recipe.steps(ctx) if step.name.startswith((
        'world.swordcamp', 'world.kart', 'world.vehicle_kart', 'world.lake')) or step.name in ('unreal.swordcamp', 'unreal.kart', 'unreal.lake')]
    source_rows = extract(selected, checkout=ROOT, build_root=ROOT / 'build')
    geometry = load('v2_geometry_templates').geometry_templates(source_rows, checkout=ROOT)
    result = load('v2_native_units').lower(source_rows, geometry, checkout=ROOT)
    units = {unit['id']: unit for unit in result['units']}
    for family, count in (('swordcamp', 14), ('kart', 4)):
        assert result['aliases']['unreal.' + family] == ('unreal.' + family + '.complete',)
        complete = units['unreal.' + family + '.complete']
        members = complete['params']['recipe']['commands'][0]['call']['defaults'][0]
        assert len(members) == count
        assert all(value['members']['derived_items']['templates'][0]['follower'] == 1
                   for value in members.values())
    assert len(units) == len(result['units'])
    kart_data = units['unreal.kart.data']
    kart = units['unreal.kart.complete']
    assert {row['source']['item'] for row in kart['inputs'] if row['source']['unit'] == kart_data['id']} == {
        output['id'] for output in kart_data['outputs']}
    camp = units['unreal.swordcamp.complete']
    assert {row['source']['unit'] for row in camp['inputs']} == {
        'unreal.swordcamp.texture.T_SwordCampAtlas',
        'unreal.swordcamp.material.M_SwordCamp', 'unreal.swordcamp.material.M_RoninBody'}
    assert all(key.startswith('world.') for key in result['follower_module_requirements'])
    assert not result.get('module_requirements')
