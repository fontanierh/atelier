"""Require real host correction provenance and non-vacuous jump replay agreement."""
import math


def jump_replay_checks(server, client, case):
    host, guest = server.get('jump_replay', {}), client.get('jump_replay', {})
    boundary = case % 3
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)
    def exact_int(value, expected):
        return type(value) is int and value == expected
    def same_response(left, right):
        if type(right) is not dict:
            return False
        # UE 5.8 FClientAdjustment uses plain FVector, whose NetSerialize writes
        # doubles without quantization. Keep these exact; do not invent slack.
        return (all(type(left.get(k)) is int and exact_int(right.get(k), left[k])
                    for k in ('epoch', 'edge', 'mode', 'checkpoint_bytes')) and
                left.get('correction') is True and right.get('correction') is True and
                left.get('checkpoint') is True and right.get('checkpoint') is True and
                all(finite(left.get(k)) and finite(right.get(k)) and left[k] == right[k]
                    for k in ('timestamp', 'z', 'vz')))
    selected, moves = guest.get('selected', {}), guest.get('moves', [])
    epoch, target, takeoff, first_air = (guest.get(k) for k in ('epoch', 'target', 'takeoff', 'first_air'))
    timing = type(epoch) is int and epoch > 0 and all(finite(v) and v > 0 for v in (target, takeoff, first_air))
    timing = timing and first_air > takeoff and ((target < takeoff and takeoff-target < .1) if boundary == 0 else target == (takeoff if boundary == 1 else first_air))
    source = (type(selected) is dict and selected and type(host.get('responses')) is list and any(same_response(selected, row) for row in host['responses']) and
              exact_int(selected.get('epoch'), epoch) and selected.get('timestamp') == target and
              selected.get('checkpoint') is True and type(selected.get('checkpoint_bytes')) is int and selected['checkpoint_bytes'] > 0)
    mode = selected.get('mode') if type(selected) is dict else None
    source = bool(source and exact_int(mode, 1 if boundary == 0 else 3) and finite(selected.get('vz')) and
                  (abs(selected['vz']) < .01 if boundary == 0 else selected['vz'] > 0))
    coverage = type(moves) is list and len(moves) >= 3
    agreement = coverage
    prior = target if finite(target) else float('inf')
    for row in moves if type(moves) is list else []:
        if not isinstance(row, dict):
            coverage = agreement = False
            continue
        stamp, dt = row.get('timestamp'), row.get('dt')
        valid = finite(stamp) and finite(dt) and 0 < dt <= .125 and stamp > prior and abs(stamp-prior-dt) < .00002 and exact_int(row.get('epoch'), epoch) and exact_int(row.get('mode'), 3)
        coverage &= valid
        if finite(stamp):
            prior = stamp
        values = [row.get(k) for k in ('original_z', 'replayed_z', 'original_vz', 'replayed_vz')]
        agreement &= all(finite(v) for v in values) and abs(values[0]-values[1]) <= 1 and abs(values[2]-values[3]) <= 1
    if coverage:
        coverage = moves[0]['timestamp'] == (takeoff if boundary == 0 else first_air) if boundary < 2 else moves[0]['timestamp'] > first_air
    first_force, last_force = host.get('first_force_seconds'), host.get('last_force_seconds')
    window = (host.get('window_closed') is True and exact_int(host.get('forced_epoch'), epoch) and
              type(host.get('forced_count')) is int and 3 <= host['forced_count'] <= 128 and
              finite(first_force) and finite(last_force) and 0 <= first_force < last_force < 3)
    checks = {
        'jump_replay_enabled': host.get('enabled') is True and guest.get('enabled') is True and exact_int(host.get('case'), case) and exact_int(guest.get('case'), case),
        'jump_replay_completed': guest.get('complete') is True and guest.get('replayed') is True and guest.get('error') == '' and exact_int(guest.get('applications'), 1),
        'jump_replay_boundary': bool(timing),
        'jump_replay_host_response': source,
        'jump_replay_scoped_window': bool(window),
        'jump_replay_coverage': bool(coverage),
        'jump_replay_agreement': bool(agreement),
    }
    if case >= 3:
        ack = guest.get('ack', {})
        stamp = ack.get('timestamp') if type(ack) is dict else None
        provenance = (type(ack) is dict and ack.get('correction') is False and exact_int(ack.get('epoch'), epoch) and
                      type(ack.get('edge')) is int and finite(stamp) and finite(target) and stamp > target and
                      type(host.get('responses')) is list and any(type(row) is dict and row.get('correction') is False and
                          exact_int(row.get('epoch'), epoch) and exact_int(row.get('edge'), ack['edge']) and
                          finite(row.get('timestamp')) and row['timestamp'] == stamp for row in host['responses']))
        checks['jump_replay_ack_order'] = bool(provenance and guest.get('ack_applied') is True and
            guest.get('pending_before_ack') is True and type(guest.get('saved_before_ack')) is int and guest['saved_before_ack'] >= 3)
        first_saved = guest.get('first_saved_before_ack')
        later_host = [row['timestamp'] for row in host.get('responses', [])
                      if type(row) is dict and exact_int(row.get('epoch'), epoch) and
                      finite(row.get('timestamp')) and finite(target) and row['timestamp'] > target] if type(host.get('responses')) is list else []
        # Bind the saved-move anchor to the next real host response as well as
        # the guest's pre-ACK state, so a self-reported later anchor cannot pass.
        checks['jump_replay_ack_coverage'] = bool(provenance and finite(first_saved) and target < first_saved <= stamp and
            later_host and first_saved == min(later_host) and type(moves) is list and moves and
            type(moves[0]) is dict and moves[0].get('timestamp') == first_saved and
            any(type(row) is dict and row.get('timestamp') == stamp for row in moves))
    return checks
