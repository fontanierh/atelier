"""`atelier playtest <game>`: play the game's latest published release, downloading it first if this machine lacks it.

The game's `game.toml` names its releases:

    [release]
    tag = "<game>-macos-"                       # the newest published release whose tag starts with this
    launcher = "<Title>/Play <Title>.command"   # inside the archive; extra arguments are passed on to it
    watch = ["<Title>"]                         # executables the memory guard follows
    log = "Library/Logs/<Title>/game.log"       # the game's log, inside its app's sandbox container

Releases come from the repository's GitHub `origin`, read without credentials. Every file listed in the release's
SHA256SUMS is downloaded and checked against it and against GitHub's own digest; a split archive's parts are joined.
Each transfer gets at most three attempts. Interrupted transfers and verified completed assets can resume
on a later invocation; partial bytes require a matching HTTP range and full final verification. A digest mismatch
discards bad bytes and refreshes the same release's metadata, checksums and failed asset once with cache-busted URLs.
The archive is unpacked with `ditto` under the render lock (as the release check does) into
~/.cache/atelier/playtests/<game>/<tag>, and the download is then deleted. Later runs reuse that folder. Installing the
latest release removes those published before it; `--tag` keeps every other release. One run at a time fetches into the
cache (a file lock); the lock does not cover play, so a game still running from an older `--tag` release can lose its
files when another run installs the latest. The launcher runs under the render lock and memory guard as a game.
"""
import datetime, fcntl, hashlib, http.client, json, plistlib, re, shutil, ssl, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path

from . import manifest, paths

API = 'https://api.github.com'
READY = 'ready.json'     # written last: the folder holds a verified, unpacked release
TRANSFER_ATTEMPTS = 3


class DigestMismatch(SystemExit):
    """A complete download failed verification; never an installable asset."""


def say(text):
    print(text, flush=True)


def repository(remote=None):
    """owner/name of the GitHub `origin` remote."""
    if remote is None:
        remote = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=paths.REPO, capture_output=True,
                                text=True).stdout.strip()
    match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$', remote)
    if not match:
        raise SystemExit(f'origin is not a GitHub repository: {remote!r}')
    return f'{match[1]}/{match[2]}'


def _open(url, accept='application/vnd.github+json', *, headers=None):
    request = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'atelier-playtest', **(headers or {})})
    return urllib.request.urlopen(request, timeout=60)


def _retryable(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (408, 429, 500, 502, 503, 504)
    cause = error.reason if isinstance(error, urllib.error.URLError) else error
    return not isinstance(cause, ssl.SSLCertVerificationError)


TRANSFER_ERRORS = (urllib.error.URLError, TimeoutError, http.client.HTTPException, ConnectionError, ssl.SSLError)


def _cache_busted(url):
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode([*query, ('atelier_retry', uuid.uuid4().hex)])))


def _json(url):
    for attempt in range(TRANSFER_ATTEMPTS):
        try:
            with _open(url) as response:
                return json.load(response)
        except TRANSFER_ERRORS as error:
            if not _retryable(error) or attempt + 1 == TRANSFER_ATTEMPTS:
                raise
            say(f'release metadata transfer interrupted; retry {attempt + 2}/{TRANSFER_ATTEMPTS}')
            time.sleep(attempt + 1)


def releases(repo):
    """The 100 most recent releases (enough to find the latest; `named` looks up older ones)."""
    return _json(f'{API}/repos/{repo}/releases?per_page=100')


def named(repo, tag):
    """The published release called `tag`."""
    try:
        return _json(f'{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}')
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise SystemExit(f'no published release {tag!r}')
        raise


def latest(found, prefix):
    """The newest published release whose tag starts with `prefix`."""
    published = [r for r in found if r['tag_name'].startswith(prefix) and not r.get('draft') and not r.get('prerelease')]
    if not published:
        raise SystemExit(f'no published release whose tag starts with {prefix!r}')
    return max(published, key=lambda r: r['published_at'])


def checksums(text):
    """{file name: SHA-256} from a SHA256SUMS file."""
    sums = {}
    for line in text.splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[name.strip().lstrip('*')] = digest.lower()
    return sums


def _verify(asset, got, expected):
    github = (asset.get('digest') or '').removeprefix('sha256:').lower()
    for what, want in (('SHA256SUMS', expected), ('GitHub', github)):
        if want and got != want:
            raise DigestMismatch(f'{asset["name"]} does not match its {what} digest: {got} != {want}')


def _digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1 << 20):
            result.update(chunk)
    return result


