"""Real terrain couplings remain inputs; unrelated implementation/library edits stop at their boundary."""
import json
from types import SimpleNamespace

import pytest

from atelier import build
from test_mega_ramp_layers import changed_by
from test_volcano_layers import RECIPE


@pytest.mark.parametrize('edited', ['belmonte/source.py', 'belmonte/terrain.py', '../train/earthworks.py',
                                   '../train/station_site.py', 'hidamari/mountains.py'])
def test_editor_geometry_does_not_read_final_terrain_implementation(edited, tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', str(RECIPE.craterpark_v4.SHIPPED))
    changed = changed_by((RECIPE.REGIONS / edited).resolve(), tmp_path, monkeypatch)
    assert 'world.craterpark_geometry' not in changed
    # These remain genuine consumers of the railway-deformed, joined terrain.
    if edited != 'hidamari/mountains.py':
        assert {'world.hidamari', 'world.layout', 'world.zeppelin'} <= changed


@pytest.mark.parametrize('edited', ['kernel', 'design'])
def test_editor_geometry_still_tracks_natural_math_and_selected_design(edited, tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', str(RECIPE.craterpark_v4.SHIPPED))
    path = RECIPE.REGIONS / 'hidamari/natural_terrain.py' if edited == 'kernel' else RECIPE.craterpark_v4.SHIPPED
    assert 'world.craterpark_geometry' in changed_by(path, tmp_path, monkeypatch)


@pytest.fixture
def registry_build(tmp_path, monkeypatch):
    """Exercise normal cutoff/stamp execution with a cheap stand-in for the Blender consumer."""
    assets = tmp_path / 'assets'
    models = assets / 'brinecove/models'
    models.mkdir(parents=True)
    model = models / 'ship.glb'
    model.write_bytes(b'model')
    provenance = models / 'ship.provenance.json'
    provenance.write_text('{}')
    library = assets / 'source-library.json'
    files = {'brinecove/models/ship.glb': {'sha256': 'a' * 64}, 'other/model.glb': {'sha256': 'b' * 64}}
    monkeypatch.setattr(RECIPE, 'ASSETS', assets)
    world = tmp_path / 'world'
    world.mkdir()
    helper = world / 'source_registry.py'
    helper.write_bytes((RECIPE.WORLD / helper.name).read_bytes())
    original_helper = RECIPE.WORLD / helper.name
    local_imports = RECIPE.build_inputs.local_imports
    # The production scanner resolves imports from the actual entrypoint. Relocate only
    # this fixture's copied verifier, preserving the rest of that complete closure.
    monkeypatch.setattr(RECIPE.build_inputs, 'local_imports', lambda *args, **kwargs:
                        [helper if path == original_helper else path
                         for path in local_imports(*args, **kwargs)])
    monkeypatch.setattr(RECIPE, 'WORLD', world)
    out = tmp_path / 'build'
    selector = RECIPE.brinecove_source_step(out)
    atomic = RECIPE._load_helper_module('registry_fixture_brinecove', RECIPE.GAME / 'brinecove_atomic_build.py')
    real = next(step for step in atomic.steps(SimpleNamespace(out=out))
                if step.name == 'world.brinecove.placements')
    outputs = [path for product in real.products for path in product.paths]
    model_root = RECIPE.GAME / 'assets/brinecove/models'
    inputs = [helper if path == original_helper else path for path in real.inputs
              if not path.is_relative_to(model_root)] + [helper, model, provenance]
    executed = []

    def consume(ctx, log):
        # The real launcher passes exactly this declared file, rather than reopening the global library.
        executed.append(json.loads(selector.outputs[0].read_text()))
        outputs[0].parent.mkdir(parents=True, exist_ok=True)
        for output in outputs:
            output.write_text('consumer output')

    consumer = build.Step(real.name, [build.Call('stand-in export', consume)], inputs=inputs,
                          needs=real.needs, outputs=outputs)
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out / 'logs', stamps=out / 'stamps', uproject=None)
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: [selector, consumer]))

    def run():
        library.write_text(json.dumps({'files': files}))
        return build.build('yorimichi', [real.name], echo=lambda message: None)

    assert run() == 0 and len(executed) == 1
    executed.clear()
    return SimpleNamespace(run=run, files=files, executed=executed, model=model, provenance=provenance,
                           snapshot=selector.outputs[0], helper=helper)


def test_unrelated_registry_edits_stop_before_the_region_export(registry_build):
    p = registry_build
    before = p.snapshot.read_bytes()
    p.files['other/model.glb']['sha256'] = 'c' * 64
    p.files['another/model.glb'] = {'sha256': 'd' * 64}
    p.files['brinecove/models/ship.glb']['unused_metadata'] = 'not consumed'
    assert p.run() == 0 and p.executed == [] and p.snapshot.read_bytes() == before


def test_verification_code_change_reaches_export_even_with_identical_snapshot(registry_build):
    p = registry_build
    before = p.snapshot.read_bytes()
    p.helper.write_text(p.helper.read_text() + '\n# changed runtime verification implementation\n')
    assert p.run() == 0 and len(p.executed) == 1 and p.snapshot.read_bytes() == before


def test_assembled_export_tracks_its_runtime_registry_helper(tmp_path, monkeypatch):
    assert 'world.brinecove' in changed_by(RECIPE.WORLD / 'source_registry.py', tmp_path, monkeypatch)


