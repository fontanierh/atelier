"""`atelier playtest`: choosing the latest release, checking its download and reusing it.

    uv run pytest platform/studio/tests/test_playtest.py

GitHub is replaced by in-memory assets and `ditto` by zipfile; nothing is launched and no lock is taken.
"""
import hashlib, http.client, io, json, ssl, urllib.error, urllib.parse, zipfile

import pytest

from atelier import playtest
from atelier.cli import parse_args

LAUNCHER = 'Game/Play Game.command'


def release(tag, published, prerelease=False, draft=False, assets=()):
    return {'tag_name': tag, 'published_at': published, 'prerelease': prerelease, 'draft': draft,
            'html_url': f'https://example.invalid/{tag}', 'assets': list(assets)}


@pytest.mark.parametrize('remote', ['https://github.com/owner/repo.git', 'git@github.com:owner/repo.git',
                                    'https://github.com/owner/repo'])
def test_repository_reads_the_github_origin(remote):
    assert playtest.repository(remote) == 'owner/repo'


def test_repository_refuses_other_hosts():
    with pytest.raises(SystemExit, match='not a GitHub'):
        playtest.repository('https://example.invalid/owner/repo.git')


def test_latest_is_the_newest_published_release_with_the_prefix():
    found = [release('game-macos-1', '2026-10-01T00:00:00Z'), release('game-macos-3', '2026-10-03T00:00:00Z'),
             release('game-macos-4', '2026-10-04T00:00:00Z', prerelease=True),
             release('game-macos-5', '2026-10-05T00:00:00Z', draft=True), release('other-9', '2026-10-09T00:00:00Z')]
    assert playtest.latest(found, 'game-macos-')['tag_name'] == 'game-macos-3'
    with pytest.raises(SystemExit, match='no published release'):
        playtest.latest(found, 'missing-')


def test_named_looks_the_tag_up(monkeypatch):
    def open_(url, accept=None):
        if url.endswith('/releases/tags/t1'):
            return io.BytesIO(json.dumps(release('t1', '1')).encode())
        raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
    monkeypatch.setattr(playtest, '_open', open_)
    assert playtest.named('owner/repo', 't1')['tag_name'] == 't1'
    with pytest.raises(SystemExit, match="no published release 't9'"):
        playtest.named('owner/repo', 't9')


def test_checksums_reads_both_shasum_forms():
    assert playtest.checksums('ABC  a.zip\ndef *b.zip\n\n') == {'a.zip': 'abc', 'b.zip': 'def'}


def test_parse_passes_launcher_arguments_after_double_dash():
    args = parse_args(['playtest', 'sandbox', '--tag', 't1', '--', '-windowed'])
    assert (args.command, args.game, args.tag, args.download_only, args.extra) == ('playtest', 'sandbox', 't1', False, ['-windowed'])


def archive():
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr(LAUNCHER, '#!/bin/bash\n')
    return data.getvalue()


class GitHub:
    """Release assets served from memory; `downloads` counts the files fetched."""

    def __init__(self, monkeypatch, files, sums=None, digests=True):
        self.files, self.downloads = files, []
        sums = sums or {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
        self.files['SHA256SUMS'] = ''.join(f'{digest}  {name}\n' for name, digest in sums.items()).encode()
        self.assets = [{'name': name, 'size': len(body), 'browser_download_url': name,
                        **({'digest': 'sha256:' + hashlib.sha256(body).hexdigest()} if digests else {})}
                       for name, body in self.files.items()]
        monkeypatch.setattr(playtest, '_open', self.open)
        monkeypatch.setattr(playtest, 'unpack', self.unpack)

    def open(self, url, accept=None, *, headers=None):
        self.downloads.append(url)
        return io.BytesIO(self.files[urllib.parse.urlsplit(url).path])

    @staticmethod
    def unpack(archive, destination, game, tag):
        destination.mkdir(parents=True)
        zipfile.ZipFile(archive).extractall(destination)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path))
    return tmp_path / 'playtests' / 'sandbox'


