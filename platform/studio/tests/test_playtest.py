"""`atelier playtest`: choosing the latest release, checking its download and reusing it.

    uv run pytest platform/studio/tests/test_playtest.py

GitHub is replaced by in-memory assets and `ditto` by zipfile; nothing is launched and no lock is taken.
"""
import hashlib, io, json, urllib.error, zipfile

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

    def open(self, url, accept=None):
        self.downloads.append(url)
        return io.BytesIO(self.files[url])

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
