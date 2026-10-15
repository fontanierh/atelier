"""Ephemeral keys, local bare Git remotes and the shipped tiny Python action; no native tools."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from atelier import artifact_bundle as bundle, artifact_publisher as publisher
from atelier import build, build_audit, build_cache, build_products, paths


def git(repo, *arguments):
    result = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Fixture',
                             '-c', 'user.email=fixture@example.invalid', *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout


@pytest.fixture(scope='module')
def source_template(tmp_path_factory):
    root = tmp_path_factory.mktemp('publisher-source')
    repo = root / 'checkout'
    game = repo / 'games/sandbox'
    game.mkdir(parents=True)
    source = paths.GAMES / 'sandbox'
    shutil.copytree(source / 'world', game / 'world', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(source / 'build.py', game / 'build.py')
    shutil.copyfile(paths.REPO / 'uv.lock', repo / 'uv.lock')
    support = repo / 'tool-support'
    support.mkdir()
    for path in build_audit.SUPPORT:
        shutil.copyfile(path, support / path.name)
    for path in publisher.TOOL_SUPPORT:
        shutil.copyfile(path, support / path.name)
    (repo / '.gitignore').write_text('build/\n__pycache__/\n')
    policy = {'schema': 1, 'actions': {'sandbox/world.block': {
        'block.shape': {'permission': 'private', 'grant': 'fixture-only'},
        'block.bounds': {'permission': 'public', 'grant': 'fixture-only'}}}}
    policy_path = repo / 'artifact-grants.json'
    policy_path.write_text(json.dumps(policy))
    git(repo, 'init', '-b', 'main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'Fixture source')
    remote = root / 'remote.git'
    git(repo, 'init', '--bare', str(remote))
    git(repo, 'push', str(remote), 'HEAD:refs/heads/main')
    return SimpleNamespace(repo=repo, remote=remote)


@pytest.fixture
def producer(tmp_path, monkeypatch, source_template):
    # Independent ordinary copies avoid seven Git setup launches for every refusal fixture.
    repo, remote = tmp_path / 'checkout', tmp_path / 'remote.git'
    shutil.copytree(source_template.repo, repo)
    shutil.copytree(source_template.remote, remote)
    support = repo / 'tool-support'
    monkeypatch.setattr(publisher, 'TOOL_SUPPORT', tuple(support / p.name for p in publisher.TOOL_SUPPORT))
    monkeypatch.setattr(build_audit, 'SUPPORT', tuple(support / p.name for p in build_audit.SUPPORT))
    monkeypatch.setattr(build_audit, 'WORKER', support / build_audit.WORKER.name)
    return profile_files(tmp_path, monkeypatch)


@pytest.fixture
def profile_only(tmp_path, monkeypatch):
    return profile_files(tmp_path, monkeypatch)


def profile_files(tmp_path, monkeypatch):
    repo, remote = tmp_path / 'checkout', tmp_path / 'remote.git'
    game = repo / 'games/sandbox'
    game.mkdir(parents=True, exist_ok=True)
    policy_path = repo / 'artifact-grants.json'
    policy = (json.loads(policy_path.read_text()) if policy_path.exists() else
              {'schema': 1, 'actions': {'sandbox/world.block': {
                  'block.shape': {'permission': 'private', 'grant': 'fixture-only'},
                  'block.bounds': {'permission': 'public', 'grant': 'fixture-only'}}}})
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'GAMES', repo / 'games')
    for name in ('ATELIER_BUILD_ROOT', 'ATELIER_PYTHON', 'PYTHONHOME', 'PYTHONPATH'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'producer-cache'))
    private = Ed25519PrivateKey.generate()
    key = tmp_path / 'signing.key'
    key.write_bytes(private.private_bytes_raw())
    key.chmod(0o600)
    profile = tmp_path / 'publisher.json'
    config = {'schema': 1, 'repository': str(repo), 'remote': str(remote), 'ref': 'refs/heads/main',
              'actions': ['sandbox/world.block'], 'grants': 'artifact-grants.json', 'signing_key': str(key)}
    profile.write_text(json.dumps(config))
    profile.chmod(0o600)
    reads = []
    real_protected = publisher._protected
    def protected(path, **kwargs):
        if Path(path) == key and kwargs.get('contents', True):
            reads.append('key-read')
        return real_protected(path, **kwargs)
    monkeypatch.setattr(publisher, '_protected', protected)
    def commit():
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Fixture change')
        git(repo, 'push', str(remote), 'HEAD:refs/heads/main')
    def configure(**changes):
        config.update(changes)
        profile.write_text(json.dumps(config))
    return SimpleNamespace(root=tmp_path, repo=repo, game=game, remote=remote,
                           private=private, key=key, profile=profile, config=config,
                           policy=policy, policy_path=policy_path, commit=commit,
                           configure=configure, reads=reads, destination=tmp_path / 'export')


def export(p, **kwargs):
    return publisher.publish('sandbox', 'world.block', p.destination, profile=p.profile,
                             echo=lambda _: None, **kwargs)


def refuse(p, match=None):
    with pytest.raises(ValueError, match=match):
        export(p)
    assert not p.destination.exists()
    assert p.reads == []


def test_export_is_v2_signed_current_action_with_explicit_execution_and_no_upload(producer):
    p = producer
    result = export(p)
    assert p.reads == ['key-read']
    assert result['exported'] is True and result['uploaded'] is False
    assert result['execution'] == 'audited-python-v1'
    assert result['public_redistribution_asserted'] is False
    envelope = json.loads((p.destination / 'manifest.json').read_text())
    payload = envelope['payload']
    assert payload['schema'] == 2 and payload['namespace'] == bundle.NAMESPACE
    assert 'guarded' not in payload['producer']
    assert payload['producer']['source_commit'] == git(p.repo, 'rev-parse', 'HEAD').decode().strip()
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    p.private.public_key().verify(base64.b64decode(envelope['signature']),
                                  b'atelier-artifact-bundle-v2\0' + canonical)
    stamp = json.loads((p.repo / 'build/sandbox/stamps/world.block.json').read_text())
    assert stamp['audit_receipt']['execution'] == 'audited-python-v1'
    assert payload['producer']['audit_sha256'] == build_products.identity(stamp['audit_receipt'])
    assert payload['producer']['tool_context'] == stamp['input_state']['tools']
    assert payload['entry'] == {'schema': 1, 'key': stamp['fingerprint'], 'products': stamp['products']}
    assert payload['root_names'] == {'block.shape': ['shape.json'], 'block.bounds': ['bounds.json']}
    assert payload['redistribution'] == p.policy['actions']['sandbox/world.block']
    blobs = list((p.destination / 'blobs').iterdir())
    assert len(blobs) == 2
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == path.name for path in blobs)


def test_cached_existing_products_cannot_replace_fresh_execution(producer, monkeypatch):
    p = producer
    calls = []
    real_run = build.run_command
    def run(*args, **kwargs):
        calls.append('run')
        return real_run(*args, **kwargs)
    monkeypatch.setattr(build, 'run_command', run)
    export(p)
    first = json.loads((p.repo / 'build/sandbox/stamps/world.block.json').read_text())['audit_receipt']
    p.destination = p.root / 'second-export'
    export(p)
    second = json.loads((p.repo / 'build/sandbox/stamps/world.block.json').read_text())['audit_receipt']
    assert calls == ['run', 'run']
    assert first['run_id'] != second['run_id']


@pytest.mark.parametrize('condition', ['tracked-dirty', 'untracked', 'unapproved-ref', 'unpushed'])
def test_clean_and_fresh_advertised_revision_are_required(producer, condition):
    p = producer
    if condition == 'tracked-dirty':
        (p.game / 'world/block.json').write_text('{"size_cm":[1,2,3]}')
    elif condition == 'untracked':
        (p.repo / 'untracked.txt').write_text('not committed')
    elif condition == 'unapproved-ref':
        p.configure(ref='refs/heads/missing')
    else:
        (p.repo / 'new.txt').write_text('local commit')
        git(p.repo, 'add', '.')
        git(p.repo, 'commit', '-m', 'Not pushed')
    refuse(p)


@pytest.mark.parametrize('hidden', ['ignored-optional', 'assume-unchanged'])
def test_git_status_cannot_hide_consumed_local_bytes(producer, hidden):
    p = producer
    if hidden == 'ignored-optional':
        with (p.repo / '.gitignore').open('a') as stream:
            stream.write('block.override.json\n')
        p.commit()
        (p.game / 'world/block.override.json').write_text('{"size_cm":[1,2,3]}')
    else:
        git(p.repo, 'update-index', '--assume-unchanged', 'games/sandbox/world/block.json')
        (p.game / 'world/block.json').write_text('{"size_cm":[1,2,3]}')
    assert git(p.repo, 'status', '--porcelain') == b''
    refuse(p, 'committed')


@pytest.mark.parametrize('change', ['missing', 'extra', 'implicit', 'unknown'])
def test_grant_policy_requires_explicit_coverage(profile_only, change):
    p = profile_only
    grants = p.policy['actions']['sandbox/world.block']
    if change == 'missing':
        grants.pop('block.bounds')
    elif change == 'extra':
        grants['other'] = deepcopy(grants['block.shape'])
    elif change == 'implicit':
        grants['block.shape'].pop('grant')
    else:
        grants['block.shape']['permission'] = 'maybe'
    p.policy_path.write_text(json.dumps(p.policy))
    step = SimpleNamespace(name='world.block', products=[build.Product(name, ()) for name in ('block.shape', 'block.bounds')])
    with pytest.raises(ValueError):
        publisher._grants(p.policy_path, 'sandbox', step)
    assert p.reads == []


@pytest.mark.parametrize('condition', ['key-public', 'key-link', 'profile-public', 'profile-in-repo', 'not-allowed'])
def test_profile_and_key_are_protected_and_action_is_allowlisted(profile_only, condition):
    p = profile_only
    if condition == 'key-public':
        p.key.chmod(0o644)
    elif condition == 'key-link':
        target = p.root / 'real.key'
        p.key.rename(target)
        p.key.symlink_to(target)
    elif condition == 'profile-public':
        p.profile.chmod(0o644)
    elif condition == 'profile-in-repo':
        target = p.repo / 'publisher.json'
        shutil.copyfile(p.profile, target)
        target.chmod(0o600)
        p.profile = target
    else:
        p.configure(actions=['sandbox/world.placements'])
    refuse(p)


@pytest.mark.parametrize('change', ['heavy', 'unaudited', 'uncached', 'native', 'custom-verify'])
def test_action_eligibility_is_checked_before_any_execution(profile_only, monkeypatch, change):
    p = profile_only
    def load(game):
        def steps(ctx):
            step = build.Step('world.block', [build.Python(p.game / 'generate.py')], audit=True, cache=True,
                              products=[build.Product('result', (ctx.out / 'result.json',))])
            if change == 'heavy':
                step.heavy = True
            elif change == 'unaudited':
                step.audit = False
            elif change == 'uncached':
                step.cache = False
            elif change == 'native':
                step.commands = [build.Blender(step.commands[0].script)]
            else:
                step.verify = lambda: pytest.fail('custom verifier executed')
            return [step]
        return SimpleNamespace(steps=steps)
    monkeypatch.setattr(build, 'load_recipe', load)
    monkeypatch.setattr(build, 'run_command', lambda *a, **kw: pytest.fail('ineligible action executed'))
    with pytest.raises(ValueError):
        publisher._eligible(build.Context('sandbox'), 'sandbox', 'world.block')
    assert p.reads == []


@pytest.mark.parametrize('change', ['source', 'output', 'audit', 'no-run'])
def test_action_receipt_and_sources_are_current_before_key_read(producer, monkeypatch, change):
    p = producer
    real_build = build._build
    def run(*args, **kwargs):
        if change == 'no-run':
            return 0
        result = real_build(*args, **kwargs)
        if change == 'source':
            (p.game / 'world/block.json').write_text('{"size_cm":[1,2,3]}')
        elif change == 'output':
            (p.repo / 'build/sandbox/block/shape.json').write_text('tampered')
        else:
            report = p.repo / 'build/sandbox/logs/world.block.audit.json'
            data = json.loads(report.read_text())
            data['accesses'] = []
            report.write_text(json.dumps(data))
        return result
    monkeypatch.setattr(build, '_build', run)
    refuse(p)


def test_existing_destination_is_never_overwritten(profile_only):
    p = profile_only
    p.destination.mkdir()
    marker = p.destination / 'keep.txt'
    marker.write_text('existing destination')
    with pytest.raises(ValueError):
        export(p)
    assert marker.read_text() == 'existing destination' and p.reads == []


def test_shipped_sandbox_export_import_restores_without_command_execution(producer, monkeypatch):
    p = producer
    export(p)
    payload = json.loads((p.destination / 'manifest.json').read_text())['payload']
    public = p.private.public_key().public_bytes_raw()
    trust = p.root / 'trust.json'
    trust.write_text(json.dumps({'schema': 1, 'publishers': {
        hashlib.sha256(public).hexdigest(): base64.b64encode(public).decode('ascii')}}))
    receiver = build_cache.Store(p.root / 'receiver-cache')
    bundle.import_bundle(p.destination, trust, store=receiver)
    ctx = build.Context('sandbox')
    step = next(s for s in build.load_recipe('sandbox').steps(ctx) if s.name == 'world.block')
    expected = {root: root.read_bytes() for product in step.products for root in product.paths}
    for root in expected:
        root.unlink()
    (ctx.stamps / 'world.block.json').unlink()
    monkeypatch.setattr(build_cache, 'Store', lambda: receiver)
    monkeypatch.setattr(build, 'run_command', lambda *a, **kw: pytest.fail('restored action executed'))
    assert build.build('sandbox', ['world.block'], echo=lambda _: None, verify=True) == 0
    assert {root: root.read_bytes() for root in expected} == expected
    assert build_products.records(step) == payload['entry']['products']
    stamp = json.loads((ctx.stamps / 'world.block.json').read_text())
    assert stamp['restored_from'] == payload['entry']['key']
    assert 'audit_receipt' not in stamp  # Restoration never claims a new execution audit.


def test_hidden_tool_support_edits_are_not_committed_source(producer):
    p = producer
    target = publisher.TOOL_SUPPORT[1]
    git(p.repo, 'update-index', '--assume-unchanged', str(target.relative_to(p.repo)))
    target.write_text(target.read_text() + '\n# hidden local tool modification\n')
    assert git(p.repo, 'status', '--porcelain') == b''
    refuse(p, 'committed bytes')


@pytest.mark.parametrize('change', ['empty-directory', 'hidden-deletion'])
def test_directory_inputs_match_complete_committed_membership(producer, change):
    p = producer
    directory = p.game / 'declared-input'
    directory.mkdir()
    source = directory / 'source.txt'
    source.write_text('committed')
    recipe = p.game / 'build.py'
    recipe.write_text(recipe.read_text().replace("inputs=[GAME / 'world/block.json']",
                      "inputs=[GAME / 'world/block.json', GAME / 'declared-input']"))
    p.commit()
    if change == 'empty-directory':
        (directory / 'uncommitted-empty').mkdir()
    else:
        git(p.repo, 'update-index', '--assume-unchanged', str(source.relative_to(p.repo)))
        source.unlink()
    assert git(p.repo, 'status', '--porcelain') == b''
    refuse(p, 'membership')


def test_self_consistent_replacement_receipt_is_not_this_execution(producer, monkeypatch):
    p = producer
    real_build = build._build
    def run(*args, **kwargs):
        result = real_build(*args, **kwargs)
        stamp_path = p.repo / 'build/sandbox/stamps/world.block.json'
        report_path = p.repo / 'build/sandbox/logs/world.block.audit.json'
        stamp, report = json.loads(stamp_path.read_text()), json.loads(report_path.read_text())
        nonce = 'f' * 32
        stamp['audit_receipt']['run_id'] = nonce
        for access in report['accesses']:
            access['nonce'] = nonce
        stamp['audit_receipt']['report_sha256'] = build_products.identity(report)
        stamp_path.write_text(json.dumps(stamp))
        report_path.write_text(json.dumps(report))
        return result
    monkeypatch.setattr(build, '_build', run)
    refuse(p, 'this publisher execution')


def test_noncanonical_product_root_name_is_refused_before_key_read(producer):
    p = producer
    recipe = p.game / 'build.py'
    script = p.game / 'world/build_block.py'
    name = 'bad\\name.txt'
    recipe.write_text(recipe.read_text().replace("ctx.out / 'block/shape.json'", "ctx.out / 'block' / " + repr(name)))
    script.write_text(script.read_text().replace("output / 'shape.json'", 'output / ' + repr(name)))
    p.commit()
    refuse(p, 'root basename')


def test_failed_fresh_action_cannot_be_exported(producer):
    p = producer
    (p.game / 'world/build_block.py').write_text("raise RuntimeError('fixture-only build failure')\n")
    p.commit()
    refuse(p, 'action failed')
    assert not (p.repo / 'build/sandbox/stamps/world.block.json').exists()


def test_manifest_install_failure_leaves_no_importable_directory(producer, monkeypatch):
    p = producer
    real_rename = Path.rename
    def rename(path, target):
        if Path(target) == p.destination / 'manifest.json':
            raise OSError('fixture-only failed final manifest installation')
        return real_rename(path, target)
    monkeypatch.setattr(Path, 'rename', rename)
    with pytest.raises(ValueError):
        export(p)
    assert not p.destination.exists()
    assert p.reads == ['key-read']  # A fully verified run was signed, but no bundle was committed.
