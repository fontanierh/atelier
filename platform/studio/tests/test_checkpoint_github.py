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
        self.refs = {'refs/heads/main': 'a' * 40}
        self.commits = {'a' * 40: dict(tree=dict(sha='b' * 40), message='baseline')}
        self.now = 1800000000
        self.upload_mutex = threading.Lock()

    def read(self, path, *, missing=False, pages=False):
        path = path.split('?refresh=')[0].split('&refresh=')[0]
        if path.startswith('git/matching-refs/'):
            return [dict(ref=name, object=dict(sha=sha)) for name, sha in self.refs.items() if name.startswith('refs/' + path[len('git/matching-refs/'):])]
        if path.startswith('git/ref/'):
            key = 'refs/' + path[len('git/ref/'):]
            return dict(ref=key, object=dict(sha=self.refs[key])) if key in self.refs else None
        if path.startswith('git/commits/'):
            return self.commits[path.split('/')[-1]]
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
        if path == 'git/commits':
            key = sha(str(data).encode())[:40]
            self.commits[key] = dict(sha=key, tree=dict(sha=data['tree']), message=data['message'])
            return deepcopy(self.commits[key])
        if path == 'git/refs':
            if data['ref'] in self.refs:
                raise release.TransportError(422)
            self.refs[data['ref']] = data['sha']
            return dict(ref=data['ref'], object=dict(sha=data['sha']))
        if path.startswith('git/refs/'):
            key = 'refs/' + path[len('git/refs/'):]
            if method == 'DELETE':
                self.refs.pop(key, None)
                return None
            self.refs[key] = data['sha']
            return dict(ref=key, object=dict(sha=data['sha']))
        if method == 'POST':
            number = max(self.releases, default=0) + 1
            self.releases[number] = dict(id=number, published_at=f'{number:04}', **data)
            self.events.append(('create', number))
            return deepcopy(self.releases[number])
        number = int(path.split('/')[2] if path.startswith('releases/assets/') else path.split('/')[1])
        if method == 'DELETE':
            if path.startswith('releases/assets/'):
                asset_id = int(path.split('/')[2])
                self.files = {key: value for key, value in self.files.items() if value[0] != asset_id}
            else:
                self.releases.pop(number)
                self.files = {key: value for key, value in self.files.items() if key[0] != number}
            self.events.append(('delete', path))
            return None
        self.releases[number].update(data)
        self.events.append(('publish', number))
        return deepcopy(self.releases[number])

    def server_time(self):
        return self.now

    def upload(self, item, path):
        key = (item['id'], path.name)
        body = path.read_bytes()
        # Model the server's unique asset IDs: file reads release the GIL and must
        # finish before the shared allocation/write critical section.
        with self.upload_mutex:
            number = max((value[0] for value in self.files.values()), default=0) + 1
            self.files[key] = (number, body)
            self.events.append(('upload', path.name))
            interrupted, self.interrupt_upload = self.interrupt_upload, False
        if interrupted:
            raise release.TransportError(500)
        return dict(id=number, name=path.name, state='uploaded', size=len(body), digest='sha256:' + sha(body))


def test_fake_transport_allocates_unique_ids_during_concurrent_file_reads(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    github = GitHub()
    item = github.api('releases', method='POST', data=dict(tag_name='parts', draft=True))
    files = [tmp_path / 'one.bin', tmp_path / 'two.bin']
    for path in files:
        path.write_bytes(path.name.encode())
    barrier = threading.Barrier(2)
    original = Path.read_bytes
    def concurrent_read(path):
        body = original(path)
        barrier.wait(timeout=3)
        return body
    monkeypatch.setattr(Path, 'read_bytes', concurrent_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda path: github.upload(item, path), files))
    assert len({value['id'] for value in results}) == 2
    for value, path in zip(results, files):
        assert github.files[(item['id'], path.name)] == (value['id'], path.name.encode())


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
    assert {part['release'] for part in data['blobs'][sha(b'unchanged')]} == {2}
    assert {part['release'] for part in data['blobs'][sha(b'new')]} == {4}
    assert sum(event[0] == 'upload' and event[1].startswith('pack-') for event in github.events) == before + 1
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(github.releases[3], data, receiver) == second


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
    monkeypatch.setenv('ATELIER_REMOTE_CHECKPOINTS', '1')
    cache = actions.Actions(SimpleNamespace(game='fixture'), dict(repository='owner/artifacts'))
    cache.store, cache.remote = receiving, remote
    monkeypatch.setattr(actions, 'key', lambda *a: action_key)
    step = build.Step('asset', [])
    assert cache.get(step, 'b' * 64) == action
    assert receiving.blob(next(iter(manifest['files'].values()))['sha256']).read_bytes() == b'old task'
    # Reuse stays local after network removal.
    cache.remote = None
    assert cache.get(step, 'b' * 64) == action


