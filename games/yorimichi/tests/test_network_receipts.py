"""Session proof must include native identity, collision agreement and both sides of teardown."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('network_review', Path(__file__).resolve().parents[1] / 'tools/review_network_session.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture
def receipts(tmp_path):
    probes = [dict(key=f'zone-{i}', complex=c, hit=True, z=100., normal_z=1.)
              for i in range(20) for c in (False, True)]
    peer = dict(session='shared-session', identity='matching-gameplay', local_players=0,
                net_mode=1, players=1, player_pawns=1, world_ready=True, instances=200,
                rails=12, rail_digest='rails', people=[dict(id='player', rider='Cairo', ready=True)],
                collision_probes=probes, error='')
    for role in ('server', 'client'):
        (tmp_path / f'{role}-connected.json').write_text(json.dumps(peer | (dict(net_mode=3, local_players=1) if role == 'client' else {})))
    (tmp_path / 'server-complete.json').write_text(json.dumps(dict(players=0, player_pawns=0, local_players=0, net_mode=1)))
    (tmp_path / 'client-complete.json').write_text(json.dumps(dict(players=1, player_pawns=1, local_players=1, net_mode=0)))
    return tmp_path


def change(folder, file, edit):
    path = folder / (file + '.json')
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))


def test_complete_native_lifecycle_and_matching_world_pass(receipts):
    assert all(review.compare_receipts(receipts).values())


@pytest.mark.parametrize('file,edit', [
    ('client-connected', lambda v: v.update(identity='stale-collision-build')),
    ('server-connected', lambda v: v.update(local_players=1)),
    ('client-connected', lambda v: v['collision_probes'][3].update(hit=False)),
    ('client-connected', lambda v: v['collision_probes'][2].update(z=101.)),
    ('client-connected', lambda v: v.update(rail_digest='different-lines')),
    ('server-complete', lambda v: v.update(player_pawns=1)),
    ('client-complete', lambda v: v.update(net_mode=3)),
    ('client-complete', lambda v: v.update(players=2)),
])
def test_incomplete_or_mismatched_evidence_fails(receipts, file, edit):
    change(receipts, file, edit)
    assert not all(review.compare_receipts(receipts).values())


def test_process_exit_without_native_receipt_is_not_success(receipts):
    (receipts / 'client-complete.json').unlink()
    with pytest.raises(RuntimeError, match='missing or failed'):
        review.compare_receipts(receipts)


def test_private_listener_requires_the_actual_driver_and_bound_address(receipts):
    endpoint = '127.0.0.1:7777'
    assert not all(review.compare_receipts(receipts, bound_endpoint=endpoint).values())
    change(receipts, 'server-connected', lambda v: v.update(
        bound_endpoint=endpoint, driver_class='/Script/Yorimichi.JapanIpNetDriver'))
    assert all(review.compare_receipts(receipts, bound_endpoint=endpoint).values())
    change(receipts, 'server-connected', lambda v: v.update(bound_endpoint='0.0.0.0:7777'))
    assert not all(review.compare_receipts(receipts, bound_endpoint=endpoint).values())
    change(receipts, 'server-connected', lambda v: v.update(
        bound_endpoint=endpoint, driver_class='/Script/OnlineSubsystemUtils.IpNetDriver'))
    assert not all(review.compare_receipts(receipts, bound_endpoint=endpoint).values())


@pytest.mark.parametrize('lag,variance,loss', [(0, 0, 0), (60, 15, 2)])
def test_emulation_requires_both_live_drivers_to_match(receipts, lag, variance, loss):
    requested = dict(lag_ms=lag, variance_ms=variance, loss_percent=loss)
    actual = dict(order=0, duplicate_percent=0, lag_min_ms=0, lag_max_ms=0,
                  incoming_lag_min_ms=0, incoming_lag_max_ms=0, incoming_loss_percent=0,
                  jitter_ms=0) | requested
    # Merely declaring launch flags cannot certify the network conditions.
    assert not all(review.compare_receipts(receipts, emulation=requested).values())
    for role in ('server', 'client'):
        change(receipts, role + '-connected', lambda v: v.update(emulation=actual))
    assert all(review.compare_receipts(receipts, emulation=requested).values())
    change(receipts, 'client-connected', lambda v: v['emulation'].update(lag_ms=lag + 1))
    assert not all(review.compare_receipts(receipts, emulation=requested).values())
    change(receipts, 'client-connected', lambda v: v.update(emulation=actual))
    change(receipts, 'server-connected', lambda v: v['emulation'].update(order=1))
    assert not all(review.compare_receipts(receipts, emulation=requested).values())


@pytest.fixture
def listen_receipts(receipts):
    for role in ('server', 'client'):
        def add_host(value):
            value.update(players=2, player_pawns=2, local_players=1)
            if role == 'server':
                value['net_mode'] = 2
            value['people'].append(dict(id='host', rider='Cairo', ready=True))
        change(receipts, role + '-connected', add_host)
    change(receipts, 'server-complete', lambda v: v.update(players=1, player_pawns=1, local_players=1, net_mode=2))
    (receipts / 'host').mkdir()
    for name in ('server-gameplay', 'client-gameplay', 'host/client-gameplay'):
        (receipts / (name + '.json')).write_text(json.dumps(dict(passed=True, accepted_pose_frames=100,
            skate_seconds=6, maximum_saved_skate_moves=0, received_peer_frames=100, applied_peer_frames=80,
            jump_cm=60, processed_edges=2, checkpoints_applied=20, checkpoints_rejected=0, interpolated_peer_frames=70, held_peer_frames=10,
            before_buffer_peer_frames=0, after_buffer_peer_frames=0, peer_timestamp_drops=0,
            position_corrections_over_1cm=0, largest_correction_cm=.06)))
    return receipts


def test_listen_pair_requires_both_observers_and_host_survives_leave(listen_receipts):
    assert all(review.compare_receipts(listen_receipts, gameplay=True, listen=True).values())


@pytest.mark.parametrize('name,field,value', [
    ('client-gameplay', 'applied_peer_frames', 0),
    ('host/client-gameplay', 'applied_peer_frames', 0),
    ('client-gameplay', 'received_peer_frames', 0),
    ('host/client-gameplay', 'received_peer_frames', 0),
    ('server-complete', 'player_pawns', 0),
    ('client-complete', 'players', 2),
    ('server-gameplay', 'jump_cm', 0),
    ('server-gameplay', 'processed_edges', 0),
    ('client-gameplay', 'checkpoints_applied', 0),
    ('client-gameplay', 'checkpoints_rejected', 1),
    ('host/client-gameplay', 'interpolated_peer_frames', 0),
    ('client-gameplay', 'held_peer_frames', 100),
    ('client-gameplay', 'after_buffer_peer_frames', 20),
    ('host/client-gameplay', 'before_buffer_peer_frames', 20),
    ('client-gameplay', 'peer_timestamp_drops', 3),
    ('client-gameplay', 'position_corrections_over_1cm', 1),
    ('host/client-gameplay', 'largest_correction_cm', 9.37),
])
def test_received_packets_alone_or_bad_listen_teardown_fail(listen_receipts, name, field, value):
    change(listen_receipts, name, lambda v: v.update({field: value}))
    assert not all(review.compare_receipts(listen_receipts, gameplay=True, listen=True).values())


def test_listen_requires_held_frame_measurement(listen_receipts):
    change(listen_receipts, 'client-gameplay', lambda v: v.pop('held_peer_frames'))
    assert not all(review.compare_receipts(listen_receipts, gameplay=True, listen=True).values())



@pytest.fixture
def combat_receipts(listen_receipts):
    final = []
    for role in ('server', 'client'):
        change(listen_receipts, role + '-connected', lambda v: v.update(emulation=dict(lag_ms=60, variance_ms=15, loss_percent=2)))
    for person_id, person in enumerate(('host', 'guest')):
        for phase, outcome in enumerate((1, 2, 3, 0, 0)):
            report = dict(person=person_id, phase=phase, host_fps=20, passed=True, callbacks=1, outcome=outcome, health_before=100,
                          health_after=92 if outcome == 0 else 100, queued=person_id,
                          resolved=person_id, cancelled=0, parries=int(phase == 0),
                          dodges=int(phase == 1), frame_count=4, frame_min=.05, frame_max=.051,
                          overflows=0, missing_samples=0, authored_fallbacks=0, rejected_defence_times=0,
                          guard_hit=phase == 2, recovering_at_contact=False,
                          contact_lateness_ms=10, window_margin_ms=40, pending_gate_passed=True,
                          pending_skate_refusals=1, pending_travel_refusals=1,
                          source_destroyed_before_resolution=True, forced_flush_passed=True,
                          flushed=int(person_id and phase == 4))
            (listen_receipts / f'combat-{person}-{phase}-result.json').write_text(json.dumps(report))
            confirmed = dict(health=report['health_after'], health_confirm_delay_ms=50, frame_count=4, frame_min=.05 if person_id == 0 else .033,
                             frame_max=.051 if person_id == 0 else .034)
            (listen_receipts / f'combat-{person}-{phase}-confirmed.json').write_text(json.dumps(confirmed))
            final.append(report)
    (listen_receipts / 'combat-final.json').write_text(json.dumps(dict(cases=final)))
    return listen_receipts


def test_combat_requires_measured_decisions_and_lifecycle(combat_receipts):
    assert all(review.compare_receipts(combat_receipts, listen=True, combat=True).values())


@pytest.mark.parametrize('name,field,value', [
    ('combat-host-0-result', 'frame_min', .02),
    ('combat-host-0-result', 'frame_max', .2),
    ('combat-host-0-result', 'host_fps', 30),
    ('combat-guest-2-result', 'rejected_defence_times', 1),
    ('combat-guest-3-confirmed', 'health_confirm_delay_ms', 1200),
    ('combat-host-0-result', 'window_margin_ms', 8),
    ('combat-host-1-result', 'frame_count', 1),
    ('combat-host-0-result', 'parries', 0),
    ('combat-guest-0-result', 'callbacks', 2),
    ('combat-guest-0-confirmed', 'frame_min', .016),
    ('combat-guest-0-result', 'overflows', 1),
    ('combat-guest-0-result', 'missing_samples', 1),
    ('combat-guest-1-result', 'authored_fallbacks', 1),
    ('combat-guest-1-result', 'rejected_defence_times', 1),
    ('combat-guest-1-result', 'dodges', 0),
    ('combat-guest-2-result', 'outcome', 0),
    ('combat-host-2-result', 'guard_hit', False),
    ('combat-guest-2-result', 'recovering_at_contact', True),
    ('combat-guest-3-result', 'source_destroyed_before_resolution', False),
    ('combat-guest-3-result', 'pending_gate_passed', False),
    ('combat-guest-3-result', 'pending_skate_refusals', 0),
    ('combat-guest-3-result', 'pending_travel_refusals', 0),
    ('combat-guest-3-result', 'resolved', 0),
    ('combat-guest-3-result', 'health_after', 100),
    ('combat-guest-3-confirmed', 'health', 100),
    ('combat-guest-4-result', 'flushed', 0),
    ('combat-guest-4-result', 'cancelled', 1),
    ('combat-guest-0-result', 'window_margin_ms', -1),
    ('combat-guest-0-result', 'contact_lateness_ms', -1),
])
def test_combat_cannot_pass_on_success_boolean_alone(combat_receipts, name, field, value):
    change(combat_receipts, name, lambda v: v.update({field: value}))
    assert not all(review.compare_receipts(combat_receipts, listen=True, combat=True).values())


def test_combat_rejects_late_duplicate(combat_receipts):
    change(combat_receipts, 'combat-final', lambda v: v['cases'][0].update(callbacks=2))
    assert not all(review.compare_receipts(combat_receipts, listen=True, combat=True).values())


def test_combat_requires_actual_lag(combat_receipts):
    change(combat_receipts, 'client-connected', lambda v: v['emulation'].update(lag_ms=0))
    assert not all(review.compare_receipts(combat_receipts, listen=True, combat=True).values())


@pytest.mark.parametrize('key', ['overflows', 'missing_samples', 'authored_fallbacks', 'rejected_defence_times', 'frame_min', 'frame_max', 'host_fps'])
def test_combat_requires_gate_measurements(combat_receipts, key):
    change(combat_receipts, 'combat-guest-0-result', lambda v: v.pop(key))
    assert not all(review.compare_receipts(combat_receipts, listen=True, combat=True).values())
