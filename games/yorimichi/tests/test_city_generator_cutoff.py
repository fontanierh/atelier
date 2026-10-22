"""A Crater-only producer edit must not regenerate unchanged city tile/tree inputs."""
import ast
import json
from types import SimpleNamespace

import pytest

from atelier import build, build_inputs
from test_volcano_layers import RECIPE


@pytest.fixture
def city_build(tmp_path, monkeypatch):
    out = tmp_path / 'build'
    source = tmp_path / 'producer.py'
    source.write_text('1')
    generator = tmp_path / 'generator.py'
    generator.write_text('1')
    names = (*RECIPE.city_inputs.TILES, *RECIPE.city_inputs.TREES, 'HD_NorthMountains')
    state = {name: dict(triangles=1, min=[0, 0, 0], max=[1, 1, 1], collision_boxes=0, unused='metadata') for name in names}
    meshes = {name: name.encode() for name in names}
    generated, exported, messages = [], [], []
    folder = out / 'hidamari'

    def export(ctx, log):
        exported.append(True)
        (folder / 'assets').mkdir(parents=True, exist_ok=True)
        (folder / 'manifest.json').write_text(json.dumps(state))
        for name, data in meshes.items():
            (folder / 'assets' / (name + '.fbx')).write_bytes(data)

    def consumer(part):
        def run(ctx, log):
            generated.append(part)
            (out / f'{part}.json').write_text(json.dumps(RECIPE.city_inputs.snapshot(out,
                RECIPE.city_inputs.TILES if part == 'tiles' else RECIPE.city_inputs.TREES)))
        return run

    steps = [build.Step('world.hidamari', [build.Call('export', export)], inputs=[source],
                        outputs=[folder / 'manifest.json']),
             RECIPE.city_input_step(out, 'tiles'), RECIPE.city_input_step(out, 'trees'),
             *[build.Step('world.city_' + part, [build.Call(part, consumer(part))],
                          inputs=[generator], needs=['world.hidamari.' + part], outputs=[out / f'{part}.json'])
               for part in ('tiles', 'trees')]]
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out/'logs', stamps=out/'stamps', uproject=None)
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: steps))

    def run(*, edited=False):
        if edited:
            source.write_text(source.read_text() + '# producer edit\n')
        return build.build('yorimichi', ['world.city_tiles', 'world.city_trees'], echo=messages.append)

    assert run() == 0 and generated == ['tiles', 'trees']
    generated.clear()
    return SimpleNamespace(out=out, folder=folder, state=state, meshes=meshes, run=run,
                           generated=generated, exported=exported, generator=generator, messages=messages)


def test_cutoff_selections_match_the_actual_generators():
    tree = ast.parse((RECIPE.WORLD/'city_tree_lods.py').read_text())
    builders = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'BUILDERS' for t in node.targets))
    assert tuple(ast.literal_eval(key) for key in builders.keys) == RECIPE.city_inputs.TREES
    tree = ast.parse((RECIPE.WORLD/'city_surface_tiles.py').read_text())
    selection = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument'
                     and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == '--sources')
    options = {kw.arg: ast.literal_eval(kw.value) for kw in selection.keywords}
    assert options == {'nargs': '+', 'required': True}
    assert not any(isinstance(node, ast.Name) and node.id == 'SOURCES' for node in ast.walk(tree))


def test_actual_city_assembly_recipe_accepts_build_log_file(tmp_path):
    from test_city_tile_products import production_manifest
    manifest = production_manifest()
    root = tmp_path/'city_surface_tiles/v1_128m'
    for name, row in manifest['sources'].items():
        folder = root/name
        folder.mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps({**manifest, 'sources': {name: row}}))
        for tile in row['tiles']:
            (folder/(tile['name']+'.fbx')).write_bytes(b'completed source')
    assembly = RECIPE.city_tile_steps(tmp_path)[-1]
    log_path = tmp_path/'assembly.log'
    with log_path.open('w') as log:
        assembly.commands[0].fn(SimpleNamespace(out=tmp_path), log)
    assert json.loads((root/'manifest.json').read_text()) == manifest
    assert log_path.read_text() == 'CITY PIECES assembled '+str(sum(len(row['tiles']) for row in manifest['sources'].values()))+'\n'


