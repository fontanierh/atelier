"""Synthetic HTTPS objects, ephemeral signing keys and tiny Python products; no real service or credentials."""
import asyncio
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from atelier import artifact_bundle as bundle, artifact_upload as upload, artifact_remote as remote
from atelier import artifact_publisher as publisher, build, build_cache, build_products
from test_artifact_bundle import package  # noqa: F401
from test_artifact_publisher import producer, source_template  # noqa: F401
from test_artifact_remote import Stream

BASE = 'https://objects.example.test/products/'
TOKEN = 'ephemeral-fixture-upload-token'


@pytest.fixture
def public_bundle(package):
    package.payload['schema'] = 2
    package.payload['producer'].pop('guarded')
    package.payload['producer'].update(execution='audited-python-v1', audit_sha256='d' * 64)
    package.payload['redistribution']['asset']['permission'] = 'public'
    package.sign()
    return package


@pytest.fixture
def objects(tmp_path, monkeypatch):
    token = tmp_path / 'upload-token'
    token.write_text(TOKEN + '\n')
    token.chmod(0o600)
    profile = tmp_path / 'upload-profile.json'
    config = {'schema': 1, 'endpoint': BASE, 'token_file': str(token)}
    profile.write_text(json.dumps(config))
    profile.chmod(0o600)
    records, calls, options, overrides, credentials = {}, [], [], {}, []

    async def serve(request):
        calls.append((request.method, request.url.path))
        assert str(request.url).startswith(BASE)
        assert request.headers['accept-encoding'] == 'identity'
        if (request.method, request.url.path) in overrides:
            return overrides[request.method, request.url.path](request)
        if request.method == 'PUT':
            assert request.headers['authorization'] == 'Bearer ' + TOKEN
            assert request.headers['if-none-match'] == '*'
            body = await request.aread()
            assert int(request.headers['content-length']) == len(body)
            if request.url.path in records:
                return httpx.Response(412)
            records[request.url.path] = body
            return httpx.Response(201)
        assert request.method == 'GET'
        if request.url.path not in records:
            return httpx.Response(404)
        return httpx.Response(200, stream=Stream([records[request.url.path]]))

    client = httpx.AsyncClient
    def configured(**kwargs):
        options.append(kwargs)
        return client(transport=httpx.MockTransport(serve), **kwargs)
    monkeypatch.setattr(upload.httpx, 'AsyncClient', configured)
    worker = upload._worker_upload
    def in_process(directory, trust, profile, *, dry_run, timeout, work, echo):
        return upload._execute(directory, trust, profile, dry_run=dry_run, timeout=timeout, work=work, echo=echo)
    monkeypatch.setattr(upload, '_worker_upload', in_process)
    def download(base, key, trust, directory, timeout, echo):
        return asyncio.run(remote._transfer(base, key, trust, directory, timeout, remote.Progress(echo)))
    monkeypatch.setattr(remote, '_worker_transfer', download)
    read_token = upload._token
    def observed(path):
        credentials.append(True)
        return read_token(path)
    monkeypatch.setattr(upload, '_token', observed)
    return SimpleNamespace(records=records, calls=calls, options=options, overrides=overrides,
                           profile=profile, token=token, config=config, credentials=credentials,
                           worker=worker)


def send(p, server, **kwargs):
    return upload.upload_bundle(p.directory, p.trust, profile=server.profile, **kwargs)


def manifest_path(p):
    return '/products/actions/' + p.payload['entry']['key'] + '/manifest.json'


def test_upload_verifies_snapshot_then_blobs_before_manifest_and_retains_existing_entry(public_bundle, objects):
    p, s = public_bundle, objects
    original = (p.directory / 'manifest.json').read_bytes()
    first = send(p, s)
    assert first['uploaded'] and not first['existing_manifest_retained']
    blob_path = '/products/blobs/' + p.blob.name
    assert s.calls == [('PUT', blob_path), ('GET', blob_path), ('PUT', manifest_path(p)), ('GET', manifest_path(p))]
    assert s.records[blob_path] == p.contents
    assert json.loads(s.records[manifest_path(p)]) == json.loads(original)
    old = dict(s.records)
    # Another trusted receipt for the same entry may have different provenance. The first
    # immutable manifest remains canonical; byte-equivalent action data is idempotent.
    p.payload['producer']['source_commit'] = 'e' * 40
    p.sign()
    again = send(p, s)
    assert again['existing_manifest_retained'] and s.records == old
    assert all(option['trust_env'] is False and option['follow_redirects'] is False
               and 'verify' not in option for option in s.options)
    assert not p.store.root.exists()