def legacy_draft(github, remote, key, body):
    tag = remote.prefix + 'legacy'
    item = github.api('releases', method='POST', data=dict(tag_name=tag, name=tag, draft=True,
        body=f'Build checkpoint {key}\nSource {"c" * 40}\nRetain this release: later checkpoints may reference its packs.',
        prerelease=False, target_commitish='main'))
    return item


def test_resume_reuses_legacy_parts_and_bounds_every_new_part(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_packs as packs
    github, store, remote = fixture
    monkeypatch.setattr(packs, 'PART_BYTES', 3)
    key = checkpoint(store, tmp_path, [b'abcdefghijklmno'])
    item = legacy_draft(github, remote, key, b'')
    path = tmp_path / ('pack-' + sha(b'abcdefgh') + '.bin'); path.write_bytes(b'abcdefgh')
    github.upload(item, path)
    data = remote.publish(store, key, 'legacy', revision='c' * 40)
    assert data['blobs'][sha(b'abcdefghijklmno')][0] == dict(release=item['id'], pack=sha(b'abcdefgh'), offset=0, size=8)
    packs_uploaded = [(rid, body) for (rid, name), (_, body) in github.files.items() if name.startswith('pack-')]
    assert all(len(body) <= 3 for rid, body in packs_uploaded if rid != item['id'])
    assert len([e for e in github.events if e == ('upload', path.name)]) == 1
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(item, data, receiver) == key
    assert receiver.blob(sha(b'abcdefghijklmno')).read_bytes() == b'abcdefghijklmno'


def test_newest_index_rehomes_legacy_packs_and_carries_pinned_checkpoint(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'old'])
    item = legacy_draft(github, remote, first, b'')
    pack = tmp_path / ('pack-' + sha(b'old') + '.bin'); pack.write_bytes(b'old')
    github.upload(item, pack)
    old = dict(schema=1, key=first, source_revision='c' * 40, checkpoint=store.load(first),
               blobs={sha(b'old'): [dict(release=item['id'], pack=sha(b'old'), offset=0, size=3)]})
    index = tmp_path / gh.INDEX; index.write_bytes(cp.canonical(old)); github.upload(item, index)
    github.api('releases/1', method='PATCH', data=dict(draft=False))
    pins = store.directory / 'pins'; pins.mkdir()
    (pins / 'fixture.json').write_text(__import__('json').dumps(dict(checkpoints=[first], release_when='fixture acceptance')))
    second = checkpoint(store, tmp_path, [b'new'])
    current = remote.publish(store, second, 'new', revision='d' * 40)
    assert len(remote.candidates()) == 1
    assert github.releases[1]['tag_name'] == 'fixture-cache-packs-retained-1'
    assert (1, pack.name) in github.files
    assert (1, gh.INDEX) not in github.files
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(remote.candidates()[0], current['retained'][first], receiver) == first
    assert receiver.blob(sha(b'old')).read_bytes() == b'old'


def test_failed_new_index_keeps_previous_checkpoint_and_all_its_packs(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'prior'])
    remote.publish(store, first, 'prior', revision='c' * 40)
    old = deepcopy(github.releases[1])
    key = checkpoint(store, tmp_path, [b'next'])
    def changed():
        raise cp.CheckpointError('changed')
    with pytest.raises(cp.CheckpointError, match='changed'):
        remote.publish(store, key, 'next', revision='d' * 40, revalidate=changed)
    assert github.releases[1] == old
    uploads = [e for e in github.events if e[0] == 'upload' and e[1].startswith('pack-')]
    remote.publish(store, key, 'next', revision='d' * 40)
    assert [e for e in github.events if e[0] == 'upload' and e[1].startswith('pack-')] == uploads
    assert len(remote.candidates()) == 1


