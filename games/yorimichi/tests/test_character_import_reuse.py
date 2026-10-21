"""Changing export implementation or FBX metadata must not reimport unchanged character content."""
import io
import json
from types import SimpleNamespace
import pytest

from atelier import build
from test_volcano_layers import fbx


def test_character_import_consumes_content_instead_of_exporter_key(tmp_path):
    recipe = build.load_recipe('yorimichi')
    character = recipe.definition.movers()[0]
    ctx = SimpleNamespace(out=tmp_path)
    steps = recipe.mover_export_steps(character, tmp_path)
    digest = next(s for s in steps if s.name == 'characters.cairo.import')
    importer = recipe.mover_import_steps(character, tmp_path)[0]
    assert 'characters.cairo' not in importer.needs
    assert digest.name in importer.needs
    root = tmp_path / character.output
    (root / 'fbx').mkdir(parents=True); (root / 'textures').mkdir()
    (root / 'fbx/Cairo.fbx').write_bytes(fbx(2025, (11, 22), [0., 1., 2.]))
    (root / 'fbx/A_Idle.fbx').write_bytes(b'idle clip')
    (root / 'textures/skin.png').write_bytes(b'pixels')
    report = root / 'export.json'
    report.write_text(json.dumps(dict(source_sha256='first source', clips={'Idle': {'frames': 30}}, materials={})))
    def imported_key(exporter_key):
        digest.commands[0].fn(ctx, io.StringIO())
        stamp = dict(fingerprint=build.fingerprint(digest, {'characters.cairo': exporter_key}),
                     result=build.outputs_digest(digest))
        current = build.result(digest, stamp['fingerprint'], stamp)
        needs = {name: 'compiled-module' for name in importer.needs}
        needs[digest.name] = current
        return build.fingerprint(importer, needs)
    original = imported_key('old exporter implementation')
    # Only metadata changes; all consumed character content stays identical.
    (root / 'fbx/Cairo.fbx').write_bytes(fbx(2026, (9876, 5432), [0., 1., 2.]))
    report.write_text(json.dumps(dict(source_sha256='new source receipt', clips={'Idle': {'frames': 30}}, materials={})))
    assert imported_key('new exporter implementation') == original
    for path, data in [(root / 'fbx/Cairo.fbx', fbx(2026, (9876, 5432), [0., 1., 2.5])),
                       (root / 'textures/skin.png', b'new pixels'),
                       (report, json.dumps(dict(clips={'Idle': {'frames': 60}}, materials={})).encode())]:
        before = path.read_bytes(); path.write_bytes(data)
        assert imported_key('new exporter implementation') != original
        path.write_bytes(before)
    (root / 'fbx/Cairo.fbx').unlink()
    # A missing mesh changes the observed membership even if the export stamp stayed current.
    with pytest.raises(FileNotFoundError, match='required character export'):
        imported_key('new exporter implementation')


def test_all_playable_body_and_riding_imports_use_content_cutoffs(tmp_path):
    recipe = build.load_recipe('yorimichi')
    for character in recipe.definition.movers():
        exports = recipe.mover_export_steps(character, tmp_path)
        imports = recipe.mover_import_steps(character, tmp_path)
        for step in imports:
            content = next(name for name in step.needs if name.startswith('characters.'))
            digest = next(s for s in exports if s.name == content)
            assert digest.cutoff and digest.deferred_inputs


def test_switching_to_content_cutoff_preserves_a_proven_warm_import(tmp_path):
    from dataclasses import replace
    from atelier import checkpoint_actions as cache
    from atelier.build_cache import atomic_json
    recipe = build.load_recipe('yorimichi')
    character = recipe.definition.movers()[0]
    step = recipe.mover_import_steps(character, tmp_path)[0]
    # Synthetic existing output; the migration runs no native work and changes only stamp metadata.
    output = tmp_path / 'character.uasset'; output.write_bytes(b'imported character')
    step = replace(step, outputs=[output], commands=[build.Call('unchanged importer', lambda *_: None)])
    ctx = SimpleNamespace(game='fixture', out=tmp_path, stamps=tmp_path / 'stamps',
                          checkpoint_incremental_compatible=True, checkpoint_observed_context='observed')
    ctx.stamps.mkdir()
    done = {name: 'same-code' for name in (*step.needs, *step.checkpoint_previous_needs)}
    done['characters.cairo.import'] = 'outputs:normalized-character-content'
    old = replace(step, needs=list(step.checkpoint_previous_needs))
    previous = dict(fingerprint=build.fingerprint(old, done), seconds=30)
    atomic_json(ctx.stamps / (step.name + '.json'), previous)
    current, state = build.fingerprint_state(step, done)
    migrated = cache.migrate_boundary(ctx, step, current, state, previous, done)
    assert migrated['fingerprint'] == current and 'checkpoint_key' not in migrated
    assert build.result(step, current, migrated) == previous['fingerprint']
    assert output.read_bytes() == b'imported character'
    # Different original exporter inputs cannot use this equivalence shortcut.
    done['characters.cairo'] = 'actually-changed-original-input'
    assert cache.migrate_boundary(ctx, step, current, state, previous, done) == previous


def test_body_migration_preserves_dependent_ride_import(tmp_path):
    from dataclasses import replace
    from atelier import checkpoint_actions as cache
    recipe = build.load_recipe('yorimichi')
    steps = recipe.mover_import_steps(recipe.definition.movers()[0], tmp_path)
    ctx = SimpleNamespace(game='fixture', out=tmp_path, stamps=tmp_path / 'stamps',
                          checkpoint_incremental_compatible=True, checkpoint_observed_context='observed')
    ctx.stamps.mkdir()
    done = {name: 'unchanged' for step in steps for name in (*step.needs, *step.checkpoint_previous_needs)}
    done.update({name: 'outputs:normalized-content' for name in done if name.endswith('.import')})
    old_done = dict(done)
    for original in steps:
        output = tmp_path / (original.name + '.uasset'); output.write_bytes(b'unchanged imported bytes')
        step = replace(original, outputs=[output], commands=[build.Call('same importer', lambda *_: None)])
        old = replace(step, needs=list(step.checkpoint_previous_needs))
        previous = dict(fingerprint=build.fingerprint(old, old_done))
        old_done[step.name] = previous['fingerprint']
        current, state = build.fingerprint_state(step, done)
        migrated = cache.migrate_boundary(ctx, step, current, state, previous, done)
        assert migrated.get('checkpoint_migrated_from') == previous['fingerprint']
        done[step.name] = build.result(step, current, migrated)
        assert done[step.name] == old_done[step.name]
