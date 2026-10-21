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
    real = RECIPE.brinecove_steps(out)[0]
    executed = []

    def consume(ctx, log):
        # The real launcher passes exactly this declared file, rather than reopening the global library.
        executed.append(json.loads(selector.outputs[0].read_text()))
        real.outputs[0].parent.mkdir(parents=True, exist_ok=True)
        for output in real.outputs:
            output.write_text('consumer output')

    consumer = build.Step(real.name, [build.Call('stand-in export', consume)], inputs=real.inputs,
                          needs=real.needs, outputs=real.outputs)
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
