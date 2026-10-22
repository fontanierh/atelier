"""Proof changes must validate, while identical final geometry stops downstream."""
import hashlib
import importlib.util
import json

import pytest

from test_ferry_source import proof
from test_volcano_layers import RECIPE

_spec = importlib.util.spec_from_file_location('city_harbor_inputs_test', RECIPE.GAME/'city_harbor_inputs.py')
harbor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harbor)


@pytest.fixture
def final_harbor(tmp_path):
    repo, out, files, cut = proof(tmp_path)
    helper = repo/'games/yorimichi/world/regions/hidamari/ferry_source.py'
    helper.write_bytes((RECIPE.REGIONS/'hidamari/ferry_source.py').read_bytes())
    manifest = out/'hidamari/manifest.json'
    manifest.write_text(json.dumps({'HD_Harbor':dict(triangles=10, min=[0, 0, 0], max=[1, 1, 1],
        collision_boxes=0, materials=1)}))
    cut.update(triangles=dict(before=10, after=8), untouched_outside_cuts=True)
    files['receipt'].write_text(json.dumps(cut))
    return repo, out, files, cut, manifest, helper


def test_exact_declared_inputs_cover_every_validator_read(final_harbor):
    repo, out, files, _, manifest, helper = final_harbor
    assert set(harbor.paths(out, repo)) == {*files.values(), manifest, helper,
        *(out/f'ferry/terminals/world_{name}.npz' for name in ('hidamari', 'brinecove', 'crossing'))}
    row = harbor.snapshot(out, repo)
    assert row == dict(source='HD_Harbor', source_path='hidamari/ferry/HD_Harbor.fbx',
        source_sha256=hashlib.sha256(files['mesh'].read_bytes()).hexdigest(),
        triangles=8, min=[0, 0, 0], max=[1, 1, 1], collision_boxes=0)


def test_cold_deferred_membership_declares_missing_prerequisites_without_certifying_them(tmp_path):
    out, repo = tmp_path/'build', tmp_path/'repo'
    assert out/'hidamari/ferry/HD_Harbor.fbx' in harbor.paths(out, repo)
    with pytest.raises(ValueError, match='Missing'):
        harbor.snapshot(out, repo)


def test_proof_only_change_is_verified_then_stops_at_identical_geometry(final_harbor):
    repo, out, files, cut, _, _ = final_harbor
    before = harbor.snapshot(out, repo)
    files['code'].write_text('changed cut code')
    with pytest.raises(ValueError, match='changed'):
        harbor.snapshot(out, repo)
    relative = str(files['code'].relative_to(repo))
    digest = hashlib.sha256(files['code'].read_bytes()).hexdigest()
    cut['inputs'][relative] = digest
    site = json.loads(files['site'].read_text())
    site['inputs']['code'][relative] = digest
    files['site'].write_text(json.dumps(site))
    cut['inputs'][str(files['site'].relative_to(repo))] = hashlib.sha256(files['site'].read_bytes()).hexdigest()
    files['receipt'].write_text(json.dumps(cut))
    assert harbor.snapshot(out, repo) == before


@pytest.mark.parametrize('changed', ['code', 'layout', 'ground', 'base', 'site', 'mesh', 'probe'])
def test_stale_complete_proof_never_publishes_projection(final_harbor, changed):
    repo, out, files, _, _, _ = final_harbor
    path = out/'ferry/terminals/world_crossing.npz' if changed == 'probe' else files[changed]
    path.write_bytes(b'changed')
    with pytest.raises((ValueError, KeyError)):
        harbor.snapshot(out, repo)


@pytest.mark.parametrize('bad', ['raw_count', 'final_count', 'collision', 'materials', 'bounds', 'outside', 'escape', 'linked',
    'boolean_raw', 'boolean_collision', 'boolean_materials'])
def test_unsafe_or_inconsistent_final_source_refuses(final_harbor, bad):
    repo, out, files, cut, manifest, _ = final_harbor
    raw = json.loads(manifest.read_text())
    if bad == 'raw_count': cut['triangles']['before'] = 9
    elif bad == 'final_count': cut['triangles']['after'] = True
    elif bad == 'collision': raw['HD_Harbor']['collision_boxes'] = 1
    elif bad == 'materials': raw['HD_Harbor']['materials'] = 2
    elif bad == 'boolean_raw': raw['HD_Harbor']['triangles'] = True
    elif bad == 'boolean_collision': raw['HD_Harbor']['collision_boxes'] = False
    elif bad == 'boolean_materials': raw['HD_Harbor']['materials'] = True
    elif bad == 'bounds': raw['HD_Harbor']['min'][0] = float('inf')
    elif bad == 'outside': cut['untouched_outside_cuts'] = False
    elif bad == 'escape':
        site = json.loads(files['site'].read_text())
        site['inputs']['code']['../outside.py'] = 'f'*64
        files['site'].write_text(json.dumps(site))
    elif bad == 'linked':
        files['mesh'].rename(files['mesh'].with_suffix('.original'))
        files['mesh'].symlink_to(files['mesh'].with_suffix('.original'))
    manifest.write_text(json.dumps(raw))
    files['receipt'].write_text(json.dumps(cut))
    with pytest.raises(ValueError):
        harbor.snapshot(out, repo)
