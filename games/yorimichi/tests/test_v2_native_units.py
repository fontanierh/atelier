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
    source_steps += [original_step(name) for name in ('world.treehouse_textures', 'world.brinecove.meshes', 'unreal.treehouse', 'unreal.brinecove')]
    return extract(source_steps, checkout=ROOT, build_root=ROOT / 'build')


def test_joined_actual_rows_expose_all_family_gaps_without_incomplete_import_aliases():
    source_rows = real_family_rows()
    geometry = load('v2_geometry_templates').geometry_templates(source_rows, checkout=ROOT)
    result = load('v2_native_units').lower(source_rows, geometry, checkout=ROOT)
    assert 'unreal.treehouse' not in result['aliases'] and 'unreal.brinecove' not in result['aliases']
    assert any(role.startswith('treehouse.palette:') for role in result['missing_roles'])
    assert any('complete directory ROOT' in role for role in result['missing_roles'])
    assert 'brinecove.hero_material_descriptors' in result['missing_roles']
    assert 'brinecove.geometry_templates' in result['missing_roles']
    assert 'treehouse.complete_native_membership_and_selection' in result['missing_roles']
    assert 'brinecove.complete_native_membership_and_selection' in result['missing_roles']
    assert any(unit['id'] == 'unreal.brinecove.material.M_Brinecove' for unit in result['units'])
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
    assert 'unreal.treehouse' not in result['aliases']
    assert not any(role.startswith('treehouse.palette:') or role.startswith('treehouse.material:') for role in result['missing_roles'])
