"""The migration's parity oracle and plan: matched copies within tolerance, every difference reported."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compare = load('v2_migrate_compare', 'tools/migrate/compare.py')
run = load('v2_migrate_run', 'tools/migrate/run.py')
BOUNDS = [-100, -100, 100, 100]


def record(mesh, rows=None, transform=None, **settings):
    base = {'mesh': mesh, 'collision_profile': 'BlockAll', 'collision_enabled': 'QUERY_ONLY', 'cast_shadow': True,
            'visible': True, 'hidden_in_game': False, 'cull_distance': [0.0, 0.0], 'tags': []}
    base.update(settings)
    if rows is not None:
        base['instances'] = rows
    else:
        base['transform'] = transform
    return base


def dump(*meshes):
    return {'schema': 1, 'bounds_cm': BOUNDS, 'meshes': list(meshes)}


def row(x, y=0.0, yaw=0.0):
    return [x, y, 0.0, 0.0, yaw, 0.0, 1.0, 1.0, 1.0]


def test_same_copies_split_differently_match():
    # One runtime group becomes two saved patches: the copies, not the components, are compared.
    original = dump(record('/Game/T', [row(1), row(50), row(-40)]))
    v2 = dump(record('/Game/T', [row(1)], tags=['V2Role:Group']), record('/Game/T', [row(-40), row(50.05)]))
    assert compare.compare(original, v2) == {}


def test_moved_missing_and_changed_copies_are_reported():
    original = dump(record('/Game/T', [row(1), row(50)]), record('/Game/House', transform=row(10)))
    v2 = dump(record('/Game/T', [row(1.5)], cast_shadow=False), record('/Game/House', transform=row(10, yaw=0.5)))
    report = compare.compare(original, v2)
    assert report['/Game/T']['only_original'] == 2 and report['/Game/T']['only_v2'] == 1
    assert report['/Game/House']['only_original'] == 1 and report['/Game/House']['only_v2'] == 1


def test_settings_differences_on_matched_copies():
    original = dump(record('/Game/T', [row(1), row(2)]))
    v2 = dump(record('/Game/T', [row(1), row(2)], cast_shadow=False))
    report = compare.compare(original, v2)
    assert report['/Game/T']['settings'] == {'cast_shadow: True -> False': 2}


def test_yaw_wraps():
    assert compare.close(row(0, yaw=179.999), row(0, yaw=-179.999))


def test_cli_explained_and_bounds(tmp_path, capsys):
    a, b, why = tmp_path / 'a.json', tmp_path / 'b.json', tmp_path / 'why.json'
    a.write_text(json.dumps(dump(record('/Game/T', [row(1)]))))
    b.write_text(json.dumps(dump()))
    assert compare.main([str(a), str(b)]) == 1
    why.write_text(json.dumps({'/Game/T': 'cleared by the Ronin camp on purpose'}))
    assert compare.main([str(a), str(b), '--explained', str(why)]) == 0
    b.write_text(json.dumps({**dump(), 'bounds_cm': [0, 0, 1, 1]}))
    assert compare.main([str(a), str(b)]) == 2


def region(game, name, bounds, maps='["/Game/V2/Maps/Slice"]'):
    path = game / f'world/regions/{name}/region.toml'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'schema = 1\nid = "region/{name}"\nbounds_cm = {bounds}\nmaps = {maps}\n')


def test_plan_uses_record_bounds_and_one_map(tmp_path):
    region(tmp_path, 'w01', '[-200, 0, -100, 100]')
    region(tmp_path, 'w00', '[-1000, -1000, 1000, 1000]')
    plan = run.make_plan(tmp_path, ['region/w01'], 'region/w00', ['Sea'], True, ['SkatePark'], 32.0)
    assert plan['map'] == '/Game/V2/Maps/Slice'
    assert plan['regions'] == [{'id': 'region/w01', 'bounds_cm': [-200.0, 0.0, -100.0, 100.0]}]
    assert plan['services'] == ['Sea'] and plan['only_migrated'] and plan['runtime_services'] == ['SkatePark']
    assert plan['held_cm'] == [[-200.0, 0.0, -100.0, 100.0]]
    # A region of the map this run leaves out still holds its box: the environment takes only what none holds.
    region(tmp_path, 'w03', '[300, 300, 400, 400]')
    held = run.make_plan(tmp_path, ['region/w01'], 'region/w00', [], False, [], 32.0)['held_cm']
    assert held == [[-200.0, 0.0, -100.0, 100.0], [300.0, 300.0, 400.0, 400.0]]
    region(tmp_path, 'w02', '[0, 0, 100, 100]', '["/Game/V2/Maps/Other"]')
    with pytest.raises(run.MigrationError, match='one map'):
        run.make_plan(tmp_path, ['region/w01', 'region/w02'], 'region/w00', [], False, [], 32.0)
    with pytest.raises(run.MigrationError, match='no region record'):
        run.make_plan(tmp_path, ['region/w09'], 'region/w00', [], False, [], 32.0)


def test_plan_refuses_overlapping_regions_of_one_map(tmp_path):
    region(tmp_path, 'w00', '[-1000, -1000, 1000, 1000]')
    region(tmp_path, 'w01', '[-200, 0, -100, 100]')
    region(tmp_path, 'w02', '[-100, 0, 0, 100]')          # shares only an edge: half-open, so disjoint
    assert len(run.make_plan(tmp_path, ['region/w01', 'region/w02'], 'region/w00', [], False, [], 32.0)['regions']) == 2
    region(tmp_path, 'w03', '[-150, 50, -50, 150]')
    with pytest.raises(run.MigrationError, match='region/w01 and region/w03 overlap'):
        run.make_plan(tmp_path, ['region/w03'], 'region/w00', [], False, [], 32.0)


def test_migration_rosters_merge_per_region(tmp_path):
    (tmp_path / 'world/regions/w01-start').mkdir(parents=True)
    run.record_rosters(tmp_path, [('/Game/__ExternalActors__/V2/Maps/Slice/0/AB/X1',
                                   'region/w01-start:Sea:SM_Sea:whole:id1')])
    run.record_rosters(tmp_path, [('/Game/__ExternalActors__/V2/Maps/Slice/0/CD/X2',
                                   'region/w01-start:HD_Bench:near:id2')])
    roster = json.loads((tmp_path / 'world/regions/w01-start/patches.json').read_text())['patches']
    assert roster == {'id1': {'key': 'Sea:SM_Sea', 'package': 'unreal/Content/__ExternalActors__/V2/Maps/Slice/0/AB/X1.uasset'},
                      'id2': {'key': 'HD_Bench', 'package': 'unreal/Content/__ExternalActors__/V2/Maps/Slice/0/CD/X2.uasset'}}


def test_roster_capture_must_be_complete():
    line = 'V2 PATCH /Game/__ExternalActors__/V2/Maps/Slice/0/AB/X1 region/w01-start:Sea:SM_Sea:whole:id1\n'
    assert run.patches_made(line + 'V2 MIGRATE DONE created=1 kept=0 patches=1\n') == [
        ('/Game/__ExternalActors__/V2/Maps/Slice/0/AB/X1', 'region/w01-start:Sea:SM_Sea:whole:id1')]
    with pytest.raises(run.MigrationError, match='incomplete'):
        run.patches_made(line + 'V2 MIGRATE DONE created=0 kept=2 patches=2\n')
    with pytest.raises(run.MigrationError, match='did not report'):
        run.patches_made('')


def test_repeated_service_flags_keep_every_name(monkeypatch):
    """`--runtime-service A --runtime-service B` keeps both (a store action kept only the last, so a whole-island run
    started only the gulls)."""
    seen = {}
    monkeypatch.setattr(run, 'make_plan', lambda game, ids, env, services, only, runtime, patch: seen.update(
        services=services, runtime=runtime) or {})
    monkeypatch.setattr(run, 'migrate', lambda game, plan, claim: None)
    assert run.main(['region/w01-start', '--environment', 'region/w00-island', '--services', 'SkyDome', '--services',
                     'Sea', '--only-migrated', '--runtime-service', 'Village', '--runtime-service', 'Ferry', 'Gulls']) == 0
    assert seen == {'services': ['SkyDome', 'Sea'], 'runtime': ['Village', 'Ferry', 'Gulls']}
