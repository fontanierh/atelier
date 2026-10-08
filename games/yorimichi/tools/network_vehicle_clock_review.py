"""Require a real moving-bike outage and the ordinary clock recovery on both peers."""
import json
import math

from network_vehicle_review import finite, frame_rate, integer


def compare_clock_bike(folder):
    def read(name):
        row = json.loads((folder / (name + '.json')).read_text())
        if row.get('error'):
            raise RuntimeError(f'{name}: {row["error"]}')
        return row

    host, guest, final = (read(n) for n in ('vehicle-result', 'vehicle-observed', 'vehicle-final'))
    rows = host.get('phases', [])
    phases = {r.get('phase'): r for r in rows}
    before = phases.get(40, {})
    owner_before = before.get('owner_observation', {})
    start, end = host.get('start_epoch'), host.get('end_epoch')

    def count(row, key, n):
        return integer(row.get(key)) and row[key] == n

    def bounded(row, key, low, high):
        return finite(row.get(key)) and low <= row[key] <= high

    checks = {
        'vehicle_clock_case': all(r.get('case') == 'clock-bike' for r in (host, guest, final)),
        'vehicle_clock_complete': host.get('passed') is True and host.get('complete') is True and guest.get('complete') is True and final.get('passed') is True,
        'vehicle_clock_phase_coverage': [r.get('phase') for r in rows] == [0, 2, 40, 41],
        'vehicle_clock_identity': isinstance(host.get('player'), str) and bool(host['player']) and guest.get('player') == host['player'],
        'vehicle_clock_one_epoch': integer(start) and start > 0 and integer(end) and end == start + 1 and host.get('epoch') == guest.get('epoch') == final.get('end_epoch') == end,
        'vehicle_clock_real_outage': bounded(guest, 'hitch_seconds', 1.05, 1.15) and bounded(guest, 'drive_seconds', .5, 5) and
            finite(guest.get('hitch_speed')) and guest['hitch_speed'] > 200 and count(guest, 'hitch_input_y', 127) and guest.get('hitch_epoch') == start,
        'vehicle_clock_recovery_observed': finite(guest.get('at')) and finite(guest.get('hitch_ended')) and .85 <= guest['at'] - guest['hitch_ended'] <= 8,
        'vehicle_clock_no_strike': all(count(r, k, 0) for r in (host, guest, final) for k in ('contacts', 'callbacks')),
        'vehicle_clock_health_unchanged': finite(host.get('health_before')) and host['health_before'] > 0 and
            host.get('health') == guest.get('health') == final.get('health') == host['health_before'] and
            count(host, 'health_changes', 0) and count(guest, 'health_changes', 0),
        'vehicle_clock_no_stale_accept': count(host.get('telemetry', {}), 'stale_moves_accepted', 0) and host.get('telemetry', {}).get('old_accepted_moves') == [],
        'vehicle_clock_old_epoch_probe': count(guest, 'stale_probe_sent', 1) and count(host, 'stale_probe_rejected', 1) and
            bounded(host, 'stale_probe_root_cm', 0, 0) and bounded(host, 'stale_probe_clock_delta', 0, 0),
        'clock_ground_handoff_stationary': count(host, 'clock_arrivals', 1) and
            all(bounded(host, k, 0, .01) for k in ('neutral_path_cm', 'clock_arrival_drift_cm')),
        'vehicle_clock_neutral_wait': bounded(host, 'neutral_max_acceleration', 0, 0) and
            integer(host.get('neutral_late_ground_frames')) and host['neutral_late_ground_frames'] > 0 and
            bounded(host, 'neutral_late_max_speed', 0, .999),
    }
    setup = phases.get(0, {})
    checks['vehicle_clock_default_off'] = all(r.get('default_disabled') is True and r.get('default_attempt') is True and count(r, 'activity', 0)
        for r in (setup, setup.get('owner_observation', {})))
    checks['vehicle_clock_host_refusal'] = any(r.get('kind') == 'bike' and r.get('enabled') is False and
        integer(r.get('request_epoch')) and r['request_epoch'] == setup.get('epoch')
        for r in setup.get('telemetry', {}).get('requests', []))
    for phase in (0, 2, 40, 41):
        row = phases.get(phase, {})
        peer = row.get('owner_observation', {})
        checks[f'vehicle_clock_phase_{phase}_replicated'] = (row.get('player') == peer.get('player') == host.get('player') and
            row.get('authority') is True and row.get('local') is False and peer.get('authority') is False and peer.get('local') is True and
            integer(row.get('epoch')) and integer(peer.get('epoch')) and row['epoch'] == peer['epoch'] and row.get('activity') == peer.get('activity') and peer.get('phase') == phase)
    for label, row, moving in (('host', host, before), ('guest', guest, owner_before)):
        checks[f'vehicle_clock_{label}_moving_bike'] = (count(moving, 'activity', 2) and moving.get('riding') is True and
            moving.get('bike_equipped') is True and moving.get('walking') is True and count(moving, 'movement_mode', 1) and
            moving.get('epoch') == start and finite(moving.get('speed')) and moving['speed'] > 200 and
            frame_rate(moving, 60 if label == 'host' else 30))
        checks[f'vehicle_clock_{label}_reset'] = count(row, 'timeout_corrections', 1) and count(row, 'time_budget_corrections', 0) and count(row, 'time_budget_rejected', 0)
        checks[f'vehicle_clock_{label}_foot'] = (count(row, 'activity', 0) and count(row, 'movement_mode', 1) and row.get('walking') is True and
            row.get('riding') is False and row.get('bike_equipped') is False and row.get('sail_equipped') is False)
        checks[f'vehicle_clock_{label}_cleared_latch'] = all(count(row, k, 0) for k in ('input_x', 'input_y', 'input_flags'))
        checks[f'vehicle_clock_{label}_parked'] = row.get('parked') is True and all(bounded(row, k, -5, 5) for k in ('wheel_front_gap_cm', 'wheel_rear_gap_cm'))
        checks[f'vehicle_clock_{label}_control'] = (integer(row.get('control_start_epoch')) and row['control_start_epoch'] > 0 and
            row.get('control_epoch') == row['control_start_epoch'] and row.get('control_riding') is True and count(row, 'control_timeouts', 0))
        checks[f'vehicle_clock_{label}_strict_prediction'] = count(row, 'position_corrections_over_1cm', 0) and bounded(row, 'largest_correction_cm', 0, .999999)
    checks['vehicle_clock_parked_final'] = final.get('parked') is True
    positions = [[r.get('parked_' + axis) for axis in 'xyz'] for r in (host, guest)]
    quaternions = [[r.get('parked_q' + axis) for axis in 'xyzw'] for r in (host, guest)]
    checks['vehicle_clock_parked_position'] = (all(finite(x) for p in positions for x in p) and math.dist(*positions) <= 1)
    valid_rotations = all(finite(x) for q in quaternions for x in q) and all(abs(sum(x*x for x in q)-1) <= .001 for q in quaternions)
    checks['vehicle_clock_parked_rotation'] = valid_rotations and 2*math.degrees(math.acos(min(1, abs(sum(a*b for a, b in zip(*quaternions))) /
        math.sqrt(math.prod(sum(x*x for x in q) for q in quaternions))))) <= 1
    return checks
