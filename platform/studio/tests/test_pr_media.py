"""`atelier pr-media push`: PR media go to refs/pr-media/<key> by plumbing alone, append-only, outside the checkout.

    uv run pytest platform/studio/tests/test_pr_media.py

The "GitHub" remote is a local bare repository: its configured URL looks like GitHub (for the owner/repo in the links),
`insteadOf` rewrites it to the bare path, and GIT_ALLOW_PROTOCOL=file keeps git off the network.
"""
import subprocess

import pytest

from atelier import pr_media
from atelier.cli import parse_args

GITHUB = 'https://github.com/example-owner/example-repo.git'
RAW = 'https://raw.githubusercontent.com/example-owner/example-repo'


def run(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    empty = tmp_path / 'gitconfig'
    empty.write_text('')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(empty))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_ALLOW_PROTOCOL', 'file')
    remote, work = tmp_path / 'remote.git', tmp_path / 'work'
    run(tmp_path, 'init', '-q', '--bare', str(remote))
    run(tmp_path, 'init', '-q', '-b', 'main', str(work))
    run(work, 'config', 'user.name', 'Fixture')
    run(work, 'config', 'user.email', 'fixture@example.com')
    run(work, 'config', f'url.{remote.as_uri()}/.insteadOf', 'https://github.com/example-owner/example-repo.git')
    run(work, 'remote', 'add', 'origin', GITHUB)
    (work / 'README').write_text('source\n')
    run(work, 'add', 'README')
    run(work, 'commit', '-q', '-m', 'source')
    run(work, 'push', '-q', 'origin', 'main')
    return work


def media(folder, name, data):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def remote_ref(repo, key):
    out = subprocess.run(['git', 'ls-remote', 'origin', f'refs/pr-media/{key}'], cwd=repo, capture_output=True,
                         text=True, check=True).stdout.split()
    return out[0] if out else None


def checkout_state(repo):
    return (run(repo, 'rev-parse', 'HEAD'), run(repo, 'symbolic-ref', 'HEAD'), run(repo, 'status', '--porcelain'),
            run(repo, 'for-each-ref', 'refs/heads', 'refs/tags', 'refs/remotes'), (repo / '.git/index').read_bytes())


def test_first_push_creates_the_ref_and_prints_links(repo, tmp_path, capsys):
    shot = media(tmp_path / 'media', 'before shot.png', b'png one')
    film = media(tmp_path / 'media', 'run.mp4', b'mp4 one')
    assert pr_media.push('42', [shot, film], repo=repo) == 0
    sha = remote_ref(repo, '42')
    assert sha and run(repo, 'rev-parse', 'refs/pr-media/42') == sha
    assert capsys.readouterr().out.splitlines() == [f'![before shot.png]({RAW}/{sha}/before%20shot.png)',
                                                     f'[run.mp4]({RAW}/{sha}/run.mp4)']
    assert run(tmp_path / 'remote.git', 'show', f'{sha}:before shot.png') == 'png one'
    assert run(tmp_path / 'remote.git', 'rev-list', '--parents', '-n1', sha) == sha   # no parent


def test_second_push_keeps_earlier_files_replaces_same_names_and_extends_history(repo, tmp_path, capsys):
    first = pr_media.push('pr-slug', [media(tmp_path / 'a', 'keep.png', b'keep'),
                                      media(tmp_path / 'a', 'shot.png', b'old')], repo=repo)
    old = remote_ref(repo, 'pr-slug')
    run(repo, 'update-ref', '-d', 'refs/pr-media/pr-slug')   # the remote's ref is fetched, not the local cache trusted
    assert first == 0 and pr_media.push('pr-slug', [media(tmp_path / 'b', 'shot.png', b'new'),
                                                    media(tmp_path / 'b', 'more.gif', b'gif')], repo=repo) == 0
    new = remote_ref(repo, 'pr-slug')
    assert run(tmp_path / 'remote.git', 'rev-list', '--parents', '-n1', new).split() == [new, old]
    assert sorted(run(tmp_path / 'remote.git', 'ls-tree', '--name-only', new).splitlines()) == ['keep.png', 'more.gif', 'shot.png']
    assert run(tmp_path / 'remote.git', 'show', f'{new}:shot.png') == 'new'
    assert run(tmp_path / 'remote.git', 'show', f'{new}:keep.png') == 'keep'
    assert run(tmp_path / 'remote.git', 'show', f'{old}:shot.png') == 'old'   # earlier links still resolve
    assert capsys.readouterr().out.splitlines()[-2:] == [f'![shot.png]({RAW}/{new}/shot.png)',
                                                         f'![more.gif]({RAW}/{new}/more.gif)']


def test_worktree_index_head_and_branches_are_untouched(repo, tmp_path):
    before = checkout_state(repo)
    pr_media.push('7', [media(tmp_path, 'a.png', b'a')], repo=repo)
    pr_media.push('7', [media(tmp_path, 'b.webp', b'b')], repo=repo)
    pr_media.push('8', [media(tmp_path, 'c.jpg', b'c')], repo=repo, dry_run=True)
    assert checkout_state(repo) == before
    assert run(tmp_path / 'remote.git', 'for-each-ref', '--format=%(refname)').splitlines() == [
        'refs/heads/main', 'refs/pr-media/7']


