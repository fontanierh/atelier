"""A failed bind must be real, exclusive and recover the ordinary host UI."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('network_bind_review', Path(__file__).resolve().parents[1] / 'tools/review_network_bind.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

BIND_LOG = 'Private listener initialization failed: Address already in use'
LIVE = dict(game_alive_before=True, game_alive_after=True, no_game_port=True, sole_blocker=True)


@pytest.fixture
def recovered():
    return dict(error='', listen_failure_seen=True, net_mode=0, game_mode='/Script/Yorimichi.JapanGameMode',
                has_game_driver=False, local_players=1, players=1, player_pawns=1, friends_menu_open=True,
                session_status='Could not open game port 7777 on Tailscale.')


def test_native_failed_bind_and_visible_solo_recovery_are_required(recovered):
    assert all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered, LIVE).values())
    assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42).values())
    assert not all(review.bind_checks(0, False, '', [42], 42, recovered, LIVE).values())
    assert not all(review.bind_checks(0, False, BIND_LOG, [42, 99], 42, recovered, LIVE).values())


@pytest.mark.parametrize('field,value', [
    ('error', 'Recovery failed'), ('listen_failure_seen', False), ('net_mode', 2),
    ('game_mode', '/Script/Yorimichi.JapanNetworkGameMode'), ('has_game_driver', True),
    ('players', 2), ('player_pawns', 0), ('local_players', 0),
    ('friends_menu_open', False), ('session_status', 'You left the shared session.'),
])
def test_failed_map_or_lost_error_is_not_accepted(recovered, field, value):
    recovered[field] = value
    assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered, LIVE).values())


def test_dedicated_requires_exit_one_from_real_bind_failure():
    log = BIND_LOG + '\nPrivate dedicated listener failed: Could not open game port\nLogExit: Exiting.'
    assert all(review.bind_checks(1, True, log, [42], 42).values())
    assert not all(review.bind_checks(0, True, log, [42], 42).values())
    assert not all(review.bind_checks(-15, True, log, [42], 42).values())
    assert not all(review.bind_checks(1, True, 'Private dedicated listener failed: No Tailscale', [42], 42).values())
    assert not all(review.bind_checks(1, True, log, [], 42).values())
    assert not all(review.bind_checks(1, True, log.replace('LogExit: Exiting.', ''), [42], 42).values())


def test_port_receipt_after_exit_cannot_certify_live_recovery(recovered):
    assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered).values())
    for key in LIVE:
        assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered, LIVE | {key: False}).values())


@pytest.mark.parametrize('socket_name,expected', [
    ('*:7777', False), ('[::1]:7777', False), ('192.0.2.3:7777', False),
    ('192.0.2.3:45000->192.0.2.4:7777', True), ('*:45000', True),
])
def test_live_socket_probe_checks_local_port_on_every_address(monkeypatch, socket_name, expected):
    from types import SimpleNamespace
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='p99\nn' + socket_name + '\n')
    monkeypatch.setattr(review.subprocess, 'run', run)
    assert review.process_udp(99, 7777)['no_game_port'] is expected
    assert calls == [['lsof', '-nP', '-a', '-p', '99', '-iUDP', '-Fpn']]


@pytest.fixture(params=['review_network_bind.py', 'review_network_session.py'])
def process_runner(request):
    path = Path(__file__).resolve().parents[1] / 'tools' / request.param
    spec = importlib.util.spec_from_file_location('guard_lifecycle_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('exit_code', [0, 1])
def test_normal_child_exit_between_guard_polls_is_reaped(process_runner, exit_code):
    from unittest.mock import Mock
    game = Mock(); game.poll.side_effect = [None, exit_code]
    guard = Mock(); guard.poll.return_value = 0
    assert process_runner.guarded_game_running(game, guard, 'host') is False
    assert game.poll.call_count == 2


@pytest.mark.parametrize('guard_exit,child_exit', [(0, None), (1, None), (1, 0), (-9, None)])
def test_stopped_guard_never_leaves_live_game_running(process_runner, guard_exit, child_exit):
    from unittest.mock import Mock
    game = Mock(); game.poll.side_effect = [None, child_exit]
    guard = Mock(); guard.poll.return_value = guard_exit
    with pytest.raises(RuntimeError, match='lost its actual-child guard'):
        process_runner.guarded_game_running(game, guard, 'host')
