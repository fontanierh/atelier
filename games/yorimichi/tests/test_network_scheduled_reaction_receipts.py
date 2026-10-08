import copy
import importlib.util
import sys
from pathlib import Path

import pytest

_tools = Path(__file__).parents[1] / 'tools'
sys.path.insert(0, str(_tools))
try:
    from network_scheduled_reaction_review import ERROR_COUNTERS, scheduled_reaction_checks
finally:
    sys.path.pop(0)
_spec = importlib.util.spec_from_file_location('delivery_fixture', Path(__file__).with_name('test_network_reaction_delivery_receipts.py'))
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)


def receipts(case=0, moving=False):
    host, guest = _fixture.native_ordering(case)
    expected = 0 if case == 7 else 2 if case == 4 else 1
    for r in (host, guest):
        r.update(scheduled_reactions=True, moving=moving)
        r['scheduled_stats'] = dict.fromkeys(ERROR_COUNTERS, 0) | dict(
            issued=expected if r is host else 0, received=expected if r is guest else 0,
            applied=0 if case == 6 else expected, replayed=0,
            through=0 if case == 6 else expected, known=0 if case == 6 else expected)
        for row in r['rows']:
            if row['event'] in ('serialized', 'received', 'applied'):
                row['reaction_through'] = expected if row['checkpoint'] else 0
    if case == 7:
        host['host_own']['scheduled_stats'] = dict(issued=0)
    else:
        hits = [r for r in host['stimuli'] if r['event'] in ('hit', 'zero_impulse_guard')]
        for sequence, hit in enumerate(hits, 1):
            identity = dict(reaction_epoch=2, sequence=sequence, resolved_generation=0,
                            resolved_stamp=1., reaction_action='GuardHit' if hit['guard'] else 'HitF',
                            payload_digest=str(sequence)*40, payload_bytes=138)
            origin = dict(previous_generation=0, previous_stamp=1.2, end_generation=0,
                          end_stamp=1.2333333, saved_dt=1/30, edge_before=4, edge_after=4)
            def row(event, at, authority, **extra):
                return identity | dict(event=event, at=at, replay=False, authority=authority,
                    local=not authority, remote_role=2 if authority else 3) | extra
            host['rows'].append(row('reaction_issued', hit['at']-.0001, True))
            guest['rows'].append(row('reaction_received', hit['at']+.03, False))
            if case != 6:
                guest['rows'].append(row('reaction_prepared', hit['at']+.04, False, **origin))
                guest['rows'].append(row('reaction_applied', hit['at']+.041, False, applied_through=sequence-1, **origin))
                host['rows'].append(row('reaction_applied', hit['at']+.08, True, applied_through=sequence-1, **origin))
        if moving:
            hits[0].update(pre_hit_speed=99.9, moving_seconds_before_hit=.2, pre_hit_input_y=127)
            guest['drive_y'] = 127
    for r in (host, guest):
        r['rows'].sort(key=lambda row: row['at'])
    return host, guest


def passed(pair, case=0, moving=False):
    return all(scheduled_reaction_checks(*pair, case, moving)[0].values())


@pytest.mark.parametrize('case,moving', [(n, False) for n in range(8)] + [(0, True), (5, True)])
def test_scheduled_contacts_need_strict_prediction_and_same_payload_boundary(case, moving):
    checks, report = scheduled_reaction_checks(*receipts(case, moving), case, moving)
    assert all(checks.values()), checks
    assert report['received'] == report['serialized']