def test_ordinary_rebuild_skips_both_generators_after_unrelated_producer_change(city_build):
    p = city_build
    p.state['HD_NorthMountains']['triangles'] = 99
    p.meshes['HD_NorthMountains'] = b'changed crater'
    assert p.run(edited=True) == 0
    assert len(p.exported) == 2 and p.generated == []


@pytest.mark.parametrize('part', ['tiles', 'trees'])
@pytest.mark.parametrize('changed', ['triangles', 'min', 'max', 'fbx'])
def test_every_selected_read_invalidates_only_its_generator(city_build, part, changed):
    p = city_build
    name = (RECIPE.city_inputs.TILES if part == 'tiles' else RECIPE.city_inputs.TREES)[-1]
    if changed == 'fbx':
        p.meshes[name] += b'changed raw bytes'
    elif changed == 'triangles':
        p.state[name][changed] += 1
    else:
        p.state[name][changed][0] += 1
    assert p.run(edited=True) == 0 and p.generated == [part]


def test_unused_manifest_fields_do_not_regenerate_city_outputs(city_build):
    p = city_build
    for value in p.state.values():
        value['unused'] = 'changed'
    assert p.run(edited=True) == 0 and p.generated == []


def test_generated_mesh_mutation_without_source_edit_is_not_a_hit(city_build):
    p = city_build
    (p.folder/'assets'/f'{RECIPE.city_inputs.TILES[0]}.fbx').write_bytes(b'outside mutation')
    assert p.run() == 0 and p.generated == ['tiles']


def test_missing_mesh_never_keeps_a_successful_generator_hit(city_build):
    p = city_build
    (p.folder/'assets'/f'{RECIPE.city_inputs.TREES[0]}.fbx').unlink()
    assert p.run() != 0 and p.generated == []


def test_generator_source_change_still_runs_both_consumers(city_build):
    p = city_build
    p.generator.write_text('2')
    assert p.run() == 0 and p.generated == ['tiles', 'trees']


@pytest.mark.parametrize('missing', ['entry', 'triangles', 'min', 'max'])
def test_missing_selected_receipt_cannot_hide_behind_a_cutoff(city_build, missing):
    p = city_build
    name = RECIPE.city_inputs.TREES[0]
    if missing == 'entry':
        del p.state[name]
    else:
        del p.state[name][missing]
    assert p.run(edited=True) != 0 and p.generated == []


def test_recipe_keeps_generator_code_and_existing_unreal_cutoffs(tmp_path):
    ctx = SimpleNamespace(out=tmp_path, uproject=None)
    steps = {s.name: s for s in RECIPE.steps(ctx)}
    consumer = steps['world.city_trees']
    cutoff = steps['world.hidamari.trees']
    assert cutoff.cutoff and not cutoff.heavy and cutoff.needs == ['world.hidamari']
    assert cutoff.name in consumer.needs and 'world.hidamari' not in consumer.needs
    assert consumer.commands[0].script in consumer.inputs
    for name in RECIPE.city_inputs.TILES:
        cutoff = steps['world.hidamari.tiles.'+name]
        piece = steps['world.city_tiles.'+name]
        assert cutoff.cutoff and cutoff.needs == ['world.hidamari']
        assert piece.needs == [cutoff.name]
        assert piece.cache and piece.products[0].name == 'city.tiles.'+name
        assert piece.commands[0].factory_startup is True
        assert piece.commands[0].script in piece.inputs
        closure = set(build_inputs.local_imports(piece.commands[0].script, (RECIPE.WORLD, RECIPE.REGIONS)))
        assert closure <= set(piece.inputs)
    assert steps['world.city_tiles'].reads == ['city.tiles.'+name for name in RECIPE.city_products.SOURCES]
    desktop = steps['unreal.desktop']
    assert set(RECIPE.unreal_modules.needs(RECIPE.IMPORT_CODE+('Yorimichi',))) <= set(desktop.needs)
    for part in ('tiles', 'trees'):
        assert steps['world.city_'+part+'.meshes'].needs == ['world.city_'+part]
    assert RECIPE.REGIONS/'hidamari/arcade.py' in consumer.inputs
    assert RECIPE.REGIONS/'hidamari/plaza.py' in consumer.inputs
    assert RECIPE.REGIONS/'village/build.py' in consumer.inputs


