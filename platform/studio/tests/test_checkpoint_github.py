"""Private release packs, deduplication and resumable publication, with an in-memory GitHub."""
from copy import deepcopy
import hashlib
from pathlib import Path
import threading

import pytest

from atelier import checkpoint_github as gh, checkpoint_store as cp, release


def sha(value):
    return hashlib.sha256(value).hexdigest()


class GitHub:
    def __init__(self):
        self.repo = 'owner/artifacts'
        self.stop = threading.Event()
        self.private = True
        self.releases, self.files, self.events = {}, {}, []
        self.interrupt_upload = False

    def read(self, path, *, missing=False, pages=False):
        if not path:
            return dict(private=self.private, default_branch='main')
        if path == 'releases?per_page=100':
            return [[deepcopy(value) for value in self.releases.values()]]
        if path.startswith('releases/tags/'):
            return next((deepcopy(r) for r in self.releases.values()
                         if not r['draft'] and r['tag_name'] == path[len('releases/tags/'):]), None)
        release_id = int(path.split('/')[1])
        if path.endswith('assets?per_page=100'):
            return [[dict(id=i, name=name, size=len(body), state='uploaded', digest='sha256:' + sha(body))
                     for (rid, name), (i, body) in self.files.items() if rid == release_id]]
        return deepcopy(self.releases[release_id])

    def api(self, path, *, method='GET', data=None, pages=False):
        if method == 'POST':
            number = len(self.releases) + 1
            self.releases[number] = dict(id=number, published_at=f'{number:04}', **data)
            self.events.append(('create', number))
            return deepcopy(self.releases[number])
        number = int(path.split('/')[1])
        self.releases[number].update(data)
        self.events.append(('publish', number))
        return deepcopy(self.releases[number])

    def upload(self, item, path):
        key = (item['id'], path.name)
        self.files[key] = (len(self.files) + 1, path.read_bytes())
        self.events.append(('upload', path.name))
        if self.interrupt_upload:
            self.interrupt_upload = False
            raise release.TransportError(500)


class Remote(gh.Remote):
    def download(self, asset, destination):
        body = next(body for number, body in self.github.files.values() if number == asset['id'])
        if len(body) != asset['size'] or sha(body) != asset['digest'][7:]:
            raise cp.CheckpointError('Download checksum differs')
        destination.write_bytes(body)


def checkpoint(store, tmp_path, values):
    files = {}
    for index, body in enumerate(values):
        path = tmp_path / f'source{index}'
        path.write_bytes(body)
        digest = sha(body)
        store.put(path, digest)
        files['generated/' + str(index)] = dict(kind='file', size=len(body), sha256=digest, mode=0o644, mtime_ns=1)
    value = dict(schema=1, game='fixture', context={}, checkout='a' * 64, steps=['asset'],
                 files=files, stamps={'asset': dict(fingerprint='b' * 64, seconds=1)})
    return store.save(value)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(gh, 'PACK_BYTES', 8)
    github = GitHub()
    store = cp.Store('fixture', tmp_path / 'store')
    return github, store, Remote('owner/artifacts', 'fixture', github=github, echo=lambda _: None)


def test_pack_round_trip_including_split_duplicate_and_empty_blobs(fixture, tmp_path):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'0123456789abcdef', b'', b'0123456789abcdef', b'other'])
    data = remote.publish(store, key, 'playtest-1', revision='c' * 40)
    assert len(data['blobs']) == 3
    assert github.events[-2][0:2] == ('upload', gh.INDEX)
    assert github.events[-1][0] == 'publish'
    assert not github.releases[1]['draft']
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(github.releases[1], data, receiver) == key
    for digest in data['blobs']:
        assert receiver.blob(digest).read_bytes() == store.blob(digest).read_bytes()


def test_later_release_reuses_prior_packs_without_delta_replay(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'unchanged', b'old'])
    remote.publish(store, first, 'playtest-1', revision='c' * 40)
    before = sum(event[0] == 'upload' and event[1].startswith('pack-') for event in github.events)
    second = checkpoint(store, tmp_path, [b'unchanged', b'new'])
    data = remote.publish(store, second, 'playtest-2', revision='d' * 40)
    assert {part['release'] for part in data['blobs'][sha(b'unchanged')]} == {1}
    assert {part['release'] for part in data['blobs'][sha(b'new')]} == {2}
    assert sum(event[0] == 'upload' and event[1].startswith('pack-') for event in github.events) == before + 1
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(github.releases[2], data, receiver) == second