def test_ensure_downloads_once_then_reuses_the_folder(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    first = playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert (first / LAUNCHER).is_file() and (first / playtest.READY).is_file()
    assert sorted(github.downloads) == ['Game-1.zip', 'SHA256SUMS']
    assert not list(first.glob('*.zip')), 'the download is deleted once unpacked'
    again = playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert again == first and len(github.downloads) == 2


def test_ensure_joins_numbered_parts(cache, monkeypatch):
    body = archive()
    github = GitHub(monkeypatch, {'Game-1.zip.part-01': body[:40], 'Game-1.zip.part-02': body[40:]})
    folder = playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert (folder / LAUNCHER).is_file()


def test_the_latest_release_replaces_older_ones_only(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    quiet = dict(say=lambda *_: None)
    playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, **quiet)
    playtest.ensure('sandbox', release('t3', '3', assets=github.assets), LAUNCHER, prune=False, **quiet)   # --tag
    assert sorted(p.name for p in cache.iterdir() if p.name != '.lock') == ['t1', 't3']
    playtest.ensure('sandbox', release('t2', '2', assets=github.assets), LAUNCHER, **quiet)
    assert sorted(p.name for p in cache.iterdir() if p.name != '.lock') == ['t2', 't3'], 'newer releases stay'
    (cache / '.t9.partial').mkdir()   # an interrupted download
    playtest.ensure('sandbox', release('t3', '3', assets=github.assets), LAUNCHER, **quiet)
    assert sorted(p.name for p in cache.iterdir() if p.name != '.lock') == ['t3']


@pytest.mark.parametrize('digests', [True, False])
def test_a_checksum_mismatch_leaves_nothing_ready(cache, monkeypatch, digests):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()}, sums={'Game-1.zip': '0' * 64}, digests=digests)
    with pytest.raises(SystemExit, match='does not match its SHA256SUMS digest'):
        playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert not (cache / 't1').exists()
    assert len(github.downloads) == 4, 'one refresh only; a persistent mismatch remains fatal'


def test_github_digest_is_checked_too(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    github.assets[0]['digest'] = 'sha256:' + '0' * 64
    with pytest.raises(SystemExit, match='does not match its GitHub digest'):
        playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)