def test_source_specific_cutoffs_rebuild_only_the_changed_city_parent(tmp_path, monkeypatch):
    out = tmp_path/'build'
    folder = out/'hidamari'
    (folder/'assets').mkdir(parents=True)
    names = RECIPE.city_inputs.TILES
    manifest = {name:dict(triangles=1,min=[0,0,0],max=[1,1,1],collision_boxes=0) for name in names}
    (folder/'manifest.json').write_text(json.dumps(manifest))
    for name in names: (folder/'assets'/ (name+'.fbx')).write_bytes(name.encode())
    runs = []
    products = []
    for name in names:
        output = out/(name+'.json')
        def export(ctx, log, name=name, output=output):
            runs.append(name)
            output.write_text(json.dumps(RECIPE.city_inputs.snapshot(out,(name,))))
        products += [RECIPE.city_input_step(out,'tiles',(name,)),
                     build.Step('piece.'+name,[build.Call('source '+name,export)],
                                needs=['world.hidamari.tiles.'+name],outputs=[output])]
    steps = [build.Step('world.hidamari',[],outputs=[folder/'manifest.json']), *products]
    ctx = SimpleNamespace(game='yorimichi',out=out,logs=out/'logs',stamps=out/'stamps',uproject=None)
    monkeypatch.setattr(build,'Context',lambda game:ctx)
    monkeypatch.setattr(build,'load_recipe',lambda game:SimpleNamespace(steps=lambda context:steps))
    targets = ['piece.'+name for name in names]
    assert build.build('yorimichi',targets,echo=lambda message:None)==0
    assert set(runs)==set(names)
    runs.clear()
    (folder/'assets/HD_Streets.fbx').write_bytes(b'changed streets')
    assert build.build('yorimichi',targets,echo=lambda message:None)==0
    assert runs==['HD_Streets']
    runs.clear()
    manifest['HD_Square']['collision_boxes'] = 1
    (folder/'manifest.json').write_text(json.dumps(manifest))
    assert build.build('yorimichi',targets,echo=lambda message:None)==0
    assert runs==['HD_Square']


def test_new_large_hds_families_share_existing_independent_source_owners(tmp_path):
    steps = {s.name:s for s in RECIPE.steps(SimpleNamespace(out=tmp_path, uproject=None))}
    names = ('HD_Terrain', 'HD_Streets', 'HD_Square', 'HD_CivicGardens', 'HD_Park')
    assert RECIPE.city_inputs.TILES == names
    assert RECIPE.city_products.SOURCES == (*names, 'HD_Harbor')
    for source in names:
        step = steps['world.city_tiles.'+source]
        assert step.commands[0].args[-1] == source
        assert step.needs == ['world.hidamari.tiles.'+source]
    harbor = steps['world.hidamari.tiles.HD_Harbor']
    assert harbor.cutoff and harbor.needs == ['world.hidamari_ferry_cut']
    piece = steps['world.city_tiles.HD_Harbor']
    assert piece.needs == [harbor.name]
    assert piece.commands[0].factory_startup is True
    assert piece.commands[0].args == ('--tag', 'v1_128m', '--sources', 'HD_Harbor',
        '--source-path', 'hidamari/ferry/HD_Harbor.fbx',
        '--metadata-path', 'digests/world.hidamari.tiles.HD_Harbor.json')


@pytest.mark.parametrize('selection', [[], ['../HD_Park'], ['HD_Ｐark'],
    ['HD_Park', 'HD_Park'], ['HD_Park', 'HD_park'], ['HD_Park', 'HD_Missing']])
def test_splitter_refuses_bad_complete_selection_before_any_output_mutation(tmp_path, monkeypatch, selection):
    import argparse
    import hashlib
    import re
    import sys
    script = RECIPE.WORLD/'city_surface_tiles.py'
    main = next(node for node in ast.parse(script.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    root = tmp_path/'hidamari'
    root.mkdir()
    (root/'manifest.json').write_text(json.dumps({'HD_Park': {}, 'HD_park': {}}))
    touched = []
    namespace = dict(argparse=argparse, hashlib=hashlib, json=json, re=re, sys=sys,
        yori=SimpleNamespace(OUT=tmp_path),
        bpy=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **kw:touched.append('reset')))))
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(script), 'exec'), namespace)
    argv = ['splitter', '--', '--tag', 'v1_128m']
    if selection: argv += ['--sources', *selection]
    monkeypatch.setattr(sys, 'argv', argv)
    with pytest.raises((SystemExit, AssertionError)):
        namespace['main']()
    assert touched == []
    assert not (tmp_path/'city_surface_tiles').exists()
