"""Portable private-pipe framing/failure tests, not a production host/cleanup proof."""
import os
import time

import pytest

from atelier.build_v2.legacy_client import (
    AuthorityLost, AuthorityRefused, LegacyChannel, LegacyClient, decode_record, encode_record,
)


def endpoints():
    host_read, child_write = os.pipe()
    child_read, host_write = os.pipe()
    return host_read, child_write, child_read, host_write


def test_original_private_channel_observes_one_reply_and_never_retries_after_eof():
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline=time.monotonic() + 2)
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


def test_truncated_reply_and_failed_closed_verifier_latch_original_channel():
    for reply, verify in [(b'\0\0\0\x10{}', lambda v: v),
                          (encode_record({'type': 'wrong'}), lambda v: (_ for _ in ()).throw(AuthorityLost('wrong reply')))]:
        host_read, child_write, child_read, host_write = endpoints()
        channel = LegacyChannel(child_write, child_read, deadline=time.monotonic() + 2)
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
    channel = LegacyChannel(child_write, child_read, deadline=time.monotonic() + 2)
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
             'deadline_ns': 999, 'selection': 'persistent-selection', 'record_digest': None,
             'frame': None, 'transition_count': 0}
    os.write(host_write, encode_record(ready))
    return LegacyClient.handshake(channel, {'version': 2, 'type': 'hello', 'nonce': 'nonce'},
                                  expected_host=host, deadline_ns=999)


@pytest.mark.parametrize('fault', ['nonce', 'sequence', 'permission', 'refused', 'extra', 'bool'])
def test_versioned_client_refuses_uncorrelated_or_wrong_permission_without_state_advance(fault):
    host_read, child_write, child_read, host_write = endpoints()
    channel = LegacyChannel(child_write, child_read, deadline=time.monotonic() + 2)
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
    channel = LegacyChannel(child_write, child_read, deadline=time.monotonic() + 2)
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
