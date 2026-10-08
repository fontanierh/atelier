"""Real moving-death epoch replacement; no position-error exemption."""
import math
import re

from network_reaction_delivery_review import delivery_outcomes
from network_reaction_review_common import ERROR_COUNTERS, finite


def _checks(host, guest, case, moving):
    outcomes = delivery_outcomes(host, guest)
    pending = int(case == 9)
    checks = {'lethal_receipts': type(case) is int and case in (8, 9) and moving is True and all(
        r.get('scheduled_reactions') is True and r.get('enabled') is True and r.get('complete') is True and
        r.get('error') == '' and r.get('packed_responses') is True and r.get('case') == case and r.get('moving') is True
        for r in (host, guest))}
    checks['scheduled_strict_prediction'] = (type(guest.get('position_corrections')) is int and
        guest['position_corrections'] == 0 and finite(guest.get('largest_correction_cm')) and
        0 <= guest['largest_correction_cm'] < 1 and type(guest.get('rejected_checkpoints')) is int and guest['rejected_checkpoints'] == 0)
    checks['lethal_closed_window'] = all(finite(r.get('response_window_end')) and
        finite(r.get('observed_until')) and r['observed_until'] >= r['response_window_end'] + 1 for r in (host, guest))
    for role, r in (('host', host), ('guest', guest)):
        stats = r['scheduled_stats']
        checks['lethal_' + role + '_counters'] = all(type(stats.get(k)) is int and
            stats[k] == (pending if role == 'host' and k == 'forced' else 0) for k in ERROR_COUNTERS)
        frames = r['frame_statistics']
        checks['lethal_' + role + '_frames'] = (type(frames.get('count')) is int and frames['count'] >= 30 and
            all(finite(frames.get(k)) for k in ('median', 'p95')) and .9/30 <= frames['median'] <= 1.15/30 and
            frames['median'] <= frames['p95'] <= 1.5/30)
        if any(not finite(row.get('at')) for row in r['rows']): raise ValueError('Invalid row clock')

    def rows(r, event): return [row for row in r['rows'] if row.get('event') == event]
    def one(items):
        if len(items) != 1: raise ValueError('Missing or repeated witness')
        return items[0]
    def integer(value): return type(value) is int and value >= 0
    def distance(a, b):
        if not all(type(v) is list and len(v) == 3 and all(finite(n) for n in v) for v in (a, b)):
            raise ValueError('Invalid root vector')
        return math.dist(a, b)

    hit = one([r for r in host['stimuli'] if r.get('event') == 'lethal_hit'])
    initial = hit['epoch']
    if not integer(initial) or initial == 0 or not finite(hit['at']): raise ValueError('Invalid contact')
    epoch = initial + 1
    checks['lethal_contact'] = (hit['health_before'] == 100-pending and hit['health_after'] == 0 and
        hit['outcome'] == 0 and hit['pending_before'] == pending and hit['issued_after'] == pending and
        finite(hit['pre_hit_speed']) and hit['pre_hit_speed'] > 40 and hit['pre_hit_input_y'] == 127 and
        finite(hit['moving_seconds_before_hit']) and hit['moving_seconds_before_hit'] >= .15)
    nonlethal = [r for r in host['stimuli'] if r.get('event') == 'hit']
    checks['lethal_same_host_frame'] = (len(nonlethal) == pending and finite(hit['world_time']) and
        all(r['at'] <= hit['at'] and r['world_time'] == hit['world_time'] for r in nonlethal))
    checks['lethal_epoch_reset'] = all(r['initial_epoch'] == initial and r['epoch'] == epoch and
        r['journal_epoch'] == epoch and r['scheduled_stats']['known'] == r['scheduled_stats']['through'] == 0
        for r in (host, guest))
    committed = one(rows(host, 'activity_committed'))
    restored = one(rows(guest, 'activity_restored'))
    before = one(rows(host, 'lethal_before_epoch'))
    checks['lethal_roles'] = (committed.get('authority') is True and committed.get('local') is False and
        before.get('authority') is True and before.get('local') is False and
        restored.get('authority') is False and restored.get('local') is True)
    checks['lethal_pending_composed'] = (before['epoch'] == before['journal_epoch'] == initial and
        before['known'] == before['through'] == pending and before['forced'] == pending and
        hit['at'] <= before['at'] <= committed['at'] and before.get('pending') is False)
    issues = rows(host, 'reaction_issued')
    applied = rows(host, 'reaction_applied')
    checks['lethal_host_exactly_once'] = (len(issues) == len(applied) == pending and
        host['scheduled_stats']['issued'] == host['scheduled_stats']['applied'] == pending and
        all(r['reaction_epoch'] == initial and r['sequence'] == 1 and r['at'] <= hit['at'] for r in issues) and
        all(r['reaction_epoch'] == initial and r['sequence'] == 1 and r['at'] <= before['at'] and
            r['payload_digest'] == issues[0]['payload_digest'] for r in applied))
    owner_applies = rows(guest, 'reaction_applied')
    owner_original = [r for r in owner_applies if r.get('replay') is False]
    checks['lethal_owner_old_epoch_bounded'] = (len(owner_original) <= pending and
        guest['scheduled_stats']['applied'] == len(owner_original) and
        all(r['reaction_epoch'] == initial and r['sequence'] == 1 and r['at'] < restored['at'] and
            issues and r['payload_digest'] == issues[0]['payload_digest'] for r in owner_applies))
    checks['lethal_handoff_state'] = all(r['epoch'] == r['journal_epoch'] == epoch and
        r.get('state_available') is True and r.get('foot_reaction') is True and r.get('target_free') is True and
        re.fullmatch('[0-9a-f]{40}', r['handoff_digest']) and r['applied_digest'] == r['handoff_digest'] and
        r['action'] == r['handoff_action'] and r['action'].startswith('Knock') for r in (committed, restored)) and (
        committed['handoff_digest'] == restored['handoff_digest'] and committed['action'] == restored['action'] and
        distance(committed['location'], restored['location']) < 1 and
        distance(committed['pending_launch'], restored['pending_launch']) < .01 and committed['health'] == 0)
    checks['lethal_handoff_deadline'] = all(0 <= r['at']-hit['at'] <= .5 for r in (committed, restored))
    checks['lethal_death_observed'] = (finite(guest['zero_health_at']) and 0 <= guest['zero_health_at']-hit['at'] <= .5 and
        guest.get('dead_input_attempted') is True and guest.get('dead_attack') is False and
        type(guest['dead_frames']) is int and guest['dead_frames'] >= 3)
    for r in (host, guest):
        if not r['health_changes'] or any(not finite(h.get('at')) or not finite(h.get('health')) or
                not 0 <= h['health'] <= 100 or type(h.get('down')) is not bool for h in r['health_changes']):
            raise ValueError('Missing health observation')
    zeros = [h for h in guest['health_changes'] if h['health'] == 0 and h['at'] >= hit['at'] and h.get('epoch') == epoch]
    first_zero = min((h['at'] for h in zeros), default=math.inf)
    revived = [h for h in host['health_changes'] if h['at'] > hit['at'] and h['health'] == 100 and h['down'] is False and h.get('epoch') == epoch]
    checks['lethal_owner_health_stays_dead_until_getup'] = (bool(zeros) and
        first_zero - hit['at'] <= .5 and all(g['health'] == 100 and g.get('epoch') == epoch and any(h['at'] <= g['at'] for h in revived)
            for g in guest['health_changes'] if g['at'] > first_zero and g['health'] > 0))
    getup_at = min((h['at'] for h in revived), default=math.inf)
    inputs = rows(host, 'dead_input')
    checks['lethal_host_dead_inputs'] = ({r.get('button') for r in inputs} >= {'attack', 'guard'} and
        all(r['epoch'] == epoch and r['health'] == 0 and committed['at'] <= r['at'] < getup_at and
            r.get('authority') is True and r.get('local') is False and r.get('down') is True and
            r.get('attacking') is False and r.get('guarding') is False and r.get('parrying') is False for r in inputs) and
        type(host['dead_frames']) is int and host['dead_frames'] >= 3 and
        host.get('dead_attack') is False and host.get('dead_defence') is False and
        finite(host.get('last_dead_at')) and committed['at'] <= host['last_dead_at'] < getup_at)
    first = {}
    for role, r, handoff in (('host', host, committed), ('guest', guest, restored)):
        move = one([m for m in rows(r, 'epoch_first_move') if m['epoch'] == epoch]); first[role] = move
        checks['lethal_' + role + '_clock_restart'] = (move['journal_epoch'] == epoch and
            finite(move['stamp']) and 0 < move['stamp'] <= (.5 if role == 'host' else .125) and
            finite(move['dt']) and 0 < move['dt'] <= .125 and move['at'] >= handoff['at'] and
            distance(move['start'], handoff['location']) < 1)
    checks['lethal_new_epoch_checkpoint'] = any(r['response_epoch'] == epoch and r['reaction_through'] == 0 and
        r['at'] >= first['host']['at'] and r['stamp'] >= first['host']['stamp'] for r in rows(guest, 'applied'))
    stale = one([r for r in host['stimuli'] if r.get('event') == 'stale_reaction_sent'])
    wrong = rows(guest, 'reaction_wrong_epoch')
    checks['lethal_stale_delivery_rejected'] = (stale['epoch'] == epoch and stale['sent_epoch'] == initial and
        stale['at'] >= restored['at'] and any(r['epoch'] == r['journal_epoch'] == epoch and
            r['reaction_epoch'] == initial and r['sequence'] == 1 and r['at'] >= stale['at'] and
            r['payload_digest'] == stale['payload_digest'] for r in wrong))
    return checks, outcomes | {'lethal_expected_forced': pending, 'owner_health_at_handoff': restored['health'],
        'owner_applied_old_before_reset': bool(owner_original), 'old_epoch_discards': len(wrong),
        'lethal_suppressed_moves': len(rows(host, 'lethal_move_suppressed')),
        'timing_scope': 'Same-Mac platform clock', 'commit_ms': 1000*(committed['at']-hit['at']), 'owner_handoff_ms': 1000*(restored['at']-hit['at'])}


def lethal_reaction_checks(host, guest, case, moving=False):
    try:
        return _checks(host, guest, case, moving)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {'lethal_receipts': False}, {}
