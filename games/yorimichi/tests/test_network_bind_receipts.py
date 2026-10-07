"""A failed bind must be real, exclusive and recover the ordinary host UI."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('network_bind_review', Path(__file__).resolve().parents[1] / 'tools/review_network_bind.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)

BIND_LOG = 'Private listener initialization failed: Address already in use'


@pytest.fixture
def recovered():
    return dict(error='', listen_failure_seen=True, net_mode=0, game_mode='/Script/Yorimichi.JapanGameMode',
                has_game_driver=False, local_players=1, players=1, player_pawns=1, friends_menu_open=True,
                session_status='Could not open game port 7777 on Tailscale.')


def test_native_failed_bind_and_visible_solo_recovery_are_required(recovered):
    assert all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered).values())
    assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42).values())
    assert not all(review.bind_checks(0, False, '', [42], 42, recovered).values())
    assert not all(review.bind_checks(0, False, BIND_LOG, [42, 99], 42, recovered).values())


@pytest.mark.parametrize('field,value', [
    ('error', 'Recovery failed'), ('listen_failure_seen', False), ('net_mode', 2),
    ('game_mode', '/Script/Yorimichi.JapanNetworkGameMode'), ('has_game_driver', True),
    ('players', 2), ('player_pawns', 0), ('local_players', 0),
    ('friends_menu_open', False), ('session_status', 'You left the shared session.'),
])
def test_failed_map_or_lost_error_is_not_accepted(recovered, field, value):
    recovered[field] = value
    assert not all(review.bind_checks(0, False, BIND_LOG, [42], 42, recovered).values())


def test_dedicated_requires_exit_one_from_real_bind_failure():
    log = BIND_LOG + '\nPrivate dedicated listener failed: Could not open game port'
    assert all(review.bind_checks(1, True, log, [42], 42).values())
    assert not all(review.bind_checks(0, True, log, [42], 42).values())
    assert not all(review.bind_checks(-15, True, log, [42], 42).values())
    assert not all(review.bind_checks(1, True, 'Private dedicated listener failed: No Tailscale', [42], 42).values())
    assert not all(review.bind_checks(1, True, log, [], 42).values())