@pytest.mark.parametrize('change', ['checksum', 'addition', 'removal'])
def test_selected_registry_changes_reach_the_region_export(registry_build, change):
    p = registry_build
    if change == 'checksum':
        p.files['brinecove/models/ship.glb']['sha256'] = 'c' * 64
    elif change == 'addition':
        p.files['brinecove/models/cannon.glb'] = {'sha256': 'c' * 64}
    else:
        # Keep a nonempty selection: removing its last model must fail instead of producing a valid snapshot.
        p.files['brinecove/models/cannon.glb'] = {'sha256': 'c' * 64}
        assert p.run() == 0
        p.executed.clear()
        del p.files['brinecove/models/ship.glb']
    assert p.run() == 0 and len(p.executed) == 1


@pytest.mark.parametrize('asset', ['model', 'provenance'])
def test_actual_asset_bytes_still_invalidate_the_export(registry_build, asset):
    p = registry_build
    getattr(p, asset).write_bytes(b'changed')
    assert p.run() == 0 and len(p.executed) == 1


def test_empty_selection_fails_without_reusing_a_prior_success(registry_build):
    p = registry_build
    del p.files['brinecove/models/ship.glb']
    assert p.run() != 0 and p.executed == []


def test_explicit_snapshot_is_verified_without_global_library_fallback(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(RECIPE.WORLD))
    monkeypatch.syspath_prepend(str(RECIPE.REGIONS))
    from brinecove import hero_sources
    missing = tmp_path / 'selection.json'
    with pytest.raises(FileNotFoundError):
        hero_sources.verify(missing)
    missing.write_text('{"files": {}}')
    with pytest.raises(ValueError, match='lists no models'):
        hero_sources.verify(missing)


def test_output_identical_craterpark_source_edit_keeps_downstream_fingerprints_and_geometry_change_invalidates_them(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', str(RECIPE.craterpark_v4.SHIPPED))
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = {s.name: s for s in RECIPE.steps(ctx)}
    geometry = steps['world.craterpark_geometry']
    assert geometry.cutoff
    dependents = ('world.hidamari.layout_data', 'world.layout', 'world.farhills', 'world.map',
                  'world.craterpark_layout', 'world.craterpark.inputs', 'world.gondola_site')
    for name in dependents:
        assert 'world.craterpark_geometry' in steps[name].needs, name

    for output in geometry.outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'geometry-v1')
    source = (RECIPE.REGIONS / 'craterpark/v2/solids.py').resolve()
    edited_bytes = {source: source.read_bytes() + b'\n# output-identical refactor\n'}

    geom_before = build.fingerprint(geometry, {})
    geom_after = build.fingerprint(geometry, {}, _input_bytes=edited_bytes)
    assert geom_before != geom_after

    digest_v1 = build.outputs_digest(geometry)
    done_before = {
        'world.craterpark_geometry': build.result(geometry, geom_before, {'fingerprint': geom_before, 'result': digest_v1}),
        'world.craterpark_layout': 'layout-v1',
        'world.layout': 'world-layout-v1',
        'world.treehouse_trees': 'trees-v1',
        'world.hidamari': 'hidamari-v1',
        'world.skatepark': 'skatepark-v1',
        'world.zeppelin': 'zeppelin-v1',
        'world.belmonte': 'belmonte-v1',
        'world.gondola_kit': 'gondola-kit-v1',
        'world.gondola_ground': 'gondola-ground-v1',
        'world.gondola_structures': 'gondola-structures-v1',
        'product:terrain.FarHills.final': 'farhills-final-v1',
        'product:brinecove.map': 'brinecove-map-v1',
        'product:belmonte.ground': 'belmonte-ground-v1',
    }
    done_after_identical = {
        **done_before,
        'world.craterpark_geometry': build.result(geometry, geom_after, {'fingerprint': geom_after, 'result': digest_v1}),
    }
    for name in dependents:
        step = steps[name]
        assert (build.fingerprint(step, done_before, _tool_identity='fixture')
                == build.fingerprint(step, done_after_identical, _input_bytes=edited_bytes, _tool_identity='fixture')), name

    geometry.outputs[0].write_bytes(b'geometry-v2-changed')
    digest_v2 = build.outputs_digest(geometry)
    assert digest_v2 != digest_v1
    done_after_changed = {
        **done_before,
        'world.craterpark_geometry': build.result(geometry, geom_after, {'fingerprint': geom_after, 'result': digest_v2}),
    }
    for name in dependents:
        step = steps[name]
        assert (build.fingerprint(step, done_before, _tool_identity='fixture')
                != build.fingerprint(step, done_after_changed, _input_bytes=edited_bytes, _tool_identity='fixture')), name


def test_legacy_megapark_forest_and_plants_inputs_are_narrowed_to_actual_importers(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    steps = RECIPE.steps(ctx)
    forest = RECIPE.REGIONS / 'megapark' / 'forest.py'
    plants = RECIPE.REGIONS / 'megapark' / 'plants.py'
    # Atomic constructors separately declare their complete query implementation
    # closures. Preserve those declarations while checking the legacy source owners
    # to which the import filtering applies.
    legacy = {'world.layout', 'world.hidamari', 'world.megapark'}
    assert {s.name for s in steps if s.name in legacy and forest in s.inputs} == {'world.layout'}
    assert {s.name for s in steps if s.name in legacy and plants in s.inputs} == {'world.megapark'}
