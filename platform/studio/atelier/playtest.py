"""`atelier playtest <game>`: play the game's latest published release, downloading it first if this machine lacks it.

The game's `game.toml` names its releases:

    [release]
    tag = "<game>-macos-"                       # the newest published release whose tag starts with this
    launcher = "<Title>/Play <Title>.command"   # inside the archive; extra arguments are passed on to it
    watch = ["<Title>"]                         # executables the memory guard follows
    log = "Library/Logs/<Title>/game.log"       # the game's log, inside its app's sandbox container

Releases come from the repository's GitHub `origin`, read without credentials. Every file listed in the release's
SHA256SUMS is downloaded and checked against it and against GitHub's own digest; a split archive's parts are joined.
The archive is unpacked with `ditto` under the render lock (as the release check does) into
~/.cache/atelier/playtests/<game>/<tag>, and the download is then deleted. Later runs reuse that folder. Once a newer
release is unpacked, older ones are removed. The launcher runs under the render lock and memory guard as a game.
"""
import datetime, hashlib, json, plistlib, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

from . import manifest, paths

API = 'https://api.github.com'
READY = 'ready.json'     # written last: the folder holds a verified, unpacked release


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


def _open(url, accept='application/vnd.github+json'):
    request = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'atelier-playtest'})
    return urllib.request.urlopen(request, timeout=60)


def releases(repo):
    with _open(f'{API}/repos/{repo}/releases?per_page=100') as response:
        return json.load(response)


def choose(found, prefix, tag=None):
    """The release called `tag`, or the newest published release whose tag starts with `prefix`."""
    if tag:
        named = [r for r in found if r['tag_name'] == tag and not r.get('draft')]
        if not named:
            raise SystemExit(f'no published release {tag!r}')
        return named[0]
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


def download(asset, target, say=say):
    """Download one release asset to `target` and return its SHA-256. Progress is printed every ten seconds."""
    part = target.with_name(target.name + '.part')
    digest, done, spoken = hashlib.sha256(), 0, time.monotonic()
    with _open(asset['browser_download_url'], 'application/octet-stream') as response, open(part, 'wb') as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if time.monotonic() - spoken >= 10:
                say(f'  {asset["name"]}: {done / 2**20:.0f} of {asset["size"] / 2**20:.0f} MiB')
                spoken = time.monotonic()
    part.rename(target)
    return digest.hexdigest()


def _fetch(assets, name, folder, expected=None, say=say):
    """Download the asset `name` into `folder`, checked against `expected` and GitHub's digest when it has one."""
    if name not in assets:
        raise SystemExit(f'the release has no {name}')
    asset = assets[name]
    got = download(asset, folder / name, say)
    github = (asset.get('digest') or '').removeprefix('sha256:').lower()
    for what, want in (('SHA256SUMS', expected), ('GitHub', github)):
        if want and got != want:
            raise SystemExit(f'{name} does not match its {what} digest: {got} != {want}')
    return folder / name


def unpack(archive, destination, game, tag):
    """`ditto -x -k` under the render lock and memory guard, like the release check's extraction."""
    from .safety import guarded
    destination.mkdir(parents=True)
    code = guarded.run(['ditto', '-x', '-k', str(archive), str(destination)], destination.parent / 'unpack.guard',
                       timeout=900, kind='job', small_gib=3, watch=('ditto',), purpose=f'atelier playtest {game}: unpack {tag}')
    if code:
        raise SystemExit(f'ditto could not unpack {archive.name} (exit {code})')


def ensure(game, release, launcher, say=say):
    """The folder holding `release` unpacked, downloading, verifying and unpacking it first if needed."""
    root = paths.cache_dir('playtests', game)
    tag = release['tag_name']
    folder = root / tag
    if (folder / READY).exists():
        return folder
    say(f'downloading {tag} ({release["html_url"]})')
    staging = root / f'.{tag}.partial'
    shutil.rmtree(staging, ignore_errors=True)
    downloads = staging / 'download'
    downloads.mkdir(parents=True)
    assets = {a['name']: a for a in release.get('assets', [])}
    sums = checksums(_fetch(assets, 'SHA256SUMS', downloads, say=say).read_text())
    files = [_fetch(assets, name, downloads, digest, say) for name, digest in sorted(sums.items())]
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
    unpack(archive, staging / 'unpacked', game, tag)
    if not (staging / 'unpacked' / launcher).is_file():
        raise SystemExit(f'{archive.name} has no {launcher}')
    shutil.rmtree(folder, ignore_errors=True)
    (staging / 'unpacked').rename(folder)
    (folder / READY).write_text(json.dumps({'tag': tag, 'url': release['html_url'], 'archive': archive.name,
                                            'files': sums}, indent=1) + '\n')
    shutil.rmtree(staging)
    for old in root.iterdir():   # older releases, and partial downloads they left
        if old != folder:
            shutil.rmtree(old, ignore_errors=True) if old.is_dir() else old.unlink()
    say(f'ready: {folder}')
    return folder


def container_log(launcher, log):
    """The game's log in its app's sandbox container (the app sits next to the launcher)."""
    for app in sorted(launcher.parent.glob('*.app')):
        with open(app / 'Contents' / 'Info.plist', 'rb') as plist:
            bundle = plistlib.load(plist)['CFBundleIdentifier']
        return Path.home() / 'Library' / 'Containers' / bundle / 'Data' / log
    return None


def main(game, tag=None, download_only=False, extra=(), limit_gib=10.):
    spec = manifest.game(game).get('release')
    if not spec:
        raise SystemExit(f'{game} has no [release] section in game.toml')
    if sys.platform != 'darwin':
        raise SystemExit('the playtest releases are macOS builds')
    release = choose(releases(repository()), spec['tag'], tag)
    folder = ensure(game, release, spec['launcher'])
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
    if log and log.exists() and log.stat().st_mtime >= started:   # this run's log, not an earlier one
        shutil.copy2(log, logs / 'game.log')
        print(f'game log: {logs / "game.log"}')
    return code
