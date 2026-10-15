"""Bounded HTTPS reads into the verified portable product store.

The endpoint supplies bytes, never trust roots, download URLs or checkout paths.
No cache lock is held while waiting for the network.
"""
import asyncio
import hashlib
import math
import os
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit

import httpx

from . import artifact_bundle as bundle
from .build_cache import DIGEST

DEFAULT_TIMEOUT = 30.0
MAX_TIMEOUT = 300.0


class RemoteError(ValueError):
    """A safe diagnostic which never includes an endpoint or response body."""


class RemoteMiss(RemoteError):
    """The requested action has no manifest at this endpoint."""


def endpoint(value):
    """An explicit HTTPS prefix with no credentials, query, redirects or ambiguous path."""
    if (type(value) is not str or not value or len(value) > 2048 or
            any(ord(c) < 33 or ord(c) == 127 or c == '\\' for c in value)):
        raise RemoteError('Invalid artifact endpoint')
    try:
        raw = urlsplit(value)
        raw_parts = unquote(raw.path).split('/')
        if ('?' in value or '#' in value or '@' in raw.netloc or '//' in raw.path or
                any(part in ('.', '..') for part in raw_parts)):
            raise RemoteError('Invalid artifact endpoint')
        url = httpx.URL(value)
        parts = unquote(url.path).split('/')
        if (url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment or
                any(part in ('.', '..') or '\\' in part or '%' in part or
                    any(ord(c) < 33 or ord(c) == 127 for c in part) for part in parts) or
                '//' in url.path or unquote(url.path).count('/') != url.path.count('/')):
            raise RemoteError('Invalid artifact endpoint')
        return str(url).rstrip('/') + '/'
    except (httpx.InvalidURL, UnicodeError, ValueError):
        raise RemoteError('Invalid artifact endpoint') from None


def timeout_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= MAX_TIMEOUT:
        raise RemoteError('Transfer deadline must be greater than zero and at most 300 seconds')
    return float(value)


class Progress:
    def __init__(self, echo):
        self.echo = echo
        self.started = self.last = time.monotonic()
        self.bytes = self.completed = 0

    def update(self, stage, *, force=False):
        now = time.monotonic()
        if self.echo is not None and (force or now - self.last >= 10):
            self.echo(f'Artifact transfer: {stage}; {self.completed} blobs, {self.bytes} bytes, '
                      f'{now - self.started:.1f} s')
            self.last = now


async def _download(client, url, output, limit, progress, *, digest=None):
    async with client.stream('GET', url) as response:
        if response.status_code == 404 and digest is None:
            raise RemoteMiss('Remote action not found')
        if response.status_code != 200:
            raise RemoteError('Artifact server refused the download')
        if response.headers.get('content-encoding', 'identity').casefold() != 'identity':
            raise RemoteError('Encoded artifact responses are not supported')
        declared = response.headers.get('content-length')
        if declared is not None and (not declared.isascii() or not declared.isdecimal() or
                                     len(declared) > 12 or int(declared) > limit):
            raise RemoteError('Artifact response exceeds its byte limit')
        received = 0
        checksum = hashlib.sha256()
        async for chunk in response.aiter_raw(chunk_size=65536):
            received += len(chunk)
            if received > limit:
                raise RemoteError('Artifact response exceeds its byte limit')
            checksum.update(chunk)
            output.write(chunk)
            progress.bytes += len(chunk)
            progress.update('downloading')
        if declared is not None and received != int(declared):
            raise RemoteError('Artifact response length differs')
        if digest is not None and (received != limit or checksum.hexdigest() != digest):
            raise RemoteError('Downloaded blob differs from signed inventory')


async def _transfer(base, key, trust_file, directory, timeout, progress):
    # Environment proxies/netrc and redirects must not send credentials or move downloads
    # to an origin chosen by a remote response. TLS uses httpx's verified default context.
    manifest = directory / 'manifest.json'
    blobs = directory / 'blobs'
    blobs.mkdir()
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                     headers={'Accept-Encoding': 'identity'},
                                     timeout=httpx.Timeout(min(timeout, 10.0)),
                                     limits=httpx.Limits(max_connections=1)) as client:
        try:
            async with asyncio.timeout(timeout):
                progress.update('waiting for signed manifest', force=True)
                with manifest.open('wb') as output:
                    await _download(client, base + f'actions/{key}/manifest.json', output,
                                    bundle.MAX_MANIFEST, progress)
                _, _, expected, _, _ = bundle.verify_manifest(manifest.read_bytes(), trust_file, expected_key=key)
                for digest, size in expected.items():
                    progress.update('waiting for blob')
                    with (blobs / digest).open('wb') as output:
                        await _download(client, base + f'blobs/{digest}', output, size, progress, digest=digest)
                    progress.completed += 1
        except TimeoutError:
            raise RemoteError('Artifact transfer deadline exceeded') from None
    return progress.bytes


