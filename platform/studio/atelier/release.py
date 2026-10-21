"""Publish an existing verified package through the caller's authenticated GitHub CLI.

No cook, extraction or game launch runs here. SHA256SUMS is the downloader's readiness manifest:
upload it last, then publish the draft. Remote assets are immutable; a matching completed upload
can resume, but a conflicting or unverifiable asset needs a different tag or explicit owner repair.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

from . import manifest, paths, playtest, release_claim

ATTEMPTS = playtest.TRANSFER_ATTEMPTS
PART_MIB = 200
WORKERS = 6


class PublishError(Exception):
    pass


class TransportError(PublishError):
    def __init__(self, code=None, *, certificate=False):
        self.code, self.certificate = code, certificate
        super().__init__('GitHub certificate verification failed' if certificate else
                         f'GitHub transport refused or interrupted (HTTP {code or "unknown"})')

    @property
    def retryable(self):
        return not self.certificate and (self.code is None or self.code in (408, 429, 500, 502, 503, 504))


def require(value, message):
    if not value:
        raise PublishError(message)


def say(text):
    print(text, flush=True)


def snapshot(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), f'{path.name}: expected a regular file, without a symlink')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def leaf(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name)
            and name not in ('.', '..'), 'release names must be plain file names')
    return name


def source_identity(source, game, package_revision=None):
    def git(*args):
        result = subprocess.run(['git', *args], cwd=source, capture_output=True, text=True, timeout=30)
        require(result.returncode == 0, 'cannot read the selected source checkout')
        return result.stdout.strip()
    revision = git('rev-parse', 'HEAD')
    require(re.fullmatch(r'[0-9a-f]{40}', revision), 'source HEAD must be a full Git commit')
    if package_revision is not None:
        require(git('rev-parse', '--verify', package_revision + '^{commit}') == revision,
                'package revision must resolve unambiguously to the selected source HEAD')
    require(not git('status', '--porcelain'), 'selected source checkout must be clean')
    spec = manifest.load(source / 'games' / leaf(game) / 'game.toml').get('release')
    require(isinstance(spec, dict) and spec.get('tag') and spec.get('launcher'), 'game needs a [release] configuration')
    origin = git('config', '--get', 'remote.origin.url')
    found = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)'
                         r'([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?', origin)
    require(found is not None, 'selected source origin must be a GitHub repository')
    return revision, '/'.join(found.groups()), spec


def prepare(package, verification, stage, *, game, tag, revision, repo, spec, part_bytes, title, notes):
    """@cc [owner:fontanierh,label:correctness] verified-release-upload-inputs
    Publication MUST bind the existing package inventory and native verification attestation to
    a caller-selected clean source commit. Rechunking MUST preserve every verified input byte.
    A filename or report alone MUST NOT claim native parity or replace native verification.
    """
    evidence = [package / 'manifest.json', verification]
    receipts = {path: snapshot(path) for path in evidence}
    raw, proof_raw = (path.read_bytes() for path in evidence)
    original, proof = json.loads(raw), json.loads(proof_raw)
    zipname = leaf(original['zip'])
    require(zipname.endswith('.zip'), 'package must describe a ZIP archive')
    package_revision = original.get('cook', {}).get('revision', original['revision'])
    require(isinstance(package_revision, str) and re.fullmatch(r'[0-9a-f]{8,40}', package_revision)
            and revision.startswith(package_revision), 'package revision differs from the selected clean source')
    require(original.get('cook', {}).get('source_dirty') in (None, False), 'package cook source was dirty')
    require(proof.get('revision') == package_revision and proof.get('files') == original['files'],
            'verification report does not attest this exact package inventory and revision')
    require(isinstance(proof.get('architectures'), str) and 'arm64' in proof['architectures'].split()
            and isinstance(proof.get('launcher_sha256'), str)
            and re.fullmatch(r'[0-9a-f]{64}', proof['launcher_sha256']),
            'verification report lacks the native architecture and launcher attestation')
    entries = original['files']
    require(isinstance(entries, list) and entries, 'package has no verified archive files')
    names = [leaf(entry['file']) for entry in entries]
    if original['split']:
        expected = [zipname + '.part-' + chr(97 + i // 26) + chr(97 + i % 26) for i in range(len(names))]
        require(len(names) <= 676 and names == expected, 'package parts are missing or out of order')
    else:
        require(names == [zipname], 'unsplit package must contain its one ZIP')
    require(Path(spec['launcher']).name == original['launcher'], 'package launcher differs from game configuration')
    require(all(type(entry['bytes']) is int and entry['bytes'] > 0
                and re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) for entry in entries), 'invalid package inventory')
    sums_path = package / 'SHA256SUMS'
    receipts[sums_path] = snapshot(sums_path)
    require(sums_path.read_text() == ''.join(f"{entry['sha256']}  {entry['file']}\n" for entry in entries),
            'package SHA256SUMS differs from its manifest')
    total = sum(entry['bytes'] for entry in entries)
    count = (total + part_bytes - 1) // part_bytes
    require(count <= 676, 'archive needs more than 676 upload parts; increase --part-mib')
    output, archive_digest = [], hashlib.sha256()
    out, digest, written, done = None, None, 0, 0
    started = spoken = time.monotonic()
    try:
        for entry in entries:
            path = package / entry['file']
            receipts[path] = snapshot(path)
            require(receipts[path][2] == entry['bytes'], f'{path.name}: package size differs from verified inventory')
            source_digest = hashlib.sha256()
            with path.open('rb') as source:
                while block := source.read(1 << 20):
                    source_digest.update(block)
                    archive_digest.update(block)
                    offset = 0
                    while offset < len(block):
                        if out is None:
                            index = len(output)
                            name = zipname if count == 1 else zipname + '.part-' + chr(97 + index // 26) + chr(97 + index % 26)
                            out = (stage / name).open('xb')
                            os.fchmod(out.fileno(), 0o600)
                            digest, written = hashlib.sha256(), 0
                        chunk = block[offset:offset + min(part_bytes - written, len(block) - offset)]
                        out.write(chunk)
                        digest.update(chunk)
                        offset += len(chunk)
                        written += len(chunk)
                        done += len(chunk)
                        if written == part_bytes or done == total:
                            out.close()
                            output.append(dict(file=Path(out.name).name, bytes=written, sha256=digest.hexdigest()))
                            out = None
                    now = time.monotonic()
                    require(now - started < 2700, 'release preparation exceeded 45 minutes')
                    if now - spoken >= 10:
                        say(f'preparing verified upload: {done / 2**20:.0f}/{total / 2**20:.0f} MiB')
                        spoken = now
            require(source_digest.hexdigest() == entry['sha256'], f'{path.name}: checksum differs from verified inventory')
            require(snapshot(path) == receipts[path], f'{path.name}: input changed while preparing publication')
    finally:
        if out is not None:
            out.close()
    publication = dict(schema=1, game=game, repository=repo, tag=tag, source_revision=revision,
                       package_revision=package_revision, package_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                       verification_sha256=hashlib.sha256(proof_raw).hexdigest(),
                       archive_sha256=archive_digest.hexdigest(), title=title,
                       notes_sha256=hashlib.sha256(notes.encode()).hexdigest())
    current = {**original, 'split': count > 1, 'files': output, 'publication': publication}
    for name, data in [('package-manifest.json', raw), ('verification.json', proof_raw),
                       ('manifest.json', (json.dumps(current, indent=2) + '\n').encode()),
                       ('SHA256SUMS', ''.join(f"{e['sha256']}  {e['file']}\n" for e in output).encode())]:
        with (stage / name).open('xb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
    for path, identity in receipts.items():
        require(snapshot(path) == identity, f'{path.name}: input changed while preparing publication')
    say(f'prepared {len(output)} verified archive asset(s), {total / 2**20:.1f} MiB; no native work run')
    return receipts


class GitHub:
    """Bounded gh subprocesses retain the caller's authentication and release author identity."""
    def __init__(self, repo, stop):
        self.repo, self.stop = repo, stop

    def run(self, args, *, data=None, timeout=60):
        require(not self.stop.is_set(), 'publication cancelled before starting another transfer')
        child = subprocess.Popen(['gh', *args], stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.stop.is_set() or time.monotonic() >= deadline:
                    raise TransportError()
                try:
                    stdout, stderr = child.communicate(input=data, timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    data = None
            if child.returncode:
                match = re.search(rb'HTTP (\d{3})', stderr)
                certificate = b'x509:' in stderr.lower() or b'certificate verify failed' in stderr.lower()
                raise TransportError(int(match[1]) if match else None, certificate=certificate)
            return stdout
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)

    def api(self, path, *, method='GET', data=None, pages=False):
        args = ['api', f'repos/{self.repo}' + ('/' + path if path else ''), '--hostname', 'github.com', '--method', method]
        if pages:
            args += ['--paginate', '--slurp']
        if data is not None:
            args += ['--input', '-']
        raw = self.run(args, data=json.dumps(data).encode() if data is not None else None)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise TransportError() from None

    def read(self, path, *, missing=False, pages=False):
        for attempt in range(ATTEMPTS):
            try:
                return self.api(path, pages=pages)
            except TransportError as error:
                if missing and error.code == 404:
                    return None
                if not error.retryable or attempt + 1 == ATTEMPTS:
                    raise
                self.stop.wait(attempt + 1)

    def upload(self, release, path):
        # Pin the numeric release, rather than resolving the mutable tag again in `gh release upload`.
        endpoint = (f'https://uploads.github.com/repos/{self.repo}/releases/{release["id"]}/assets?'
                    + 'name=' + quote(path.name, safe=''))
        self.run(['api', endpoint, '--hostname', 'github.com', '--method', 'POST',
                  '--header', 'Content-Type: application/octet-stream', '--input', str(path)], timeout=300)


def asset_map(github, release):
    pages = github.read(f'releases/{release["id"]}/assets?per_page=100', pages=True)
    assets = [asset for page in pages for asset in page]
    require(len({asset['name'] for asset in assets}) == len(assets), 'release has duplicate asset names')
    return {asset['name']: asset for asset in assets}


def matches(asset, path, digest):
    require(asset.get('state') == 'uploaded' and asset.get('size') == path.stat().st_size
            and asset.get('digest') == 'sha256:' + digest,
            f'{path.name}: remote asset conflicts or lacks a verified GitHub digest; never clobber it')


def ensure_asset(github, release, path, digest):
    """@cc [owner:fontanierh,label:correctness] observed-immutable-release-upload
    Every upload MUST be size/digest verified from fresh remote state. Ambiguous failures MUST
    observe the named remote asset before any bounded retry. Conflicts MUST NOT be overwritten.
    """
    for attempt in range(ATTEMPTS):
        existing = asset_map(github, release).get(path.name)
        if existing:
            matches(existing, path, digest)
            say(f'verified remote asset: {path.name}')
            return
        failure = None
        try:
            github.upload(release, path)
        except TransportError as error:
            failure = error
        # An interrupted request may have committed. Observe before retry, including final failure.
        existing = asset_map(github, release).get(path.name)
        if existing:
            matches(existing, path, digest)
            say(f'verified uploaded asset: {path.name}')
            return
        if (failure is not None and not failure.retryable) or attempt + 1 == ATTEMPTS:
            raise failure or PublishError(f'{path.name}: upload was not remotely verified')
        say(f'{path.name}: remote asset absent after transfer; retry {attempt + 2}/{ATTEMPTS}')
        github.stop.wait(attempt + 1)


def check_release(value, metadata, release_id=None):
    require(type(value) is dict and (release_id is None or value.get('id') == release_id), 'release identity changed')
    require(type(value.get('id')) is int and value['id'] > 0 and type(value.get('draft')) is bool, 'invalid release identity/state')
    for name in ('tag_name', 'name', 'body', 'prerelease', 'target_commitish'):
        require(value.get(name) == metadata[name], f'release {name} conflicts; choose a new tag instead of editing it')


def check_tag(github, tag, revision, *, required=False):
    value = github.read('git/ref/tags/' + quote(tag, safe=''), missing=True)
    for _ in range(5):
        if value is None:
            require(not required, 'published release tag is not yet observable; rerun to verify it')
            return
        obj = value['object']
        if obj['type'] == 'commit':
            require(obj['sha'] == revision, 'remote tag points to a different source revision')
            return
        require(obj['type'] == 'tag', 'remote tag does not identify a commit')
        value = github.read('git/tags/' + obj['sha'])
    raise PublishError('remote annotated tag nesting exceeds the supported bound')


def find_release(github, tag):
    value = github.read('releases/tags/' + quote(tag, safe=''), missing=True)
    if value is not None:
        return value
    # REST's tag endpoint finds published tags, not every draft's pending tag. Authenticated
    # release listings include drafts; observe them before any create/retry to avoid duplicates.
    pages = github.read('releases?per_page=100', pages=True)
    found = [value for page in pages for value in page if value['tag_name'] == tag]
    require(len(found) <= 1, 'multiple releases use this tag; refusing ambiguous publication')
    return found[0] if found else None


def select_release(github, metadata, claim):
    tag = metadata['tag_name']
    if claim.value['state'] == 'selected':
        identifier = claim.value['release_id']
        release = github.read(f'releases/{identifier}', missing=True)
        require(release is not None, 'previously selected release is not observable; no new draft was created')
        check_release(release, metadata, identifier)
        return release
    release = find_release(github, tag)
    if release is not None:
        check_release(release, metadata)
        claim.save('selected', release['id'])
        return release
    if claim.value['state'] == 'not-created':
        claim.save('creating')  # Durable before sending the non-idempotent POST.
        try:
            release = github.api('releases', method='POST', data={**metadata, 'draft': True})
        except TransportError as error:
            # These responses affirm rejection. Unknown/timeout/5xx outcomes can
            # have committed and stay observation-only, including on a new CLI run.
            if error.certificate or error.code in (400, 401, 403, 404, 405, 410, 422, 429):
                claim.save('not-created')
                raise
        else:
            check_release(release, metadata)
            require(release['draft'], 'create response unexpectedly describes a published release')
            claim.save('selected', release['id'])
            return release  # The successful response already pins the exact ID.
    for attempt in range(ATTEMPTS):
        release = find_release(github, tag)
        if release is not None:
            check_release(release, metadata)
            claim.save('selected', release['id'])
            return release
        if attempt + 1 < ATTEMPTS:
            github.stop.wait(attempt + 1)
    raise PublishError('release creation remains unconfirmed; no second create was sent; '
                       'rerun the same command to observe it, or choose a new tag; '
                       f'retained claim: {claim.path}')


def publish_assets(github, stage, metadata, *, workers, revalidate):
    """@cc [owner:fontanierh,label:correctness] manifest-last-release-publication
    Archive and evidence assets MUST all be remotely verified before SHA256SUMS is uploaded last.
    Only a complete verified draft MAY be published. Existing published releases MUST be complete
    and identical; source/input/output mutations MUST refuse final publication. No clobber is allowed.
    """
    try:
        with release_claim.acquire(github.repo, metadata) as claim:
            return _publish_assets(github, stage, metadata, workers=workers, revalidate=revalidate, claim=claim)
    except release_claim.ClaimError as error:
        raise PublishError(str(error)) from None


def _publish_assets(github, stage, metadata, *, workers, revalidate, claim):
    tag = metadata['tag_name']
    check_tag(github, tag, metadata['target_commitish'])
    release = select_release(github, metadata, claim)
    files = sorted(stage.iterdir())
    digests = {p.name: playtest._digest(p).hexdigest() for p in files}
    snapshots = {p: snapshot(p) for p in files}
    def verify_local():
        revalidate()
        for path, identity in snapshots.items():
            require(snapshot(path) == identity and playtest._digest(path).hexdigest() == digests[path.name],
                    f'{path.name}: staged output changed during publication')
    remote = asset_map(github, release)
    require(set(remote) <= set(digests), 'release contains unexpected assets; choose a fresh tag')
    require('SHA256SUMS' not in remote or set(remote) == set(digests),
            'release has a readiness manifest but missing assets; refusing automatic repair')
    for path in files:
        if path.name in remote:
            matches(remote[path.name], path, digests[path.name])
        elif not release['draft']:
            raise PublishError('published release is incomplete; refusing to mutate it')
    if not release['draft']:
        verify_local()
        check_tag(github, tag, metadata['target_commitish'], required=True)
        say('release already published with identical verified assets')
        return release
    pending = [p for p in files if p.name != 'SHA256SUMS']
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(ensure_asset, github, release, p, digests[p.name]) for p in pending}
    try:
        remaining = futures
        while remaining:
            finished, remaining = wait(remaining, timeout=10, return_when=FIRST_COMPLETED)
            for future in finished:
                future.result()
            if not finished:
                say(f'uploading: {len(futures) - len(remaining)}/{len(futures)} assets verified; waiting for transfers')
    except BaseException:
        github.stop.set()
        for future in futures:
            future.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    def verify_all(include_sums):
        verify_local()
        current = github.read(f'releases/{release["id"]}')
        check_release(current, metadata, release['id'])
        check_tag(github, tag, metadata['target_commitish'], required=not current['draft'])
        remote = asset_map(github, release)
        require(set(remote) <= set(digests), 'release assets changed during publication')
        require(current['draft'] or set(remote) == set(digests),
                'release was published before all assets were ready; refusing further uploads')
        for path in files:
            if include_sums or path.name != 'SHA256SUMS':
                require(path.name in remote, f'{path.name}: remote asset disappeared')
                matches(remote[path.name], path, digests[path.name])
        return current
    verify_all(False)
    ensure_asset(github, release, stage / 'SHA256SUMS', digests['SHA256SUMS'])
    for attempt in range(ATTEMPTS):
        current = verify_all(True)
        if not current['draft']:
            return current
        failure = None
        try:
            github.api(f'releases/{release["id"]}', method='PATCH', data={'draft': False})
        except TransportError as error:
            failure = error
        current = github.read(f'releases/{release["id"]}')
        check_release(current, metadata, release['id'])
        if not current['draft']:
            return verify_all(True)
        if (failure and not failure.retryable) or attempt + 1 == ATTEMPTS:
            raise failure or PublishError('final publication was not remotely observed; rerun to resume')
    raise PublishError('publication attempts exhausted')


