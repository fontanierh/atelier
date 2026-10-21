"""Private pack retirement, pin lifecycle and cross-machine/read exclusion; no network/native work."""
from copy import deepcopy
import json
import threading

import pytest

from atelier import checkpoint_coordination as coordination, checkpoint_gc as gc, checkpoint_pins as pins, release
from atelier import checkpoint_store as cp
from test_checkpoint_github import checkpoint, fixture, GitHub, Remote, sha


def pin(store, key, name='acceptance', **options):
    folder = store.directory / 'pins'; folder.mkdir(exist_ok=True)
    (folder / (name + '.json')).write_text(json.dumps(dict(schema=1, checkpoints=[key],
        release_when='verified upload and receiving restore accepted', **options)))


def test_release_condition_tombstone_reclaims_bytes_and_stale_file_cannot_resurrect(fixture, tmp_path):
    github, store, remote = fixture
    messages = []; remote.echo = messages.append
    first = checkpoint(store, tmp_path, [b'old'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pin(store, first)
    second = checkpoint(store, tmp_path, [b'new'])
    remote.publish(store, second, 'B', revision='d' * 40)
    assert any(body == b'old' for _, body in github.files.values())
    with remote.transaction():
        pins.release_pin(remote, 'acceptance', 'receiving restore accepted')
    third = checkpoint(store, tmp_path, [b'fresh'])
    newest = remote.publish(store, third, 'C', revision='e' * 40)
    assert first not in newest['retained']
    assert not any(body in (b'old', b'new') for _, body in github.files.values())
    assert pins.all_records(remote)['acceptance']['state'] == 'released'
    assert any('6 bytes freed' in message for message in messages)
    assert len(remote.candidates()) == 1


def test_pin_expiry_uses_shared_server_clock(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'pinned'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pin(store, first, expires=github.now + 10)
    second = checkpoint(store, tmp_path, [b'next'])
    remote.publish(store, second, 'B', revision='d' * 40)
    github.now += 11
    third = checkpoint(store, tmp_path, [b'latest'])
    data = remote.publish(store, third, 'C', revision='e' * 40)
    assert first not in data['retained']
    assert not any(body == b'pinned' for _, body in github.files.values())


def test_failed_upload_pin_protects_parts_until_bounded_retry_expiry(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'partial'])
    def interrupted():
        raise cp.CheckpointError('interrupted')
    with pytest.raises(cp.CheckpointError, match='interrupted'):
        remote.publish(store, first, 'A', revision='c' * 40, revalidate=interrupted)
    second = checkpoint(store, tmp_path, [b'next'])
    remote.publish(store, second, 'B', revision='d' * 40)
    assert any(body == b'partial' for _, body in github.files.values())
    github.now += pins.RETRY_SECONDS + 1
    third = checkpoint(store, tmp_path, [b'latest'])
    remote.publish(store, third, 'C', revision='e' * 40)
    assert not any(body == b'partial' for _, body in github.files.values())


def test_invalid_remote_pin_blocks_all_deletion(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'old'])
    remote.publish(store, first, 'A', revision='c' * 40)
    key = 'f' * 40
    github.commits[key] = dict(message='not valid pin JSON')
    github.refs['refs/' + pins.prefix(remote) + 'bad'] = key
    before = deepcopy(github.files)
    with pytest.raises(cp.CheckpointError, match='Unverifiable remote pin'):
        remote.publish(store, first, 'A', revision='c' * 40)
    assert github.files == before


def test_download_owns_same_atomic_ref_as_collectors(fixture, tmp_path, monkeypatch):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'protected download'])
    data = remote.publish(store, key, 'A', revision='c' * 40)
    original = remote.download
    observations = []
    def protected(asset, target):
        writer = 'refs/' + coordination.reference(remote)
        assert writer in github.refs
        with pytest.raises(release.TransportError):
            github.api('git/refs', method='POST', data=dict(ref=writer, sha='f' * 40))
        observations.append(asset['id'])
        return original(asset, target)
    monkeypatch.setattr(remote, 'download', protected)
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    remote.fetch(remote.candidates()[0], data, receiver)
    assert observations
    assert 'refs/' + coordination.reference(remote) not in github.refs