def test_an_archive_without_the_launcher_is_refused(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    with pytest.raises(SystemExit, match='has no Other/Play.command'):
        playtest.ensure('sandbox', release('t1', '1', assets=github.assets), 'Other/Play.command', say=lambda *_: None)
    assert not (cache / 't1').exists()


class Response(io.BytesIO):
    def __init__(self, body, *, status=200, content_range=None):
        super().__init__(body)
        self.status, self.headers = status, {'Content-Range': content_range} if content_range else {}


def asset(body=b'abcdef'):
    return dict(name='archive.zip', size=len(body), browser_download_url='https://example.invalid/archive.zip',
                digest='sha256:' + hashlib.sha256(body).hexdigest())


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(playtest.time, 'sleep', lambda seconds: None)


@pytest.mark.parametrize('failure', [http.client.IncompleteRead(b'{', 20),
    urllib.error.HTTPError('https://example.invalid', 503, 'Unavailable', {}, None),
    urllib.error.URLError(TimeoutError('handshake timed out'))])
def test_release_metadata_retries_transient_transport(monkeypatch, no_backoff, failure):
    calls = []
    def open_(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise failure
        return Response(json.dumps(release('t1', '1')).encode())
    monkeypatch.setattr(playtest, '_open', open_)
    assert playtest.named('owner/repo', 't1')['tag_name'] == 't1'
    assert len(calls) == 2


def test_incomplete_read_resumes_only_with_matching_content_range(tmp_path, monkeypatch, no_backoff):
    class Interrupted(Response):
        def read(self, size=-1):
            raise http.client.IncompleteRead(b'abc', 3)
    calls = []
    def open_(url, accept=None, *, headers=None):
        calls.append((url, headers))
        if len(calls) == 1:
            return Interrupted(b'')
        assert headers == {'Range': 'bytes=3-'}
        assert 'atelier_retry=' in url
        return Response(b'def', status=206, content_range='bytes 3-5/6')
    monkeypatch.setattr(playtest, '_open', open_)
    target = tmp_path / 'archive.zip'
    assert playtest.download(asset(), target, say=lambda *_: None) == hashlib.sha256(b'abcdef').hexdigest()
    assert target.read_bytes() == b'abcdef' and not target.with_name(target.name + '.part').exists()
    assert len(calls) == 2


@pytest.mark.parametrize('failure', [TimeoutError('SSL handshake timed out'),
                                   urllib.error.URLError(TimeoutError('SSL handshake timed out'))])
def test_ssl_handshake_timeout_retries_without_a_partial(tmp_path, monkeypatch, no_backoff, failure):
    calls = []
    def open_(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise failure
        return Response(b'abcdef')
    monkeypatch.setattr(playtest, '_open', open_)
    target = tmp_path / 'archive.zip'
    playtest.download(asset(), target, say=lambda *_: None)
    assert target.read_bytes() == b'abcdef' and len(calls) == 2


@pytest.mark.parametrize('prefix', [b'abc', b'abb'])
def test_exhausted_transfer_retains_only_partial_for_a_later_invocation(tmp_path, monkeypatch, no_backoff, prefix):
    calls = []
    class Interrupted(Response):
        def read(self, size=-1):
            raise http.client.IncompleteRead(prefix[len(calls) - 1:len(calls)], 4)
    def fail(url, accept=None, *, headers=None):
        calls.append(headers)
        offset = len(calls) - 1
        return Interrupted(b'', status=206 if offset else 200,
                           content_range=f'bytes {offset}-5/6' if offset else None)
    monkeypatch.setattr(playtest, '_open', fail)
    target = tmp_path / 'archive.zip'
    with pytest.raises(http.client.IncompleteRead):
        playtest.download(asset(), target, say=lambda *_: None)
    assert len(calls) == 3 and not target.exists()
    assert (tmp_path / 'archive.zip.part').read_bytes() == prefix
    monkeypatch.setattr(playtest, '_open', lambda *args, **kwargs: Response(b'def', status=206, content_range='bytes 3-5/6'))
    if prefix == b'abc':
        playtest.download(asset(), target, say=lambda *_: None)
        assert target.read_bytes() == b'abcdef'
    else:
        # Corrupt retained prefixes are never accepted, even when the suffix/range is valid.
        with pytest.raises(playtest.DigestMismatch):
            playtest.download(asset(), target, say=lambda *_: None)
        assert not target.exists()
    assert not (tmp_path / 'archive.zip.part').exists()


@pytest.mark.parametrize('range_response', ['ignored', 'wrong', 'refused'])
def test_server_cannot_append_an_unvalidated_range(tmp_path, monkeypatch, no_backoff, range_response):
    target = tmp_path / 'archive.zip'
    (tmp_path / 'archive.zip.part').write_bytes(b'xx')
    calls = []
    def open_(url, accept=None, *, headers=None):
        calls.append(headers)
        if len(calls) == 1:
            assert headers == {'Range': 'bytes=2-'}
            if range_response == 'wrong':
                return Response(b'bcdef', status=206, content_range='bytes 1-5/6')
            if range_response == 'refused':
                raise urllib.error.HTTPError(url, 416, 'Range Not Satisfiable', {}, None)
        else:
            assert headers is None
        return Response(b'abcdef')
    monkeypatch.setattr(playtest, '_open', open_)
    playtest.download(asset(), target, say=lambda *_: None)
    assert target.read_bytes() == b'abcdef'
    assert len(calls) == (1 if range_response == 'ignored' else 2)


@pytest.mark.parametrize('failure', [urllib.error.HTTPError('https://example.invalid', 404, 'Not Found', {}, None),
                                   urllib.error.URLError(ssl.SSLCertVerificationError('untrusted certificate'))])
def test_terminal_http_and_certificate_failures_are_not_retried(tmp_path, monkeypatch, no_backoff, failure):
    calls = []
    def open_(*args, **kwargs):
        calls.append(args)
        raise failure
    monkeypatch.setattr(playtest, '_open', open_)
    with pytest.raises(type(failure)):
        playtest.download(asset(), tmp_path / 'archive.zip', say=lambda *_: None)
    assert len(calls) == 1


@pytest.mark.parametrize('body', [b'abc', b'abcdefg'])
def test_wrong_published_length_cannot_promote_or_retain_untrusted_bytes(tmp_path, monkeypatch, no_backoff, body):
    calls = []
    def open_(*args, **kwargs):
        calls.append(args)
        return Response(body)
    monkeypatch.setattr(playtest, '_open', open_)
    target = tmp_path / 'archive.zip'
    with pytest.raises(playtest.DigestMismatch, match='published size'):
        playtest.download(asset(), target, say=lambda *_: None)
    assert not target.exists() and not (tmp_path / 'archive.zip.part').exists()
    assert len(calls) == (3 if len(body) < 6 else 1)


def test_stale_cdn_archive_is_refetched_once_with_fresh_checksums(cache, monkeypatch):
    body = archive()
    github = GitHub(monkeypatch, {'Game-1.zip': body})
    original = github.open
    requests = []
    def open_(url, accept=None, **kwargs):
        requests.append(url)
        if url == 'Game-1.zip':
            return Response(b'x' * len(body))
        return original(url, accept, **kwargs)
    monkeypatch.setattr(playtest, '_open', open_)
    folder = playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert (folder / playtest.READY).exists()
    assert len(requests) == 4
    assert all('atelier_retry=' in url for url in requests[2:])


def test_stale_cdn_checksum_manifest_is_refetched_once(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    original = github.open
    requests = []
    def open_(url, accept=None, **kwargs):
        requests.append(url)
        if url == 'SHA256SUMS':
            return Response(b'x' * len(github.files['SHA256SUMS']))
        return original(url, accept, **kwargs)
    monkeypatch.setattr(playtest, '_open', open_)
    folder = playtest.ensure('sandbox', release('t1', '1', assets=github.assets), LAUNCHER, say=lambda *_: None)
    assert (folder / playtest.READY).exists() and len(requests) == 3
    assert 'atelier_retry=' in requests[1]


def test_stale_api_digest_refresh_keeps_the_same_release_identity(cache, monkeypatch):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()})
    current = release('t1', '1', assets=github.assets)
    current.update(id=123, url=playtest.API + '/repos/owner/repo/releases/123')
    stale = json.loads(json.dumps(current))
    stale['assets'][0]['digest'] = 'sha256:' + '0' * 64
    original = github.open
    metadata = []
    def open_(url, accept=None, **kwargs):
        if url.startswith(current['url']):
            metadata.append(url)
            return Response(json.dumps(current).encode())
        return original(url, accept, **kwargs)
    monkeypatch.setattr(playtest, '_open', open_)
    folder = playtest.ensure('sandbox', stale, LAUNCHER, say=lambda *_: None)
    assert (folder / playtest.READY).exists() and len(metadata) == 1
    assert 'atelier_retry=' in metadata[0]


@pytest.mark.parametrize('change', [dict(id=456), dict(tag_name='different')])
def test_metadata_refresh_cannot_switch_release_identity(cache, monkeypatch, change):
    github = GitHub(monkeypatch, {'Game-1.zip': archive()}, sums={'Game-1.zip': '0' * 64})
    original = github.open
    spec = release('t1', '1', assets=github.assets)
    spec.update(id=123, url=playtest.API + '/repos/owner/repo/releases/123')
    def open_(url, accept=None, **kwargs):
        if url.startswith(spec['url']):
            return Response(json.dumps(spec | change).encode())
        return original(url, accept, **kwargs)
    monkeypatch.setattr(playtest, '_open', open_)
    with pytest.raises(SystemExit, match='release identity changed'):
        playtest.ensure('sandbox', spec, LAUNCHER, say=lambda *_: None)
    assert not (cache / 't1').exists()


def test_failed_part_retry_reuses_already_verified_downloads(cache, monkeypatch, no_backoff):
    body = archive()
    github = GitHub(monkeypatch, {'Game-1.zip.part-01': body[:40], 'Game-1.zip.part-02': body[40:]})
    original = github.open
    blocked = [True]
    def open_(url, accept=None, **kwargs):
        if blocked[0] and url.startswith('Game-1.zip.part-02'):
            raise TimeoutError('handshake timed out')
        return original(url, accept, **kwargs)
    monkeypatch.setattr(playtest, '_open', open_)
    spec = release('t1', '1', assets=github.assets)
    with pytest.raises(TimeoutError):
        playtest.ensure('sandbox', spec, LAUNCHER, say=lambda *_: None)
    assert not (cache / 't1' / playtest.READY).exists()
    blocked[0] = False
    folder = playtest.ensure('sandbox', spec, LAUNCHER, say=lambda *_: None)
    assert (folder / playtest.READY).exists()
    assert github.downloads.count('SHA256SUMS') == github.downloads.count('Game-1.zip.part-01') == 1