def _stop(child):
    """Reap only this downloader, including a resolver stuck in an executor thread."""
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def _worker_transfer(base, key, trust_file, directory, timeout, echo):
    from .safety.process import spawn
    request = directory.parent / 'request.json'
    result = directory.parent / 'result.json'
    request.write_text(json.dumps({'base': base, 'key': key, 'trust': str(Path(trust_file).absolute()),
                                   'directory': str(directory), 'result': str(result), 'timeout': timeout}))
    deadline = time.monotonic() + timeout
    # A separate owned process bounds even blocking DNS resolver shutdown. Cancellation
    # inside asyncio alone cannot guarantee that its executor threads will finish.
    log_path = directory.parent / 'progress.log'
    with log_path.open('w') as log:
        child = spawn([sys.executable, '-m', 'atelier.artifact_remote_worker', str(request)],
                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.DEVNULL)
        position = 0
        next_heartbeat = time.monotonic() + 10
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RemoteError('Artifact transfer deadline exceeded')
                try:
                    code = child.wait(timeout=min(1, remaining))
                except subprocess.TimeoutExpired:
                    code = None
                if log_path.stat().st_size > 65536:
                    raise RemoteError('Artifact progress limit exceeded')
                with log_path.open() as reader:
                    reader.seek(position)
                    for line in reader:
                        if not line.endswith('\n'):
                            break
                        position += len(line)
                        if echo is not None:
                            echo(line.rstrip('\n'))
                if code is not None:
                    break
                now = time.monotonic()
                if echo is not None and now >= next_heartbeat:
                    echo(f'Artifact transfer: waiting for downloader; {timeout - max(0, deadline - now):.1f} s elapsed, '
                         f'{max(0, deadline - now):.1f} s remaining')
                    next_heartbeat = now + 10
            if not result.is_file() or result.stat().st_size > 4096:
                raise RemoteError('Artifact downloader did not complete')
            outcome = json.loads(result.read_bytes())
            if type(outcome) is not dict:
                raise RemoteError('Invalid artifact transfer receipt')
            if code != 0 or outcome.get('error'):
                # Only this worker creates the private receipt; its errors are fixed literals.
                error = RemoteMiss if outcome.get('missing') is True else RemoteError
                raise error(outcome.get('error') or 'Artifact downloader did not complete')
            downloaded = outcome['downloaded_bytes']
            if type(downloaded) is not int or not 0 <= downloaded <= bundle.MAX_BYTES + bundle.MAX_MANIFEST:
                raise RemoteError('Invalid artifact transfer receipt')
            return downloaded
        finally:
            _stop(child)


def fetch_bundle(base_url, key, trust_file: Path, *, store=None, dry_run=False,
                 timeout=DEFAULT_TIMEOUT, echo=None):
    """@cc [owner:fontanierh,label:security] authenticated-bounded-remote-artifacts
    Only HTTPS at the configured origin MAY be contacted; redirects and implicit credentials
    MUST be refused. The signed requested action, policy and quotas MUST pass before any blob
    request. Network waiting MUST have an absolute deadline. Only the existing bundle importer
    MAY publish verified bytes; this transfer MUST NOT write outputs or success stamps.
    """
    try:
        base = endpoint(base_url)
        if type(key) is not str or not DIGEST.fullmatch(key):
            raise RemoteError('Invalid requested action key')
        timeout = timeout_seconds(timeout)
        if type(dry_run) is not bool:
            raise RemoteError('Dry run must be a boolean')
        with tempfile.TemporaryDirectory(prefix='atelier-download-') as folder:
            directory = Path(folder) / 'bundle'
            directory.mkdir()
            downloaded = _worker_transfer(base, key, trust_file, directory, timeout, echo)
            bundle.verify_manifest((directory / 'manifest.json').read_bytes(), trust_file, expected_key=key)
            if echo is not None:
                echo('Artifact transfer: verifying local publication')
            receipt = bundle.import_bundle(directory, trust_file, store=store, dry_run=dry_run)
            return {**receipt, 'transport': 'https', 'downloaded_bytes': downloaded}
    except RemoteError:
        raise
    except bundle.BundleError as error:
        # BundleError messages are fixed and safe, unlike parser/HTTP/filesystem errors.
        raise RemoteError(str(error)) from None
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, AttributeError):
        raise RemoteError('Artifact download or import failed') from None


def stderr_progress(message):
    print(message, file=sys.stderr, flush=True)


class RemoteCache:
    """One optional build's lookup budget. An outage disables its remaining lookups."""
    def __init__(self, base, trust, timeout):
        self.base, self.trust, self.timeout = base, trust, timeout
        self.remaining = timeout
        self.disabled = False

    def fetch(self, key, store, echo):
        if self.disabled:
            return False
        now = time.monotonic()
        try:
            if self.remaining <= 0:
                raise RemoteError('Artifact lookup budget exhausted')
            fetch_bundle(self.base, key, self.trust, store=store, timeout=self.remaining, echo=echo)
            return True
        except RemoteMiss:
            return False
        except RemoteError as error:
            self.disabled = True
            echo(f'Remote cache unavailable ({error}); continuing locally')
            return False
        finally:
            # Local generation between misses must not consume the lookup allowance.
            self.remaining -= time.monotonic() - now


def configured():
    """No environment configuration means no network, including ordinary offline builds."""
    base = os.environ.get('ATELIER_ARTIFACT_URL')
    trust = os.environ.get('ATELIER_ARTIFACT_TRUST')
    if base is None and trust is None:
        return None
    if not base or not trust:
        raise RemoteError('Remote cache requires both ATELIER_ARTIFACT_URL and ATELIER_ARTIFACT_TRUST')
    try:
        timeout = timeout_seconds(float(os.environ.get('ATELIER_ARTIFACT_TIMEOUT', DEFAULT_TIMEOUT)))
    except (ValueError, TypeError):
        raise RemoteError('Invalid remote cache transfer budget') from None
    return RemoteCache(endpoint(base), Path(trust), timeout)