def test_ambiguous_upload_is_observed_and_completed_assets_are_not_reuploaded(fixture, tmp_path):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'tiny'])
    github.interrupt_upload = True
    remote.publish(store, key, 'playtest-1', revision='c' * 40)
    uploads = [e for e in github.events if e[0] == 'upload']
    assert len(uploads) == 2  # One pack and one final index; ambiguous commit was reused.
    remote.publish(store, key, 'playtest-1', revision='c' * 40)
    assert [e for e in github.events if e[0] == 'upload'] == uploads


def test_public_repository_refuses_before_any_upload(fixture, tmp_path):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'private development output'])
    github.private = False
    with pytest.raises(cp.CheckpointError, match='private repository'):
        remote.publish(store, key, 'playtest-1', revision='c' * 40)
    assert not github.events


def test_changed_source_prevents_completion_and_can_resume(fixture, tmp_path):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'tiny'])
    def changed():
        raise cp.CheckpointError('source changed')
    with pytest.raises(cp.CheckpointError, match='source changed'):
        remote.publish(store, key, 'playtest-1', revision='c' * 40, revalidate=changed)
    assert github.releases[1]['draft']
    assert not any(name == gh.INDEX for (_, name) in github.files)
    remote.publish(store, key, 'playtest-1', revision='c' * 40)
    assert not github.releases[1]['draft']


def test_changed_checkpoint_cannot_clobber_published_tag(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'first'])
    remote.publish(store, first, 'playtest-1', revision='c' * 40)
    second = checkpoint(store, tmp_path, [b'second'])
    with pytest.raises(release.PublishError, match='conflicts'):
        remote.publish(store, second, 'playtest-1', revision='d' * 40)


@pytest.mark.parametrize('damage', ['missing', 'range', 'size', 'digest'])
def test_bad_pack_inventory_never_publishes_a_local_manifest(fixture, tmp_path, damage):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'0123456789abcdef'])
    data = remote.publish(store, key, 'playtest-1', revision='c' * 40)
    damaged = deepcopy(data)
    blob = damaged['blobs'][sha(b'0123456789abcdef')]
    if damage == 'missing':
        damaged['blobs'].clear()
    elif damage == 'range':
        blob[0]['offset'] = -1
    elif damage == 'size':
        blob[0]['size'] -= 1
    else:
        blob[0]['pack'] = 'e' * 64
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    with pytest.raises(cp.CheckpointError):
        remote.fetch(github.releases[1], damaged, receiver)
    assert not list(receiver.manifests.glob('*.json'))


def test_old_task_result_is_found_after_twenty_newer_releases(fixture, tmp_path, monkeypatch):
    from atelier import build, checkpoint_actions as actions
    from types import SimpleNamespace
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'old task'])
    manifest = store.load(key)
    action_key = 'f' * 64
    action = dict(schema=1, game='fixture', key=action_key, task='asset', fingerprint='b' * 64,
                  roots=[dict(path='generated/0', kind='file')], files=manifest['files'], stamp=manifest['stamps']['asset'])
    action['stamp']['checkpoint_key'] = action_key
    action['stamp']['checkpoint_inventory'] = actions.inventory_identity(action['roots'], action['files'])
    old_key = store.save(dict(manifest, actions={action_key: action}))
    remote.publish(store, old_key, 'old', revision='c' * 40)
    for number in range(21):
        remote.publish(store, key, 'new-' + str(number), revision='d' * 40)
    receiving = cp.Store('fixture', tmp_path / 'receiver')
    cache = actions.Actions(SimpleNamespace(game='fixture'), dict(repository='owner/artifacts'))
    cache.store, cache.remote = receiving, remote
    monkeypatch.setattr(actions, 'key', lambda *a: action_key)
    step = build.Step('asset', [])
    assert cache.get(step, 'b' * 64) == action
    assert receiving.blob(next(iter(manifest['files'].values()))['sha256']).read_bytes() == b'old task'
    # Reuse stays local after network removal.
    cache.remote = None
    assert cache.get(step, 'b' * 64) == action
