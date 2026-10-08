"""Match actual packed-response observations without treating a send as delivery.

Timing uses one machine's platform clock. Deliberate send holds belong to the
stimulus receipt and must be reported separately from production latency.
"""
import math
import re


def delivery_outcomes(host, guest):
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    def key(row):
        epoch, stamp, edge = (row.get(name) for name in ('response_epoch', 'stamp', 'edge'))
        correction, checkpoint = row.get('correction'), row.get('checkpoint')
        action, digest = row.get('action'), row.get('digest')
        if (type(epoch) is not int or epoch <= 0 or not finite(stamp) or stamp <= 0 or
                type(edge) is not int or not 0 <= edge <= 65535 or
                type(correction) is not bool or type(checkpoint) is not bool or
                type(action) is not str or type(digest) is not str or
                not finite(row.get('at'))):
            raise ValueError('Invalid response identity or clock')
        if checkpoint:
            if not correction or not action or not re.fullmatch(r'[0-9a-f]{40}', digest):
                raise ValueError('Invalid checkpoint provenance')
        elif action or digest:
            raise ValueError('Payload identity without a checkpoint')
        return epoch, stamp, edge, correction, checkpoint, action, digest

    for receipt in (host, guest):
        if (type(receipt) is not dict or type(receipt.get('overflow')) is not int or
                receipt['overflow'] != 0 or type(receipt.get('rows')) is not list or
                not all(type(row) is dict for row in receipt['rows'])):
            raise ValueError('Missing or overflowed delivery evidence')
    if not host.get('player_id') or host['player_id'] != guest.get('player_id'):
        raise ValueError('Delivery evidence belongs to different players')

    window = host.get('response_window_end', float('inf'))
    if window != float('inf') and (not finite(window) or guest.get('response_window_end') != window or
            any(not finite(r.get('observed_until')) or r['observed_until'] < window + 1 for r in (host, guest))):
        raise ValueError('Incomplete post-window observation')

    sent, received, applied = {}, {}, {}
    for rows, event, output in ((host['rows'], 'serialized', sent),
                                (guest['rows'], 'received', received),
                                (guest['rows'], 'applied', applied)):
        for row in rows:
            if row.get('event') != event:
                continue
            identity = key(row)
            # After the closed host window, newer epochs/stamps remain ordinary
            # traffic. They cannot prove or disprove delivery within this window.
            if event != 'serialized' and window != float('inf'):
                last = max((k[1] for k in sent if k[0] == identity[0]), default=-1)
                if identity[1] > last:
                    if row['at'] <= window:
                        raise ValueError('Unproven response inside measurement window')
                    continue
            if identity in output:
                raise ValueError('Ambiguous duplicate response identity')
            output[identity] = row
    if not sent:
        raise ValueError('No serialized responses observed')
    for identity, row in received.items():
        if identity not in sent or row['at'] < sent[identity]['at']:
            raise ValueError('Received response has no preceding host provenance')
    for identity, row in applied.items():
        if identity not in received or row['at'] < received[identity]['at']:
            raise ValueError('Applied checkpoint has no preceding guest receipt')

    outcomes = []
    for identity, row in sent.items():
        if row['at'] > window:
            continue
        arrival = received.get(identity)
        result = dict(epoch=identity[0], stamp=identity[1], checkpoint=identity[4],
                      action=identity[5], digest=identity[6], serialized_at=row['at'],
                      outcome='received' if arrival else 'lost', applied=identity in applied)
        if arrival:
            result['received_at'] = arrival['at']
            result['delivery_ms'] = (arrival['at'] - row['at']) * 1000
        else:
            # A later accepted checkpoint is recovery evidence, not proof that
            # the lost response itself arrived. Keep the two outcomes separate.
            later = [v for k, v in applied.items() if k[0] == identity[0] and k[1] > identity[1]
                     and v['at'] >= row['at'] and k[3] and k[4]]
            recovery = min(later, key=lambda v: v['at'], default=None)
            result['next_checkpoint_ms'] = ((recovery['at'] - row['at']) * 1000) if recovery else None
            result['next_checkpoint_stamp'] = recovery['stamp'] if recovery else None
        outcomes.append(result)
    return dict(serialized=len(outcomes), received=sum(r['outcome'] == 'received' for r in outcomes),
                applied=sum(r['applied'] for r in outcomes),
                lost=sum(row['outcome'] == 'lost' for row in outcomes), responses=outcomes)


