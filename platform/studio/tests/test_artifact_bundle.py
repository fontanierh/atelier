"""Offline trust and byte boundaries; no network, native tools, or persistent keys."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atelier import artifact_bundle as bundle
from atelier import build, build_cache, build_products, paths
from atelier.build import Product, Python, Step


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


@pytest.fixture
def package(tmp_path):
    directory = tmp_path / 'bundle'
    blobs = directory / 'blobs'
    blobs.mkdir(parents=True)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    publisher = hashlib.sha256(public).hexdigest()
    contents = b'hello-bundle'
    digest = hashlib.sha256(contents).hexdigest()
    blob = blobs / digest
    blob.write_bytes(contents)
    inventory = {'schema': 1, 'files': {'0/.': {'kind': 'directory'},
                 '0/asset.txt': {'kind': 'file', 'size': len(contents), 'sha256': digest},
                 '0/empty': {'kind': 'directory'}}}
    payload = {'schema': 1, 'namespace': bundle.NAMESPACE, 'publisher': publisher,
               'entry': {'schema': 1, 'key': 'a' * 64, 'products': {
                   'asset': {'digest': build_products.identity(inventory), 'inventory': inventory}}},
               'producer': {'source_commit': 'b' * 40, 'clean': True, 'pushed': True,
                            'guarded': True, 'tool_context': 'c' * 64},
               'redistribution': {'asset': {'permission': 'private', 'grant': 'approval-123'}},
               'root_names': {'asset': ['asset']}}
    trust = tmp_path / 'trust.json'
    trust.write_text(json.dumps({'schema': 1, 'publishers': {
        publisher: base64.b64encode(public).decode('ascii')}}))

    def sign(*, rehash=True, domain=None):
        if rehash:
            for record in payload['entry']['products'].values():
                record['digest'] = build_products.identity(record['inventory'])
        selected = bundle.DOMAIN if payload['schema'] == 1 else bundle.DOMAIN_V2
        signature = key.sign((selected if domain is None else domain) + canonical(payload))
        (directory / 'manifest.json').write_text(json.dumps({
            'payload': payload, 'signature': base64.b64encode(signature).decode('ascii')}, sort_keys=True))

    sign()
    return SimpleNamespace(directory=directory, blobs=blobs, blob=blob, contents=contents,
                           payload=payload, trust=trust, sign=sign,
                           store=build_cache.Store(tmp_path / 'store'), root=tmp_path)


def ingest(p, **kwargs):
    return bundle.import_bundle(p.directory, p.trust, store=p.store, **kwargs)


def assert_refused_without_store(p):
    with pytest.raises(ValueError):
        ingest(p)
    assert not p.store.root.exists()


def test_verified_snapshot_preserves_manifest_bytes_and_consumer_errors(package):
    class ConsumerError(ValueError):
        pass
    original = (package.directory / 'manifest.json').read_bytes()
    with pytest.raises(ConsumerError, match='consumer failure'):
        with bundle.verified_snapshot(package.directory, package.trust) as snapshot:
            assert snapshot.manifest == original
            assert (snapshot.blobs / package.blob.name).read_bytes() == package.contents
            raise ConsumerError('consumer failure')
    assert not snapshot.staging.exists() and not package.store.root.exists()


def test_verified_import_preserves_exact_cas_entry_and_private_assertion(package):
    p = package
    receipt = ingest(p)
    assert receipt['imported'] and not receipt['dry_run']
    assert receipt['products'] == ['asset'] and receipt['blobs'] == 1
    assert receipt['logical_bytes'] == len(p.contents)
    assert receipt['public_redistribution_asserted'] is False
    assert receipt['redistribution'] == p.payload['redistribution']
    assert receipt['provenance_verification'] == 'pinned publisher assertion only'
    assert json.loads(p.store.action('a' * 64).read_text()) == p.payload['entry']
    assert p.store.blob(p.blob.name).read_bytes() == p.contents
    ingest(p)  # Identical imports retain the existing immutable entry.
    p.blob.write_bytes(b'changed input after successful import')
    assert p.store.blob(p.blob.name).read_bytes() == p.contents


def test_public_permission_is_explicit_and_survives_receipt(package):
    p = package
    p.payload['redistribution']['asset']['permission'] = 'public'
    p.sign()
    assert ingest(p)['public_redistribution_asserted'] is True


def test_v1_guarded_and_v2_audited_producers_preserve_the_same_cas_entry(package):
    p = package
    v1 = ingest(p)
    original = p.store.action('a' * 64).read_bytes()
    p.payload['schema'] = 2
    p.payload['producer'].pop('guarded')
    p.payload['producer'].update(execution='audited-python-v1', audit_sha256='d' * 64)
    p.sign()
    v2 = ingest(p)
    assert p.store.action('a' * 64).read_bytes() == original
    assert v1['producer_attestation']['guarded'] is True
    assert v2['producer_attestation']['execution'] == 'audited-python-v1'
    assert 'guarded' not in v2['producer_attestation']


@pytest.mark.parametrize('condition', ['wrong-domain', 'mixed-variant', 'missing-audit', 'bad-audit',
                                     'unknown-execution', 'numeric-clean', 'v1-with-v2-fields'])
def test_versioned_producer_variants_and_signature_domains_are_exact(package, condition):
    p = package
    p.payload['schema'] = 2
    producer = p.payload['producer']
    producer.pop('guarded')
    producer.update(execution='audited-python-v1', audit_sha256='d' * 64)
    if condition == 'mixed-variant':
        producer['guarded'] = True
    elif condition == 'missing-audit':
        producer.pop('audit_sha256')
    elif condition == 'bad-audit':
        producer['audit_sha256'] = 'unknown'
    elif condition == 'unknown-execution':
        producer['execution'] = 'native'
    elif condition == 'numeric-clean':
        producer['clean'] = 1
    elif condition == 'v1-with-v2-fields':
        p.payload['schema'] = 1
    p.sign(domain=bundle.DOMAIN if condition == 'wrong-domain' else None)
    assert_refused_without_store(p)


def test_multiple_products_and_ordered_file_roots_preserve_exact_inventories(package):
    p = package
    file_record = deepcopy(p.payload['entry']['products']['asset']['inventory']['files']['0/asset.txt'])
    inventory = {'schema': 1, 'files': {'0/.': file_record, '1/.': deepcopy(file_record)}}
    p.payload['entry']['products']['pair'] = {'digest': '', 'inventory': inventory}
    p.payload['root_names']['pair'] = ['first.txt', 'second.txt']
    p.payload['redistribution']['pair'] = {'permission': 'public', 'grant': 'approval-456'}
    p.sign()
    receipt = ingest(p)
    assert receipt['products'] == ['asset', 'pair'] and receipt['blobs'] == 1
    assert receipt['logical_bytes'] == 3 * len(p.contents)
    assert receipt['public_redistribution_asserted'] is False
    assert json.loads(p.store.action('a' * 64).read_text()) == p.payload['entry']


def test_dry_run_fully_verifies_without_creating_or_changing_store(package):
    p = package
    result = ingest(p, dry_run=True)
    assert result['dry_run'] and not result['imported']
    assert not p.store.root.exists()
    ingest(p)
    before = {str(f.relative_to(p.store.root)): (f.read_bytes(), f.stat().st_mtime_ns)
              for f in p.store.root.rglob('*') if f.is_file()}
    ingest(p, dry_run=True)
    after = {str(f.relative_to(p.store.root)): (f.read_bytes(), f.stat().st_mtime_ns)
             for f in p.store.root.rglob('*') if f.is_file()}
    assert before == after
    p.blob.write_bytes(b'x' * len(p.contents))
    with pytest.raises(ValueError):
        ingest(p, dry_run=True)


def test_payload_and_blob_tampering_are_rejected(package):
    p = package
    path = p.directory / 'manifest.json'
    original = path.read_text()
    value = json.loads(original)
    value['payload']['producer']['source_commit'] = 'd' * 40
    path.write_text(json.dumps(value))
    assert_refused_without_store(p)
    path.write_text(original)
    p.blob.write_bytes(b'x' * len(p.contents))
    assert_refused_without_store(p)


def test_wrong_publisher_key_or_unsigned_envelope_is_refused(package):
    p = package
    p.trust.write_text(json.dumps({'schema': 1, 'publishers': {}}))
    assert_refused_without_store(p)
    (p.directory / 'manifest.json').write_text(json.dumps({'payload': p.payload}))
    assert_refused_without_store(p)


@pytest.mark.parametrize('change', ['missing_grant', 'missing_product_grant', 'invalid_permission',
                                 'false_attestation', 'numeric_attestation', 'unknown_namespace',
                                 'extra_payload_field', 'missing_root_names', 'wrong_root_count'])
def test_trusted_signatures_do_not_bypass_policy_or_schema(package, change):
    p = package
    if change == 'missing_grant':
        p.payload.pop('redistribution')
    elif change == 'missing_product_grant':
        p.payload['redistribution'] = {}
    elif change == 'invalid_permission':
        p.payload['redistribution']['asset']['permission'] = 'unspecified'
    elif change == 'false_attestation':
        p.payload['producer']['guarded'] = False
    elif change == 'numeric_attestation':
        p.payload['producer']['clean'] = 1
    elif change == 'unknown_namespace':
        p.payload['namespace'] = 'native-unreal'
    elif change == 'extra_payload_field':
        p.payload['unrecognized'] = True
    elif change == 'missing_root_names':
        p.payload.pop('root_names')
    else:
        p.payload['root_names']['asset'] = []
    p.sign()
    assert_refused_without_store(p)


@pytest.mark.parametrize('name', ['.env', '.env.production', 'auth.json', 'billing.csv',
                                'ledger.json', 'Content/asset.txt', 'asset.UASSET',
                                'asset.dll', '../escape', '/absolute', 'a\\b'])
def test_unsafe_inventory_members_are_refused_even_when_signed(package, name):
    p = package
    files = p.payload['entry']['products']['asset']['inventory']['files']
    files['0/' + name] = files.pop('0/asset.txt')
    p.sign()
    assert_refused_without_store(p)


@pytest.mark.parametrize('label', ['.env', 'auth.json', 'ledger.json', 'asset.uasset', 'Binaries',
                                 '../asset', '/asset', '.', 'a/b', 'a\\b', 'asset/', './asset',
                                 '.netrc', '.npmrc', '.pypirc', 'id_rsa', 'id_ed25519', 'api-key.json',
                                 'asset.pak', 'asset.ucas', 'asset.utoc', 'shaders.metallib', 'shader.spv'])
def test_signed_original_root_names_close_indexed_root_filename_gap(package, label):
    p = package
    p.payload['root_names']['asset'] = [label]
    p.sign()
    assert_refused_without_store(p)


@pytest.mark.parametrize('target', ['bundle', 'manifest', 'blobs', 'blob', 'trust'])
def test_symlink_inputs_are_refused(package, target):
    p = package
    if target == 'bundle':
        link = p.root / 'linked-bundle'
        link.symlink_to(p.directory, target_is_directory=True)
        p.directory = link
    elif target == 'blobs':
        moved = p.root / 'real-blobs'
        p.blobs.rename(moved)
        p.blobs.symlink_to(moved, target_is_directory=True)
    else:
        path = {'manifest': p.directory / 'manifest.json', 'blob': p.blob, 'trust': p.trust}[target]
        actual = p.root / ('actual-' + target)
        path.rename(actual)
        path.symlink_to(actual)
    assert_refused_without_store(p)


def test_special_file_is_refused_without_blocking(package):
    p = package
    p.blob.unlink()
    os.mkfifo(p.blob)
    assert_refused_without_store(p)


@pytest.mark.parametrize('change', ['missing_blob', 'extra_blob', 'incomplete_root', 'missing_parent',
                                 'bad_inventory_digest', 'wrong_size', 'unknown_record_field'])
def test_complete_inventory_and_blob_set_are_required(package, change):
    p = package
    record = p.payload['entry']['products']['asset']
    files = record['inventory']['files']
    if change == 'missing_blob':
        p.blob.unlink()
    elif change == 'extra_blob':
        (p.blobs / ('f' * 64)).write_bytes(b'not declared')
    elif change == 'incomplete_root':
        files.pop('0/.')
    elif change == 'missing_parent':
        files['0/nested/asset.txt'] = files.pop('0/asset.txt')
    elif change == 'wrong_size':
        files['0/asset.txt']['size'] += 1
    elif change == 'unknown_record_field':
        files['0/asset.txt']['extra'] = True
    p.sign()
    if change == 'bad_inventory_digest':
        # Keep the envelope signature valid while claiming an unrelated inventory digest.
        record['digest'] = 'f' * 64
        p.sign(rehash=False)
    assert_refused_without_store(p)


def test_missing_parent_is_refused_before_copying_any_product(package, monkeypatch):
    p = package
    files = p.payload['entry']['products']['asset']['inventory']['files']
    files['0/a/b/c/d/asset.txt'] = files.pop('0/asset.txt')
    p.sign()
    def unexpected_copy(*args, **kwargs):
        pytest.fail('Invalid sparse inventory reached product staging')
    monkeypatch.setattr(build_cache, 'copy_file', unexpected_copy)
    with pytest.raises(ValueError, match='Incomplete product directory inventory'):
        ingest(p)
    assert not p.store.root.exists()


@pytest.mark.parametrize('limit', ['MAX_MANIFEST', 'MAX_TRUST', 'MAX_RECORDS', 'MAX_PRODUCTS', 'MAX_ROOTS', 'MAX_BYTES'])
def test_resource_limits_fail_before_store_mutation(package, monkeypatch, limit):
    monkeypatch.setattr(bundle, limit, 0)
    assert_refused_without_store(package)


def test_logical_quota_counts_repeated_references_to_one_blob(package, monkeypatch):
    p = package
    files = p.payload['entry']['products']['asset']['inventory']['files']
    files['0/copy.txt'] = deepcopy(files['0/asset.txt'])
    p.sign()
    monkeypatch.setattr(bundle, 'MAX_BYTES', 2 * len(p.contents) - 1)
    assert_refused_without_store(p)


@pytest.mark.parametrize('kind', ['duplicate', 'float', 'nan', 'deep'])
def test_bounded_strict_json_is_required(package, kind):
    p = package
    path = p.directory / 'manifest.json'
    text = path.read_text()
    if kind == 'duplicate':
        text = text.replace('"schema": 1', '"schema": 1, "schema": 1', 1)
    elif kind == 'float':
        text = text.replace('"schema": 1', '"schema": 1.0', 1)
    elif kind == 'nan':
        text = text.replace('"schema": 1', '"schema": NaN', 1)
    else:
        text = '[' * 10000 + '0' + ']' * 10000
    path.write_text(text)
    assert_refused_without_store(p)


def test_interruption_before_action_commit_never_publishes_an_action(package, monkeypatch):
    p = package
    def interrupted(*args):
        raise OSError('unsafe private path must not be included')
    monkeypatch.setattr(build_cache, 'atomic_json', interrupted)
    with pytest.raises(ValueError) as error:
        ingest(p)
    assert 'unsafe private path' not in str(error.value)
    assert not p.store.action('a' * 64).exists()


def test_conflicting_action_keeps_first_entry_and_disables_reuse(package, monkeypatch):
    p = package
    ingest(p)
    original = p.store.action('a' * 64).read_bytes()
    original_entry = deepcopy(p.payload['entry'])
    files = p.payload['entry']['products']['asset']['inventory']['files']
    files['0/renamed.txt'] = files.pop('0/asset.txt')
    p.sign()
    with pytest.raises(ValueError):
        ingest(p)
    assert p.store.action('a' * 64).read_bytes() == original
    conflict = p.store.action('a' * 64).with_suffix('.conflict.json')
    marker = conflict.read_bytes()
    p.payload['entry'] = original_entry
    p.sign()
    def no_publication(*args, **kwargs):
        pytest.fail('quarantined action reached store publication')
    monkeypatch.setattr(p.store, 'publish', no_publication)
    with pytest.raises(ValueError, match='Action key conflict'):
        ingest(p)
    assert p.store.action('a' * 64).read_bytes() == original
    assert conflict.read_bytes() == marker


def test_normal_build_restores_imported_action_without_executing_script(package, monkeypatch):
    p = package
    checkout = p.root / 'checkout'
    checkout.mkdir()
    script = checkout / 'generate.py'
    script.write_text("raise RuntimeError('imported cache hit must not execute this script')\n")
    ctx = SimpleNamespace(game='fixture', out=checkout / 'build/fixture',
                          logs=checkout / 'build/fixture/logs', stamps=checkout / 'build/fixture/stamps')
    step = Step('generate', [Python(script)], cache=True,
                products=[Product('asset', (ctx.out / 'asset',))])
    monkeypatch.setattr(paths, 'REPO', checkout)
    monkeypatch.setattr(paths, 'build_root', lambda: ctx.out.parent)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *args, **kwargs: {'tool': 'fixture'})
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: [step]))
    p.payload['entry']['key'] = build.fingerprint(step, {})
    p.sign()
    ingest(p)
    assert not ctx.out.exists()  # Import creates only CAS content, never successful stamps.
    monkeypatch.setattr(build_cache, 'Store', lambda: p.store)
    def no_execution(*args, **kwargs):
        pytest.fail('normal build executed a command instead of restoring the imported action')
    monkeypatch.setattr(build, 'run_command', no_execution)
    assert build.build('fixture', echo=lambda message: None) == 0
    assert (ctx.out / 'asset/asset.txt').read_bytes() == p.contents
    assert (ctx.out / 'asset/empty').is_dir()
    stamp = json.loads((ctx.stamps / 'generate.json').read_text())
    assert stamp['products'] == p.payload['entry']['products']
    (ctx.out / 'asset/asset.txt').write_bytes(b'independent checkout mutation')
    assert p.store.blob(p.blob.name).read_bytes() == p.contents


def test_shipped_sandbox_block_import_and_automatic_restore(package, monkeypatch):
    p = package
    source = paths.GAMES / 'sandbox'
    repo = p.root / 'sandbox-checkout'
    game = repo / 'games/sandbox'
    game.mkdir(parents=True)
    shutil.copytree(source / 'world', game / 'world', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(source / 'build.py', game / 'build.py')
    shutil.copyfile(paths.REPO / 'uv.lock', repo / 'uv.lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'GAMES', repo / 'games')
    monkeypatch.setenv('ATELIER_CACHE', str(p.root / 'producer-cache'))
    for name in ('ATELIER_BUILD_ROOT', 'ATELIER_PYTHON', 'PYTHONHOME', 'PYTHONPATH'):
        monkeypatch.delenv(name, raising=False)
    calls = []
    real_run = build.run_command
    def run(ctx, step, *args, **kwargs):
        assert not step.heavy
        calls.append(step.name)
        return real_run(ctx, step, *args, **kwargs)
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('sandbox', ['world.block'], echo=lambda message: None) == 0
    assert calls == ['world.block']
    ctx = build.Context('sandbox')
    step = next(s for s in build.load_recipe('sandbox').steps(ctx) if s.name == 'world.block')
    expected_bytes = {root: root.read_bytes() for product in step.products for root in product.paths}
    stamp_path = ctx.stamps / 'world.block.json'
    key = json.loads(stamp_path.read_text())['fingerprint']
    producer_store = build_cache.Store()
    p.payload['entry'] = json.loads(producer_store.action(key).read_text())
    p.payload['root_names'] = {product.name: [root.name for root in product.paths] for product in step.products}
    p.payload['redistribution'] = {product.name: {'permission': 'private', 'grant': 'fixture-only'}
                                   for product in step.products}
    # Ephemeral test assertions simulate a trusted publisher, not production provenance.
    for blob in p.blobs.iterdir():
        blob.unlink()
    for record in p.payload['entry']['products'].values():
        for item in record['inventory']['files'].values():
            if item['kind'] == 'file':
                shutil.copyfile(producer_store.blob(item['sha256']), p.blobs / item['sha256'])
    p.sign()
    ingest(p)
    for root in expected_bytes:
        root.unlink()
    stamp_path.unlink()
    monkeypatch.setattr(build_cache, 'Store', lambda: p.store)
    def no_execution(*args, **kwargs):
        pytest.fail('sandbox executed a command instead of restoring its imported products')
    monkeypatch.setattr(build, 'run_command', no_execution)
    assert build.build('sandbox', ['world.block'], echo=lambda message: None) == 0
    assert {root: root.read_bytes() for root in expected_bytes} == expected_bytes
    assert build_products.records(step) == p.payload['entry']['products']
    restored = json.loads(stamp_path.read_text())
    assert restored['restored_from'] == key
    assert restored['products'] == p.payload['entry']['products']
