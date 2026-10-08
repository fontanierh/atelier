"""Require the same immutable reaction at the same saved-move boundary on both peers."""
import math
import re

from network_reaction_delivery_review import delivery_outcomes
from network_reaction_review_common import ERROR_COUNTERS, finite
from network_lethal_reaction_review import lethal_reaction_checks


ORIGIN = ('previous_generation', 'previous_stamp', 'end_generation', 'end_stamp',
          'saved_dt', 'edge_before', 'edge_after')
IDENTITY = ('reaction_epoch', 'sequence', 'resolved_generation', 'resolved_stamp',
            'reaction_action', 'payload_digest', 'payload_bytes')


def _checks(host, guest, case, moving):
    checks = {'scheduled_receipts': False}
    if type(case) is not int or not 0 <= case <= 7 or type(moving) is not bool or (moving and case not in (0, 5)):
        return checks, {}
    outcomes = delivery_outcomes(host, guest)
    checks['scheduled_receipts'] = all(r.get('scheduled_reactions') is True and r.get('enabled') is True and
        r.get('complete') is True and r.get('error') == '' and r.get('packed_responses') is True and
        type(r.get('case')) is int and r['case'] == case and r.get('moving') is moving for r in (host, guest))
    checks['scheduled_strict_prediction'] = (type(guest.get('position_corrections')) is int and
        guest['position_corrections'] == 0 and finite(guest.get('largest_correction_cm')) and
        0 <= guest['largest_correction_cm'] < 1 and type(guest.get('rejected_checkpoints')) is int and
        guest['rejected_checkpoints'] == 0)
    checks['scheduled_closed_window'] = all(finite(r.get('response_window_end')) and
        finite(r.get('observed_until')) and r['observed_until'] >= r['response_window_end'] + 1 for r in (host, guest))
    checks['scheduled_no_recovery'] = all(type(r.get('scheduled_stats')) is dict and
        all(type(r['scheduled_stats'].get(k)) is int and r['scheduled_stats'][k] == 0 for k in ERROR_COUNTERS)
        for r in (host, guest))
    for role, r in (('host', host), ('guest', guest)):
        frames = r.get('frame_statistics', {})
        checks['scheduled_' + role + '_frames'] = (type(frames.get('count')) is int and frames['count'] >= 30 and
            all(finite(frames.get(k)) for k in ('median', 'p95')) and
            .9 / 30 <= frames['median'] <= 1.15 / 30 and frames['median'] <= frames['p95'] <= 1.5 / 30)
    checks['scheduled_hold_label'] = (host.get('artificial_send_hold') is (case == 2) and
        type(host.get('held_sends')) is int and (host['held_sends'] > 0 if case == 2 else host['held_sends'] == 0))
    for receipt in (host, guest):
        if any(type(row) is not dict or not finite(row.get('at')) for row in receipt['rows']):
            raise ValueError('Malformed event or event clock')
        stats = receipt['scheduled_stats']
        if any(type(stats.get(k)) is not int or stats[k] < 0 for k in
               ('issued', 'received', 'applied', 'replayed', 'through', 'known')):
            raise ValueError('Malformed journal counters')
    stimuli = host['stimuli']
    if any(type(row) is not dict or not finite(row.get('at')) for row in stimuli):
        raise ValueError('Malformed stimulus')
    hits = [r for r in stimuli if r.get('event') in ('hit', 'zero_impulse_guard', 'host_own_hit')]
    checks['scheduled_stimulus_count'] = len(hits) == (2 if case == 4 else 1)
    if moving:
        checks['scheduled_moving_victim'] = len(hits) == 1 and all(finite(hits[0].get(k)) for k in
            ('pre_hit_speed', 'moving_seconds_before_hit')) and hits[0]['pre_hit_speed'] > 40 and (
            hits[0]['moving_seconds_before_hit'] >= .15 and hits[0].get('pre_hit_input_y') == 127 and guest.get('drive_y') == 127)

    def events(receipt, name):
        return [r for r in receipt['rows'] if r.get('event') == name]

    def index(rows):
        out = {}
        for row in rows:
            for k in ('reaction_epoch', 'sequence', 'resolved_generation', 'payload_bytes'):
                if type(row.get(k)) is not int or not 0 <= row[k] <= 0xffffffff:
                    raise ValueError('Invalid reaction identity')
            if (not row['reaction_epoch'] or not row['sequence'] or not 0 < row['payload_bytes'] <= 256 or
                    not finite(row.get('resolved_stamp')) or row['resolved_stamp'] < 0 or not finite(row.get('at')) or
                    type(row.get('reaction_action')) is not str or
                    not re.fullmatch(r'[0-9a-f]{40}', row.get('payload_digest', ''))):
                raise ValueError('Missing immutable payload identity')
            key = row['reaction_epoch'], row['sequence']
            if key in out:
                raise ValueError('Duplicate non-replayed event')
            out[key] = row
        return out

    issued = index(events(host, 'reaction_issued'))
    received = index(events(guest, 'reaction_received'))
    prepared = index(events(guest, 'reaction_prepared'))
    host_applied = index(events(host, 'reaction_applied'))
    owner_applied = index([r for r in events(guest, 'reaction_applied') if r.get('replay') is False])
    checks['scheduled_roles'] = all(r.get('authority') is True and r.get('local') is False and
        type(r.get('remote_role')) is int and r['remote_role'] == 2 and r.get('replay') is False
        for rows in (issued, host_applied) for r in rows.values()) and all(
        r.get('authority') is False and r.get('local') is True and type(r.get('replay')) is bool
        for rows in (received, prepared, owner_applied) for r in rows.values())
    expected = 0 if case == 7 else 2 if case == 4 else 1
    checks['scheduled_issued_count'] = len(issued) == expected and host['scheduled_stats']['issued'] == expected
    measurements = []
    if case not in (6, 7):
        checks['scheduled_exactly_once'] = (issued.keys() == received.keys() == prepared.keys() == host_applied.keys() == owner_applied.keys() and
            guest['scheduled_stats']['received'] == expected and host['scheduled_stats']['applied'] == expected and
            guest['scheduled_stats']['applied'] == expected)
        identity_valid = boundary_valid = order_valid = bool(issued)
        for key, issue in issued.items():
            group = [mapping.get(key) for mapping in (received, prepared, host_applied, owner_applied)]
            if any(r is None for r in group):
                identity_valid = boundary_valid = order_valid = False
                continue
            arrival, origin, authority, owner = group
            identity_valid &= all(tuple(r.get(k) for k in IDENTITY) == tuple(issue.get(k) for k in IDENTITY) for r in group)
            boundary_valid &= all(type(origin.get(k)) is int and origin[k] >= 0 for k in
                ('previous_generation', 'end_generation', 'edge_before', 'edge_after')) and all(
                    finite(origin.get(k)) for k in ('previous_stamp', 'end_stamp', 'saved_dt'))
            boundary_valid &= (0 <= origin['edge_before'] <= 65535 and 0 <= origin['edge_after'] <= 65535 and
                (origin['edge_after'] - origin['edge_before']) % 65536 <= 16 and
                (origin['previous_generation'], origin['previous_stamp']) < (origin['end_generation'], origin['end_stamp']))
            boundary_valid &= 0 < origin.get('saved_dt', 0) <= .125 and all(
                tuple(r.get(k) for k in ORIGIN) == tuple(origin.get(k) for k in ORIGIN) for r in (authority, owner))
            order_valid &= issue['at'] <= arrival['at'] <= origin['at'] <= owner['at'] <= authority['at']
            measurements.append({'epoch': key[0], 'sequence': key[1], 'delivery_ms': 1000 * (arrival['at'] - issue['at']),
                                 'owner_to_host_ms': 1000 * (authority['at'] - owner['at']),
                                 'origin': {k: origin.get(k) for k in ORIGIN}})
        checks['scheduled_identical_payloads'] = bool(identity_valid)
        checks['scheduled_identical_boundaries'] = bool(boundary_valid)
        checks['scheduled_delivery_order'] = bool(order_valid)
        checks['scheduled_final_markers'] = all(r['scheduled_stats'].get('through') == expected and
            r['scheduled_stats'].get('known') == expected for r in (host, guest))
        replay_valid = True
        for row in events(guest, 'reaction_applied'):
            key = row.get('reaction_epoch'), row.get('sequence')
            replay_valid &= key in issued and all(row.get(k) == issued[key].get(k) for k in IDENTITY)
            replay_valid &= key in prepared and all(row.get(k) == prepared[key].get(k) for k in ORIGIN)
        checks['scheduled_replay_identity'] = bool(replay_valid)
        checks['scheduled_replay_count'] = guest['scheduled_stats']['replayed'] == len([
            r for r in events(guest, 'reaction_applied') if r.get('replay') is True])
        checks['scheduled_apply_prefix'] = all(type(r.get('applied_through')) is int and
            r['applied_through'] == r['sequence'] - 1 for receipt in (host, guest)
            for r in events(receipt, 'reaction_applied'))
        prior = -math.inf
        bound_hits = len(hits) == len(issued)
        for hit in hits:
            bound_hits &= len([r for r in issued.values() if prior < r['at'] <= hit['at']]) == 1
            prior = hit['at']
        checks['scheduled_issue_per_contact'] = bool(bound_hits)
    elif case == 6:
        before = [r for r in stimuli if r.get('event') == 'cancel_before_epoch']
        after = [r for r in stimuli if r.get('event') == 'cancel_after_epoch']
        checks['scheduled_epoch_cancel'] = (len(before) == len(after) == 1 and
            after[0]['epoch'] == before[0]['epoch'] + 1 and not host_applied and
            all(r['scheduled_stats']['through'] == 0 and r['scheduled_stats']['known'] == 0 for r in (host, guest)))
    else:
        own = host['host_own']
        checks['scheduled_local_immediate'] = (not issued and not received and not host_applied and not owner_applied and
            own['scheduled_stats']['issued'] == 0 and len([r for r in hits if r.get('event') == 'host_own_hit']) == 1)
    serialized = events(host, 'serialized')
    captures = events(host, 'capture')
    def witness(name):
        found = [r for r in stimuli if r.get('event') == name]
        return found[0] if len(found) == 1 else {}
    if case == 0:
        before = witness('correction_before_hit')
        checks['scheduled_after_real_correction'] = bool(before) and bool(hits) and before['at'] <= hits[0]['at'] and any(
            r.get('correction') is True and r.get('checkpoint') is True and r['at'] <= before['at'] and
            r.get('stamp') == before.get('checkpoint_stamp') for r in serialized)
    elif case == 1:
        guard = witness('zero_impulse_guard')
        checks['scheduled_guard_stimulus'] = bool(guard) and guard.get('guard') is True and guard.get('outcome') == 3 and (
            finite(guard.get('speed')) and 0 <= guard['speed'] <= .01)
        checks['scheduled_guard_payload'] = bool(issued) and all(r['reaction_action'] in ('GuardHit', 'SwordGuardHit') for r in issued.values())
    elif case == 2:
        after = [r for r in serialized if hits and r['at'] >= hits[0]['at']]
        first = min((r['at'] for r in after), default=-1)
        checks['scheduled_held_captures'] = len({r.get('stamp') for r in captures if hits and
            hits[0]['at'] <= r['at'] <= first and r.get('pending') is True and r.get('captured') is True}) >= 3
    elif case in (3, 5):
        before = witness('prepared_good_ack' if case == 3 else 'prepared_correction_before_hit')
        hit_at = hits[0]['at'] if hits else math.inf
        first_capture = min((r['at'] for r in captures if r['at'] >= hit_at), default=-1)
        stale = [r for r in serialized if hit_at <= r['at'] < first_capture and r.get('correction') is (case == 5)]
        checks['scheduled_stale_response_sent'] = bool(before) and before['at'] <= hit_at and bool(stale)
        if case == 5:
            checks['scheduled_stale_did_not_consume'] = bool(stale) and any(r.get('pending') is True and
                r.get('captured') is False and stale[0]['at'] <= r['at'] < first_capture
                for r in events(host, 'send_timer_advanced'))
    elif case == 4:
        second = witness('second_after_capture')
        checks['scheduled_second_after_capture'] = bool(second) and len(hits) == 2 and any(
            hits[0]['at'] <= r['at'] <= second['at'] <= hits[1]['at'] and r.get('captured') is True for r in captures)
    response_key = ('response_epoch', 'stamp', 'edge', 'correction', 'checkpoint', 'action', 'digest')
    sent = {tuple(r.get(k) for k in response_key): r for r in serialized}
    checks['scheduled_checkpoint_prefix_wire'] = all(type(r.get('reaction_through')) is int and r['reaction_through'] >= 0 and
        (r.get('checkpoint') is True or r['reaction_through'] == 0) for r in serialized) and all(
        r.get('reaction_through') == sent[key].get('reaction_through')
        for r in events(guest, 'received') + events(guest, 'applied')
        if (key := tuple(r.get(k) for k in response_key)) in sent)
    if case not in (6, 7):
        last_apply = max((r['at'] for r in host_applied.values()), default=math.inf)
        epochs = {key[0] for key in issued}
        checks['scheduled_final_checkpoint_accepted'] = any(
            r['at'] >= last_apply and r.get('response_epoch') in epochs and
            type(r.get('reaction_through')) is int and r['reaction_through'] == expected and
            (key := tuple(r.get(k) for k in response_key)) in sent and
            sent[key].get('reaction_through') == expected
            for r in events(guest, 'applied'))
    # Report only: response acceptance time on the same-machine platform clock.
    # This includes a pre-hit response still in flight when the contact resolved.
    # No samples means unknown, never an inferred zero. The global gate above
    # continues to cover every correction, including spawn and earlier responses.
    first_hit = min((r['at'] for r in hits), default=math.inf)
    post_hit = [r['correction_cm'] for r in events(guest, 'accepted')
                if r['at'] >= first_hit and r.get('correction') is True and
                finite(r.get('correction_cm')) and r['correction_cm'] >= 0]
    return checks, outcomes | {'scheduled_reactions': measurements,
        'post_hit_max_cm': max(post_hit, default=None), 'post_hit_correction_samples': len(post_hit),
        'post_hit_scope': 'Accepted after first host contact; includes pre-hit responses still in flight'}


def scheduled_reaction_checks(host, guest, case, moving=False):
    if type(case) is int and case in (8, 9):
        return lethal_reaction_checks(host, guest, case, moving)
    try:
        return _checks(host, guest, case, moving)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {'scheduled_receipts': False}, {}