def test_small_vault_limit_rolls_over_and_restore_follows_each_part(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_packs as packs
    github, store, remote = fixture
    monkeypatch.setattr(packs, 'PART_BYTES', 3)
    monkeypatch.setattr(packs, 'VAULT_ASSETS', 2)
    key = checkpoint(store, tmp_path, [b'abcdefghijklmnopq'])
    data = remote.publish(store, key, 'split', revision='c' * 40)
    vaults = [r for r in github.releases.values() if '-cache-packs-' in r['tag_name']]
    assert len(vaults) == 3
    assert all(len(release.asset_map(github, r)) <= 2 for r in vaults)
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(remote.candidates()[0], data, receiver) == key


def test_private_parallel_uploads_have_bounded_spool(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_packs as packs
    github, store, remote = fixture
    monkeypatch.setattr(packs, 'PART_BYTES', 3)
    original = github.upload
    submit = packs.Spool.submit
    active = maximum = started = peak_bytes = 0
    mutex = threading.Lock()
    first_window = threading.Barrier(6, timeout=5)
    controller = threading.get_ident()

    def measured_submit(spool, path, digest):
        nonlocal peak_bytes
        # Only the controller creates/removes spool files. Worker-side glob/stat
        # races with its legitimate cleanup, regardless of a test-only mutex.
        assert threading.get_ident() == controller
        peak_bytes = max(peak_bytes, sum(p.stat().st_size for p in path.parent.glob('pack-*.bin')))
        return submit(spool, path, digest)

    def slow(item, path):
        nonlocal active, maximum, started
        if not path.name.startswith('pack-'):
            return original(item, path)
        with mutex:
            active += 1; maximum = max(maximum, active)
            started += 1
            first = started <= 6
        try:
            if first:
                first_window.wait()
            return original(item, path)
        finally:
            with mutex:
                active -= 1
    monkeypatch.setattr(packs.Spool, 'submit', measured_submit)
    monkeypatch.setattr(github, 'upload', slow)
    key = checkpoint(store, tmp_path, [bytes(range(100))])
    remote.publish(store, key, 'parallel', revision='c' * 40)
    assert maximum == 6
    assert peak_bytes >= 6 * 3  # The sampler actually observed a populated worker window.
    assert peak_bytes <= 7 * 3  # Six in flight plus one prepared part.
    assert not list(store.directory.glob('tmp*/pack-*.bin'))


@pytest.mark.parametrize('damage', ['missing-pack', 'short-range', 'changed-index', 'changed-old-body'])
def test_retention_never_deletes_prior_checkpoint_on_incomplete_proof(fixture, tmp_path, monkeypatch, damage):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'old'])
    remote.publish(store, first, 'old', revision='c' * 40)
    # Pin the whole older workspace so each proof failure exercises its exact retained bytes.
    pins = store.directory / 'pins'; pins.mkdir()
    (pins / 'test.json').write_text(__import__('json').dumps(dict(checkpoints=[first], release_when='fixture acceptance')))
    if damage == 'missing-pack':
        pack_key = next(key for key in github.files if key[1].startswith('pack-'))
        github.files.pop(pack_key)
    elif damage == 'short-range':
        asset_id, body = github.files[(1, gh.INDEX)]
        index = __import__('json').loads(body)
        next(iter(index['blobs'].values()))[0]['size'] -= 1
        github.files[(1, gh.INDEX)] = (asset_id, cp.canonical(index))
    elif damage == 'changed-old-body':
        github.releases[1]['body'] = 'unknown ownership'
    else:
        original = github.api
        def change_completion(path, *, method='GET', data=None, pages=False):
            result = original(path, method=method, data=data, pages=pages)
            if method == 'PATCH' and data == dict(draft=False) and result['tag_name'].endswith('-next'):
                asset_id, raw = github.files[(result['id'], gh.INDEX)]
                value = __import__('json').loads(raw); value['source_revision'] = 'f' * 40
                github.files[(result['id'], gh.INDEX)] = (asset_id, cp.canonical(value))
            return result
        monkeypatch.setattr(github, 'api', change_completion)
    second = checkpoint(store, tmp_path, [b'new'])
    with pytest.raises((cp.CheckpointError, release.PublishError)):
        remote.publish(store, second, 'next', revision='d' * 40)
    assert 1 in github.releases
    assert not any(event[0] == 'delete' for event in github.events)


