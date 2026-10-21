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
    state = {name: dict(triangles=1, min=[0, 0, 0], max=[1, 1, 1], unused='metadata') for name in names}
    for name in RECIPE.city_inputs.TILES:
        state[name].update(slots={'asphalt':1}, collision_boxes=0)
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
    sources = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'SOURCES' for t in node.targets))
    assert ast.literal_eval(sources) == RECIPE.city_inputs.TILES


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


@pytest.mark.parametrize('field', ['slots', 'collision_boxes'])
def test_city_surface_material_and_collision_reads_are_inside_the_cutoff(city_build, field):
    p = city_build
    entry = p.state['HD_Streets']
    if field == 'slots': entry['slots']['stone'] = 1
    else: entry['collision_boxes'] = 1
    assert p.run(edited=True) == 0 and p.generated == ['tiles']


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
    for part in ('tiles', 'trees'):
        cutoff = steps['world.hidamari.' + part]
        consumer = steps['world.city_' + part]
        assert cutoff.cutoff and not cutoff.heavy and cutoff.needs == ['world.hidamari']
        assert 'world.hidamari' not in consumer.needs and cutoff.name in consumer.needs
        assert consumer.commands[0].script in consumer.inputs
        closure = set(build_inputs.local_imports(consumer.commands[0].script, (RECIPE.WORLD, RECIPE.REGIONS)))
        assert closure <= set(consumer.inputs)  # Test the assembled recipe, after its ImportScanner pass.
        assert steps[consumer.name + '.meshes'].needs == [consumer.name]
    assert RECIPE.REGIONS/'hidamari/arcade.py' in steps['world.city_trees'].inputs
    assert RECIPE.REGIONS/'hidamari/plaza.py' in steps['world.city_trees'].inputs
    assert RECIPE.REGIONS/'village/build.py' in steps['world.city_trees'].inputs
