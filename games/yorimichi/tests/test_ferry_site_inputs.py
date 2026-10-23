"""Final source construction refuses stale or incomplete sweep prerequisite data."""
import importlib.util
import json
from pathlib import Path

import pytest
from atelier.export_manifest import sha

PATH = Path(__file__).resolve().parents[1] / 'world/regions/ferry/site_inputs.py'
spec = importlib.util.spec_from_file_location('ferry_source_proof', PATH)
proof = importlib.util.module_from_spec(spec); spec.loader.exec_module(proof)


def inputs(tmp_path):
    root = tmp_path.resolve() / 'repo'; build = root / 'build/game'
    code = root / 'games/game/world/route.py'
    code.parent.mkdir(parents=True); code.write_bytes(b'route')
    query = build / 'queries/Harbor.npz'
    query.parent.mkdir(parents=True); query.write_bytes(b'exact query input')
    probes = {}
    for key in proof.PROBES:
        target = build / f'ferry/terminals/world_{key}.npz'
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(key.encode())
        probes[key] = sha(target)
    value = {'pass': True, 'inputs': dict(code={code.relative_to(root).as_posix(): sha(code)},
        exports={key: {query.relative_to(build).as_posix(): sha(query)} for key in proof.PROBES}, world_probes=probes)}
    value['hidamari'] = {'berth': {'world_cuts': [dict(what='quay rail', x=[2, 4], y=[-1, 1], z_from=2.375)]}}
    site = build / proof.SITE; site.write_text(json.dumps(value))
    return root, build, code, query, site, value


def test_declared_membership_exactly_covers_all_validator_reads(tmp_path):
    repo, build, code, query, site, value = inputs(tmp_path)
    assert proof.validate(build, repo) == value
    assert set(proof.paths(build, repo)) == {code, query, site,
        *(build / f'ferry/terminals/world_{key}.npz' for key in proof.PROBES)}


@pytest.mark.parametrize('kind', ['query', 'code', 'probe', 'missing', 'failed', 'incomplete', 'escape', 'link'])
def test_cut_cannot_use_changed_missing_unsafe_or_failed_proof(tmp_path, kind):
    repo, build, code, query, site, value = inputs(tmp_path)
    if kind == 'query': query.write_bytes(b'changed geometry')
    if kind == 'code': code.write_bytes(b'changed route')
    if kind == 'probe': (build / 'ferry/terminals/world_crossing.npz').write_bytes(b'changed probe')
    if kind == 'missing': query.unlink()
    if kind == 'failed': value['pass'] = False
    if kind == 'incomplete': value['inputs']['world_probes'].pop('crossing')
    if kind == 'escape': value['inputs']['exports']['hidamari'] = {'../outside': '0' * 64}
    if kind == 'link':
        query.rename(query.with_suffix('.kept')); query.symlink_to(query.with_suffix('.kept'))
    site.write_text(json.dumps(value))
    with pytest.raises(ValueError): proof.validate(build, repo)


def test_cold_membership_is_declared_without_creating_prerequisites(tmp_path):
    build, repo = tmp_path.resolve() / 'build', tmp_path.resolve() / 'repo'
    assert set(proof.paths(build, repo)) == {build / proof.SITE,
        *(build / f'ferry/terminals/world_{key}.npz' for key in proof.PROBES)}
    assert not build.exists() and not repo.exists()


def test_proof_only_changes_validate_then_stop_before_geometry(tmp_path):
    import io
    repo, build, code, _, site, value = inputs(tmp_path)
    output = build / 'projected/cut-data.json'
    proof.record(build, repo, output, io.StringIO())
    before, timestamp = output.read_bytes(), output.stat().st_mtime_ns
    code.write_bytes(b'changed but successfully revalidated route proof')
    value['inputs']['code'][code.relative_to(repo).as_posix()] = sha(code)
    site.write_text(json.dumps(value))
    proof.record(build, repo, output, io.StringIO())
    assert output.read_bytes() == before and output.stat().st_mtime_ns == timestamp
    code.write_bytes(b'unvalidated stale route')
    with pytest.raises(ValueError, match='changed'): proof.record(build, repo, output, io.StringIO())
    assert output.read_bytes() == before
    value['inputs']['code'][code.relative_to(repo).as_posix()] = sha(code)
    value['hidamari']['berth']['world_cuts'][0]['x'][1] = 5
    site.write_text(json.dumps(value))
    proof.record(build, repo, output, io.StringIO())
    assert json.loads(output.read_text())['cuts'][0]['x'] == [2, 5]
    output.write_bytes(b'corrupted previous owned output')
    proof.record(build, repo, output, io.StringIO())
    assert json.loads(output.read_text())['cuts'][0]['x'] == [2, 5]


@pytest.mark.parametrize('kind', ['missing', 'reversed', 'nonfinite', 'foreign', 'wrong-stage'])
def test_cut_projection_retains_exact_geometry_and_rejects_incomplete_data(tmp_path, kind):
    repo, build, _, _, _, _ = inputs(tmp_path)
    value = proof.projection(build, repo)
    if kind == 'missing': value['cuts'] = []
    if kind == 'reversed': value['cuts'][0]['x'] = [4, 2]
    if kind == 'nonfinite': value['cuts'][0]['z_from'] = float('inf')
    if kind == 'foreign': value['cuts'][0]['source_mesh'] = 'not-an-input.fbx'
    if kind == 'wrong-stage': value['stage'] = 'raw'
    with pytest.raises(ValueError): proof.read_projection(value)
