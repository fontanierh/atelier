"""Acceptance from native vehicle observations, never control-file intentions.

Certifies only the selected motion, pending-request or terminal-park route.
Each route needs its own native receipt before enabling the default-off rule.
"""
import json
import math


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int


def frame_rate(row, fps):
    stats = row.get('frame_statistics', {})
    return (integer(stats.get('count')) and stats['count'] >= 30 and
            all(finite(stats.get(k)) for k in ('min', 'max', 'median', 'p95')) and
            0 < stats['min'] <= stats['median'] <= stats['p95'] <= stats['max'] <= .1251 and
            .9 / fps <= stats['median'] <= 1.15 / fps and stats['p95'] <= 1.5 / fps)


def compare_vehicle(folder, case):
    if case == 'clock-bike':
        from network_vehicle_clock_review import compare_clock_bike
        return compare_clock_bike(folder)
    if case not in ('bike', 'sail', 'mount-bike', 'mount-sail', 'park', 'crash'):
        raise ValueError('Unsupported native vehicle case')
    def read(name):
        data = json.loads((folder / (name + '.json')).read_text())
        if data.get('error'):
            raise RuntimeError(f'{name}: {data["error"]}')
        return data
    result, guest, final = (read(n) for n in ('vehicle-result', 'vehicle-observed', 'vehicle-final'))
    rows = result.get('phases', [])
    phases = {r.get('phase'): r for r in rows}
    pending = case.startswith('mount-')
    order = [0, 2, 30, 31, 32] if pending else [0, 2, 3, 4, 5, 6, 7, 8, 9, 10] if case == 'bike' else [0, 2, 7, 8, 3, 4, 5, 6, 9, 10]
    if case == 'park':
        order = [0, 2, 3, 4, 5, 6, 7, 8, 10]
    elif case == 'crash':
        order = [0, 2, 10]
    checks = {
        'vehicle_case': result.get('case') == guest.get('case') == final.get('case') == case,
        'vehicle_complete': result.get('passed') is True and result.get('complete') is True and guest.get('complete') is True and final.get('passed') is True,
        'vehicle_phase_coverage': [r.get('phase') for r in rows] == order and len(rows) == len(phases),
        'vehicle_identity': isinstance(result.get('player'), str) and bool(result['player']) and result['player'] == guest.get('player'),
        'vehicle_exactly_once': all(integer(r.get(k)) for r, k in ((result, 'contacts'), (result, 'callbacks'), (final, 'contacts'), (final, 'callbacks'), (result, 'health_changes'), (guest, 'health_changes'), (result, 'outcome'))) and result.get('contacts') == result.get('callbacks') == final.get('contacts') == final.get('callbacks') == result.get('health_changes') == guest.get('health_changes') == 1 and result.get('outcome') == 0,
        'vehicle_damage': finite(result.get('health_before')) and finite(result.get('health')) and abs(result['health_before'] - result['health'] - 8) < .01 and result['health'] == guest.get('health') == final.get('health'),
        'vehicle_epoch_handoff': integer(result.get('start_epoch')) and result['start_epoch'] > 0 and integer(result.get('end_epoch')) and result['end_epoch'] > result['start_epoch'] and result['end_epoch'] == result.get('epoch') == guest.get('epoch') == final.get('end_epoch'),
        'vehicle_on_foot': all(integer(r.get('activity')) for r in (result, guest)) and result.get('activity') == guest.get('activity') == 0 and all(r.get('bike_equipped') is False and r.get('sail_equipped') is False for r in (result, guest)),
        'vehicle_normal_park': case == 'crash' or result.get('normal_park_and_remount') is True,
        'vehicle_recovery_deadline': pending or (finite(result.get('since_resolve')) and 2 <= result['since_resolve'] <= 12),
    }
    for phase in order:
        row = phases.get(phase, {})
        peer = row.get('owner_observation', {})
        checks[f'vehicle_phase_{phase}_replicated'] = (
            row.get('player') == peer.get('player') == result.get('player') and
            row.get('authority') is True and row.get('local') is False and
            peer.get('authority') is False and peer.get('local') is True and
            integer(row.get('epoch')) and integer(peer.get('epoch')) and row.get('epoch') == peer.get('epoch') and row.get('activity') == peer.get('activity') and peer.get('phase') == phase)
    sail = case.endswith('sail')
    activity, mode = (3, 5) if sail else (2, 1)
    for phase in order:
        row = phases.get(phase, {})
        foot = phase in ((0, 2, 30, 32) if pending else (0, 7, 10))
        for label, observed in (('host', row), ('guest', row.get('owner_observation', {}))):
            swimming = sail and phase == 10 and observed.get('swimming') is True
            checks[f'vehicle_phase_{phase}_{label}_state'] = (
                integer(observed.get('activity')) and observed['activity'] == (0 if foot else activity) and
                observed.get('riding') is (not foot) and integer(observed.get('movement_mode')) and
                observed['movement_mode'] == (6 if swimming else 1 if foot else mode) and
                observed.get('walking') is (not swimming and (foot or not sail)) and
                observed.get('bike_equipped') is (not foot and not sail) and observed.get('sail_equipped') is (not foot and sail))
            if phase in (3, 4, 5, 9, 10, 32):
                checks[f'vehicle_phase_{phase}_{label}_fps'] = frame_rate(observed, 60 if label == 'host' else 30)
    park_phase = 32 if pending else 7
    if case != 'crash':
        parked_row = phases.get(park_phase, {})
        checks['vehicle_normal_park'] &= all(r.get('activity') == 0 and r.get('riding') is False and r.get('walking') is True and r.get('movement_mode') == 1 for r in (parked_row, parked_row.get('owner_observation', {})))
    checks['vehicle_contact_fps'] = (frame_rate({'frame_statistics': result.get('contact_frame_statistics', {})}, 60) and
        finite(result.get('contact_frame_dt')) and .9 / 60 <= result['contact_frame_dt'] <= 1.5 / 60)
    host_telemetry = result.get('telemetry', {})
    checks['vehicle_no_stale_acceptance'] = (integer(host_telemetry.get('stale_moves_accepted')) and host_telemetry['stale_moves_accepted'] == 0 and host_telemetry.get('old_accepted_moves') == [])
    if not pending:
        rejected = host_telemetry.get('rejected_moves', [])
        checks['vehicle_stale_epoch_rejection'] = (finite(result.get('resolved_at')) and
            any(integer(r.get('input_epoch')) and r['input_epoch'] == result.get('start_epoch') and
                r.get('epoch') == result.get('end_epoch') and finite(r.get('platform_at')) and
                r['platform_at'] > result['resolved_at'] for r in rejected))
    setup = phases.get(0, {})
    for label, row in (('host', setup), ('guest', setup.get('owner_observation', {}))):
        requests = row.get('telemetry', {}).get('requests', [])
        checks[f'vehicle_default_off_{label}'] = row.get('default_disabled') is True and row.get('default_attempt') is True and row.get('activity') == 0
        if label == 'host':
            checks['vehicle_default_off_host_request'] = any(integer(r.get('request_epoch')) and r['request_epoch'] == setup.get('epoch') and r.get('enabled') is False and r.get('kind') == ('bike' if case in ('park', 'crash') else case.removeprefix('mount-')) for r in requests)
    if case == 'crash':
        site = result.get('crash_site', {})
        crashes = result.get('telemetry', {}).get('crashes', [])
        checks['vehicle_authored_crash_site'] = site.get('authored_fixed') is True and isinstance(site.get('owner_class'), str) and bool(site['owner_class']) and integer(site.get('item')) and isinstance(site.get('mesh'), str) and bool(site['mesh']) and site.get('flat_samples') == 9 and site.get('approach_cm') == 1800
        checks['vehicle_real_crash_contact'] = (len(crashes) == 1 and finite(crashes[0].get('speed')) and crashes[0]['speed'] > 450 and all(crashes[0].get(k) == site.get(k) for k in ('owner_class', 'mesh', 'item')))
        checks['vehicle_crash_terminal'] = result.get('terminal_at_contact') is True and result.get('hit_clip') == result.get('parked_clip') == 'BikeCrash' and result.get('end_epoch') == result.get('start_epoch', -1) + 1
        checks['vehicle_crash_supported_pose'] = all(r.get('parked') is True for r in (result, guest, final)) and all(finite(result.get(k)) and abs(result[k]) <= 5 for k in ('wheel_front_gap_cm', 'wheel_rear_gap_cm'))
        checks['vehicle_crash_safe_end'] = result.get('walking') is True and guest.get('walking') is True
        return checks
    if pending:
        counter = 'pending_sail_refusals' if case == 'mount-sail' else 'pending_bike_refusals'
        times = [result.get(key) for key in ('contact_at', 'pending_request_at', 'due')]
        checks['vehicle_pending_refusal'] = (result.get('pending_refused') is True and integer(result.get(counter)) and result[counter] == 1 and
            all(finite(t) for t in times) and times[0] <= times[1] < times[2])
        matching = [r for r in result.get('telemetry', {}).get('requests', []) if
            r.get('at') == result.get('pending_request_at') and r.get('kind') == case.removeprefix('mount-')]
        checks['vehicle_pending_exclusive_cause'] = (len(matching) == 1 and matching[0].get('pending') is True and
            matching[0].get('locked') is False and matching[0].get('encounter') is False and
            integer(matching[0].get('request_epoch')) and integer(result.get('contact_epoch')) and matching[0]['request_epoch'] == result['contact_epoch'])
        mounted = phases.get(31, {})
        checks['vehicle_after_hit_mount_control'] = (result.get('later_mount') is True and
            integer(result.get('later_request_epoch')) and result['later_request_epoch'] == result.get('contact_epoch') and
            mounted.get('riding') is True and mounted.get('owner_observation', {}).get('riding') is True and
            mounted.get('epoch', -1) > result.get('contact_epoch', 0))
        return checks
    for label, row in (('host', result), ('guest', guest)):
        telemetry = row.get('telemetry', {})
        moves = telemetry.get('moves', [])
        checks[f'vehicle_telemetry_{label}'] = (telemetry.get('overflow') == 0 and telemetry.get('invalid_checkpoints') == 0 and telemetry.get('stale_moves_accepted') == 0 and len(moves) >= 30 and all(
            finite(m.get('distance_cm')) and finite(m.get('turn_degrees')) and finite(m.get('dt')) and 0 < m['dt'] <= .1251 for m in moves))
        live = [m for m in moves if m.get('replay') is False]
        forward = phases.get(3, {})
        turn = phases.get(4, {})
        if label == 'guest':
            forward, turn = (r.get('owner_observation', {}) for r in (forward, turn))
        checks[f'vehicle_forward_{label}'] = finite(forward.get('phase_forward_cm')) and forward['phase_forward_cm'] >= 200
        checks[f'vehicle_signed_turn_{label}'] = finite(turn.get('phase_turn_degrees')) and turn['phase_turn_degrees'] >= 10
    owner = guest.get('telemetry', {})
    replays = [m for m in owner.get('moves', []) if m.get('replay') is True]
    checks['vehicle_checkpoint_replay'] = owner.get('checkpoints', 0) > 0 and len(replays) > 0 and any(abs(m.get('turn_degrees', 0)) > .1 for m in replays)
    checks['vehicle_remote_presentation'] = guest.get('peer_telemetry', {}).get('applied_presentations', 0) >= 10
    brake = phases.get(6, {})
    brake_moves = [m for m in brake.get('telemetry', {}).get('moves', []) if
        m.get('replay') is False and finite(m.get('platform_at')) and finite(brake.get('phase_began')) and finite(brake.get('at')) and
        brake['phase_began'] <= m['platform_at'] <= brake['at']]
    checks['vehicle_menu_brake'] = (brake.get('menu_sent') is True and brake.get('owner_observation', {}).get('menu_sent') is True and finite(brake.get('speed')) and abs(brake['speed']) < .1 and any(m.get('flags', 0) & 8 for m in brake_moves))
    if case in ('bike', 'park'):
        actions = result.get('telemetry', {}).get('actions', [])
        checks['vehicle_bike_actions'] = ({'dodge', 'attack', 'wave', 'bike_sprint'} | ({'jump'} if case == 'bike' else set())) <= {a.get('button') for a in actions if a.get('accepted') is True}
        checks['vehicle_action_replay'] = any(a.get('accepted') is True and a.get('replay') is True for a in owner.get('actions', []))
        if case == 'park':
            checks['vehicle_park_terminal'] = result.get('terminal_at_contact') is True and result.get('hit_clip') == result.get('parked_clip') == 'BikeKickstand' and result.get('end_epoch') == result.get('start_epoch', -1) + 1
            checks['vehicle_terminal_ground_pose'] = (all(r.get('parked') is True for r in (result, guest, final)) and all(finite(result.get(k)) and abs(result[k]) <= 5 for k in ('wheel_front_gap_cm', 'wheel_rear_gap_cm')))
            checks['vehicle_terminal_safe_end'] = result.get('walking') is True and guest.get('walking') is True
            return checks
        checks['vehicle_hop_strike'] = result.get('hop_at_contact') is True and phases.get(9, {}).get('clip') == 'BikeHop' and finite(phases.get(9, {}).get('phase_lift_cm')) and phases[9]['phase_lift_cm'] > 5 and result.get('hit_clip') == 'BikeHop' and finite(result.get('hop_lift_cm')) and result['hop_lift_cm'] > 5
        checks['vehicle_hop_stowed'] = result.get('parked') is False and guest.get('parked') is False and final.get('parked') is False
        checks['vehicle_safe_landing'] = result.get('walking') is True and guest.get('walking') is True
    else:
        reverse = phases.get(5, {})
        for label, row in (('host', reverse), ('guest', reverse.get('owner_observation', {}))):
            start, low, end = (row.get(k) for k in ('sail_start', 'sail_min', 'sail'))
            began, at = row.get('phase_began'), row.get('at')
            moves = [m for m in row.get('telemetry', {}).get('moves', []) if
                     finite(began) and finite(at) and finite(m.get('platform_at')) and began <= m['platform_at'] <= at and m.get('replay') is False]
            checks[f'vehicle_sail_controls_{label}'] = (all(finite(x) for x in (start, low, end)) and start >= .8 and low <= .2 and end >= .8 and
                any(finite(m.get('y')) and m['y'] < -15 for m in moves) and any(finite(m.get('y')) and m['y'] > 15 for m in moves))
        checks['vehicle_deep_water_strike'] = finite(result.get('ground_below_water_cm')) and result['ground_below_water_cm'] >= 80
        checks['vehicle_safe_water_end'] = (finite(result.get('since_resolve')) and 0 <= result['since_resolve'] <= 12 and ((result.get('swimming') is True and guest.get('swimming') is True) or (result.get('walking') is True and guest.get('walking') is True)))
    return checks
