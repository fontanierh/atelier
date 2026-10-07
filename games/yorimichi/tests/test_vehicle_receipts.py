import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('vehicle_review', Path(__file__).resolve().parents[1] / 'tools/network_vehicle_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def write(folder, name, data):
    (folder / (name + '.json')).write_text(json.dumps(data))


def mutate(folder, name, edit):
    data = json.loads((folder / (name + '.json')).read_text())
    edit(data)
    write(folder, name, data)


def phase(data, n):
    return next(row for row in data['phases'] if row['phase'] == n)


def fixture(folder, case):
    sail, pending = case.endswith('sail'), case.startswith('mount-')
    start, end = (1, 3) if pending else (4, 5)
    kind = 'sail' if sail else 'bike'
    def telemetry(authority):
        moves = [dict(distance_cm=10, turn_degrees=.4, dt=.033, replay=False, flags=8,
                      platform_at=21+i*.033, y=-127 if i < 20 else 127) for i in range(40)]
        return dict(overflow=0, invalid_checkpoints=0, stale_moves_accepted=0, old_accepted_moves=[],
                    stale_moves_rejected=3, rejected_moves=[dict(input_epoch=start, epoch=end, platform_at=101)],
                    checkpoints=8, applied_presentations=20,
                    moves=moves + [dict(distance_cm=10, turn_degrees=.4, dt=.033, replay=True, flags=0)],
                    requests=[dict(enabled=False, kind=kind, request_epoch=1)],
                    actions=[dict(button=b, accepted=True, replay=not authority) for b in ('jump', 'dodge', 'attack', 'wave', 'bike_sprint')])
    guest = dict(case=case, player='guest', authority=False, local=True, epoch=end, activity=0,
                 health=92, health_changes=1, complete=True, bike_equipped=False, sail_equipped=False,
                 parked=case in ('park', 'crash'), walking=True, swimming=False,
                 riding=False, movement_mode=1, telemetry=telemetry(False), peer_telemetry=dict(applied_presentations=20))
    result = guest | dict(passed=True, authority=True, local=False, contacts=1, callbacks=1, outcome=0,
                         health_before=100, start_epoch=start, end_epoch=end, normal_park_and_remount=True,
                         hop_at_contact=True, hop_lift_cm=25, hit_clip='BikeHop', telemetry=telemetry(True),
                         resolved_at=100, since_resolve=2.5, ground_below_water_cm=150,
                         contact_frame_statistics=dict(count=60, min=.016, median=.0167, p95=.018, max=.023), contact_frame_dt=.0167)
    if case in ('park', 'crash'):
        result.update(terminal_at_contact=True, hit_clip='BikeKickstand' if case == 'park' else 'BikeCrash',
                      parked_clip='BikeKickstand' if case == 'park' else 'BikeCrash', wheel_front_gap_cm=1, wheel_rear_gap_cm=-1)
    if pending:
        result.update(pending_refused=True, later_mount=True, contact_at=50, pending_request_at=50.08,
                      due=50.15, contact_epoch=1, later_request_epoch=1,
                      pending_bike_refusals=0 if sail else 1, pending_sail_refusals=1 if sail else 0)
        result['telemetry']['requests'].append(dict(at=50.08, kind=kind, pending=True, locked=False, encounter=False, request_epoch=1))
    if case == 'crash':
        result['crash_site'] = dict(authored_fixed=True, mesh='/Game/Wall', owner_class='JapanWorld', item=3, flat_samples=9, approach_cm=1800)
        result['telemetry']['crashes'] = [dict(mesh='/Game/Wall', owner_class='JapanWorld', item=3, speed=700)]
    order = [0, 2, 30, 31, 32] if pending else [0, 2, 7, 8, 3, 4, 5, 6, 9, 10] if sail else [0, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    if case == 'park': order.remove(9)
    if case == 'crash': order = [0, 2, 10]
    rows = []
    for n in order:
        foot = n in ((0, 2, 30, 32) if pending else (0, 7, 10))
        epoch = (3 if n == 32 else 2 if n == 31 else 1) if pending else (1 if n == 0 else 3 if n == 7 else end if n == 10 else 4 if n in (8, 9) else 2)
        peer = copy.deepcopy(guest) | dict(phase=n, epoch=epoch, default_disabled=True, default_attempt=True,
            menu_sent=True, speed=0, clip='BikeHop' if n == 9 else 'BikeRide', phase_lift_cm=25 if n == 9 else 0,
            activity=0 if foot else 3 if sail else 2, riding=not foot, walking=foot or not sail,
            movement_mode=1 if foot or not sail else 5, bike_equipped=not foot and not sail, sail_equipped=not foot and sail,
            phase_forward_cm=800, phase_turn_degrees=45, sail_start=1, sail_min=0, sail=1,
            phase_began=20, at=25, frame_statistics=dict(count=90, min=.033, median=.0334, p95=.035, max=.04))
        row = copy.deepcopy(peer) | dict(authority=True, local=False, telemetry=telemetry(True),
            frame_statistics=dict(count=180, min=.016, median=.0167, p95=.018, max=.023), owner_observation=peer)
        rows.append(row)
    result['phases'] = rows
    final = dict(case=case, passed=True, contacts=1, callbacks=1, end_epoch=end, health=92, parked=case in ('park','crash'))
    for name, data in [('vehicle-result', result), ('vehicle-observed', guest), ('vehicle-final', final)]: write(folder, name, data)
    return folder


@pytest.fixture
def vehicle(tmp_path):
    return fixture(tmp_path, 'bike')


@pytest.mark.parametrize('case', ['bike', 'sail', 'mount-bike', 'mount-sail', 'park', 'crash'])
def test_native_vehicle_observations_pass(tmp_path, case):
    checks = review.compare_vehicle(fixture(tmp_path, case), case)
    assert all(checks.values()), [k for k, v in checks.items() if not v]


@pytest.mark.parametrize('file,edit', [
    ('vehicle-result', lambda r: r.update(phases=[])),
    ('vehicle-result', lambda r: r['phases'].append(r['phases'][-1])),
    ('vehicle-result', lambda r: phase(r, 0).update(default_disabled=False)),
    ('vehicle-result', lambda r: phase(r, 0)['telemetry'].update(requests=[])),
    ('vehicle-result', lambda r: phase(r, 4)['owner_observation'].update(epoch=99)),
    ('vehicle-result', lambda r: phase(r, 4)['owner_observation'].update(authority=True)),
    ('vehicle-result', lambda r: r['telemetry'].update(moves=[])),
    ('vehicle-result', lambda r: r['telemetry'].update(stale_moves_accepted=1)),
    ('vehicle-result', lambda r: r['telemetry']['rejected_moves'][0].update(input_epoch=1)),
    ('vehicle-result', lambda r: r['telemetry']['rejected_moves'][0].update(platform_at=99)),
    ('vehicle-result', lambda r: r['telemetry'].update(old_accepted_moves=[dict(input_epoch=4, epoch=5, platform_at=101)])),
    ('vehicle-result', lambda r: r.update(hop_lift_cm=0)),
    ('vehicle-result', lambda r: r.update(hop_lift_cm=float('nan'))),
    ('vehicle-result', lambda r: r.update(hop_at_contact=False)),
    ('vehicle-result', lambda r: r.update(parked=True)),
    ('vehicle-result', lambda r: r['telemetry']['moves'][0].update(distance_cm=float('inf'))),
    ('vehicle-result', lambda r: r['telemetry'].update(actions=[])),
    ('vehicle-result', lambda r: phase(r, 3).update(phase_forward_cm=5)),
    ('vehicle-result', lambda r: phase(r, 4).update(phase_turn_degrees=0)),
    ('vehicle-result', lambda r: phase(r, 4).update(phase_turn_degrees=-45)),
    ('vehicle-result', lambda r: phase(r, 3)['owner_observation'].update(phase_forward_cm=5)),
    ('vehicle-result', lambda r: phase(r, 3)['frame_statistics'].update(median=.125, p95=.125, max=.125)),
    ('vehicle-result', lambda r: phase(r, 3)['owner_observation']['frame_statistics'].update(median=.06, p95=.06, max=.06)),
    ('vehicle-result', lambda r: phase(r, 7).update(activity=2, riding=True)),
    ('vehicle-result', lambda r: phase(r, 9).update(movement_mode=3, walking=False)),
    ('vehicle-result', lambda r: phase(r, 9)['owner_observation'].update(movement_mode=3, walking=False)),
    ('vehicle-result', lambda r: phase(r, 9)['frame_statistics'].update(median=.04, p95=.05)),
    ('vehicle-result', lambda r: phase(r, 9)['owner_observation']['frame_statistics'].update(median=.06, p95=.06)),
    ('vehicle-result', lambda r: r['contact_frame_statistics'].update(median=.033, p95=.034)),
    ('vehicle-result', lambda r: r.update(contact_frame_dt=.05)),
    ('vehicle-result', lambda r: r.update(activity=False)),
    ('vehicle-observed', lambda r: r.update(activity=False)),
    ('vehicle-result', lambda r: phase(r, 0).update(epoch=True)),
    ('vehicle-result', lambda r: phase(r, 0)['owner_observation'].update(epoch=True)),
    ('vehicle-result', lambda r: phase(r, 0)['telemetry']['requests'][0].update(request_epoch=True)),
    ('vehicle-result', lambda r: [m.update(platform_at=19) for m in phase(r, 6)['telemetry']['moves']]),
    ('vehicle-result', lambda r: [m.update(platform_at=26) for m in phase(r, 6)['telemetry']['moves']]),
    ('vehicle-result', lambda r: r.update(since_resolve=12.01)),
    ('vehicle-result', lambda r: r.update(contacts=True)),
    ('vehicle-result', lambda r: r.update(start_epoch=True)),
    ('vehicle-observed', lambda r: r['telemetry'].update(checkpoints=0)),
    ('vehicle-observed', lambda r: r['telemetry'].update(invalid_checkpoints=1)),
    ('vehicle-observed', lambda r: r['telemetry'].update(overflow=1)),
    ('vehicle-observed', lambda r: r['telemetry'].update(actions=[])),
    ('vehicle-observed', lambda r: [m.update(replay=False) for m in r['telemetry']['moves']]),
    ('vehicle-observed', lambda r: r['peer_telemetry'].update(applied_presentations=0)),
    ('vehicle-observed', lambda r: r.update(health_changes=2)),
    ('vehicle-observed', lambda r: r.update(health=100)),
    ('vehicle-final', lambda r: r.update(callbacks=2)),
    ('vehicle-final', lambda r: r.update(end_epoch=5+1)),
    ('vehicle-final', lambda r: r.update(health=84)),
])
def test_reject_missing_or_false_vehicle_evidence(vehicle, file, edit):
    mutate(vehicle, file, edit)
    assert not all(review.compare_vehicle(vehicle, 'bike').values())


@pytest.mark.parametrize('edit', [
    lambda r: r.update(ground_below_water_cm=79),
    lambda r: r.update(since_resolve=13),
    lambda r: r.update(walking=False, swimming=False),
    lambda r: phase(r, 5).update(sail_min=1),
    lambda r: phase(r, 5).update(sail=0),
    lambda r: phase(r, 5).update(sail_start=0),
    lambda r: [m.update(y=127) for m in phase(r, 5)['telemetry']['moves']],
    lambda r: [m.update(platform_at=19) for m in phase(r, 5)['telemetry']['moves']],
    lambda r: phase(r, 3).update(movement_mode=1),
    lambda r: phase(r, 5)['owner_observation'].update(sail_min=.9),
])
def test_sail_missing_depth_controls_or_safe_end_fails(tmp_path, edit):
    fixture(tmp_path, 'sail');mutate(tmp_path, 'vehicle-result', edit)
    assert not all(review.compare_vehicle(tmp_path, 'sail').values())


@pytest.mark.parametrize('case', ['mount-bike', 'mount-sail'])
@pytest.mark.parametrize('edit', [
    lambda r: r.update(pending_request_at=r['due']),
    lambda r: r['telemetry']['requests'][-1].update(locked=True),
    lambda r: r['telemetry']['requests'][-1].update(encounter=True),
    lambda r: r['telemetry']['requests'][-1].update(pending=False),
    lambda r: r.update(later_request_epoch=99),
    lambda r: r.update(later_request_epoch=True),
    lambda r: r.update(contact_epoch=True),
    lambda r: r['telemetry']['requests'][-1].update(request_epoch=True),
    lambda r: r.update(pending_bike_refusals=True, pending_sail_refusals=True),
    lambda r: phase(r, 31).update(riding=False),
    lambda r: phase(r, 32).update(walking=False),
])
def test_pending_refusal_requires_cause_window_and_positive_control(tmp_path, case, edit):
    fixture(tmp_path, case);mutate(tmp_path, 'vehicle-result', edit)
    assert not all(review.compare_vehicle(tmp_path, case).values())


@pytest.mark.parametrize('case', ['park', 'crash'])
@pytest.mark.parametrize('edit', [
    lambda r: r.update(terminal_at_contact=False),
    lambda r: r.update(parked_clip='BikeDismount'),
    lambda r: r.update(wheel_front_gap_cm=100),
    lambda r: r.update(end_epoch=6),
    lambda r: r.update(walking=False),
])
def test_terminal_pose_and_single_handoff_required(tmp_path, case, edit):
    fixture(tmp_path, case);mutate(tmp_path, 'vehicle-result', edit)
    assert not all(review.compare_vehicle(tmp_path, case).values())


def test_crash_must_hit_the_authored_fixture(tmp_path):
    fixture(tmp_path, 'crash');mutate(tmp_path, 'vehicle-result', lambda r: r['telemetry']['crashes'][0].update(mesh='/Game/Different'))
    assert not all(review.compare_vehicle(tmp_path, 'crash').values())


@pytest.mark.parametrize('key', ['owner_class', 'item'])
def test_crash_missing_identity_cannot_match_missing_hit_identity(tmp_path, key):
    fixture(tmp_path, 'crash')
    def erase(result):
        result['crash_site'].pop(key)
        result['telemetry']['crashes'][0].pop(key)
    mutate(tmp_path, 'vehicle-result', erase)
    assert not all(review.compare_vehicle(tmp_path, 'crash').values())


def test_unimplemented_cases_fail_closed(vehicle):
    with pytest.raises(ValueError, match='Unsupported'):
        review.compare_vehicle(vehicle, 'unsupported')