def download(asset, target, say=say, *, expected=None, cache_bust=False):
    """@cc [owner:fontanierh,label:correctness] verified-bounded-release-download
    Transport retries MUST be bounded. Resumed bytes MUST use a matching Content-Range, or restart
    from zero. An asset MUST match its full length and every available digest before promotion.
    A mismatch MUST remove untrusted bytes; an interrupted transfer MAY retain a resumable partial.
    """
    part = target.with_name(target.name + '.part')
    size = asset['size']
    if type(size) is not int or size < 0:
        raise ValueError('release asset size must be a nonnegative integer')
    url = _cache_busted(asset['browser_download_url']) if cache_bust else asset['browser_download_url']
    for attempt in range(TRANSFER_ATTEMPTS):
        done = part.stat().st_size if part.exists() else 0
        if done > size:
            part.unlink()
            done = 0
        digest = _digest(part) if done else hashlib.sha256()
        try:
            if not part.exists() or done != size:
                headers = {'Range': f'bytes={done}-'} if done else {}
                with _open(_cache_busted(url) if attempt else url, 'application/octet-stream',
                           **({'headers': headers} if headers else {})) as response:
                    status = getattr(response, 'status', 200)
                    if status == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if not match or tuple(map(int, match.groups())) != (done, size - 1, size):
                            part.unlink(missing_ok=True)
                            raise http.client.HTTPException('invalid download Content-Range')
                    elif status == 200:
                        done, digest = 0, hashlib.sha256()  # A server may ignore Range.
                    else:
                        raise http.client.HTTPException('unexpected download response')
                    spoken = time.monotonic()
                    with part.open('ab' if done else 'wb') as out:
                        while True:
                            failure = None
                            try:
                                chunk = response.read(1 << 20)
                            except http.client.IncompleteRead as error:
                                chunk, failure = error.partial, error
                            if done + len(chunk) > size:
                                part.unlink(missing_ok=True)
                                raise DigestMismatch(f'{asset["name"]} does not match its published size')
                            out.write(chunk)
                            digest.update(chunk)
                            done += len(chunk)
                            if time.monotonic() - spoken >= 10:
                                say(f'  {asset["name"]}: {done / 2**20:.0f} of {size / 2**20:.0f} MiB')
                                spoken = time.monotonic()
                            if failure:
                                raise failure
                            if not chunk:
                                break
                if done != size:
                    if attempt + 1 == TRANSFER_ATTEMPTS:
                        raise DigestMismatch(f'{asset["name"]} does not match its published size')
                    raise http.client.IncompleteRead(b'', size - done)
            _verify(asset, digest.hexdigest(), expected)
            part.replace(target)
            return digest.hexdigest()
        except DigestMismatch:
            part.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        except TRANSFER_ERRORS as error:
            range_refused = isinstance(error, urllib.error.HTTPError) and error.code == 416 and done > 0
            if range_refused:
                part.unlink(missing_ok=True)
            if not (range_refused or _retryable(error)) or attempt + 1 == TRANSFER_ATTEMPTS:
                raise
            say(f'  {asset["name"]}: transfer interrupted at {done / 2**20:.1f} MiB; '
                f'retry {attempt + 2}/{TRANSFER_ATTEMPTS}')
            time.sleep(attempt + 1)


def _fetch(assets, name, folder, expected=None, say=say, *, cache_bust=False):
    """Download the asset `name` into `folder`, checked against `expected` and GitHub's digest when it has one."""
    if name not in assets:
        raise SystemExit(f'the release has no {name}')
    asset = assets[name]
    target = folder / name
    if target.is_file() and target.stat().st_size == asset['size']:
        try:
            _verify(asset, _digest(target).hexdigest(), expected)
            return target
        except DigestMismatch:
            target.unlink()
    elif target.exists():
        target.unlink()
    download(asset, target, say, expected=expected, cache_bust=cache_bust)
    return target


def unpack(archive, destination, game, tag):
    """`ditto -x -k` under the render lock and memory guard, like the release check's extraction."""
    from .safety import guarded
    destination.mkdir(parents=True)
    code = guarded.run(['ditto', '-x', '-k', str(archive), str(destination)], destination.parent / 'unpack.guard',
                       timeout=900, kind='job', small_gib=3, watch=('ditto',), purpose=f'atelier playtest {game}: unpack {tag}')
    if code:
        raise SystemExit(f'ditto could not unpack {archive.name} (exit {code})')


