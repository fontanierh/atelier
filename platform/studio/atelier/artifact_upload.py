"""Explicit immutable HTTPS publication of already signed, public portable-source bundles."""
import asyncio
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import httpx

from . import artifact_bundle as bundle, artifact_remote as remote

MAX_TRANSFER_BYTES = 2 * (bundle.MAX_BYTES + bundle.MAX_MANIFEST)
TOKEN = re.compile(rb'[A-Za-z0-9._~+/-]{1,4096}={0,2}\Z')


class UploadError(bundle.BundleError):
    """Fixed safe diagnostics; never include credentials, endpoint or response text."""


class Progress(remote.Progress):
    def update(self, stage, *, force=False):
        if self.bytes > MAX_TRANSFER_BYTES:
            raise UploadError('Artifact upload payload budget exceeded')
        super().update(stage, force=force)


def _outside_checkout(path, directory):
    path = Path(path)
    if not path.is_absolute():
        raise UploadError('Upload profile and credential paths must be absolute')
    path = path.parent.resolve() / path.name
    if path.is_relative_to(Path(directory).resolve()) or any((parent / '.git').exists() for parent in path.parents):
        raise UploadError('Upload profile and credentials must be outside checkouts and the bundle')
    return path


def _protected(path, limit):
    with ExitStack() as stack:
        fd, before = bundle._open_file(stack, path)
        if before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_nlink != 1 or before.st_size > limit:
            raise UploadError('Upload profile and credentials must be owner-only regular files')
        data = os.read(fd, limit + 1)
        if len(data) != before.st_size or bundle._signature(os.fstat(fd)) != bundle._signature(before):
            raise UploadError('Upload profile or credentials changed')
        return data


def _profile(path, directory):
    path = _outside_checkout(path, directory)
    config = bundle._json(_protected(path, bundle.MAX_TRUST))
    bundle._fields(config, ('schema', 'endpoint', 'token_file'))
    if type(config['schema']) is not int or config['schema'] != 1:
        raise UploadError('Unsupported upload profile')
    base = remote.endpoint(config['endpoint'])
    if type(config['token_file']) is not str:
        raise UploadError('Invalid upload credential path')
    return base, _outside_checkout(config['token_file'], directory)


def _token(path):
    raw = _protected(path, 4099)
    if raw.endswith(b'\n'):
        raw = raw[:-1]
    if not TOKEN.fullmatch(raw):
        raise UploadError('Invalid upload bearer credential')
    return raw.decode('ascii')


def _public_v2(payload):
    if payload['schema'] != 2:
        raise UploadError('Upload requires a V2 audited Python bundle')
    if any(grant['permission'] != 'public' for grant in payload['redistribution'].values()):
        raise UploadError('Every uploaded product requires an explicit public redistribution grant')


async def _put(client, url, chunks, size):
    async with client.stream('PUT', url, content=chunks,
                             headers={'If-None-Match': '*', 'Content-Length': str(size)}) as response:
        if response.status_code not in (200, 201, 204, 412):
            raise UploadError('Artifact server refused immutable publication')
        return response.status_code == 412


async def _body(path, size, progress):
    sent = 0
    with path.open('rb') as stream:
        while chunk := stream.read(min(65536, size + 1 - sent)):
            sent += len(chunk)
            if sent > size:
                raise UploadError('Verified upload snapshot changed')
            progress.bytes += len(chunk)
            progress.update('uploading verified blob')
            yield chunk
    if sent != size:
        raise UploadError('Verified upload snapshot changed')


class Discard:
    def write(self, chunk):
        return len(chunk)


async def _transfer(base, token, snapshot, trust, timeout, progress):
    payload = snapshot.payload
    key = payload['entry']['key']
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                headers={'Accept-Encoding': 'identity', 'Authorization': 'Bearer ' + token},
                                timeout=httpx.Timeout(min(timeout, 10.)),
                                limits=httpx.Limits(max_connections=1)) as client:
        async with asyncio.timeout(timeout):
            for digest, size in snapshot.sizes.items():
                url = base + 'blobs/' + digest
                await _put(client, url, _body(snapshot.blobs / digest, size, progress), size)
                # A successful PUT or precondition refusal alone proves neither presence nor
                # contents. Check exact bytes before making the action manifest discoverable.
                await remote._download(client, url, Discard(), size, progress, digest=digest)
                progress.completed += 1
            progress.update('publishing signed manifest', force=True)
            progress.bytes += len(snapshot.manifest)
            progress.update('publishing signed manifest')
            reused = await _put(client, base + f'actions/{key}/manifest.json', snapshot.manifest,
                                len(snapshot.manifest))
            received = io.BytesIO()
            await remote._download(client, base + f'actions/{key}/manifest.json', received,
                                   bundle.MAX_MANIFEST, progress)
            installed, _, _, _, _ = bundle.verify_manifest(received.getvalue(), trust, expected_key=key)
            _public_v2(installed)
            if installed['entry'] != payload['entry']:
                raise UploadError('Remote action conflicts with the verified bundle')
    return installed, reused


