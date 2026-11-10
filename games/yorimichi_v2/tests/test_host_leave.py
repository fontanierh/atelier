"""The packaged host-and-leave judge (tools/package/host_leave.py) against the receipts JapanNetworkQA's host-leave role
writes, and the role's presence in the native QA code."""
import json
import sys
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'package'))
import host_leave as hl  # noqa: E402

QA = GAME / 'unreal/Source/Yorimichi/Dev/JapanNetworkQA.cpp'


def _receipts(folder, connected=None, complete=None, failed=None):
    hosted = {'role': 'host-leave', 'stage': 'connected', 'net_mode': 2, 'game_mode': hl.NETWORK_MODE,
              'has_game_driver': True, 'bound_endpoint': '100.64.0.2:7777', 'session': 'S', 'identity': '1:c:s',
              'local_players': 1, 'player_pawns': 1, 'compiled_code_digest': 'c'}
    solo = {'role': 'host-leave', 'stage': 'complete', 'net_mode': 0, 'game_mode': hl.SOLO_MODE,
            'has_game_driver': False, 'local_players': 1, 'player_pawns': 1, 'compiled_code_digest': 'c'}
    for stage, base, change in (('connected', hosted, connected), ('complete', solo, complete)):
        if change is not False:
            (folder / f'host-leave-{stage}.json').write_text(json.dumps({**base, **(change or {})}))
    if failed:
        (folder / 'host-leave-failed.json').write_text(json.dumps({'error': failed}))


def test_a_hosted_listen_session_that_returns_to_solo_passes(tmp_path):
    _receipts(tmp_path)
    assert all(hl.checks(tmp_path).values())
    assert hl.report(tmp_path, 0) == 0
    assert json.loads((tmp_path / 'checks.json').read_text())['passed'] is True


def test_each_missing_or_wrong_fact_fails_its_check(tmp_path):
    cases = {
        'hosted_listen': ({'net_mode': 0}, None),
        'hosted_driver': ({'bound_endpoint': '100.64.0.2:7778'}, None),
        'hosted_session': ({'session': ''}, None),
        'left_to_solo': (None, {'has_game_driver': True}),
        'solo_rider': (None, {'player_pawns': 0}),
        'same_build': (None, {'compiled_code_digest': 'd'}),
    }
    for name, (connected, complete) in cases.items():
        folder = tmp_path / name
        folder.mkdir()
        _receipts(folder, connected, complete)
        result = hl.checks(folder)
        assert result[name] is False and sum(not ok for ok in result.values()) == 1, name


def test_a_failed_receipt_a_missing_stage_or_a_bad_exit_fails(tmp_path):
    for name, kwargs, code in (('failed', {'failed': 'deadline'}, 0), ('missing', {'complete': False}, 0),
                               ('exit', {}, 1)):
        folder = tmp_path / name
        folder.mkdir()
        _receipts(folder, **kwargs)
        assert not all(hl.checks(folder, code).values()), name
    assert hl.report(tmp_path / 'missing', 0) == 1


def test_the_native_role_hosts_through_the_menu_path_and_leaves():
    """The judge's role exists in the native QA code, calls HostGame then LeaveGame, and saves the two receipts."""
    source = QA.read_text()
    start = source.index('if (NetworkQARole == TEXT("host-leave"))')
    body = source[start:source.index('if (NetworkQARole == TEXT("bind-failure"))', start)]
    order = [body.index(s) for s in ('HostGame(2)', 'WriteNetworkQA(TEXT("connected"))', 'LeaveGame()',
                                    'WriteNetworkQA(TEXT("complete"))')]
    assert order == sorted(order)
    assert 'NetworkQARole != TEXT("host-leave")' in source
