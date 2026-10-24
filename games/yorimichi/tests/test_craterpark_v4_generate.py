"""The v4 integration fails closed and keeps structural gates in preview mode."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
sys.path.insert(0, str(GAME / 'world'))
from craterpark.v2 import export, v4_config, v4_generate, validate  # noqa: E402


@pytest.fixture
def selection(tmp_path, monkeypatch):
    path = tmp_path / 'design.json'
    path.write_text(json.dumps({'ground': {'dig': {'DEPTH': 65}}}))
    monkeypatch.setenv(v4_config.SWITCH, str(path))
    return path


def test_selection_missing_and_invalid_are_never_legacy(tmp_path, monkeypatch):
    monkeypatch.delenv(v4_config.SWITCH, raising=False)
    assert not v4_config.selected() and v4_config.input_paths() == []
    monkeypatch.setenv(v4_config.SWITCH, str(tmp_path / 'missing.json'))
    assert v4_config.selected()
    with pytest.raises(OSError):
        v4_config.input_paths()
    (tmp_path / 'missing.json').write_text('[]')
    with pytest.raises(ValueError, match='object'):
        v4_config.input_paths()


def test_provenance_hashes_referenced_bytes_without_machine_paths(selection):
    heightmap = selection.parent / 'terrain.npz'
    heightmap.write_bytes(b'one')
    selection.write_text(json.dumps({'ground': {'heightmap': heightmap.name, 'dig': {'DEPTH': 65}}}))
    before = v4_config.provenance()
    assert before['depth'] == 65
    assert [p['name'] for p in before['inputs']] == ['design.json', 'terrain.npz']
    heightmap.write_bytes(b'two')
    after = v4_config.provenance()
    assert before['design_sha256'] == after['design_sha256']
    assert before['source_sha256'] != after['source_sha256']
    heightmap.unlink()
    with pytest.raises(ValueError, match='missing'):
        v4_config.provenance()


def test_validator_grid_transposes_native_zx_and_rejects_unequal_spacing():
    terrain = SimpleNamespace(x=np.array([0., 2.]), z=np.array([0., 2., 4.]),
                              heights=np.array([[0., 2.], [4., 6.], [8., 10.]]))
    ground = v4_generate.validator_ground(SimpleNamespace(terrain=terrain))
    assert ground.H.shape == (2, 3)
    assert ground.at(1., 1.) == pytest.approx(3.)
    terrain.z = np.array([0., 3., 6.])
    with pytest.raises(ValueError, match='spacing'):
        v4_generate.validator_ground(SimpleNamespace(terrain=terrain))


@pytest.mark.parametrize('failure,passes', [('outlines', True), ('topology', False), ('terrain', False),
                                          ('ownership', False), ('unknown', False)])
def test_preview_only_admits_named_cosmetic_failures(tmp_path, monkeypatch, failure, passes):
    (tmp_path / 'PREVIEW').touch()
    calls = []
    def fake_validate(park, out, **kwargs):
        calls.append(kwargs)
        return {'ok': False, 'checks': {failure: {'ok': False}}}, False
    monkeypatch.setattr(validate, 'validate_park', fake_validate)
    ground = object()
    if passes:
        result = v4_generate.run_validators(object(), tmp_path, ground)
        assert result['preview'] and not result['ok']
        assert not json.loads((tmp_path / 'validation.json').read_text())['ok']
    else:
        with pytest.raises(ValueError, match='validation failed'):
            v4_generate.run_validators(object(), tmp_path, ground)
    assert calls == [{'ground': ground}]


def test_export_rejects_stale_or_unselected_v4_before_fbx(selection, tmp_path, monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('FBX writing must not start')
    geometry = {'index': np.asarray(json.dumps({'v4': {'stale': True}}))}
    with pytest.raises(ValueError, match='does not match'):
        export.write(tmp_path / 'out', tmp_path, geometry, object(), forbidden)
    monkeypatch.delenv(v4_config.SWITCH)
    with pytest.raises(ValueError, match='explicit design'):
        export.write(tmp_path / 'out', tmp_path, geometry, object(), forbidden)
    assert calls == []


def test_recipe_selection_declares_data_and_geometry_dependencies(selection, tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('yorimichi_v4_recipe_test', GAME / 'build.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    steps = module.world_steps(SimpleNamespace(out=tmp_path))
    by_name = {s.name: s for s in steps}
    geometry = by_name['world.craterpark_geometry']
    assert selection in geometry.inputs
    assert geometry.commands[0].script.name == 'v4_generate.py'
    assert geometry.outputs == [tmp_path / 'craterpark/v2' / name for name in
                                ('geometry.npz', 'geometry-report.json', 'lines')]
    assert geometry.cutoff and geometry.heavy and not geometry.cache
    layout = by_name['world.craterpark_layout']
    assert layout.cutoff and layout.needs == ['world.craterpark_geometry']
    assert selection in layout.inputs
    for name in ('world.layout', 'world.hidamari.layout_data', 'world.map'):
        assert 'world.craterpark_layout' in by_name[name].needs
        if name == 'world.hidamari.layout_data':
            assert selection in by_name[name].inputs  # selected source queries consume the design directly
        else:
            assert 'world.craterpark_geometry' not in by_name[name].needs
            assert selection not in by_name[name].inputs
    monkeypatch.delenv(v4_config.SWITCH)
    legacy = module.craterpark_v2_steps(tmp_path)[0]
    assert legacy.commands[0].script.name == 'generate.py'


def test_export_v4_uses_checked_start_without_old_drop_in(selection, tmp_path):
    (tmp_path / 'scene.json').write_text('{}')
    provenance = v4_config.provenance()
    spawn = {'location_cm': [12., 34., 560.], 'yaw_deg': 42.}
    index = {'v4': provenance, 'accepted': True,
             'validation': {'ran': True, 'ok': True, 'supports': {'ran': True, 'ok': True}},
             'bounds_native': [[0., 0., 0.], [1., 1., 1.]],
             'render': [], 'collision': [], 'rails': [],
             'lines': [{'key': 'L1', 'spawn': spawn}]}
    geometry = {'index': np.asarray(json.dumps(index))}
    placement = SimpleNamespace(unreal_transform=lambda: {'location_cm': [0., 0., 0.], 'yaw_deg': 0.},
                                summary=lambda: pytest.fail('v4 export must use passed geometry, not canonical output'))
    build, park = export.write(tmp_path / 'export', tmp_path, geometry, placement,
                               entry_mesh=lambda *args, **kwargs: {})
    assert park['spawn'] == spawn
    assert park['source_sha256'] == provenance['source_sha256']
    assert build['scene_sha256'] == export.sha(tmp_path / 'scene.json')
    assert build['v4'] == park['v4'] == provenance


def test_site_provenance_follows_explicit_preference_order(selection):
    preferred = selection.parent / 'preferred.json'
    preferred.write_text('{}')
    selection.write_text(json.dumps({'site': {'file': 'missing-fallback.json',
                                              'prefer': ['missing-option.json', preferred.name]}}))
    assert v4_config.input_paths() == [selection, preferred]


def test_file_hash_cache_reuses_unchanged_bytes_and_detects_restored_mtime(tmp_path, monkeypatch):
    import os
    file = tmp_path / 'data.npz'
    file.write_bytes(b'first')
    before = file.stat()
    reads = []
    original = Path.read_bytes
    def read(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    first = v4_config.file_sha(file)
    assert v4_config.file_sha(file) == first
    assert reads == [file]
    file.write_bytes(b'other')
    os.utime(file, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert v4_config.file_sha(file) != first
    assert reads == [file, file]


def test_export_does_not_publish_json_if_design_changes_during_fbx(selection, tmp_path):
    (tmp_path / 'scene.json').write_text('{}')
    provenance = v4_config.provenance()
    index = {'v4': provenance, 'accepted': True,
             'validation': {'ran': True, 'ok': True, 'supports': {'ran': True, 'ok': True}},
             'bounds_native': [[0., 0., 0.], [1., 1., 1.]],
             'render': [], 'collision': [], 'rails': [],
             'lines': [{'key': 'L1', 'spawn': {'location_cm': [0., 0., 0.], 'yaw_deg': 0.}}]}
    geometry = {'index': np.asarray(json.dumps(index))}
    placement = SimpleNamespace(unreal_transform=lambda: {'location_cm': [0., 0., 0.], 'yaw_deg': 0.})
    def changed_during_export(*args, **kwargs):
        selection.write_text('{"changed": true}')
        return {}
    out = tmp_path / 'export'
    with pytest.raises(ValueError, match='changed during export'):
        export.write(out, tmp_path, geometry, placement, entry_mesh=changed_during_export)
    assert not (out / 'build.json').exists()
    assert not (out / 'park.json').exists()


def test_export_refuses_renamed_diagnostic_geometry(selection, tmp_path):
    index = {'v4': v4_config.provenance(), 'accepted': False, 'lines': [{'key': 'L1'}]}
    geometry = {'index': np.asarray(json.dumps(index))}
    with pytest.raises(ValueError, match='diagnostic artifacts cannot export'):
        export.write(tmp_path / 'out', tmp_path, geometry, object(), lambda *args: {})


def test_rainbow_posts_without_material_bodies_cannot_inherit_tower_clearance(tmp_path,monkeypatch):
    monkeypatch.setattr(validate,'validate_park',lambda *a,**kw:({'ok':True,'checks':{}},True))
    park=SimpleNamespace(checks=[{'kind':'v4_rainbow','feature':'gap.rainbow'}],
                         mesh=SimpleNamespace(features=('gap.rainbow',)))
    with pytest.raises(ValueError,match='supports'):
        v4_generate.run_validators(park,tmp_path,object())
    report=json.loads((tmp_path/'validation.json').read_text())
    assert report['checks']['supports']['failures'][0]['kind']=='unresolved_rainbow_post_supports'
