"""Signed transport boundaries and owned-worker deadlines; no external service or native tools."""
import asyncio
from contextlib import ExitStack
import json
import shutil
import subprocess
import sys
import time

import httpx
import pytest

from atelier import artifact_bundle as bundle, artifact_remote as remote, build, build_products
from test_artifact_bundle import package  # noqa: F401 -- shared signed-bundle fixture
from test_build_cache import project  # noqa: F401 -- real build/cache fixture


KEY = 'a' * 64
BASE = 'https://cache.example.test/prefix/'


@pytest.fixture(autouse=True)
def no_ambient_remote(monkeypatch):
    for name in ('ATELIER_ARTIFACT_URL', 'ATELIER_ARTIFACT_TRUST', 'ATELIER_ARTIFACT_TIMEOUT'):
        monkeypatch.delenv(name, raising=False)


class Stream(httpx.AsyncByteStream):
    def __init__(self, contents, *, delay=0):
        self.contents, self.delay = contents, delay

    async def __aiter__(self):
        for chunk in self.contents:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk


@pytest.fixture
def server(package, monkeypatch):
    p = package
    requests, options = [], []
    responses = {}
    manifest_path = f'/prefix/actions/{KEY}/manifest.json'

    def serve(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.headers['accept-encoding'] == 'identity'
        assert not request.headers.get('authorization')
        path = request.url.path
        if path in responses:
            return responses[path](request)
        if path == f'/prefix/actions/{p.payload["entry"]["key"]}/manifest.json':
            contents = (p.directory / 'manifest.json').read_bytes()
        elif path.startswith('/prefix/blobs/') and (p.blobs / path.rsplit('/', 1)[-1]).is_file():
            contents = (p.blobs / path.rsplit('/', 1)[-1]).read_bytes()
        else:
            return httpx.Response(404)
        return httpx.Response(200, stream=Stream([contents]))

    client = httpx.AsyncClient
    def configured_client(**kwargs):
        options.append(kwargs)
        return client(transport=httpx.MockTransport(serve), **kwargs)
    monkeypatch.setattr(remote.httpx, 'AsyncClient', configured_client)

    def transfer(directory, *, timeout=1):
        return asyncio.run(remote._transfer(BASE, KEY, p.trust, directory, timeout, remote.Progress(None)))

    def in_process(base, key, trust, directory, timeout, echo):
        return asyncio.run(remote._transfer(base, key, trust, directory, timeout, remote.Progress(echo)))
    monkeypatch.setattr(remote, '_worker_transfer', in_process)
    return type('Server', (), {'requests': requests, 'options': options, 'responses': responses,
                               'transfer': staticmethod(transfer), 'manifest_path': manifest_path,
                               'client': staticmethod(client)})()


def fetch(p, **kwargs):
    return remote.fetch_bundle(BASE, KEY, p.trust, store=p.store, **kwargs)


def test_fetch_authenticates_then_uses_the_existing_importer(package, server):
    p = package
    messages = []
    receipt = fetch(p, echo=messages.append)
    assert receipt['key'] == KEY and receipt['transport'] == 'https' and receipt['imported']
    assert receipt['downloaded_bytes'] == len((p.directory / 'manifest.json').read_bytes()) + len(p.contents)
    assert [r.url.path for r in server.requests] == [server.manifest_path, f'/prefix/blobs/{p.blob.name}']
    assert all(o['trust_env'] is False and o['follow_redirects'] is False and 'verify' not in o for o in server.options)
    assert json.loads(p.store.action(KEY).read_bytes()) == p.payload['entry']
    assert p.store.blob(p.blob.name).read_bytes() == p.contents
    assert messages and all(BASE not in message for message in messages)


def test_dry_run_downloads_and_verifies_without_touching_store(package, server):
    receipt = fetch(package, dry_run=True)
    assert receipt['dry_run'] and not receipt['imported']
    assert len(server.requests) == 2 and not package.store.root.exists()


@pytest.mark.parametrize('change', ['wrong_key', 'unpinned', 'signature', 'missing_grant', 'native', 'quota'])
def test_bad_manifest_never_causes_a_blob_request(package, server, change):
    p = package
    if change == 'wrong_key':
        p.payload['entry']['key'] = 'b' * 64
    elif change == 'unpinned':
        p.trust.write_text('{"schema":1,"publishers":{}}')
    elif change == 'missing_grant':
        p.payload['redistribution'] = {}
    elif change == 'native':
        p.payload['root_names']['asset'] = ['owned.uasset']
    elif change == 'quota':
        p.payload['entry']['products']['asset']['inventory']['files']['0/asset.txt']['size'] = bundle.MAX_BYTES + 1
    p.sign()
    if change == 'signature':
        manifest = p.directory / 'manifest.json'
        manifest.write_bytes(manifest.read_bytes().replace(b'approval-123', b'approval-456'))
    with pytest.raises(remote.RemoteError):
        fetch(p)
    assert [r.url.path for r in server.requests] == [server.manifest_path]
    assert not p.store.root.exists()


@pytest.mark.parametrize('status', [301, 302, 307, 308, 206, 401, 403, 500])
def test_server_cannot_redirect_or_supply_partial_responses(package, server, status):
    server.responses[server.manifest_path] = lambda request: httpx.Response(
        status, headers={'location': 'http://other.example.test/secret?token=hidden'})
    with pytest.raises(remote.RemoteError, match='refused'):
        fetch(package)
    assert len(server.requests) == 1 and not package.store.root.exists()


def test_missing_action_is_an_explicit_miss(package, server):
    server.responses[server.manifest_path] = lambda request: httpx.Response(404)
    with pytest.raises(remote.RemoteMiss):
        fetch(package)
    assert len(server.requests) == 1 and not package.store.root.exists()


@pytest.mark.parametrize('change', ['oversize_header', 'oversize_stream', 'encoding', 'truncated_header',
                                  'wrong_size', 'wrong_hash', 'missing_blob'])
def test_malformed_responses_never_publish(package, server, change):
    p = package
    path = f'/prefix/blobs/{p.blob.name}'
    body, headers, status = p.contents, {}, 200
    if change == 'oversize_header':
        headers['content-length'] = str(len(body) + 1)
    elif change == 'oversize_stream':
        body += b'extra'
    elif change == 'encoding':
        headers['content-encoding'] = 'gzip'
    elif change == 'truncated_header':
        headers['content-length'] = str(len(body))
        body = body[:-1]
    elif change == 'wrong_size':
        body = body[:-1]
    elif change == 'wrong_hash':
        body = b'x' * len(body)
    elif change == 'missing_blob':
        status = 404
    server.responses[path] = lambda request: httpx.Response(status, headers=headers, stream=Stream([body]))
    with pytest.raises(remote.RemoteError):
        fetch(p)
    assert len(server.requests) == 2 and not p.store.root.exists()


def test_manifest_body_limit_is_streamed_not_trusted_from_headers(package, server):
    server.responses[server.manifest_path] = lambda request: httpx.Response(
        200, stream=Stream([b'x' * 65536] * (bundle.MAX_MANIFEST // 65536 + 1)))
    with pytest.raises(remote.RemoteError, match='byte limit'):
        fetch(package)
    assert len(server.requests) == 1 and not package.store.root.exists()


def test_trust_is_rechecked_after_download_before_publication(package, server):
    p = package
    path = f'/prefix/blobs/{p.blob.name}'
    def revoke(request):
        p.trust.write_text('{"schema":1,"publishers":{}}')
        return httpx.Response(200, stream=Stream([p.contents]))
    server.responses[path] = revoke
    with pytest.raises(remote.RemoteError, match='not pinned'):
        fetch(p)
    assert not p.store.root.exists()


def test_deadline_spans_manifest_and_blob_not_individual_requests(package, server):
    p = package
    for path, body in ((server.manifest_path, (p.directory / 'manifest.json').read_bytes()),
                       (f'/prefix/blobs/{p.blob.name}', p.contents)):
        server.responses[path] = lambda request, body=body: httpx.Response(200, stream=Stream([body], delay=.08))
    with pytest.raises(remote.RemoteError, match='deadline'):
        fetch(p, timeout=.13)
    assert not p.store.root.exists()


def test_slow_trickle_has_absolute_deadline(package, server):
    body = (package.directory / 'manifest.json').read_bytes()
    server.responses[server.manifest_path] = lambda request: httpx.Response(
        200, stream=Stream([body[i:i+1] for i in range(len(body))], delay=.01))
    before = time.monotonic()
    with pytest.raises(remote.RemoteError, match='deadline'):
        fetch(package, timeout=.1)
    assert time.monotonic() - before < 1 and not package.store.root.exists()


def test_foreign_network_error_does_not_leak_endpoint_or_credentials(package, server, capsys):
    def fail(request):
        raise httpx.ConnectError('https://user:password@example.test/?api_key=hidden')
    server.responses[server.manifest_path] = fail
    with pytest.raises(remote.RemoteError) as error:
        fetch(package, echo=print)
    assert str(error.value) == 'Artifact download or import failed'
    assert 'hidden' not in capsys.readouterr().out
    assert not package.store.root.exists()


@pytest.mark.parametrize('url', ['http://cache.example.test', 'https://user:secret@cache.example.test',
    'https://cache.example.test/?key=secret', 'https://cache.example.test/#fragment',
    'https://cache.example.test/a/../b', 'https://cache.example.test/a/%2e%2e/b',
    'https://cache.example.test/a//b', 'https://cache.example.test/a/%2fb',
    'https://cache.example.test/a/%255cb', 'https://cache.example.test/\\b',
    'https://cache.example.test/\n', 'https://cache.example.test:bad', '//cache.example.test', ''])
def test_unsafe_endpoint_refused_before_network(package, server, url):
    with pytest.raises(remote.RemoteError, match='endpoint'):
        remote.fetch_bundle(url, KEY, package.trust, store=package.store)
    assert server.requests == []


@pytest.mark.parametrize('value', [True, 0, -1, 301, float('nan'), float('inf'), '30'])
def test_invalid_deadline_refused_before_network(package, server, value):
    with pytest.raises(remote.RemoteError, match='deadline'):
        fetch(package, timeout=value)
    assert server.requests == []


def test_worker_hard_deadline_reaps_a_stuck_resolver_process(package, tmp_path, monkeypatch):
    from atelier.safety import process
    children = []
    def stuck(argv, **kwargs):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(process, 'spawn', stuck)
    before = time.monotonic()
    with ExitStack() as cleanup:
        cleanup.callback(lambda: [remote._stop(child) for child in children])
        with pytest.raises(remote.RemoteError, match='deadline'):
            remote.fetch_bundle(BASE, KEY, package.trust, store=package.store, timeout=.2)
        assert len(children) == 1 and children[0].poll() is not None
    assert time.monotonic() - before < 3 and not package.store.root.exists()


def test_ordinary_build_fetches_then_restores_verified_products_without_execution(package, server, project, monkeypatch):
    p, signed = project, package
    assert p.run() == 0
    expected = build_products.records(p.step)
    key = build.fingerprint(p.step, {})
    signed.payload['entry'] = json.loads(p.store.action(key).read_bytes())
    signed.payload['root_names'] = {product.name: [path.name for path in product.paths] for product in p.step.products}
    signed.payload['redistribution'] = {product.name: {'permission': 'private', 'grant': 'fixture-approval'}
                                        for product in p.step.products}
    shutil.rmtree(signed.blobs)
    signed.blobs.mkdir()
    for blob in (p.store.root / 'blobs').glob('*/*'):
        shutil.copyfile(blob, signed.blobs / (blob.parent.name + blob.name))
    signed.sign()
    shutil.rmtree(p.store.root)
    shutil.rmtree(p.ctx.out)
    p.calls.clear()
    def cannot_run(*args, **kwargs):
        pytest.fail('remote hit must restore independently without running the action')
    monkeypatch.setattr(build, 'run_command', cannot_run)
    monkeypatch.setenv('ATELIER_ARTIFACT_URL', BASE)
    monkeypatch.setenv('ATELIER_ARTIFACT_TRUST', str(signed.trust))
    assert p.run() == 0 and not p.calls
    assert build_products.records(p.step) == expected
    stamp = json.loads((p.ctx.stamps / 'mesh.json').read_bytes())
    assert stamp['restored_from'] == key and stamp['fingerprint'] == key
    assert len(server.requests) == 3  # Manifest plus two unique files across two products.
    server.requests.clear()
    assert p.run() == 0 and server.requests == []  # Current local products do not use the network.


@pytest.mark.parametrize('mode', ['outage', 'corruption', 'bad_configuration', 'disabled', 'force'])
def test_remote_problem_or_bypass_runs_the_real_local_fallback(package, server, project, monkeypatch, mode):
    p = project
    if mode != 'disabled':
        monkeypatch.setenv('ATELIER_ARTIFACT_URL', BASE)
        monkeypatch.setenv('ATELIER_ARTIFACT_TRUST', str(package.trust))
    if mode == 'bad_configuration':
        monkeypatch.setenv('ATELIER_ARTIFACT_URL', 'http://user:secret@example.test')
    elif mode == 'outage':
        def fail(*args, **kwargs):
            raise remote.RemoteError('Artifact download failed')
        monkeypatch.setattr(remote, 'fetch_bundle', fail)
    elif mode == 'corruption':
        def bad(request):
            return httpx.Response(200, stream=Stream([b'corrupt']))
        # Real build action has a different key; return malformed bytes at every manifest path.
        monkeypatch.setattr(remote.httpx, 'AsyncClient', lambda **kwargs: server.client(
            transport=httpx.MockTransport(bad), **kwargs))
    assert p.run(force=mode == 'force') == 0 and p.calls == ['mesh']
    stamp = json.loads((p.ctx.stamps / 'mesh.json').read_bytes())
    assert 'restored_from' not in stamp
    assert (p.ctx.out / 'mesh/vertices').read_text() == 'one'
    if mode in ('bad_configuration', 'disabled', 'force', 'outage'):
        assert server.requests == []
    if mode == 'bad_configuration':
        assert all('secret' not in message for message in p.messages)


def test_one_outage_disables_later_actions_without_repeated_waits(monkeypatch):
    calls, messages = [], []
    def fail(*args, **kwargs):
        calls.append(args)
        raise remote.RemoteError('Artifact download failed')
    monkeypatch.setattr(remote, 'fetch_bundle', fail)
    lookup = remote.RemoteCache(BASE, 'trust.json', 30)
    assert not lookup.fetch(KEY, object(), messages.append)
    assert not lookup.fetch('b' * 64, object(), messages.append)
    assert len(calls) == 1 and len(messages) == 1


def test_lookup_budget_is_shared_across_distinct_missing_actions(monkeypatch):
    clock = [100.0]
    calls, messages = [], []
    monkeypatch.setattr(remote.time, 'monotonic', lambda: clock[0])
    def missing(*args, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0] += 2
        raise remote.RemoteMiss('Remote action not found')
    monkeypatch.setattr(remote, 'fetch_bundle', missing)
    lookup = remote.RemoteCache(BASE, 'trust.json', 3)
    assert not lookup.fetch(KEY, object(), messages.append)
    clock[0] += 100  # A long local generator must not consume the network allowance.
    assert not lookup.fetch('b' * 64, object(), messages.append)
    assert not lookup.fetch('c' * 64, object(), messages.append)
    assert calls == [3, 1] and lookup.disabled
    assert len(messages) == 1 and 'budget exhausted' in messages[0]


def test_configuration_is_opt_in_and_requires_both_endpoint_and_trust(monkeypatch):
    assert remote.configured() is None
    monkeypatch.setenv('ATELIER_ARTIFACT_URL', BASE)
    with pytest.raises(remote.RemoteError, match='requires both'):
        remote.configured()
    monkeypatch.setenv('ATELIER_ARTIFACT_TRUST', 'publishers.json')
    monkeypatch.setenv('ATELIER_ARTIFACT_TIMEOUT', '5')
    config = remote.configured()
    assert (config.base, str(config.trust), config.timeout) == (BASE, 'publishers.json', 5)


def test_read_only_plan_does_not_even_load_remote_configuration(project, monkeypatch):
    def cannot_configure():
        pytest.fail('a plan must never configure or fetch remote artifacts')
    monkeypatch.setattr(remote, 'configured', cannot_configure)
    assert project.run(dry=True) == 0 and not project.calls


@pytest.fixture
def worker_script(tmp_path, monkeypatch):
    """Keep real worker lifecycle assertions, with deterministic subprocess HTTP responses."""
    from atelier.safety import process
    children = []
    script = tmp_path / 'download_standin.py'
    def install(source):
        script.write_text(source)
        def spawn(argv, **kwargs):
            child = subprocess.Popen([sys.executable, str(script), argv[-1]], **kwargs)
            children.append(child)
            return child
        monkeypatch.setattr(process, 'spawn', spawn)
        return children
    try:
        yield install
    finally:
        for child in children:
            remote._stop(child)


def test_actual_worker_protocol_downloads_then_parent_imports(package, worker_script):
    p = package
    # The child runs production worker + transport, with only HTTP responses replaced.
    worker_script('''
import json, sys
from pathlib import Path
import httpx
from atelier import artifact_remote as remote, artifact_remote_worker as worker
request = json.loads(Path(sys.argv[1]).read_bytes())
source = Path(request['trust']).parent / 'bundle'
class Stream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield self.data
def respond(request):
    path = source / ('manifest.json' if request.url.path.endswith('/manifest.json') else 'blobs/' + request.url.path.rsplit('/', 1)[-1])
    stream = Stream()
    stream.data = path.read_bytes()
    return httpx.Response(200, stream=stream)
client = httpx.AsyncClient
remote.httpx.AsyncClient = lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs)
raise SystemExit(worker.main(sys.argv[1]))
''')
    result = fetch(p, timeout=5)
    assert result['key'] == KEY and p.store.blob(p.blob.name).read_bytes() == p.contents


@pytest.mark.parametrize('mode', ['no_receipt', 'oversized', 'invalid_json', 'non_object', 'bad_count', 'nonzero'])
def test_bad_worker_completion_is_refused_and_reaped(package, worker_script, mode):
    source = f'''
import json, sys
from pathlib import Path
request = json.loads(Path(sys.argv[1]).read_bytes())
mode = {mode!r}
result = Path(request['result'])
if mode == 'oversized': result.write_text('x' * 4097)
elif mode == 'invalid_json': result.write_text('{{')
elif mode == 'non_object': result.write_text('[]')
elif mode == 'bad_count': result.write_text('{{"downloaded_bytes":true}}')
elif mode == 'nonzero': result.write_text('{{"error":"Artifact download failed"}}')
raise SystemExit(1 if mode == 'nonzero' else 0)
'''
    children = worker_script(source)
    with pytest.raises(remote.RemoteError):
        fetch(package, timeout=5)
    assert len(children) == 1 and children[0].poll() is not None
    assert not package.store.root.exists()


def test_parent_reaps_worker_if_progress_consumer_raises(package, worker_script):
    children = worker_script("import time; print('Artifact transfer: waiting', flush=True); time.sleep(60)")
    def broken_progress(message):
        raise RuntimeError('consumer stopped')
    with pytest.raises(RuntimeError, match='consumer stopped'):
        fetch(package, timeout=5, echo=broken_progress)
    assert len(children) == 1 and children[0].poll() is not None
    assert not package.store.root.exists()


def test_parent_checks_requested_key_again_before_import(package, monkeypatch):
    p = package
    p.payload['entry']['key'] = 'b' * 64
    p.sign()
    def false_completion(base, key, trust, directory, timeout, echo):
        shutil.copytree(p.directory, directory, dirs_exist_ok=True)
        return len(p.contents)
    monkeypatch.setattr(remote, '_worker_transfer', false_completion)
    with pytest.raises(remote.RemoteError, match='differs from requested'):
        fetch(p)
    assert not p.store.root.exists()
