import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('network_jump_replay_review', Path(__file__).parents[1] / 'tools/network_jump_replay_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def receipts(case):
    boundary = case % 3
    target = [.9, 1., 1.1][boundary]
    selected = dict(epoch=2, timestamp=target, edge=2, correction=True, mode=1 if boundary == 0 else 3, z=1000., vz=0. if boundary == 0 else 441., checkpoint=True, checkpoint_bytes=599)
    moves = [dict(timestamp=round(target + .1*i, 6), dt=.1, epoch=2, mode=3,
                  original_z=1000.+i, replayed_z=1000.+i, original_vz=400.-49*i, replayed_vz=400.-49*i) for i in range(1, 4)]
    host, guest = (dict(jump_replay=dict(enabled=True, case=case, responses=[copy.deepcopy(selected)],
                                 forced_epoch=2, forced_count=20, first_force_seconds=.03, last_force_seconds=.7, window_closed=True)),
            dict(jump_replay=dict(enabled=True, case=case, complete=True, replayed=True, error='', applications=1,
                                 epoch=2, target=target, takeoff=1., first_air=1.1, selected=selected, moves=moves)))
    if case >= 3:
        ack = dict(epoch=2, timestamp=round(target + .1, 6), edge=2, correction=False)
        guest['jump_replay'].update(ack=ack, ack_applied=True, pending_before_ack=True, saved_before_ack=3)
        host['jump_replay']['responses'].append(copy.deepcopy(ack))
    return host, guest


@pytest.mark.parametrize('case', range(6))
def test_real_host_boundary_and_replay_pass(case):
    host, guest = receipts(case)
    assert all(review.jump_replay_checks(host, guest, case).values())


@pytest.mark.parametrize('path,value', [
    ('enabled', False), ('case', True), ('complete', False), ('replayed', False), ('error', 'deadline'),
    ('applications', 0), ('applications', 2), ('applications', True), ('epoch', False), ('target', float('nan')),
    ('takeoff', None), ('first_air', 1.), ('selected.checkpoint', False), ('selected.checkpoint_bytes', True),
    ('selected.mode', 1), ('selected.timestamp', 1.2), ('selected.epoch', 1), ('moves', []),
    ('moves', [None, None, None]), ('moves.0.timestamp', 1.3), ('moves.0.dt', False), ('moves.0.epoch', 1),
    ('moves.0.mode', 1), ('moves.0.replayed_z', 1015.), ('moves.0.replayed_vz', 302.),
    ('moves.0.original_z', float('nan')), ('moves.0.replayed_vz', True),
])
def test_missing_corrupt_or_divergent_replay_fails(path, value):
    host, guest = receipts(1)
    target = guest['jump_replay']
    pieces = path.split('.')
    for key in pieces[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    target[pieces[-1]] = value
    assert not all(review.jump_replay_checks(host, guest, 1).values())


@pytest.mark.parametrize('responses', [[], None, False, [{'timestamp': 1.}]])
def test_missing_host_provenance_fails(responses):
    host, guest = receipts(1)
    host['jump_replay']['responses'] = responses
    assert not all(review.jump_replay_checks(host, guest, 1).values())


def test_skipped_replay_move_fails():
    host, guest = receipts(1)
    guest['jump_replay']['moves'].pop(1)
    assert not all(review.jump_replay_checks(host, guest, 1).values())


@pytest.mark.parametrize('key,value', [('epoch', 3), ('timestamp', 1.01), ('edge', 1), ('mode', 1),
    ('checkpoint_bytes', 598), ('checkpoint', False), ('z', 1000.0001), ('vz', 441.0001),
    ('z', float('inf')), ('vz', True), ('edge', True)])
def test_wrong_host_packet_fails(key, value):
    host, guest = receipts(1)
    host['jump_replay']['responses'][0][key] = value
    assert not review.jump_replay_checks(host, guest, 1)['jump_replay_host_response']


@pytest.mark.parametrize('key,value', [('forced_epoch', 1), ('forced_count', 0), ('forced_count', True),
    ('forced_count', 129), ('first_force_seconds', -.1), ('last_force_seconds', 3.),
    ('last_force_seconds', float('nan')), ('first_force_seconds', .8), ('window_closed', False)])
def test_missing_or_excessive_force_window_fails(key, value):
    host, guest = receipts(1)
    host['jump_replay'][key] = value
    assert not review.jump_replay_checks(host, guest, 1)['jump_replay_scoped_window']


@pytest.mark.parametrize('key,value', [('ack', {}), ('ack', None), ('ack_applied', False),
    ('pending_before_ack', False), ('saved_before_ack', True), ('saved_before_ack', 2)])
def test_missing_paired_response_or_pending_replay_fails(key, value):
    host, guest = receipts(4)
    guest['jump_replay'][key] = value
    assert not review.jump_replay_checks(host, guest, 4)['jump_replay_ack_order']


@pytest.mark.parametrize('key,value', [('correction', True), ('timestamp', .9), ('timestamp', float('nan')),
    ('epoch', 1), ('edge', True), ('edge', 3)])
def test_wrong_paired_ack_fails(key, value):
    host, guest = receipts(4)
    guest['jump_replay']['ack'][key] = value
    assert not review.jump_replay_checks(host, guest, 4)['jump_replay_ack_order']


@pytest.mark.parametrize('case', [3, 4, 5])
def test_ack_discarding_first_replay_move_fails(case):
    host, guest = receipts(case)
    guest['jump_replay']['moves'].pop(0)
    assert not review.jump_replay_checks(host, guest, case)['jump_replay_coverage']