def test_ambiguous_claim_release_is_not_retried_or_stolen(fixture, tmp_path, monkeypatch):
    github, _, remote = fixture
    target = tmp_path / 'writer.json'
    monkeypatch.setattr(coordination, 'claim_path', lambda remote: target)
    original = github.api
    releases = []
    def uncertain(path, **kw):
        if path == 'git/refs/' + coordination.reference(remote) and kw.get('method') == 'DELETE':
            releases.append(path)
            raise release.TransportError(500)  # Uncertain result, ref still visible.
        return original(path, **kw)
    monkeypatch.setattr(github, 'api', uncertain)
    with coordination.owned(remote):
        pass
    assert cp.read_json(target)['state'] == 'releasing'
    with pytest.raises(cp.CheckpointError, match='release is uncertain'):
        with coordination.owned(remote):
            pytest.fail('uncertain ownership reused')
    assert len(releases) == 1


def test_cross_machine_ref_claim_serializes_independent_writers(fixture, tmp_path, monkeypatch):
    github, _, first = fixture
    second_transport = GitHub()
    second_transport.refs, second_transport.commits = github.refs, github.commits
    second = Remote('owner/artifacts', 'fixture', github=second_transport, echo=lambda _: None)
    first.local_claim, second.local_claim = tmp_path / 'first.json', tmp_path / 'second.json'
    monkeypatch.setattr(coordination, 'claim_path', lambda remote: remote.local_claim)
    entered = threading.Event(); release_first = threading.Event(); entered_second = threading.Event()
    errors = []
    def one():
        try:
            with coordination.owned(first):
                entered.set()
                assert release_first.wait(4)
        except BaseException as error:
            errors.append(error)
    def two():
        try:
            with coordination.owned(second):
                entered_second.set()
        except BaseException as error:
            errors.append(error)
    a = threading.Thread(target=one); b = threading.Thread(target=two)
    a.start(); assert entered.wait(2)
    b.start(); assert not entered_second.wait(.05)
    release_first.set()
    a.join(3); b.join(3)
    assert not a.is_alive() and not b.is_alive() and not errors
    assert entered_second.is_set()


def test_collection_requires_claim_and_valid_authoritative_clock(fixture, tmp_path):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'bytes'])
    index = remote.publish(store, key, 'A', revision='c' * 40)
    with pytest.raises(cp.CheckpointError, match='exclusive writer'):
        gc.collect(remote, remote.candidates()[0], index)
    github.now = float('nan')
    with pytest.raises(cp.CheckpointError, match='Invalid GitHub UTC'):
        pins.live(remote)


def test_normal_joined_cancellation_releases_claim_with_independent_cleanup_event(fixture, tmp_path, monkeypatch):
    github, _, remote = fixture
    target = tmp_path / 'claim.json'
    monkeypatch.setattr(coordination, 'claim_path', lambda remote: target)
    operation_stop = github.stop
    original = github.read
    def respecting_stop(*a, **kw):
        if github.stop.is_set():
            raise release.TransportError()
        return original(*a, **kw)
    monkeypatch.setattr(github, 'read', respecting_stop)
    with coordination.owned(remote):
        operation_stop.set()
    assert github.stop is operation_stop and operation_stop.is_set()
    assert cp.read_json(target)['state'] == 'released'
    assert 'refs/' + coordination.reference(remote) not in github.refs


