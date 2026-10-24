"""Portable private-pipe framing/failure tests, not a production host/cleanup proof."""
import os
from types import SimpleNamespace

import pytest

from atelier.build_v2 import legacy_client as protocol
from atelier.build_v2.legacy_client import (
    AuthorityLost, AuthorityRefused, LegacyChannel, LegacyClient, decode_record, encode_record,
    authority_now_ns, scheduler_request, validate_scheduler_request,
)


def endpoints():
    host_read, child_write = os.pipe()
    child_read, host_write = os.pipe()
    return host_read, child_write, child_read, host_write


def test_original_private_channel_observes_one_reply_and_never_retries_after_eof():
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline_ns=authority_now_ns() + 2_000_000_000)
    try:
        os.write(host_write, encode_record({'type': 'ack', 'sequence': 1}))
        assert channel.exchange({'sequence': 1}, verify=lambda v: v) == {'type': 'ack', 'sequence': 1}
        assert os.read(host_read, 4096) == encode_record({'sequence': 1})
        os.close(host_write)
        host_write = None
        with pytest.raises(AuthorityLost, match='closed'):
            channel.exchange({'sequence': 2}, verify=lambda v: v)
        os.read(host_read, 4096)  # The uncertain request was sent once, never automatically resent.
        with pytest.raises(AuthorityLost, match='cannot start'):
            channel.exchange({'sequence': 2}, verify=lambda v: v)
        os.set_blocking(host_read, False)
        with pytest.raises(BlockingIOError):
            os.read(host_read, 4096)
    finally:
        channel.close()
        os.close(host_read)
        if host_write is not None:
            os.close(host_write)


@pytest.mark.parametrize('payload', [b'[]', b'{"a":1,"a":2}', b'{"nested":{"x":1,"x":2}}',
                                     b'{"x":NaN}', b'{"x":Infinity}', b'not json'])
def test_strict_authority_records_refuse_positional_duplicates_and_nonfinite(payload):
    with pytest.raises(AuthorityLost):
        decode_record(payload)


def test_authority_encoding_bounds_aggregate_text_before_serialization():
    for record in ({'text': 'a' * 65537}, {'many': ['a' * 24000] * 3},
                   {'bad': '\ud800'}, {'too_large': 2**64}):
        with pytest.raises(AuthorityLost):
            encode_record(record)


def test_truncated_reply_and_failed_closed_verifier_latch_original_channel():
    for reply, verify in [(b'\0\0\0\x10{}', lambda v: v),
                          (encode_record({'type': 'wrong'}), lambda v: (_ for _ in ()).throw(AuthorityLost('wrong reply')))]:
        host_read, child_write, child_read, host_write = endpoints()
        channel = LegacyChannel(child_write, child_read, deadline_ns=authority_now_ns() + 2_000_000_000)
        try:
            os.write(host_write, reply)
            os.close(host_write)
            with pytest.raises(AuthorityLost):
                channel.exchange({'sequence': 1}, verify=verify)
            assert channel.failed
            with pytest.raises(AuthorityLost):
                channel.exchange({'sequence': 2}, verify=verify)
        finally:
            channel.close()
            os.close(host_read)


def test_failed_send_is_typed_unknown_and_cannot_reconnect():
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline_ns=authority_now_ns() + 2_000_000_000)
    os.close(host_read)
    try:
        with pytest.raises(AuthorityLost, match='could not be completed'):
            channel.exchange({'sequence': 1}, verify=lambda v: v)
        assert channel.failed and not channel.pending
        with pytest.raises(AuthorityLost, match='cannot start'):
            channel.exchange({'sequence': 1}, verify=lambda v: v)
    finally:
        channel.close()
        os.close(host_write)


def started_client(host_write, channel):
    host = {'pid': 42, 'boot': 'test-boot', 'started': '100'}
    ready = {'version': 2, 'type': 'ready', 'nonce': 'nonce', 'host': host,
             'clock_domain': protocol.CLOCK_ID,
             'deadline_ns': channel.deadline_ns + 1_000_000_000, 'work_deadline_ns': channel.deadline_ns,
             'selection': 'persistent-selection', 'record_digest': None,
             'frame': None, 'transition_count': 0}
    os.write(host_write, encode_record(ready))
    return LegacyClient.handshake(channel, {'version': 2, 'type': 'hello', 'nonce': 'nonce'},
                                  expected_host=host, deadline_ns=ready['deadline_ns'],
                                  work_deadline_ns=ready['work_deadline_ns'])


@pytest.mark.parametrize('fault', ['nonce', 'sequence', 'permission', 'refused', 'extra', 'bool'])
def test_versioned_client_refuses_uncorrelated_or_wrong_permission_without_state_advance(fault):
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline_ns=authority_now_ns() + 2_000_000_000)
    try:
        client = started_client(host_write, channel)
        reply = {'version': 2, 'type': 'ack', 'nonce': 'nonce', 'selection': 'persistent-selection',
                 'sequence': 1, 'record_digest': 'a' * 64, 'frame': None,
                 'transition_count': 1, 'permission': 'prepared', 'record_page': None}
        if fault == 'nonce':
            reply['nonce'] = 'other-invocation'
        elif fault == 'sequence':
            reply['sequence'] = 2
        elif fault == 'permission':
            reply['permission'] = 'mutation'
        elif fault == 'refused':
            reply.update(type='refused', permission='none')
        elif fault == 'extra':
            reply['unchecked'] = True
        else:
            reply['sequence'] = True
        os.write(host_write, encode_record(reply))
        with pytest.raises(AuthorityRefused if fault == 'refused' else AuthorityLost):
            client.request({'type': 'prepare_selection', 'observation': {}})
        assert channel.failed and client.sequence == 1 and client.record_digest is None
        with pytest.raises(AuthorityLost):
            client.request({'type': 'prepare_selection', 'observation': {}})
    finally:
        channel.close()
        os.close(host_read)
        os.close(host_write)