def test_retention_leaves_other_games_public_names_and_unfinished_drafts(fixture, tmp_path):
    github, store, remote = fixture
    foreign = []
    for tag in ['other-checkpoint-playtest', 'fixture-macos-playtest', 'fixture-checkpoint-unfinished']:
        item = github.api('releases', method='POST', data=dict(tag_name=tag, name=tag,
            draft=tag.endswith('unfinished'), body='outside completed ownership', target_commitish='main', prerelease=False))
        foreign.append(deepcopy(item))
    key = checkpoint(store, tmp_path, [b'new'])
    remote.publish(store, key, 'new', revision='d' * 40)
    assert all(github.releases[item['id']] == item for item in foreign)


def test_resume_after_full_vault_does_not_overflow_or_reupload(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_packs as packs
    github, store, remote = fixture
    monkeypatch.setattr(packs, 'PART_BYTES', 3)
    monkeypatch.setattr(packs, 'VAULT_ASSETS', 2)
    key = checkpoint(store, tmp_path, [b'abcdefghijklmnopq'])
    original = github.upload
    count = 0
    def interrupt(item, path):
        nonlocal count
        if path.name.startswith('pack-'):
            count += 1
            if count > 2:
                raise release.TransportError(403)
        return original(item, path)
    monkeypatch.setattr(github, 'upload', interrupt)
    with pytest.raises(release.TransportError):
        remote.publish(store, key, 'retry', revision='c' * 40)
    verified = {key for key in github.files if key[1].startswith('pack-')}
    monkeypatch.setattr(github, 'upload', original)
    github.stop.clear()
    remote.publish(store, key, 'retry', revision='c' * 40)
    assert verified <= set(github.files)
    for (_, name) in verified:
        assert len([e for e in github.events if e == ('upload', name)]) == 1
    for item in github.releases.values():
        if '-cache-packs-' in item['tag_name']:
            assert len(release.asset_map(github, item)) <= 2


def test_final_fresh_pack_inventory_refuses_uncommitted_upload_claim(fixture, tmp_path, monkeypatch):
    github, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'uncommitted'])
    def lie(item, path):
        return dict(id=42, state='uploaded', size=path.stat().st_size, digest='sha256:' + sha(path.read_bytes()))
    monkeypatch.setattr(github, 'upload', lie)
    with pytest.raises(cp.CheckpointError, match='missing or changed'):
        remote.publish(store, key, 'lie', revision='c' * 40)
    assert not any(name == gh.INDEX for (_, name) in github.files)
    assert github.releases[1]['draft'] is True


def test_older_completed_retry_cannot_retire_newer_results(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_archive as archive
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'first'])
    remote.publish(store, first, 'A', revision='c' * 40)
    # B completes its index, but retirement is interrupted. Both checkpoints survive.
    actual = archive.retire
    def interrupted(*a, **kw):
        raise cp.CheckpointError('interrupted retirement')
    monkeypatch.setattr(archive, 'retire', interrupted)
    second = checkpoint(store, tmp_path, [b'newer'])
    with pytest.raises(cp.CheckpointError, match='interrupted retirement'):
        remote.publish(store, second, 'B', revision='d' * 40)
    monkeypatch.setattr(archive, 'retire', actual)
    latest_before = remote.candidates()[0]
    remote.publish(store, first, 'A', revision='c' * 40)
    # Replaying A may consolidate metadata, but the latest B result must stay readable.
    latest = remote.candidates()[0]
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(latest, remote.descriptor(latest, tmp_path), receiver) == second
    assert len(remote.candidates()) == 1


