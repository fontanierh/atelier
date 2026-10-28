"""Transport context stays useful without exposing paths, request values or raw errors."""
import errno
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from atelier.harness import capacity_client as client
from atelier.harness import capacity_protocol as wire


@pytest.mark.parametrize('phase,error', [
    ('endpoint', PermissionError(errno.EACCES, 'private endpoint contents')),
    ('connect', ConnectionRefusedError(errno.ECONNREFUSED, 'private connection contents')),
    ('send', BrokenPipeError(errno.EPIPE, 'private send contents')),
    ('receive', TimeoutError('private timeout contents')),
    ('receive', ValueError('private parse contents')),
])
def test_transport_refusal_names_stage_without_retry_or_raw_values(monkeypatch, phase, error):
    channel = Mock()
    channel.__enter__ = Mock(return_value=channel)
    channel.__exit__ = Mock(return_value=False)
    calls = SimpleNamespace(endpoint=Mock(return_value=Path('/private/socket')),
                            send=Mock(), receive=Mock())
    target = calls.endpoint if phase == 'endpoint' else channel.connect if phase == 'connect' else getattr(calls, phase)
    target.side_effect = error
    monkeypatch.setattr(client, '_endpoint', calls.endpoint)
    monkeypatch.setattr(client.socket, 'socket', Mock(return_value=channel))
    monkeypatch.setattr(client.wire, 'send', calls.send)
    monkeypatch.setattr(client.wire, 'receive', calls.receive)
    monkeypatch.setattr(client.time, 'monotonic', lambda: 10.)

    with pytest.raises(wire.CapacityError) as caught:
        client._rpc('/private/socket', {'action': 'check', 'nonce': 'private request contents'}, 2.)
    text = str(caught.value)
    assert 'no fallback admission' in text
    assert f'action=check, phase={phase}, error={type(error).__name__}' in text
    assert f'errno={error.errno if isinstance(error, OSError) else None}' in text
    assert 'elapsed=0.000s, timeout=2.000s' in text
    assert 'private' not in text and 'nonce' not in text
    assert target.call_count == 1  # No transport retry can extend the absolute deadline.


@pytest.mark.parametrize('value', ['private unknown action', '\nprivate', None, [], {'action': []},
                                  {'action': 'private unknown action'}])
def test_unknown_diagnostic_actions_never_echo_input(value):
    assert wire.action_name(value) == 'invalid'


@pytest.mark.parametrize('action', ['check', 'abandon-interrupted', 'abandon-completed', 'abandon-unwitnessed'])
def test_known_diagnostic_action(action):
    assert wire.action_name({'action': action, 'nonce': 'private'}) == action