def test_versioned_client_keeps_original_record_observation_and_finish_is_terminal():
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline_ns=authority_now_ns() + 2_000_000_000)
    try:
        client = started_client(host_write, channel)
        reply = {'version': 2, 'type': 'ack', 'nonce': 'nonce', 'selection': 'persistent-selection',
                 'sequence': 1, 'record_digest': None, 'frame': None,
                 'transition_count': 0, 'permission': 'observed', 'record_page': None}
        os.write(host_write, encode_record(reply))
        client.request({'type': 'observe', 'witnesses': [], 'record_offset': None})
        reply.update(sequence=2, record_digest='a' * 64, transition_count=1, permission='finished')
        os.write(host_write, encode_record(reply))
        client.request({'type': 'finish', 'sources': [], 'outputs': [], 'topology': 'a' * 64})
        assert client.finished
        os.read(host_read, 8192)
        with pytest.raises(AuthorityLost, match='unavailable'):
            client.request({'type': 'observe', 'witnesses': [], 'record_offset': None})
        os.set_blocking(host_read, False)
        with pytest.raises(BlockingIOError):
            os.read(host_read, 8192)
    finally:
        channel.close()
        os.close(host_read)
        os.close(host_write)


def test_original_default_request_has_no_synthetic_task_and_options_remain_explicit():
    request = scheduler_request('ordinary_game', (), verify=True, max_heavy_commands=3)
    assert request['wanted'] == [] and request['options'] == {
        'verify': True, 'max_heavy_commands': 3, 'fail_fast': False}
    assert validate_scheduler_request(decode_record(encode_record(request)[4:])) == request
    for replacement in ([2, 'ordinary_game', [], {}], request | {'extra': 'unchecked'},
                        request | {'options': [True, 3, False]},
                        request | {'options': dict(request['options'], max_heavy_commands=True)}):
        with pytest.raises(AuthorityLost):
            validate_scheduler_request(replacement)


def test_authority_deadline_uses_explicit_posix_clock_and_only_relative_wait_duration(monkeypatch):
    calls = []
    def clock(domain):
        calls.append(domain)
        return 1_000_000_000
    def wrong_clock():
        raise AssertionError('mach-absolute Python monotonic domain must not be used')
    monkeypatch.setattr(protocol, 'time', SimpleNamespace(
        clock_gettime_ns=clock, CLOCK_MONOTONIC=protocol.time.CLOCK_MONOTONIC,
        monotonic=wrong_clock, monotonic_ns=wrong_clock))
    host_read, child_write, child_read, host_write = endpoints()
    try:
        with pytest.raises(AuthorityLost, match='deadline'):
            LegacyChannel(child_write, child_read, deadline_ns=3_000_000_000, clock_domain='mach-absolute')
        channel = LegacyChannel(child_write, child_read, deadline_ns=3_000_000_000)
        waits = []
        def ready(read, write, errors, timeout):
            waits.append(timeout)
            return read, write, []
        monkeypatch.setattr(protocol.select, 'select', ready)
        channel._wait(child_write, writing=True)
        assert waits == [.05] and calls and set(calls) == {protocol.time.CLOCK_MONOTONIC}
        channel.close()
    finally:
        os.close(host_read)
        os.close(host_write)


def test_ordinary_host_lifetime_is_bounded_without_shortening_native_limits(monkeypatch):
    now = 1_000_000_000
    monkeypatch.setattr(protocol, 'authority_now_ns', lambda: now)
    ordinary = protocol.host_budgets()
    assert ordinary == {'clock_domain': 'posix-clock-monotonic-v1',
                        'deadline_ns': now + 48 * 60 * 60 * 1_000_000_000,
                        'startup_budget_ns': 60_000_000_000, 'cleanup_budget_ns': 600_000_000_000}
    earlier = now + 1000_000_000_000
    assert protocol.host_budgets(enclosing_deadline_ns=earlier)['deadline_ns'] == earlier
    assert protocol.host_budgets(enclosing_deadline_ns=ordinary['deadline_ns'] + 1) == ordinary
    for invalid in (True, 1.0, now, now + 660_000_000_000):
        with pytest.raises(AuthorityLost):
            protocol.host_budgets(enclosing_deadline_ns=invalid)


def test_original_rebuild_reasons_are_bounded_request_data_not_permission():
    from atelier.build_v2.legacy_client import scheduler_request, validate_scheduler_request, AuthorityLost
    reason = 'world.closed.task=First guarded cold migration with no verified checkpoint'
    request = scheduler_request('fixture', ['data.stage'], rebuild_reason=[reason])
    assert request['options']['rebuild_reason'] == [reason]
    assert validate_scheduler_request(request) == request
    assert 'rebuild_reason' not in scheduler_request('fixture', [])['options']
    for bad in (True, [True], ['bad\nreason'], ['x'] * 65, ['x' * 1025]):
        record = {**request, 'options': {**request['options'], 'rebuild_reason': bad}}
        with pytest.raises(AuthorityLost):
            validate_scheduler_request(record)
