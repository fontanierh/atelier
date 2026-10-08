import copy
import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).parents[1] / 'tools' / 'network_reaction_delivery_review.py'
_spec = importlib.util.spec_from_file_location('reaction_delivery_review', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
delivery_outcomes = _module.delivery_outcomes


def response(event, stamp, at):
    return dict(event=event, response_epoch=2, stamp=stamp, edge=4, correction=True,
                checkpoint=True, action='HitF', digest='a' * 40, at=at)


def receipts():
    host = dict(player_id='guest', overflow=0, rows=[response('serialized', 1., 10.),
                                                   response('serialized', 1.2, 10.2)])
    guest = dict(player_id='guest', overflow=0, rows=[response('received', 1.2, 10.26),
                                                    response('applied', 1.2, 10.261)])
    return host, guest


def test_loss_is_not_delivery_and_later_checkpoint_is_separate_recovery():
    report = delivery_outcomes(*receipts())
    assert (report['serialized'], report['received'], report['applied'], report['lost']) == (2, 1, 1, 1)
    lost, arrived = report['responses']
    assert lost['outcome'] == 'lost' and not lost['applied']
    assert lost['next_checkpoint_stamp'] == 1.2
    assert lost['next_checkpoint_ms'] == pytest.approx(261)
    assert arrived['delivery_ms'] == pytest.approx(60)


def test_lost_response_without_later_checkpoint_does_not_claim_recovery():
    host, guest = receipts()
    guest['rows'] = []
    report = delivery_outcomes(host, guest)
    assert report['lost'] == 2
    assert all(row['next_checkpoint_ms'] is None for row in report['responses'])


@pytest.mark.parametrize('field,value', [('response_epoch', 3), ('stamp', 1.3), ('edge', 5),
                                      ('action', 'GuardHit'), ('digest', 'b' * 40)])
def test_forged_received_provenance_fails(field, value):
    host, guest = receipts()
    guest['rows'][0][field] = value
    with pytest.raises(ValueError):
        delivery_outcomes(host, guest)


@pytest.mark.parametrize('field,value', [('response_epoch', True), ('stamp', True), ('stamp', float('nan')),
                                      ('edge', False), ('correction', 1), ('checkpoint', 1),
                                      ('digest', 'unprepared'), ('at', float('inf'))])
def test_malformed_fields_fail_closed(field, value):
    host, guest = receipts()
    host['rows'][0][field] = value
    with pytest.raises(ValueError):
        delivery_outcomes(host, guest)


def test_wrong_player_and_overflow_fail_closed():
    for index, field, value in [(1, 'player_id', 'host'), (0, 'overflow', 1), (1, 'overflow', False)]:
        pair = list(receipts())
        pair[index][field] = value
        with pytest.raises(ValueError):
            delivery_outcomes(*pair)


def test_guest_application_requires_receipt_not_just_send():
    host, guest = receipts()
    guest['rows'] = guest['rows'][1:]
    with pytest.raises(ValueError):
        delivery_outcomes(host, guest)


def test_duplicate_identity_is_ambiguous_and_does_not_count_twice():
    host, guest = receipts()
    host['rows'].append(copy.deepcopy(host['rows'][0]))
    with pytest.raises(ValueError):
        delivery_outcomes(host, guest)


def test_closed_window_does_not_call_final_in_flight_response_lost():
    host, guest = receipts()
    for receipt in (host, guest):
        receipt.update(response_window_end=10.3, observed_until=11.31)
    host['rows'].append(response('serialized', 2., 11.3))
    guest['rows'].append(response('received', 2., 11.4))
    report = delivery_outcomes(host, guest)
    assert report['serialized'] == 2 and report['lost'] == 1


def test_short_drain_cannot_claim_packet_loss():
    host, guest = receipts()
    for receipt in (host, guest):
        receipt.update(response_window_end=10.3, observed_until=10.4)
    with pytest.raises(ValueError):
        delivery_outcomes(host, guest)


def native_ordering(case):
    frames = dict(count=100, median=1/30, p95=.034)
    common = dict(moving=False, case=case, complete=True, error='', enabled=True, packed_responses=True,
                  minimum_adjustment_interval=.05, frame_statistics=frames,
                  response_window_end=12., observed_until=13.1, player_id='guest', overflow=0)
    host = common | dict(rows=[], stimuli=[], artificial_send_hold=case == 2, held_sends=3 if case == 2 else 0)
    guest = common | dict(rows=[], position_corrections=0, largest_correction_cm=.06, rejected_checkpoints=0)

    def sent(stamp, at, action='HitF', checkpoint=True):
        row = response('serialized', stamp, at)
        row.update(action=action if checkpoint else '', digest='a'*40 if checkpoint else '',
                   correction=checkpoint, checkpoint=checkpoint)
        host['rows'].append(row)
        guest['rows'].append(row | dict(event='received', at=at+.06))
        if checkpoint:
            guest['rows'].append(row | dict(event='applied', at=at+.061))

    def state(event, at, stamp, action='HitF', epoch=2, pending=True, captured=False):
        row = dict(event=event, at=at, stamp=stamp, epoch=epoch, pending=pending, captured=captured,
                   action=action, live_action=action, checkpoint_stamp=stamp,
                   authority=True, local=False, remote_role=2)
        host['rows'].append(row)
        return row

    sent(.9, 9.9, 'Idle')
    if case == 7:
        host['stimuli'] = [dict(event='host_own_hit', at=10.01)]
        host['host_own'] = common | dict(player_id='host', rows=[dict(event='ineligible_queue', at=10.01,
                authority=True, local=True, pending=False)])
        return host, guest
    guard = case == 1
    action = 'GuardHit' if guard else 'HitF'
    state('queued', 10.01, 1., action)
    if not guard: state('queued', 10.0105, 1., action)
    host['stimuli'] = [dict(event='zero_impulse_guard' if guard else 'hit', at=10.011,
                           guard=guard, outcome=3 if guard else 0, speed=0 if guard else 160.)]
    if case == 0:
        host['stimuli'].insert(0, dict(event='correction_before_hit', at=9.901, checkpoint_stamp=.9))
    if case == 6:
        host['stimuli'] += [dict(event='cancel_before_epoch', at=10.012, epoch=2),
                            dict(event='cancel_after_epoch', at=10.014, epoch=3)]
        state('epoch_reset', 10.013, 1., epoch=3)
        state('epoch_reset_complete', 10.0131, 1., epoch=3, pending=False)
        return host, guest
    if case in (3, 5):
        host['stimuli'].insert(0, dict(event='prepared_good_ack' if case == 3 else 'prepared_correction_before_hit', at=10.009))
        sent(1., 10.02, 'Idle', case == 5)
        if case == 5:
            state('send_timer_advanced', 10.021, 1., 'Idle')
    state('capture', 10.04, 1.033, action, captured=True)
    if case == 4:
        host['stimuli'] += [dict(event='second_after_capture', at=10.0401),
                            dict(event='zero_impulse_guard', at=10.042, guard=True, outcome=3, speed=0)]
        state('queued', 10.041, 1.033, 'GuardHit')
        state('capture', 10.075, 1.066, 'GuardHit', captured=True)
        sent(1.066, 10.076, 'GuardHit')
    elif case == 2:
        state('capture', 10.07, 1.066, captured=True)
        state('capture', 10.10, 1.099, captured=True)
        sent(1.099, 10.101)
    else:
        sent(1.033, 10.10 if case == 5 else 10.041, action)
    host['rows'].sort(key=lambda r:r['at'])
    guest['rows'].sort(key=lambda r:r['at'])
    return host, guest


@pytest.mark.parametrize('case', range(8))
def test_each_native_ordering_needs_a_distinct_witness(case):
    checks, report = _module.reaction_delivery_checks(*native_ordering(case), case)
    assert all(checks.values()), checks
    assert report['received'] == report['serialized']


@pytest.mark.parametrize('case,event', [(0,'correction_before_hit'), (1,'zero_impulse_guard'),
    (3,'prepared_good_ack'), (4,'second_after_capture'), (5,'prepared_correction_before_hit'),
    (6,'cancel_after_epoch'), (7,'host_own_hit')])
def test_missing_native_ordering_witness_cannot_pass(case, event):
    host, guest = native_ordering(case)
    host['stimuli'] = [row for row in host['stimuli'] if row['event'] != event]
    assert not all(_module.reaction_delivery_checks(host, guest, case)[0].values())


@pytest.mark.parametrize('mutation', ['capture_count', 'label', 'queue_role', 'queue_action', 'packed',
                                    'drift', 'rejected', 'short_window', 'frames', 'wrong_case'])
def test_delivery_does_not_excuse_missing_simulation_or_provenance(mutation):
    host, guest = native_ordering(2)
    if mutation == 'capture_count':
        host['rows'] = [row for row in host['rows'] if row.get('stamp') != 1.066]
    elif mutation == 'label': host['artificial_send_hold'] = False
    elif mutation == 'queue_role': next(r for r in host['rows'] if r['event']=='queued')['remote_role'] = True
    elif mutation == 'queue_action': next(r for r in host['rows'] if r['event']=='queued')['live_action'] = 'Idle'
    elif mutation == 'packed': guest['packed_responses'] = False
    elif mutation == 'drift': guest['largest_correction_cm'] = 1.565
    elif mutation == 'rejected': guest['rejected_checkpoints'] = 1
    elif mutation == 'short_window': guest['observed_until'] = 12.1
    elif mutation == 'frames': guest['frame_statistics'] = dict(count=2, median=1/30, p95=.034)
    else: guest['case'] = True
    assert not all(_module.reaction_delivery_checks(host, guest, 2)[0].values())


def test_real_throttle_requires_pending_to_survive_the_old_actual_send():
    host, guest = native_ordering(5)
    next(r for r in host['rows'] if r['event']=='send_timer_advanced')['pending'] = False
    assert not all(_module.reaction_delivery_checks(host, guest, 5)[0].values())


def test_epoch_cancellation_requires_cleared_state_not_only_an_epoch_number():
    host, guest = native_ordering(6)
    next(r for r in host['rows'] if r['event']=='epoch_reset_complete')['pending'] = True
    assert not all(_module.reaction_delivery_checks(host, guest, 6)[0].values())


def session_module():
    path = _path.with_name('review_network_session.py')
    spec = importlib.util.spec_from_file_location('reaction_session_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('extra', [[], ['--lag-ms','60','--variance-ms','15','--loss-percent','2']])
def test_reaction_cli_selects_only_its_listen_route(monkeypatch, tmp_path, extra):
    import sys
    module = session_module()
    seen = []
    monkeypatch.setattr(module, 'worker', lambda *args: seen.append(args) or 0)
    monkeypatch.setattr(sys, 'argv', ['review', '--worker', '--output', str(tmp_path), '--port', '43210',
                                    '--reaction-delivery-case', '0', *extra])
    assert module.main() == 0
    assert len(seen) == 1 and seen[0][2] is False and seen[0][3] is True and seen[0][-2] == 0 and seen[0][-1] is False


@pytest.mark.parametrize('extra', [['--gameplay'], ['--vehicle-case','bike'], ['--enemy'], ['--combat'],
    ['--jump-replay','1'], ['--modori-shield','1'], ['--movement-hitch-ms','229'],
    ['--skate-hitch-ms','229'], ['--app','unused'], ['--lag-ms','5']])
def test_reaction_cli_rejects_other_stimuli_before_admission(monkeypatch, extra):
    import sys
    module = session_module()
    monkeypatch.setattr(sys, 'argv', ['review', '--reaction-delivery-case', '0', *extra])
    with pytest.raises(SystemExit) as raised:
        module.main()
    assert raised.value.code == 2


@pytest.mark.parametrize('case', [0, 5])
def test_moving_reaction_needs_measured_drive_before_the_real_hit(case):
    host, guest = native_ordering(case)
    for receipt in (host, guest): receipt['moving'] = True
    guest['drive_y'] = 127
    hit = next(r for r in host['stimuli'] if r['event'] == 'hit')
    hit.update(pre_hit_speed=160., pre_hit_input_y=127, moving_seconds_before_hit=.2)
    assert all(_module.reaction_delivery_checks(host, guest, case, True)[0].values())
    for field, value in [('pre_hit_speed', 0.), ('pre_hit_speed', float('nan')),
                         ('pre_hit_input_y', 0), ('moving_seconds_before_hit', .01)]:
        modified = copy.deepcopy(host)
        next(r for r in modified['stimuli'] if r['event'] == 'hit')[field] = value
        assert not all(_module.reaction_delivery_checks(modified, guest, case, True)[0].values())
    guest['drive_y'] = 0
    assert not all(_module.reaction_delivery_checks(host, guest, case, True)[0].values())


@pytest.mark.parametrize('case', [None, 1, 2, 3, 4, 6, 7])
def test_moving_reaction_cli_rejects_unsupported_case_before_admission(monkeypatch, case):
    import sys
    module = session_module()
    monkeypatch.setattr(sys, 'argv', ['review', '--reaction-delivery-moving'] +
                       ([] if case is None else ['--reaction-delivery-case', str(case)]))
    with pytest.raises(SystemExit) as raised: module.main()
    assert raised.value.code == 2


@pytest.mark.parametrize('case', [0, 2, 3, 4, 5, 6])
def test_nested_hit_requests_are_one_stimulus_but_both_calls_remain_proven(case):
    checks, report = _module.reaction_delivery_checks(*native_ordering(case), case)
    assert all(checks.values()), checks
    assert report['raw_queue_count'] == (3 if case == 4 else 2)
    assert [g['calls'] for g in report['queue_groups']] == ([2, 1] if case == 4 else [2])
    assert len(report['deliveries']) == (2 if case == 4 else 1)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'stamp', 'epoch', 'action', 'interleaved', 'after_hit'])
def test_duplicate_requests_cannot_hide_an_extra_hit_or_intervening_capture(mutation):
    host, guest = native_ordering(0)
    queues = [r for r in host['rows'] if r['event'] == 'queued']
    if mutation == 'missing': host['rows'].remove(queues[0])
    elif mutation == 'extra': host['rows'].append(queues[0] | dict(at=10.0102))
    elif mutation == 'stamp': queues[1]['stamp'] += .033
    elif mutation == 'epoch': queues[1]['epoch'] += 1
    elif mutation == 'action': queues[1]['live_action'] = 'GuardHit'
    elif mutation == 'interleaved': host['rows'].append(queues[0] | dict(event='capture', at=10.0102, captured=True))
    else: queues[1]['at'] = 10.012
    host['rows'].sort(key=lambda r:r['at'])
    assert not all(_module.reaction_delivery_checks(host, guest, 0)[0].values())


def test_second_hit_remains_a_distinct_delivery_after_first_capture():
    host, guest = native_ordering(4)
    last = [r for r in host['rows'] if r['event'] == 'queued'][-1]
    last['at'] = 10.0107
    host['rows'].sort(key=lambda r:r['at'])
    assert not all(_module.reaction_delivery_checks(host, guest, 4)[0].values())
