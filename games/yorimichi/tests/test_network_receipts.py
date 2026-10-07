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
            skate_seconds=6, maximum_saved_skate_moves=0, received_peer_frames=100, applied_peer_frames=80)))
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
])
def test_received_packets_alone_or_bad_listen_teardown_fail(listen_receipts, name, field, value):
    change(listen_receipts, name, lambda v: v.update({field: value}))
    assert not all(review.compare_receipts(listen_receipts, gameplay=True, listen=True).values())