def main(game, package, *, tag, verification, title=None, notes_file=None, source=None, part_mib=PART_MIB,
         workers=WORKERS, prerelease=False):
    stop = threading.Event()
    try:
        require(type(part_mib) is int and 1 <= part_mib <= 1900, '--part-mib must be between 1 and 1900')
        require(type(workers) is int and 1 <= workers <= WORKERS, '--workers must be between 1 and 6')
        source = Path(source or paths.REPO).resolve()
        revision, repo, spec = source_identity(source, game)
        leaf(tag)
        require(tag.startswith(spec['tag']), 'release tag must start with the game configuration tag prefix')
        notes_path = Path(notes_file) if notes_file else None
        notes_snapshot = snapshot(notes_path) if notes_path else None
        notes = notes_path.read_text() if notes_path else ''
        title = title or tag
        require(isinstance(title, str) and title.strip(), 'release title must not be empty')
        base = paths.build_dir(game) / 'release-publish'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=tag + '-', dir=base) as temporary:
            stage = Path(temporary)
            inputs = prepare(Path(package), Path(verification), stage, game=game, tag=tag, revision=revision,
                             repo=repo, spec=spec, part_bytes=part_mib * 2**20, title=title, notes=notes)
            package_revision = json.loads((stage / 'manifest.json').read_text())['publication']['package_revision']
            def revalidate():
                require(source_identity(source, game, package_revision) == (revision, repo, spec),
                        'selected source changed during publication')
                for path, identity in inputs.items():
                    require(snapshot(path) == identity, f'{path.name}: input changed during publication')
                if notes_path:
                    require(snapshot(notes_path) == notes_snapshot, 'release notes changed during publication')
            revalidate()
            from . import build_checkpoints
            try:
                build_checkpoints.publish(source, game, tag, revision, revalidate=revalidate)
            except RuntimeError as error:
                raise PublishError(str(error)) from None
            result = publish_assets(GitHub(repo, stop), stage,
                dict(tag_name=tag, target_commitish=revision, name=title, body=notes, prerelease=prerelease),
                workers=workers, revalidate=revalidate)
            say(f'published verified release: {result.get("html_url", tag)}')
            return 0
    except KeyboardInterrupt:
        stop.set()
        raise SystemExit('publication cancelled; verified remote assets remain resumable; rerun the same command') from None
    except (PublishError, OSError, ValueError, KeyError, TypeError) as error:
        stop.set()
        raise SystemExit(str(error)) from None