def _execute(directory, trust, profile, *, dry_run, timeout, work, echo=None):
    try:
        progress = Progress(echo)
        progress.update('verifying signed bundle', force=True)
        with bundle.verified_snapshot(directory, trust, temporary_root=work) as snapshot:
            _public_v2(snapshot.payload)
            base, credential = _profile(profile, directory)
            installed, reused = snapshot.payload, False
            if not dry_run:
                token = _token(credential)
                installed, reused = asyncio.run(_transfer(base, token, snapshot, trust, timeout, progress))
            return {'schema': 1, 'transport': 'https', 'key': installed['entry']['key'],
                    'publisher': installed['publisher'], 'source_publisher': snapshot.payload['publisher'],
                    'manifest_sha256': hashlib.sha256(bundle._canonical(installed)).hexdigest(),
                    'products': sorted(installed['entry']['products']), 'blobs': len(snapshot.sizes),
                    'logical_bytes': snapshot.logical_bytes, 'payload_bytes_transferred': progress.bytes,
                    'dry_run': dry_run, 'uploaded': not dry_run, 'existing_manifest_retained': reused,
                    'public_redistribution_asserted': True, 'provenance_verification': 'pinned publisher assertion only'}
    except UploadError:
        raise
    except (bundle.BundleError, remote.RemoteError) as error:
        raise UploadError(str(error)) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, httpx.HTTPError, TimeoutError):
        raise UploadError('Artifact verification or HTTPS publication failed') from None


def _worker_upload(directory, trust, profile, *, dry_run, timeout, work, echo):
    from .safety.process import spawn
    work = Path(work)
    request, result = work / 'request.json', work / 'result.json'
    request.write_text(json.dumps({'directory': str(Path(directory).absolute()), 'trust': str(Path(trust).absolute()),
                                   'profile': str(Path(profile).absolute()), 'dry_run': dry_run,
                                   'timeout': timeout, 'work': str(work), 'result': str(result)}))
    deadline, spoken = time.monotonic() + timeout, time.monotonic()
    with (work / 'progress.log').open('w') as log:
        if echo is not None:
            echo('Artifact upload: starting owned bundle verifier/transfer worker')
        child = spawn([sys.executable, '-m', 'atelier.artifact_upload_worker', str(request)],
                      stdout=log, stderr=log)
        try:
            while child.poll() is None:
                if time.monotonic() >= deadline:
                    raise UploadError('Artifact upload deadline exceeded')
                if echo is not None and time.monotonic() - spoken >= 10:
                    spoken = time.monotonic()
                    echo('Artifact upload: waiting for owned verifier/transfer worker')
                if log.tell() > 65536:
                    raise UploadError('Artifact upload progress exceeded its limit')
                time.sleep(.05)
            if not result.is_file() or result.is_symlink() or result.stat().st_size > 65536:
                raise UploadError('Artifact upload worker did not complete')
            outcome = json.loads(result.read_bytes())
            if child.returncode or type(outcome) is not dict or 'receipt' not in outcome:
                # This private worker emits only fixed diagnostics. Never relay its stderr.
                raise UploadError(outcome.get('error', 'Artifact upload worker failed')
                                  if type(outcome) is dict else 'Artifact upload worker failed')
            receipt = outcome['receipt']
            if (type(receipt) is not dict or type(receipt.get('payload_bytes_transferred')) is not int
                    or not 0 <= receipt['payload_bytes_transferred'] <= MAX_TRANSFER_BYTES):
                raise UploadError('Invalid artifact upload receipt')
            return receipt
        finally:
            remote._stop(child)


def upload_bundle(directory: Path, trust_file: Path, *, profile: Path, dry_run=False,
                  timeout=remote.DEFAULT_TIMEOUT, echo=None):
    """@cc [owner:fontanierh,label:security] public-verified-artifact-upload
    Upload MUST require a completely verified independent V2 snapshot and public grants for every
    product before reading write credentials. Only the profile's HTTPS origin MAY receive credentials;
    redirects and implicit credentials MUST be disabled. Blobs MUST verify remotely before the signed
    action manifest is conditionally published last. Conflicting entries MUST NOT be overwritten.
    An owned worker MUST bound total verification/network time and be reaped before scratch removal.
    Dry runs MUST NOT read credentials, contact the network, or change stores, outputs or stamps.
    """
    try:
        if type(dry_run) is not bool:
            raise UploadError('Dry run must be a boolean')
        timeout = remote.timeout_seconds(timeout)
        with tempfile.TemporaryDirectory(prefix='atelier-upload-') as work:
            return _worker_upload(directory, trust_file, profile, dry_run=dry_run, timeout=timeout,
                                  work=work, echo=echo)
    except UploadError:
        raise
    except remote.RemoteError as error:
        raise UploadError(str(error)) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise UploadError('Artifact verification or HTTPS publication failed') from None
