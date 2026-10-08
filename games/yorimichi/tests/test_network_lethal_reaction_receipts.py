"""Missing death/epoch witnesses cannot turn an ordinary successful session into proof."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
try:
    from network_scheduled_reaction_review import ERROR_COUNTERS, scheduled_reaction_checks
finally:
    sys.path.pop(0)


def receipts(case=8, owner_applied=False):
    count = int(case == 9)
    def receipt(authority):
        stats = dict.fromkeys(ERROR_COUNTERS, 0) | dict(known=0, through=0, issued=count if authority else 0,
            applied=count if authority else int(owner_applied), received=0 if authority else count, replayed=0)
        stats['forced'] = count if authority else 0
        return dict(scheduled_reactions=True, enabled=True, complete=True, error='', packed_responses=True,
            case=case, moving=True, initial_epoch=1, epoch=2, journal_epoch=2, scheduled_stats=stats,
            frame_statistics=dict(count=90, median=1/30, p95=1/30), rows=[], stimuli=[],
            health_changes=[dict(at=10.11, health=0, down=True, epoch=2)], overflow=0, player_id='guest', response_window_end=12., observed_until=13.1,
            position_corrections=0, largest_correction_cm=.05, rejected_checkpoints=0,
            zero_health_at=10.11, dead_input_attempted=True, dead_attack=False, dead_defence=False, dead_frames=20, last_dead_at=12.)
    host, guest = receipt(True), receipt(False)
    hit = dict(event='lethal_hit', at=10., world_time=5., epoch=1, health_before=100-count, health_after=0,
               outcome=0, pending_before=count, issued_after=count, pre_hit_speed=99.9,
               pre_hit_input_y=127, moving_seconds_before_hit=.2)
    host['stimuli'] = [hit, dict(event='stale_reaction_sent', at=10.2, epoch=2, sent_epoch=1, payload_digest='d'*40)]
    if count: host['stimuli'].insert(0, dict(event='hit', at=9.99, world_time=5.))
    def row(event, at, authority, **fields):
        return dict(event=event, at=at, authority=authority, local=not authority, **fields)
    if count:
        identity = dict(reaction_epoch=1, sequence=1, payload_digest='a'*40)
        host['rows'] += [row('reaction_issued', 9.99, True, **identity), row('reaction_applied', 10.01, True, **identity)]
        if owner_applied: guest['rows'].append(row('reaction_applied', 10.02, False, replay=False, **identity))
    host['rows'].append(row('lethal_before_epoch', 10.025, True, epoch=1, journal_epoch=1, known=count,
        through=count, forced=count, pending=False))
    pose = dict(epoch=2, journal_epoch=2, state_available=True, foot_reaction=True, target_free=True,
                handoff_digest='b'*40, applied_digest='b'*40, action='KnockF', handoff_action='KnockF',
                location=[0., 0., 100.], pending_launch=[-380., 0., 280.], health=0)
    host['rows'].append(row('activity_committed', 10.03, True, **copy.deepcopy(pose)))
    guest['rows'].append(row('activity_restored', 10.1, False, **copy.deepcopy(pose)))
    for r, authority, at in ((host, True, 10.16), (guest, False, 10.12)):
        r['rows'].append(row('epoch_first_move', at, authority, epoch=2, journal_epoch=2,
                            stamp=1/30, dt=1/30, start=[0., 0., 100.]))
    for button in ('attack', 'guard'):
        host['rows'].append(row('dead_input', 10.18, True, epoch=2, health=0, down=True,
            attacking=False, guarding=False, parrying=False, button=button))
    guest['rows'].append(row('reaction_wrong_epoch', 10.3, False, epoch=2, journal_epoch=2,
                            reaction_epoch=1, sequence=1, payload_digest='d'*40))
    response = dict(response_epoch=2, stamp=.2, edge=0, correction=True, checkpoint=True,
                    action='KnockF', digest='c'*40, reaction_through=0)
    host['rows'].append(row('serialized', 10.4, True, **response))
    guest['rows'] += [row('received', 10.45, False, **response), row('applied', 10.46, False, **response)]
    return host, guest


def checks(pair, case=8): return scheduled_reaction_checks(*pair, case, True)[0]


@pytest.mark.parametrize('case,owner_applied', [(8, False), (9, False), (9, True)])
def test_lethal_replaces_epoch_with_exact_pending_composition(case, owner_applied):
    result = checks(receipts(case, owner_applied), case)
    assert all(result.values()), result


@pytest.mark.parametrize('role,event', [('host', 'lethal_before_epoch'), ('host', 'activity_committed'),
    ('guest', 'activity_restored'), ('host', 'epoch_first_move'), ('guest', 'epoch_first_move'),
    ('guest', 'reaction_wrong_epoch'), ('guest', 'applied')])
def test_missing_witness_fails(role, event):
    pair = receipts()
    r = pair[role == 'guest']
    found = next(v for v in r['rows'] if v['event'] == event)
    r['rows'].remove(found)
    assert not all(checks(pair).values())


@pytest.mark.parametrize('mutation', ['correction', 'forced', 'uncomposed', 'late_commit', 'late_owner',
    'root', 'launch', 'digest', 'target', 'role', 'old_clock', 'health', 'post_death_issue', 'owner_after_reset',
    'new_journal', 'late_payload_applied', 'no_dead_inputs', 'dead_attack', 'wrong_epoch_probe', 'unrelated_discard', 'open_window', 'different_frame', 'missing_input', 'host_attack', 'host_guard', 'regressed_health'])
def test_forged_or_incomplete_death_proof_fails(mutation):
    host, guest = pair = receipts(9, True)
    def row(r, event): return next(v for v in r['rows'] if v['event'] == event)
    if mutation == 'correction': guest['largest_correction_cm'] = 1.01
    elif mutation == 'forced': host['scheduled_stats']['forced'] = 0
    elif mutation == 'uncomposed': row(host, 'lethal_before_epoch')['through'] = 0
    elif mutation == 'late_commit': row(host, 'activity_committed')['at'] = 10.6
    elif mutation == 'late_owner': row(guest, 'activity_restored')['at'] = 10.6
    elif mutation == 'root': row(guest, 'activity_restored')['location'][0] = 2.
    elif mutation == 'launch': row(guest, 'activity_restored')['pending_launch'][0] = 0.
    elif mutation == 'digest': row(guest, 'activity_restored')['applied_digest'] = 'd'*40
    elif mutation == 'target': row(host, 'activity_committed')['target_free'] = False
    elif mutation == 'role': row(guest, 'activity_restored')['authority'] = True
    elif mutation == 'old_clock': row(host, 'epoch_first_move')['stamp'] = 2.
    elif mutation == 'health': next(r for r in host['stimuli'] if r['event'] == 'lethal_hit')['health_after'] = 1
    elif mutation == 'post_death_issue': row(host, 'reaction_issued')['at'] = 10.02
    elif mutation == 'owner_after_reset': row(guest, 'reaction_applied')['at'] = 10.11
    elif mutation == 'new_journal': guest['journal_epoch'] = 1
    elif mutation == 'late_payload_applied': row(guest, 'reaction_applied')['epoch'] = row(guest, 'reaction_applied')['reaction_epoch'] = 2
    elif mutation == 'no_dead_inputs': guest['dead_input_attempted'] = False
    elif mutation == 'dead_attack': guest['dead_attack'] = True
    elif mutation == 'wrong_epoch_probe': row(guest, 'reaction_wrong_epoch')['reaction_epoch'] = 2
    elif mutation == 'unrelated_discard': row(guest, 'reaction_wrong_epoch')['payload_digest'] = 'e'*40
    elif mutation == 'open_window': guest['observed_until'] = 12.1
    elif mutation == 'different_frame': host['stimuli'][0]['world_time'] -= .033
    elif mutation == 'missing_input': host['rows'] = [r for r in host['rows'] if r['event'] != 'dead_input']
    elif mutation == 'host_attack': host['dead_attack'] = True
    elif mutation == 'host_guard': row(host, 'dead_input')['guarding'] = True
    elif mutation == 'regressed_health': guest['health_changes'].append(dict(at=10.4, health=100, down=True, epoch=2))
    assert not all(checks(pair, 9).values()), mutation


@pytest.mark.parametrize("event", ["activity_committed", "lethal_before_epoch", "epoch_first_move"])
def test_repeated_host_transition_fails(event):
    host, guest = receipts()
    host["rows"].append(copy.deepcopy(next(r for r in host["rows"] if r["event"] == event)))
    assert not all(checks((host, guest)).values())


def test_late_health_notification_and_authoritative_getup_are_distinct():
    host, guest = receipts()
    next(r for r in guest['rows'] if r['event'] == 'activity_restored')['health'] = 100
    host['health_changes'].append(dict(at=12.5, health=100, down=False, epoch=2))
    guest['health_changes'].append(dict(at=12.6, health=100, down=False, epoch=2))
    assert all(checks((host, guest)).values())
    host['health_changes'][-1]['down'] = True
    assert not all(checks((host, guest)).values())


@pytest.mark.parametrize('mutation', ['wrong_epoch', 'partial_health', 'dead_after_getup'])
def test_getup_cannot_hide_a_health_or_dead_witness_error(mutation):
    host, guest = receipts()
    host['health_changes'].append(dict(at=12.5, health=100, down=False, epoch=2))
    guest['health_changes'].append(dict(at=12.6, health=100, down=False, epoch=2))
    if mutation == 'wrong_epoch': host['health_changes'][-1]['epoch'] = 1
    elif mutation == 'partial_health': guest['health_changes'][-1]['health'] = 99
    else: host['last_dead_at'] = 12.6
    assert not all(checks((host, guest)).values())


def test_zero_before_epoch_must_be_reobserved_in_new_epoch():
    host, guest = receipts()
    guest['health_changes'][0]['epoch'] = 1
    assert not all(checks((host, guest)).values())
    guest['health_changes'].append(dict(at=10.12, health=0, down=True, epoch=2))
    assert all(checks((host, guest)).values())
