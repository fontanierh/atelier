"""The staged runtime files retain their source bytes."""
from dataclasses import replace
import io
import os
from types import SimpleNamespace

from atelier import build


def test_staging_copies_required_sources_and_preserves_unrelated_data(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    data = recipe.runtime_data
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'build')
    destination = tmp_path / 'Content' / 'Data'
    course_bytes = data.RACING_COURSES.read_bytes()
    scene_bytes = (data.ASSETS / 'belmonte/source.json').read_bytes()
    monkeypatch.setattr(data, 'REGIONS', tmp_path / 'regions')
    monkeypatch.setattr(data, 'ASSETS', tmp_path / 'assets')
    monkeypatch.setattr(data, 'RACING_COURSES', tmp_path / 'courses.json')
    data.RACING_COURSES.write_bytes(course_bytes)
    scene = data.ASSETS / 'belmonte/source.json'
    scene.parent.mkdir(parents=True)
    scene.write_bytes(scene_bytes)
    model_path = data.courses.surface_inputs()[0]
    model_copy = scene.parent / model_path.relative_to(data.courses.SCENE.parent)
    model_copy.parent.mkdir(parents=True, exist_ok=True)
    model_copy.write_bytes(model_path.read_bytes())
    monkeypatch.setattr(data.paths, 'content_data', lambda game: destination)
    expected = {}
    for rel in data.staged(ctx.out):
        source = data.staged_source(ctx.out, rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        expected[rel] = course_bytes if rel == 'racing/belmonte_courses.json' else rel.encode()
        source.write_bytes(expected[rel])
        os.utime(source, ns=(1_000_000_000, 2_000_000_000))
    # The committed skatepark source wins over any similarly named generated file.
    (ctx.out / 'skatepark').mkdir(exist_ok=True)
    (ctx.out / 'skatepark/park.json').write_bytes(b'wrong generated park')
    retained = destination / 'SkateRide/clips.json'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'keep source data')
    controller_owned = destination / data.RACING_RUNTIME
    controller_owned.parent.mkdir(parents=True)
    controller_owned.write_bytes(b'keep controller-owned bytes')
    previous_course_stamp = controller_owned.stat().st_mtime_ns

    log = io.StringIO()
    recipe.stage_data(ctx, log)

    for rel, content in expected.items():
        target = destination / rel
        assert target.read_bytes() == content
        assert target.stat().st_mtime_ns == 2_000_000_000
    assert retained.read_bytes() == b'keep source data'
    assert controller_owned.read_bytes() == b'keep controller-owned bytes'
    assert controller_owned.stat().st_mtime_ns == previous_course_stamp
    assert log.getvalue().splitlines() == [f'staged {rel}' for rel in data.staged(ctx.out)]


def test_staging_implementation_is_a_narrow_fingerprint_input(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    steps = recipe.steps(ctx)
    stage = next(step for step in steps if step.name == 'data.stage')
    implementation = recipe.GAME / 'runtime_data.py'
    assert implementation in stage.inputs
    assert stage.commands[0].fn is recipe.runtime_data.stage_data
    assert all(implementation not in step.inputs for step in steps if step.name != 'data.stage')

    source = tmp_path / 'runtime_data.py'
    source.write_bytes(implementation.read_bytes())
    contract = replace(stage, inputs=[source])
    done = {name: name for name in stage.needs}
    previous = build.fingerprint(contract, done)
    source.write_text(source.read_text() + '\n# a staging implementation change\n')
    assert build.fingerprint(contract, done) != previous


def test_map_required_outputs_cover_runtime_sources_and_auxiliary_files(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    steps = recipe.steps(ctx)
    producer = next(step for step in steps if step.name == 'world.map')
    stage = next(step for step in steps if step.name == 'data.stage')
    assert producer in build.order(steps, ['data.stage'])
    assert producer.name in stage.needs

    required = {ctx.out / 'map' / name for name in
                ('rough.png', 'rough.jpg', 'map.jpg', 'map_lines.json')}
    assert required <= set(producer.outputs)
    for rel in ('map/map.jpg', 'map/map_lines.json'):
        assert rel in recipe.runtime_data.staged(ctx.out)
        source = recipe.runtime_data.staged_source(ctx.out, rel)
        assert source in required
        assert [step.name for step in steps if source in step.outputs] == [producer.name]

    # Exercise the ordinary required-output check with every old representative present.
    # These private placeholders test declaration completeness, not rendered map validity.
    for output in producer.outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'map output placeholder')
    assert build.outputs_present(producer)
    for output in sorted(required):
        output.unlink()
        assert not build.outputs_present(producer), output.name
        output.write_bytes(b'map output placeholder')
    assert build.outputs_present(producer)


def test_staging_factory_declares_character_helper_roster_and_optional_adventures(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    chars = tmp_path / 'characters'
    pipeline = chars / 'pipeline'
    pipeline.mkdir(parents=True)
    helper = pipeline / 'definition.py'
    helper.write_bytes((recipe.PIPELINE / 'definition.py').read_bytes())
    for source in sorted(recipe.CHARS.glob('*/character.toml')):
        target = chars / source.parent.name / source.name
        target.parent.mkdir()
        target.write_bytes(source.read_bytes())
        adventure = source.with_name('adventure.toml')
        if adventure.exists():
            target.with_name('adventure.toml').write_bytes(adventure.read_bytes())
    monkeypatch.setattr(recipe, 'CHARS', chars)
    monkeypatch.setattr(recipe, 'PIPELINE', pipeline)
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'build', uproject=None)

    def projection():
        # The real existing factory supplies declarations. Project only the new inputs
        # when exercising the unchanged fingerprint; no map/mesh/native output is built.
        actual = next(step for step in recipe.staging_steps(ctx) if step.name == 'data.stage')
        roster = sorted(chars.glob('*/character.toml'))
        assert helper in actual.inputs and set(roster) <= set(actual.inputs)
        assert actual.optional_inputs == [path.with_name('adventure.toml') for path in roster]
        return replace(actual, inputs=[p for p in actual.inputs if p.is_relative_to(chars)])

    def fingerprint():
        actual = projection()
        return build.fingerprint(actual, {name: name for name in actual.needs})

    initial = fingerprint()
    original = helper.read_bytes()
    helper.write_bytes(original + b'\n# changed staging helper implementation\n')
    assert fingerprint() != initial
    helper.write_bytes(original)
    assert fingerprint() == initial

    character = next(iter(sorted(chars.glob('*/character.toml'))))
    original = character.read_bytes()
    character.write_bytes(original + b'\n# changed character configuration bytes\n')
    assert fingerprint() != initial
    character.write_bytes(original)
    assert fingerprint() == initial

    absent = next(p for p in projection().optional_inputs if not p.exists())
    absent.write_bytes(b'# newly present optional adventure\n')
    assert fingerprint() != initial
    absent.unlink()
    assert fingerprint() == initial

    future = chars / 'future-member' / 'character.toml'
    future.parent.mkdir()
    future.write_bytes(b'id = "future-member"\n')
    assert future in projection().inputs and future.with_name('adventure.toml') in projection().optional_inputs
    assert fingerprint() != initial
    future.unlink()
    assert fingerprint() == initial