def test_dry_run_never_loads_credentials_or_network_and_original_mutation_cannot_change_upload(public_bundle, objects, monkeypatch):
    p, s = public_bundle, objects
    token_bytes = s.token.read_bytes()
    s.token.unlink()
    receipt = send(p, s, dry_run=True)
    assert receipt['dry_run'] and not receipt['uploaded'] and receipt['payload_bytes_transferred'] == 0
    assert s.calls == [] and s.credentials == []
    s.token.write_bytes(token_bytes)
    s.token.chmod(0o600)
    read = upload._token
    def mutate_original(path):
        p.blob.write_bytes(b'input changed after complete verification')
        return read(path)
    monkeypatch.setattr(upload, '_token', mutate_original)
    assert send(p, s)['uploaded']
    assert s.records['/products/blobs/' + p.blob.name] == p.contents


@pytest.mark.parametrize('change', ['signature', 'unpinned', 'private', 'v1', 'blob', 'missing', 'symlink', 'extra', 'quota'])
def test_invalid_export_never_loads_credentials_or_contacts_server(public_bundle, objects, change, monkeypatch):
    p, s = public_bundle, objects
    if change == 'signature':
        path = p.directory / 'manifest.json'
        path.write_bytes(path.read_bytes().replace(b'approval-123', b'approval-456'))
    elif change == 'unpinned':
        p.trust.write_text('{"schema":1,"publishers":{}}')
    elif change == 'private':
        p.payload['redistribution']['asset']['permission'] = 'private'
        p.sign()
    elif change == 'v1':
        p.payload['schema'] = 1
        p.payload['producer'].pop('execution')
        p.payload['producer'].pop('audit_sha256')
        p.payload['producer']['guarded'] = True
        p.sign()
    elif change == 'blob':
        p.blob.write_bytes(b'bad')
    elif change == 'missing':
        p.blob.unlink()
    elif change == 'symlink':
        target = p.root / 'original-blob'
        p.blob.rename(target)
        p.blob.symlink_to(target)
    elif change == 'extra':
        (p.directory / 'unexpected').write_text('extra')
    else:
        monkeypatch.setattr(bundle, 'MAX_BYTES', len(p.contents) - 1)
    with pytest.raises(upload.UploadError):
        send(p, s)
    assert s.calls == [] and s.credentials == [] and not p.store.root.exists()


@pytest.mark.parametrize('change', ['http', 'userinfo', 'profile_mode', 'token_mode', 'token_link', 'token_header', 'profile_extra'])
def test_profile_and_credentials_are_explicit_protected_and_not_logged(public_bundle, objects, change):
    p, s = public_bundle, objects
    if change in ('http', 'userinfo'):
        s.config['endpoint'] = 'http://objects.example.test/' if change == 'http' else 'https://secret@example.test/'
        s.profile.write_text(json.dumps(s.config))
    elif change == 'profile_mode':
        s.profile.chmod(0o644)
    elif change == 'token_mode':
        s.token.chmod(0o644)
    elif change == 'token_link':
        target = p.root / 'token-target'
        s.token.rename(target)
        s.token.symlink_to(target)
    elif change == 'token_header':
        s.token.write_text('private-credential\r\nInjected: secret')
    else:
        s.config['secret'] = 'private-credential'
        s.profile.write_text(json.dumps(s.config))
    with pytest.raises(upload.UploadError) as error:
        send(p, s)
    assert s.calls == []
    assert TOKEN not in str(error.value) and 'private-credential' not in str(error.value) and BASE not in str(error.value)


@pytest.mark.parametrize('location', ['profile_checkout', 'token_checkout', 'token_bundle'])
def test_upload_configuration_cannot_live_in_checkout_or_bundle(public_bundle, objects, location, tmp_path):
    p, s = public_bundle, objects
    checkout = tmp_path / 'unrelated-checkout'
    (checkout / '.git').mkdir(parents=True)
    if location == 'profile_checkout':
        destination = checkout / 'upload.json'
        destination.write_bytes(s.profile.read_bytes())
        destination.chmod(0o600)
        s.profile = destination
    else:
        s.config['token_file'] = str(checkout / 'token' if location == 'token_checkout' else p.blob)
        s.profile.write_text(json.dumps(s.config))
    with pytest.raises(upload.UploadError, match='outside checkouts'):
        send(p, s)
    assert s.calls == [] and s.credentials == []


def test_transfer_payload_budget_stops_publication(public_bundle, objects, monkeypatch):
    monkeypatch.setattr(upload, 'MAX_TRANSFER_BYTES', 1)
    with pytest.raises(upload.UploadError, match='payload budget'):
        send(public_bundle, objects)
    assert manifest_path(public_bundle) not in objects.records


@pytest.mark.parametrize('status', [301, 302, 307, 308, 401, 403, 500])
def test_refused_or_redirected_write_cannot_publish_manifest(public_bundle, objects, status):
    p, s = public_bundle, objects
    path = '/products/blobs/' + p.blob.name
    s.overrides['PUT', path] = lambda request: httpx.Response(status, headers={'location': 'https://foreign.example.test/'})
    with pytest.raises(upload.UploadError):
        send(p, s)
    assert s.calls == [('PUT', path)] and s.records == {}


