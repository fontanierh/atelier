import copy
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def review(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'tools'))
    return importlib.import_module('network_vehicle_review')


@pytest.fixture
def receipt(tmp_path):
    common = dict(case='clock-bike', player='guest', epoch=3, activity=0,
        movement_mode=1, walking=True, riding=False, bike_equipped=False, sail_equipped=False,
        complete=True, health=100, health_changes=0, contacts=0, callbacks=0,
        timeout_corrections=1, time_budget_corrections=0, time_budget_rejected=0,
        position_corrections_over_1cm=0, largest_correction_cm=.01,
        input_x=0, input_y=0, input_flags=0, parked=True,
        parked_x=10, parked_y=20, parked_z=30, parked_qx=0, parked_qy=0, parked_qz=0, parked_qw=1,
        wheel_front_gap_cm=0, wheel_rear_gap_cm=0,
        control_start_epoch=2, control_epoch=2, control_riding=True, control_timeouts=0)
    guest = common | dict(authority=False, local=True, hitch_seconds=1.051, hitch_ended=101.051,
        at=102, drive_seconds=1.4, hitch_speed=300, hitch_input_y=127, hitch_epoch=2, stale_probe_sent=1)
    host = common | dict(authority=True, local=False, passed=True, start_epoch=2, end_epoch=3,
        health_before=100, stale_probe_rejected=1, stale_probe_root_cm=0, stale_probe_clock_delta=0,
        clock_arrivals=1, neutral_path_cm=0, clock_arrival_drift_cm=0, neutral_max_acceleration=0,
        neutral_late_ground_frames=5, neutral_late_max_speed=0,
        telemetry=dict(stale_moves_accepted=0, old_accepted_moves=[]))
    rows = []
    for n in (0, 2, 40, 41):
        riding = n in (2, 40)
        peer = copy.deepcopy(guest) | dict(phase=n, epoch=1 if n == 0 else 3 if n == 41 else 2,
            activity=2 if riding else 0, riding=riding, bike_equipped=riding,
            default_disabled=True, default_attempt=True, speed=300 if n == 40 else 0,
            frame_statistics=dict(count=40, min=.033, median=.0334, p95=.035, max=.04))
        row = copy.deepcopy(peer) | dict(authority=True, local=False, owner_observation=peer,
            telemetry=dict(requests=[dict(kind='bike', enabled=False, request_epoch=1)]),
            frame_statistics=dict(count=80, min=.016, median=.0167, p95=.018, max=.023))
        rows.append(row)
    host['phases'] = rows
    final = dict(case='clock-bike', passed=True, contacts=0, callbacks=0, end_epoch=3, health=100, parked=True)
    for name, row in [('vehicle-result', host), ('vehicle-observed', guest), ('vehicle-final', final)]:
        (tmp_path / (name + '.json')).write_text(json.dumps(row))
    return tmp_path


def change(folder, name, edit):
    file = folder / (name + '.json')
    row = json.loads(file.read_text())
    edit(row)
    file.write_text(json.dumps(row))


def test_moving_bike_timeout_evidence(review, receipt):
    checks = review.compare_vehicle(receipt, 'clock-bike')
    assert all(checks.values()), [key for key, passed in checks.items() if not passed]