def ensure(game, release, launcher, prune=True, say=say):
    """The folder holding `release` unpacked, downloading, verifying and unpacking it first if needed. `prune` removes
    the releases published before it once it is ready."""
    root = paths.cache_dir('playtests', game)
    with open(root / '.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say(f'waiting for another atelier playtest fetching into {root}')
            fcntl.flock(lock, fcntl.LOCK_EX)
        folder = _ensure(root, game, release, launcher, say)
        if prune:
            _prune(root, folder, release['published_at'])
        return folder


def _published(folder):
    try:
        return json.loads((folder / READY).read_text())['published_at']
    except (OSError, KeyError, ValueError):
        return ''   # unfinished, or from before published_at was recorded


def _prune(root, keep, published):
    """Remove the cached releases published before `published`, and leftovers of unfinished downloads."""
    for old in root.iterdir():
        if old != keep and old.name != '.lock' and old.is_dir() and _published(old) < published:
            shutil.rmtree(old, ignore_errors=True)


def _ensure(root, game, release, launcher, say):
    tag = release['tag_name']
    folder = root / tag
    if (folder / READY).exists():
        return folder
    say(f'downloading {tag} ({release["html_url"]})')
    staging = root / f'.{tag}.partial'
    downloads = staging / 'download'
    downloads.mkdir(parents=True, exist_ok=True)
    for refresh in range(2):
        assets = {a['name']: a for a in release.get('assets', [])}
        try:
            sums = checksums(_fetch(assets, 'SHA256SUMS', downloads, say=say, cache_bust=bool(refresh)).read_text())
            files = [_fetch(assets, name, downloads, digest, say, cache_bust=bool(refresh))
                     for name, digest in sorted(sums.items())]
            break
        except DigestMismatch:
            if refresh:
                raise
            say('digest mismatch; refreshing release metadata and checksums once to bypass stale CDN data')
            url = release.get('url', '')
            if url.startswith(API + '/repos/'):
                updated = _json(_cache_busted(url))
                if updated['tag_name'] != tag or ('id' in release and updated.get('id') != release['id']):
                    raise SystemExit('release identity changed during download; retry the playtest command')
                release = updated
            for name in ('SHA256SUMS', 'SHA256SUMS.part'):
                (downloads / name).unlink(missing_ok=True)
    zips = [f for f in files if f.suffix == '.zip']
    if len(zips) == 1:
        archive = zips[0]
    else:   # numbered parts: <name>.zip.part-NN, joined in order
        parts = sorted(f for f in files if '.zip.part-' in f.name)
        if not parts or zips:
            raise SystemExit(f'SHA256SUMS lists no single archive or archive parts: {sorted(sums)}')
        archive = downloads / parts[0].name.split('.part-')[0]
        with open(archive, 'wb') as out:
            for part in parts:
                with open(part, 'rb') as source:
                    shutil.copyfileobj(source, out, 1 << 20)
    shutil.rmtree(staging / 'unpacked', ignore_errors=True)
    unpack(archive, staging / 'unpacked', game, tag)
    if not (staging / 'unpacked' / launcher).is_file():
        raise SystemExit(f'{archive.name} has no {launcher}')
    shutil.rmtree(folder, ignore_errors=True)
    (staging / 'unpacked').rename(folder)
    (folder / READY).write_text(json.dumps({'tag': tag, 'published_at': release['published_at'], 'url': release['html_url'],
                                            'archive': archive.name, 'files': sums}, indent=1) + '\n')
    shutil.rmtree(staging)
    say(f'ready: {folder}')
    return folder


def container_log(launcher, log):
    """The game's log in its app's sandbox container (the app sits next to the launcher)."""
    for app in sorted(launcher.parent.glob('*.app')):
        try:
            with open(app / 'Contents' / 'Info.plist', 'rb') as plist:
                bundle = plistlib.load(plist)['CFBundleIdentifier']
        except (OSError, KeyError, plistlib.InvalidFileException):
            return None
        return Path.home() / 'Library' / 'Containers' / bundle / 'Data' / log
    return None


def main(game, tag=None, download_only=False, extra=(), limit_gib=10.):
    if not download_only:
        from .build_snapshot import require_complete
        require_complete(paths.build_root() / game, game=game)
    spec = manifest.game(game).get('release')
    if not spec:
        raise SystemExit(f'{game} has no [release] section in game.toml')
    if sys.platform != 'darwin':
        raise SystemExit('the playtest releases are macOS builds')
    repo = repository()
    release = named(repo, tag) if tag else latest(releases(repo), spec['tag'])
    folder = ensure(game, release, spec['launcher'], prune=not tag)
    if download_only:
        print(f'{release["tag_name"]}: {folder}')
        return 0
    launcher = folder / spec['launcher']
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    logs = paths.build_dir(game) / 'logs' / f'playtest-{release["tag_name"]}-{stamp}'
    logs.mkdir(parents=True, exist_ok=True)
    from .safety import guarded
    print(f'playing {release["tag_name"]}; guard reports in {logs}')
    started = time.time()
    code = guarded.run(['/bin/bash', str(launcher), *extra], logs, purpose=f'atelier playtest {game} {release["tag_name"]}',
                       kind='game', watch=tuple(spec.get('watch', ())), limit_gib=limit_gib)
    log = container_log(launcher, spec['log']) if spec.get('log') else None
    try:
        if log and log.exists() and log.stat().st_mtime >= started:   # this run's log, not an earlier one
            shutil.copy2(log, logs / 'game.log')
            print(f'game log: {logs / "game.log"}')
    except OSError as error:
        print(f'game log not copied: {error}')
    return code