def test_new_pin_after_completion_defers_retirement_until_new_checkpoint(fixture, tmp_path, monkeypatch):
    from atelier import checkpoint_archive as archive
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'first'])
    remote.publish(store, first, 'A', revision='c' * 40)
    actual = archive.retire
    def interrupted(*a, **kw):
        raise cp.CheckpointError('interrupted retirement')
    monkeypatch.setattr(archive, 'retire', interrupted)
    second = checkpoint(store, tmp_path, [b'newer'])
    with pytest.raises(cp.CheckpointError, match='interrupted retirement'):
        remote.publish(store, second, 'B', revision='d' * 40)
    monkeypatch.setattr(archive, 'retire', actual)
    pins = store.directory / 'pins'; pins.mkdir()
    (pins / 'new.json').write_text(__import__('json').dumps(dict(checkpoints=[first], release_when='fixture acceptance')))
    remote.publish(store, second, 'B', revision='d' * 40)
    assert len(remote.candidates()) == 1
    assert first in remote.descriptor(remote.candidates()[0], tmp_path)['retained']
    third = checkpoint(store, tmp_path, [b'latest'])
    data = remote.publish(store, third, 'C', revision='e' * 40)
    assert len(remote.candidates()) == 1
    assert first in data['retained']


def test_unreferenced_legacy_pack_owner_is_collected_after_exclusive_save(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'old'])
    item = legacy_draft(github, remote, first, b'')
    path = tmp_path / ('pack-' + sha(b'old') + '.bin'); path.write_bytes(b'old')
    github.upload(item, path)
    old = dict(schema=1, key=first, source_revision='c' * 40, checkpoint=store.load(first),
               blobs={sha(b'old'): [dict(release=1, pack=sha(b'old'), offset=0, size=3)]})
    index = tmp_path / gh.INDEX; index.write_bytes(cp.canonical(old)); github.upload(item, index)
    github.api('releases/1', method='PATCH', data=dict(draft=False))
    second = checkpoint(store, tmp_path, [b'new'])
    newest = remote.publish(store, second, 'next', revision='d' * 40)
    assert sha(b'old') not in newest['blobs']
    assert 1 not in github.releases
    assert (1, path.name) not in github.files
    assert len(remote.candidates()) == 1


def test_published_pin_survives_another_machine_without_local_pin_file(fixture, tmp_path):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'pinned'])
    remote.publish(store, first, 'A', revision='c' * 40)
    pins = store.directory / 'pins'; pins.mkdir()
    local_pin = pins / 'machine-A.json'
    local_pin.write_text(__import__('json').dumps(dict(checkpoints=[first], release_when='fixture acceptance')))
    second = checkpoint(store, tmp_path, [b'next'])
    published = remote.publish(store, second, 'B', revision='d' * 40)
    assert first in published['retained']
    local_pin.unlink()  # A different machine knows only remote published retention roots.
    third = checkpoint(store, tmp_path, [b'latest'])
    newest = remote.publish(store, third, 'C', revision='e' * 40)
    assert first in newest['retained']
    receiver = cp.Store('fixture', tmp_path / 'receiver')
    assert remote.fetch(remote.candidates()[0], newest['retained'][first], receiver) == first
    assert receiver.blob(sha(b'pinned')).read_bytes() == b'pinned'


def test_resume_existing_draft_index_survives_newer_history_without_rewriting(fixture, tmp_path, monkeypatch):
    github, store, remote = fixture
    first = checkpoint(store, tmp_path, [b'first'])
    actual = github.api
    def stop_publication(path, *, method='GET', data=None, pages=False):
        if path == 'releases/1' and method == 'PATCH' and data == dict(draft=False):
            raise release.TransportError(500)
        return actual(path, method=method, data=data, pages=pages)
    monkeypatch.setattr(github, 'api', stop_publication)
    with pytest.raises(release.TransportError):
        remote.publish(store, first, 'A', revision='c' * 40)
    original_completion = github.files[(1, gh.INDEX)]
    monkeypatch.setattr(github, 'api', actual)
    second = checkpoint(store, tmp_path, [b'other'])
    remote.publish(store, second, 'B', revision='d' * 40)
    original_upload = github.upload
    def forbid_rewrite(item, path):
        assert not (item['id'] == 1 and path.name == gh.INDEX)
        return original_upload(item, path)
    monkeypatch.setattr(github, 'upload', forbid_rewrite)
    before = [event for event in github.events if event[0] == 'upload' and event[1].startswith('pack-')]
    result = remote.publish(store, first, 'A', revision='c' * 40)
    assert cp.canonical(result) == original_completion[1]
    assert [event for event in github.events if event[0] == 'upload' and event[1].startswith('pack-')] == before
    assert len(remote.candidates()) == 1