def test_existing_corrupt_blob_is_never_overwritten_or_followed_by_manifest(public_bundle, objects):
    p, s = public_bundle, objects
    path = '/products/blobs/' + p.blob.name
    s.records[path] = b'wrong remote bytes'
    with pytest.raises(upload.UploadError):
        send(p, s)
    assert manifest_path(p) not in s.records and s.records[path] == b'wrong remote bytes'


def test_conflicting_signed_entry_is_retained_and_refused(public_bundle, objects):
    p, s = public_bundle, objects
    original = deepcopy(p.payload)
    p.payload['entry']['products']['asset']['inventory']['files']['0/asset.txt']['sha256'] = 'f' * 64
    p.sign()
    conflict = (p.directory / 'manifest.json').read_bytes()
    s.records[manifest_path(p)] = conflict
    p.payload.clear()
    p.payload.update(original)
    p.sign()
    with pytest.raises(upload.UploadError, match='conflicts'):
        send(p, s)
    assert s.records[manifest_path(p)] == conflict


@pytest.mark.parametrize('change', ['signature', 'unpinned', 'private', 'v1'])
def test_existing_manifest_must_also_be_trusted_public_and_v2(public_bundle, objects, change):
    p, s = public_bundle, objects
    original = deepcopy(p.payload)
    if change == 'private':
        p.payload['redistribution']['asset']['permission'] = 'private'
    elif change == 'unpinned':
        p.payload['publisher'] = '0' * 64
    elif change == 'v1':
        p.payload['schema'] = 1
        p.payload['producer'].pop('execution')
        p.payload['producer'].pop('audit_sha256')
        p.payload['producer']['guarded'] = True
    p.sign()
    existing = (p.directory / 'manifest.json').read_bytes()
    if change == 'signature':
        existing = existing.replace(b'approval-123', b'approval-456')
    s.records[manifest_path(p)] = existing
    p.payload.clear()
    p.payload.update(original)
    p.sign()
    with pytest.raises(upload.UploadError):
        send(p, s)
    assert s.records[manifest_path(p)] == existing


def test_readback_timeout_leaves_only_unreferenced_blob(public_bundle, objects):
    p, s = public_bundle, objects
    path = '/products/blobs/' + p.blob.name
    s.overrides['GET', path] = lambda request: httpx.Response(200, stream=Stream([p.contents], delay=.2))
    with pytest.raises(upload.UploadError):
        send(p, s, timeout=.03)
    assert manifest_path(p) not in s.records


def test_real_worker_dry_run_uses_no_credentials(public_bundle, objects, monkeypatch):
    objects.token.unlink()
    monkeypatch.setattr(upload, '_worker_upload', objects.worker)
    receipt = send(public_bundle, objects, dry_run=True, timeout=5)
    assert receipt['dry_run'] and objects.calls == []


def test_hard_deadline_reaps_only_owned_worker(public_bundle, objects, monkeypatch):
    from atelier.safety import process
    children = []
    def sleeper(command, **kwargs):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(process, 'spawn', sleeper)
    monkeypatch.setattr(upload, '_worker_upload', objects.worker)
    with pytest.raises(upload.UploadError, match='deadline'):
        send(public_bundle, objects, timeout=.05)
    assert len(children) == 1 and children[0].poll() is not None
    assert objects.calls == [] and objects.credentials == []


def test_shipped_sandbox_export_upload_fetch_and_normal_restore(producer, objects, monkeypatch):
    p = producer
    for grant in p.policy['actions']['sandbox/world.block'].values():
        grant['permission'] = 'public'
    p.policy_path.write_text(json.dumps(p.policy))
    p.commit()
    publisher.publish('sandbox', 'world.block', p.destination, profile=p.profile, echo=lambda _: None)
    payload = json.loads((p.destination / 'manifest.json').read_bytes())['payload']
    public = p.private.public_key().public_bytes_raw()
    trust = p.root / 'receiver-trust.json'
    trust.write_text(json.dumps({'schema': 1, 'publishers': {
        hashlib.sha256(public).hexdigest(): base64.b64encode(public).decode('ascii')}}))
    assert upload.upload_bundle(p.destination, trust, profile=objects.profile)['uploaded']
    receiver = build_cache.Store(p.root / 'receiver-cache')
    remote.fetch_bundle(BASE, payload['entry']['key'], trust, store=receiver)
    ctx = build.Context('sandbox')
    step = next(s for s in build.load_recipe('sandbox').steps(ctx) if s.name == 'world.block')
    expected = {root: root.read_bytes() for product in step.products for root in product.paths}
    for root in expected:
        root.unlink()
    (ctx.stamps / 'world.block.json').unlink()
    monkeypatch.setattr(build_cache, 'Store', lambda: receiver)
    monkeypatch.setattr(build, 'run_command', lambda *args, **kwargs: pytest.fail('receiver executed a command'))
    assert build.build('sandbox', ['world.block'], echo=lambda _: None, verify=True) == 0
    assert {root: root.read_bytes() for root in expected} == expected
    assert build_products.records(step) == payload['entry']['products']