@pytest.mark.parametrize('role,event', [('host', 'reaction_issued'), ('host', 'reaction_applied'),
    ('guest', 'reaction_received'), ('guest', 'reaction_prepared'), ('guest', 'reaction_applied')])
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'digest', 'epoch', 'sequence', 'action', 'nan', 'role'])
def test_missing_forged_or_repeated_reaction_cannot_pass(role, event, mutation):
    pair = receipts()
    r = pair[role == 'guest']
    row = next(row for row in r['rows'] if row['event'] == event)
    if mutation == 'missing': r['rows'].remove(row)
    elif mutation == 'duplicate': r['rows'].append(copy.deepcopy(row))
    elif mutation == 'digest': row['payload_digest'] = 'b'*40
    elif mutation == 'epoch': row['reaction_epoch'] += 1
    elif mutation == 'sequence': row['sequence'] = True
    elif mutation == 'action': row['reaction_action'] = 'KnockF'
    elif mutation == 'nan': row['at'] = float('nan')
    elif mutation == 'role': row['authority'] = not row['authority']
    assert not passed(pair)


@pytest.mark.parametrize('field,value', [('previous_stamp', 1.1), ('end_stamp', 1.3),
    ('saved_dt', .04), ('edge_before', 3), ('edge_after', 5), ('end_generation', 1),
    ('applied_through', 1)])
def test_a_reaction_on_a_different_host_move_is_not_the_same_prediction(field, value):
    host, guest = receipts()
    next(row for row in host['rows'] if row['event'] == 'reaction_applied')[field] = value
    assert not passed((host, guest))


@pytest.mark.parametrize('counter', ERROR_COUNTERS)
@pytest.mark.parametrize('value', [1, True, None])
def test_recovery_and_malformed_counters_cannot_hide_a_failure(counter, value):
    host, guest = receipts()
    guest['scheduled_stats'][counter] = value
    assert not passed((host, guest))


def test_replay_requires_same_retained_payload_and_original_boundary():
    pair = receipts()
    guest = pair[1]
    row = copy.deepcopy(next(row for row in guest['rows'] if row['event'] == 'reaction_applied'))
    row.update(replay=True, at=10.3)
    guest['rows'].append(row)
    guest['scheduled_stats']['replayed'] = 1
    assert passed(pair)
    row['end_stamp'] += 1/30
    assert not passed(pair)


@pytest.mark.parametrize('error', [.999, 1., 1.565, 8.23, float('nan')])
def test_no_recoil_exemption(error):
    pair = receipts()
    pair[1]['largest_correction_cm'] = error
    assert passed(pair) is (error < 1)


@pytest.mark.parametrize('case,event', [(0, 'correction_before_hit'), (1, 'zero_impulse_guard'),
    (3, 'prepared_good_ack'), (4, 'second_after_capture'), (5, 'prepared_correction_before_hit'),
    (6, 'cancel_after_epoch'), (7, 'host_own_hit')])
def test_scheduled_transport_cannot_skip_the_ordering_stimulus(case, event):
    pair = receipts(case)
    pair[0]['stimuli'] = [r for r in pair[0]['stimuli'] if r['event'] != event]
    assert not passed(pair, case)


@pytest.mark.parametrize('field', ['reaction_through', 'authority', 'local'])
def test_corrupt_checkpoint_prefix_or_replay_role_fails(field):
    pair = receipts()
    if field == 'reaction_through':
        next(r for r in pair[1]['rows'] if r['event'] == 'received')[field] = 200
    else:
        next(r for r in pair[1]['rows'] if r['event'] == 'reaction_prepared')[field] = (field == 'authority')
    assert not passed(pair)


@pytest.mark.parametrize('mutation', ['all_lost', 'unapplied', 'old_prefix', 'before_host'])
def test_journal_completion_requires_a_real_guest_accepted_final_checkpoint(mutation):
    pair = receipts()
    if mutation == 'all_lost':
        pair[1]['rows'] = [r for r in pair[1]['rows'] if r['event'] not in ('received', 'applied')]
    elif mutation == 'unapplied':
        pair[1]['rows'] = [r for r in pair[1]['rows'] if r['event'] != 'applied']
    elif mutation == 'old_prefix':
        for receipt in pair:
            for row in receipt['rows']:
                if row['event'] in ('serialized', 'received', 'applied'): row['reaction_through'] = 0
    else:
        for row in pair[0]['rows']:
            if row['event'] == 'reaction_applied': row['at'] = 11.9
    assert not passed(pair)