def test_dry_run_builds_the_commit_but_creates_no_remote_ref(repo, tmp_path, capsys):
    assert pr_media.push('9', [media(tmp_path, 'a.png', b'a')], repo=repo, dry_run=True) == 0
    line = capsys.readouterr().out.strip()
    sha = line.split('/')[-2]
    assert line == f'![a.png]({RAW}/{sha}/a.png)'
    assert run(repo, 'cat-file', '-t', sha) == 'commit'
    assert remote_ref(repo, '9') is None
    assert subprocess.run(['git', 'rev-parse', '--verify', '-q', 'refs/pr-media/9'], cwd=repo).returncode


def test_a_non_fast_forward_update_is_refused_not_forced(repo, tmp_path, monkeypatch):
    pr_media.push('5', [media(tmp_path, 'a.png', b'a')], repo=repo)
    kept = remote_ref(repo, '5')
    monkeypatch.setattr(pr_media, 'remote_head', lambda *args: None)   # as if another push landed after our fetch
    with pytest.raises(SystemExit, match='push to refs/pr-media/5 failed'):
        pr_media.push('5', [media(tmp_path, 'b.png', b'b')], repo=repo)
    assert remote_ref(repo, '5') == kept


@pytest.mark.parametrize('key', ['', 'a/b', '-x', '.x', 'x..y', 'x.lock', 'x.', 'a b', 'x' * 101])
def test_unsafe_keys_are_refused(repo, tmp_path, key):
    with pytest.raises(SystemExit, match='pr-media key'):
        pr_media.push(key, [media(tmp_path, 'a.png', b'a')], repo=repo)


def test_file_validation(repo, tmp_path, monkeypatch, capsys):
    good = media(tmp_path / 'one', 'a.png', b'a')
    with pytest.raises(SystemExit, match='not a regular file'):
        pr_media.push('1', [str(tmp_path / 'missing.png')], repo=repo)
    with pytest.raises(SystemExit, match='not a regular file'):
        pr_media.push('1', [str(tmp_path / 'one')], repo=repo)
    with pytest.raises(SystemExit, match='not a media file'):
        pr_media.push('1', [media(tmp_path, 'notes.txt', b'x')], repo=repo)
    with pytest.raises(SystemExit, match='also named'):
        pr_media.push('1', [good, media(tmp_path / 'two', 'a.png', b'b')], repo=repo)
    monkeypatch.setattr(pr_media, 'MAX_BYTES', 4)
    with pytest.raises(SystemExit, match='over the'):
        pr_media.push('1', [media(tmp_path, 'big.mov', b'12345')], repo=repo)
    assert remote_ref(repo, '1') is None
    monkeypatch.setattr(pr_media, 'WARN_BYTES', 0)
    assert pr_media.push('1', [media(tmp_path, 'UPPER.JPG', b'1')], repo=repo, dry_run=True) == 0
    assert 'warning: ' in capsys.readouterr().err


@pytest.mark.parametrize('url', ['https://github.com/own-er/re.po.git', 'https://github.com/own-er/re.po',
                                 'https://github.com/own-er/re.po/', 'git@github.com:own-er/re.po.git',
                                 'ssh://git@github.com/own-er/re.po.git', 'https://token@github.com/own-er/re.po.git'])
def test_github_remote_urls(url):
    assert pr_media.github_repository(url) == ('own-er', 're.po')


@pytest.mark.parametrize('url', ['/tmp/remote.git', 'https://gitlab.com/own/repo.git', 'https://github.com/own'])
def test_non_github_remote_urls(url):
    assert pr_media.github_repository(url) is None


def test_non_github_remote_is_refused_before_anything_is_written(repo, tmp_path):
    run(repo, 'remote', 'add', 'elsewhere', str(tmp_path / 'remote.git'))
    with pytest.raises(SystemExit, match='not a GitHub repository'):
        pr_media.push('3', [media(tmp_path, 'a.png', b'a')], remote='elsewhere', repo=repo)


def test_markdown_escapes_and_encodes_names():
    raw = 'https://raw.githubusercontent.com/o/r/abc'
    assert pr_media.markdown('o', 'r', 'abc', 'a [b]#?.png') == rf'![a \[b\]#?.png]({raw}/a%20%5Bb%5D%23%3F.png)'
    assert pr_media.markdown('o', 'r', 'abc', 'clip.WEBM') == f'[clip.WEBM]({raw}/clip.WEBM)'


def test_cli_parses_push():
    args = parse_args(['pr-media', 'push', '276', 'a.png', 'b.mp4', '--remote', 'upstream', '--dry-run'])
    assert (args.command, args.action, args.key, args.files, args.remote, args.dry_run) == (
        'pr-media', 'push', '276', ['a.png', 'b.mp4'], 'upstream', True)
    assert parse_args(['pr-media', 'push', '276', 'a.png']).remote == 'origin'