@pytest.mark.parametrize('name,edit', [
    ('vehicle-observed', lambda r: r.update(hitch_seconds=0)),
    ('vehicle-observed', lambda r: r.update(hitch_seconds=1.2)),
    ('vehicle-observed', lambda r: r.update(hitch_seconds=float('nan'))),
    ('vehicle-observed', lambda r: r.update(hitch_speed=0)),
    ('vehicle-observed', lambda r: r.update(hitch_input_y=0)),
    ('vehicle-observed', lambda r: r.update(hitch_epoch=1)),
    ('vehicle-observed', lambda r: r.update(drive_seconds=.2)),
    ('vehicle-observed', lambda r: r.update(at=101.5)),
    ('vehicle-observed', lambda r: r.update(epoch=4)),
    ('vehicle-result', lambda r: r.update(end_epoch=4, epoch=4)),
    ('vehicle-result', lambda r: r.update(clock_arrivals=2)),
    ('vehicle-result', lambda r: r.update(clock_arrivals=True)),
    ('vehicle-result', lambda r: r.update(neutral_path_cm=.011)),
    ('vehicle-result', lambda r: r.update(clock_arrival_drift_cm=.011)),
    ('vehicle-result', lambda r: r.update(neutral_max_acceleration=1)),
    ('vehicle-result', lambda r: r.update(neutral_late_ground_frames=0)),
    ('vehicle-result', lambda r: r.update(neutral_late_max_speed=2)),
    ('vehicle-result', lambda r: r.update(timeout_corrections=2)),
    ('vehicle-observed', lambda r: r.update(timeout_corrections=0)),
    ('vehicle-result', lambda r: r.update(time_budget_corrections=1)),
    ('vehicle-result', lambda r: r.update(time_budget_rejected=1)),
    ('vehicle-result', lambda r: r['telemetry'].update(stale_moves_accepted=1)),
    ('vehicle-result', lambda r: r['telemetry'].update(old_accepted_moves=[{'epoch': 2}])),
    ('vehicle-result', lambda r: r.update(stale_probe_rejected=0)),
    ('vehicle-observed', lambda r: r.update(stale_probe_sent=0)),
    ('vehicle-result', lambda r: r.update(stale_probe_root_cm=.01)),
    ('vehicle-result', lambda r: r.update(stale_probe_clock_delta=.01)),
    ('vehicle-result', lambda r: r.update(phases=[])),
    ('vehicle-result', lambda r: r['phases'].pop(2)),
    ('vehicle-result', lambda r: r['phases'][0]['telemetry'].update(requests=[])),
    ('vehicle-result', lambda r: r['phases'][2]['owner_observation'].update(speed=0)),
    ('vehicle-result', lambda r: r['phases'][2]['owner_observation'].update(player='host')),
    ('vehicle-result', lambda r: r['phases'][2]['frame_statistics'].update(median=.04, p95=.05, max=.05)),
    ('vehicle-result', lambda r: r['phases'][2]['owner_observation']['frame_statistics'].update(count=2)),
    ('vehicle-observed', lambda r: r.update(input_y=127)),
    ('vehicle-result', lambda r: r.update(contacts=1)),
    ('vehicle-final', lambda r: r.update(callbacks=1)),
    ('vehicle-observed', lambda r: r.update(health=92)),
    ('vehicle-result', lambda r: r.update(control_epoch=3)),
    ('vehicle-observed', lambda r: r.update(control_riding=False)),
    ('vehicle-observed', lambda r: r.update(control_timeouts=1)),
    ('vehicle-observed', lambda r: r.update(parked=False)),
    ('vehicle-observed', lambda r: r.update(parked_x=11.01)),
    ('vehicle-observed', lambda r: r.update(parked_x=float('inf'))),
    ('vehicle-observed', lambda r: r.update(parked_qw=0)),
    ('vehicle-observed', lambda r: r.update(parked_qw=.999847695, parked_qz=.017452406)),
    ('vehicle-observed', lambda r: r.update(wheel_front_gap_cm=5.01)),
    ('vehicle-observed', lambda r: r.update(position_corrections_over_1cm=1)),
    ('vehicle-observed', lambda r: r.update(largest_correction_cm=1.01)),
    ('vehicle-observed', lambda r: r.pop('hitch_ended')),
])
def test_reject_unproven_bike_clock_recovery(review, receipt, name, edit):
    change(receipt, name, edit)
    assert not all(review.compare_vehicle(receipt, 'clock-bike').values())


def test_equivalent_quaternion_sign_passes(review, receipt):
    change(receipt, 'vehicle-observed', lambda r: r.update(parked_qw=-1))
    assert all(review.compare_vehicle(receipt, 'clock-bike').values())


@pytest.mark.parametrize('count', [0, 5])
def test_natural_stale_rejects_are_observation_only(review, receipt, count):
    change(receipt, 'vehicle-result', lambda r: r.update(stale_epoch_moves=count))
    assert all(review.compare_vehicle(receipt, 'clock-bike').values())