def _reaction_delivery_checks(host, guest, case, moving=False):
    """Require native ordering witnesses; reported packet loss never excuses drift."""
    checks = dict(reaction_receipts=False)
    if type(case) is not int or not 0 <= case <= 7 or type(moving) is not bool or (moving and case not in (0, 5)):
        return checks, {}
    try:
        outcomes = delivery_outcomes(host, guest)
        rows = host['rows']
        stimuli = host['stimuli']
        if (not all(type(r) is dict for r in stimuli) or
                any(type(r.get('at')) not in (int, float) or not math.isfinite(r['at'])
                    for r in rows + stimuli)):
            return checks, outcomes
    except (KeyError, TypeError, ValueError):
        return checks, {}
    checks['reaction_receipts'] = all(r.get('case') == case and type(r.get('case')) is int and
        r.get('complete') is True and r.get('error') == '' and r.get('enabled') is True and
        r.get('packed_responses') is True for r in (host, guest))
    checks['reaction_drive_mode'] = host.get('moving') is moving and guest.get('moving') is moving
    if moving:
        hits = [r for r in stimuli if r.get('event') == 'hit']
        checks['reaction_moving_victim'] = len(hits) == 1 and all(
            type(hits[0].get(k)) in (int, float) and math.isfinite(hits[0][k])
            for k in ('pre_hit_speed', 'moving_seconds_before_hit')) and (
            hits[0]['pre_hit_speed'] > 40 and hits[0]['moving_seconds_before_hit'] >= .15 and
            type(hits[0].get('pre_hit_input_y')) is int and hits[0]['pre_hit_input_y'] == 127 and
            type(guest.get('drive_y')) is int and guest['drive_y'] == 127)
    checks['reaction_closed_window'] = all(type(r.get('response_window_end')) in (int, float) and
        math.isfinite(r['response_window_end']) and type(r.get('observed_until')) in (int, float) and
        math.isfinite(r['observed_until']) and r['observed_until'] >= r['response_window_end'] + 1
        for r in (host, guest))
    checks['reaction_strict_prediction'] = (type(guest.get('position_corrections')) is int and
        guest['position_corrections'] == 0 and type(guest.get('largest_correction_cm')) in (int, float) and
        0 <= guest['largest_correction_cm'] < 1 and type(guest.get('rejected_checkpoints')) is int and
        guest['rejected_checkpoints'] == 0)
    checks['reaction_hold_label'] = (host.get('artificial_send_hold') is (case == 2) and
        type(host.get('held_sends')) is int and (host['held_sends'] > 0 if case == 2 else host['held_sends'] == 0))
    for role, receipt in (('host', host), ('guest', guest)):
        stats = receipt.get('frame_statistics', {})
        checks['reaction_' + role + '_frames'] = (type(stats.get('count')) is int and stats['count'] >= 30 and
            all(type(stats.get(k)) in (int, float) and math.isfinite(stats[k]) for k in ('median', 'p95')) and
            .9 / 30 <= stats['median'] <= 1.15 / 30 and stats['median'] <= stats['p95'] <= 1.5 / 30)

    def events(name, source=rows):
        return [r for r in source if r.get('event') == name]

    raw_queues = events('queued')
    # IncomingStrike and its nested TakeHit each request the same delivery.
    # Bind those two calls to one observed hit, keeping both raw witnesses.
    # A guard has no nested TakeHit and therefore makes exactly one request.
    hits = [r for r in stimuli if r.get('event') in ('hit', 'zero_impulse_guard')]
    queue_groups, queues, grouped = [], [], []
    previous_hit = -float('inf')
    groups_valid = True
    for hit in hits:
        group = [r for r in raw_queues if previous_hit < r['at'] <= hit['at']]
        expected_calls = 2 if hit['event'] == 'hit' else 1
        valid = len(group) == expected_calls
        if valid:
            valid = all(tuple(r.get(k) for k in ('epoch', 'stamp', 'live_action')) ==
                        tuple(group[0].get(k) for k in ('epoch', 'stamp', 'live_action')) for r in group)
            # The synchronous nested calls cannot contain a capture or send.
            between = [r for r in rows if group[0]['at'] <= r['at'] <= group[-1]['at']]
            valid = valid and len(between) == expected_calls and all(r.get('event') == 'queued' for r in between)
            queues.append(group[-1])
        groups_valid = groups_valid and valid
        queue_groups.append(dict(stimulus=hit['event'], stimulus_at=hit['at'], calls=len(group),
                                 first_queue_at=group[0]['at'] if group else None,
                                 last_queue_at=group[-1]['at'] if group else None))
        grouped.extend(group)
        previous_hit = hit['at']
    groups_valid = groups_valid and len(grouped) == len(raw_queues)
    captures = [r for r in events('capture') if r.get('pending') is True and r.get('captured') is True]
    expected = 0 if case == 7 else 2 if case == 4 else 1
    checks['reaction_queue_count'] = (groups_valid and len(queues) == expected and all(r.get('authority') is True and
        r.get('local') is False and r.get('remote_role') == 2 and type(r.get('remote_role')) is int and
        r.get('pending') is True and r.get('captured') is False and
        type(r.get('stamp')) in (int, float) and math.isfinite(r['stamp']) and r['stamp'] > 0 and
        r.get('live_action') in ('HitF', 'GuardHit', 'SwordGuardHit') for r in raw_queues))
    checks['reaction_stimulus'] = (len([r for r in stimuli if r.get('event') in
        ('hit', 'zero_impulse_guard', 'host_own_hit')]) == (2 if case == 4 else 1))
    deliveries = []
    for queue in queues:
        next_queue = next((r for r in queues if r['at'] > queue['at']), None)
        end = next_queue['at'] if next_queue else host.get('response_window_end', -1)
        candidates = [r for r in captures if queue['at'] <= r['at'] < end and r.get('epoch') == queue.get('epoch')]
        sent = [r for r in outcomes['responses'] if r['checkpoint'] and r['epoch'] == queue.get('epoch') and
                queue['at'] <= r['serialized_at'] < end and any(c.get('stamp') == r['stamp'] and
                c['at'] <= r['serialized_at'] and c.get('action') == r['action'] for c in candidates)]
        first = min(sent, key=lambda r: r['serialized_at'], default=None)
        distinct = sorted({r['stamp'] for r in candidates if type(r.get('stamp')) in (int, float) and
                           math.isfinite(r['stamp']) and r['stamp'] > queue.get('stamp', float('inf'))})
        deliveries.append(dict(queue_at=queue['at'], resolve_stamp=queue.get('stamp'),
            first_capture_stamp=min(distinct, default=None), serialized=first,
            accepted_moves_before_send=sum(stamp < first['stamp'] for stamp in distinct) if first else None))
    if case not in (6, 7):
        # Case 4 deliberately supersedes the first captured action before it can
        # be sent; the second queue must still be captured and delivered promptly.
        required = deliveries[-1:] if case == 4 else deliveries
        checks['reaction_captured_delivery'] = bool(required) and all(d['serialized'] and
            d['serialized']['action'] in ('HitF', 'GuardHit', 'SwordGuardHit') for d in required)
        interval = host.get('minimum_adjustment_interval')
        valid_interval = type(interval) in (int, float) and math.isfinite(interval) and 0 < interval <= .25
        checks['reaction_actual_send_interval'] = valid_interval
        allowance = 3 if case == 2 else math.ceil(interval * 30) + 1 if case == 5 and valid_interval else 1
        checks['reaction_bounded_moves_to_send'] = bool(required) and all(d['accepted_moves_before_send'] is not None and
            0 <= d['accepted_moves_before_send'] <= allowance for d in required)
        checks['reaction_guest_observed_action'] = any(r['applied'] and r['action'] in
            ('HitF', 'GuardHit', 'SwordGuardHit') for r in outcomes['responses'])
    if case == 0:
        before = events('correction_before_hit', stimuli)
        checks['reaction_after_real_correction'] = len(before) == 1 and bool(queues) and before[0]['at'] <= queues[0]['at'] and any(
            r.get('correction') is True and r.get('checkpoint') is True and
            r['at'] <= before[0]['at'] and r.get('stamp') == before[0].get('checkpoint_stamp') for r in events('serialized'))
    elif case == 1:
        guard = events('zero_impulse_guard', stimuli)
        checks['reaction_zero_impulse_guard'] = (len(guard) == 1 and guard[0].get('guard') is True and guard[0].get('outcome') == 3 and
            type(guard[0].get('speed')) in (int, float) and 0 <= guard[0]['speed'] <= .01)
        checks['reaction_guard_checkpoint'] = any(r['applied'] and r['action'] in ('GuardHit', 'SwordGuardHit') for r in outcomes['responses'])
    elif case == 2:
        first = deliveries[0]['serialized'] if deliveries else None
        before = [r for r in captures if first and r['at'] <= first['serialized_at']]
        checks['reaction_multiple_pending_captures'] = len({r.get('stamp') for r in before}) >= 3
    elif case in (3, 5):
        name = 'prepared_good_ack' if case == 3 else 'prepared_correction_before_hit'
        prepared = events(name, stimuli)
        q = queues[0] if queues else {}
        first_capture = min((r['at'] for r in captures if r['at'] >= q.get('at', float('inf'))), default=-1)
        old = [r for r in events('serialized') if q.get('at', float('inf')) <= r['at'] < first_capture and
               r.get('correction') is (case == 5)]
        checks['reaction_old_response_survives'] = len(prepared) == 1 and bool(old) and bool(captures)
        if case == 5:
            checks['reaction_natural_throttle'] = (bool(old) and any(r.get('pending') is True and r.get('captured') is False and
                old[0]['at'] <= r['at'] < first_capture for r in events('send_timer_advanced')) and bool(deliveries) and
                deliveries[0]['serialized'] is not None and deliveries[0]['serialized']['serialized_at'] - old[0]['at'] >= interval - .001)
    elif case == 4:
        checks['reaction_second_queue_invalidates_capture'] = len(queues) == 2 and len(events('second_after_capture', stimuli)) == 1 and any(
            queues[0]['at'] <= r['at'] <= queues[1]['at'] for r in captures) and bool(deliveries) and deliveries[0]['serialized'] is None
    elif case == 6:
        before, after = events('cancel_before_epoch', stimuli), events('cancel_after_epoch', stimuli)
        checks['reaction_epoch_cancel'] = (len(before) == len(after) == 1 and type(before[0].get('epoch')) is int and
            type(after[0].get('epoch')) is int and after[0]['epoch'] == before[0]['epoch'] + 1 and any(
            r.get('pending') is True and before[0]['at'] <= r['at'] <= after[0]['at'] for r in events('epoch_reset')) and any(
            r.get('epoch') == after[0]['epoch'] and r.get('pending') is False and r.get('captured') is False and
            before[0]['at'] <= r['at'] <= after[0]['at'] for r in events('epoch_reset_complete')) and not any(
            r['serialized_at'] >= after[0]['at'] and r['epoch'] == before[0]['epoch'] and r['checkpoint'] for r in outcomes['responses']))
    else:
        own = host.get('host_own', {})
        own_rows = own.get('rows', [])
        checks['reaction_host_own_no_pending'] = (own.get('enabled') is True and own.get('packed_responses') is True and
            bool(own.get('player_id')) and own['player_id'] != host.get('player_id') and own.get('overflow') == 0 and
            len(events('host_own_hit', stimuli)) == 1 and not events('queued', own_rows) and any(
            r.get('event') == 'ineligible_queue' and r.get('local') is True and r.get('authority') is True and
            r.get('pending') is False for r in own_rows))
    return checks, outcomes | dict(deliveries=deliveries, queue_groups=queue_groups, raw_queue_count=len(raw_queues))


def reaction_delivery_checks(host, guest, case, moving=False):
    try:
        return _reaction_delivery_checks(host, guest, case, moving)
    except (KeyError, TypeError, ValueError):
        return dict(reaction_receipts=False), {}