def test_crashed_held_claim_requires_transport_cleanup_evidence(fixture, tmp_path, monkeypatch):
    github, _, remote = fixture
    target = tmp_path / 'claim.json'
    monkeypatch.setattr(coordination, 'claim_path', lambda remote: target)
    with coordination.owned(remote):
        value = cp.read_json(target)
    value['state'] = 'held'; cp.atomic_json(target, value)
    github.refs['refs/' + coordination.reference(remote)] = value['commit']
    with pytest.raises(cp.CheckpointError, match='worker and transport cleanup proof'):
        with coordination.owned(remote):
            pytest.fail('crashed claim reused without transport cleanup')
    evidence = tmp_path / 'cleanup.json'
    evidence.write_text(json.dumps(dict(schema=1, commit=value['commit'], worker_cleanup_complete=True,
                                        transport_release_resolved=True)))
    coordination.recover(remote, value['commit'], evidence)
    with coordination.owned(remote):
        assert cp.read_json(target)['commit'] != value['commit']


def test_completed_replay_consolidates_released_pin_and_reclaims_its_bytes(fixture, tmp_path):
    github, store, remote = fixture
    messages = []; remote.echo = messages.append
    first = checkpoint(store, tmp_path, [b'pinned'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pin(store, first)
    second = checkpoint(store, tmp_path, [b'latest'])
    remote.publish(store, second, 'B', revision='d' * 40)
    with remote.transaction():
        pins.release_pin(remote, 'acceptance', 'receiving acceptance complete')
    remote.publish(store, second, 'B', revision='d' * 40)
    latest = remote.candidates()[0]
    descriptor = remote.descriptor(latest, tmp_path)
    assert descriptor['key'] == second and first not in descriptor['retained']
    assert len(remote.candidates()) == 1
    assert not any(body == b'pinned' for _, body in github.files.values())
    assert any('6 bytes freed' in message for message in messages)


def test_missing_explicit_pin_descriptor_blocks_retirement_and_collection(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'old'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pin(store, 'f' * 64)
    second = checkpoint(store, tmp_path, [b'next'])
    with pytest.raises(cp.CheckpointError, match='no complete verified descriptor'):
        remote.publish(store, second, 'B', revision='d' * 40)
    assert any(body == b'old' for _, body in github.files.values())
    assert not any(event[0] == 'delete' for event in github.events)


def certified(store, key, action_key, task):
    from atelier import checkpoint_actions as actions
    manifest = store.load(key)
    stamp = dict(manifest['stamps']['asset'], checkpoint_key=action_key)
    roots = [dict(path='generated/0', kind='file')]
    stamp['checkpoint_inventory'] = actions.inventory_identity(roots, manifest['files'])
    action = dict(schema=1, game='fixture', key=action_key, task=task, fingerprint=stamp['fingerprint'],
                  roots=roots, files=manifest['files'], stamp=stamp)
    return store.save(dict(manifest, actions={action_key: action}))


def test_incomparable_completed_indexes_keep_certified_union_after_retry_expiry(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_actions as actions, build
    from types import SimpleNamespace
    github, store, remote = fixture
    first = certified(store, checkpoint(store, tmp_path, [b'actionA']), 'a' * 64, 'A')
    original = github.api
    def stop_first(path, *, method='GET', data=None, pages=False):
        if path == 'releases/1' and method == 'PATCH' and data == dict(draft=False):
            raise release.TransportError(500)
        return original(path, method=method, data=data, pages=pages)
    monkeypatch.setattr(github, 'api', stop_first)
    with pytest.raises(release.TransportError):
        remote.publish(store, first, 'A', revision='c' * 40)
    monkeypatch.setattr(github, 'api', original)
    second = certified(store, checkpoint(store, tmp_path, [b'actionB']), 'b' * 64, 'B')
    remote.publish(store, second, 'B', revision='d' * 40)
    remote.publish(store, first, 'A', revision='c' * 40)
    github.now += pins.RETRY_SECONDS + 1
    remote.publish(store, first, 'A', revision='c' * 40)
    assert len(remote.candidates()) == 1
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    cache = actions.Actions(SimpleNamespace(game='fixture'), dict(repository='owner/artifacts'))
    cache.store, cache.remote = receiver, remote
    for name, action_key, body in [('A', 'a' * 64, b'actionA'), ('B', 'b' * 64, b'actionB')]:
        monkeypatch.setattr(actions, 'key', lambda *a, k=action_key: k)
        assert cache.get(build.Step(name, []), 'b' * 64)['key'] == action_key
        assert receiver.blob(sha(body)).read_bytes() == body


def test_unreferenced_failed_upload_placeholder_is_collected(fixture, tmp_path, monkeypatch):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'live'])
    data = remote.publish(store, key, 'A', revision='c' * 40)
    vault = next(item for item in github.releases.values() if '-cache-packs-' in item['tag_name'])
    name = 'pack-' + 'f' * 64 + '.bin'
    github.files[(vault['id'], name)] = (999, b'')
    original = github.read
    def with_placeholder(path, **kw):
        result = original(path, **kw)
        if 'assets?per_page=' in path:
            for page in result:
                for asset in page:
                    if asset['id'] == 999:
                        asset.update(state='starter', digest=None)
        return result
    monkeypatch.setattr(github, 'read', with_placeholder)
    with remote.transaction():
        result = gc.collect(remote, remote.candidates()[0], data)
    assert result == dict(removed_packs=1, freed_bytes=0)
    assert (vault['id'], name) not in github.files


@pytest.mark.parametrize('transport_failure', [False, True, 'interrupt'])
def test_unobserved_asset_delete_does_not_report_freed_bytes(fixture, tmp_path, monkeypatch, transport_failure):
    github, store, remote = fixture
    target = tmp_path / 'claim.json'
    monkeypatch.setattr(coordination, 'claim_path', lambda remote: target)
    key = checkpoint(store, tmp_path, [b'live'])
    data = remote.publish(store, key, 'A', revision='c' * 40)
    vault = next(item for item in github.releases.values() if '-cache-packs-' in item['tag_name'])
    body = b'orphan'; name = 'pack-' + sha(body) + '.bin'
    github.files[(vault['id'], name)] = (999, body)
    original = github.api
    def unobserved(path, **kw):
        if path == 'releases/assets/999':
            if transport_failure == 'interrupt':
                raise KeyboardInterrupt()
            if transport_failure:
                raise release.TransportError(500)
            return None
        return original(path, **kw)
    monkeypatch.setattr(github, 'api', unobserved)
    messages = []; remote.echo = messages.append
    error = KeyboardInterrupt if transport_failure == 'interrupt' else release.TransportError if transport_failure else cp.CheckpointError
    with remote.transaction(), pytest.raises(error):
        gc.collect(remote, remote.candidates()[0], data)
    assert (vault['id'], name) in github.files
    assert not any('bytes freed' in message for message in messages)
    assert cp.read_json(target)['state'] == 'held'
    assert 'refs/' + coordination.reference(remote) in github.refs
    with pytest.raises(cp.CheckpointError, match='worker and transport cleanup proof'):
        with remote.transaction():
            pytest.fail('unresolved asset mutation ownership reused')


def test_ambiguous_consolidated_publication_keeps_writer_claim(fixture, tmp_path, monkeypatch):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'pinned'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pin(store, first)
    second = checkpoint(store, tmp_path, [b'latest'])
    remote.publish(store, second, 'B', revision='d' * 40)
    with remote.transaction():
        pins.release_pin(remote, 'acceptance', 'receiving acceptance complete')
    target = coordination.claim_path(remote)
    original = github.api
    def uncertain_completion(path, **kw):
        if (kw.get('method') == 'PATCH' and kw.get('data') == dict(draft=False)
                and github.releases[int(path.split('/')[1])]['tag_name'].startswith(remote.prefix + 'index-')):
            raise release.TransportError(500)
        return original(path, **kw)
    monkeypatch.setattr(github, 'api', uncertain_completion)
    with pytest.raises(release.TransportError):
        remote.publish(store, second, 'B', revision='d' * 40)
    assert cp.read_json(target)['state'] == 'held'
    assert 'refs/' + coordination.reference(remote) in github.refs
    assert any(body == b'pinned' for _, body in github.files.values())
