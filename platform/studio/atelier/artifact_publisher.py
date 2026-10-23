"""Build and export one trusted, independent audited Python action as a signed bundle.

This is local directory export, not upload. The recipe and host are trusted: Python
input auditing is not hostile-code isolation. Owner-only keys outside the checkout
are read only after validation; same-UID malicious code is outside this guarantee.
"""
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import shutil
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import artifact_bundle as bundle, build, build_audit, build_cache, build_products, paths
from .build_hashes import HashIndex

DOMAIN = bundle.DOMAIN_V2
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_GIT_OUTPUT = 1024 * 1024
REF = re.compile(r'refs/heads/[A-Za-z0-9][A-Za-z0-9_./-]{0,200}\Z')
# Pin the executed adapter and identity support, plus the publisher's host build/certification
# engine. The latter two are trust checks, not inputs to the source action's execution key.
TOOL_SUPPORT = (Path(build_cache.__file__).with_name('build.py'), *build_cache.tool_support().values(),
                *(Path(build_cache.__file__).with_name(name) for name in build_cache.IDENTITY_SUPPORT))


class PublisherError(ValueError):
    """Fixed diagnostics: never disclose paths, git output or key material."""


def _fail(message):
    raise PublisherError(message)


def _git(repo, *arguments, limit=MAX_GIT_OUTPUT, request=None):
    """Bound output and time even for a misconfigured approved remote."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='file:https:ssh')
    argv = ['git', '--no-replace-objects', '--literal-pathspecs', '-C', str(repo),
            '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *arguments]
    with ExitStack() as cleanup:
        stdin = subprocess.DEVNULL
        if request is not None:
            stdin = cleanup.enter_context(tempfile.TemporaryFile())
            stdin.write(request)
            stdin.seek(0)
        child = cleanup.enter_context(subprocess.Popen(
            argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, start_new_session=True))
        completed = False
        try:
            data = bytearray()
            deadline = time.monotonic() + 15
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _fail('Git verification timed out')
                    if not ready.select(min(remaining, .1)):
                        continue
                    chunk = os.read(child.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > limit:
                        _fail('Git verification output exceeds limit')
            if child.wait(timeout=max(.001, deadline - time.monotonic())):
                _fail('Git verification failed')
            completed = True
            return data
        finally:
            if not completed:
                # Git may delegate to a remote/credential helper. Own a process group so a
                # deadline cannot abandon those children; never search or signal by name.
                for stop in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(child.pid, stop)
                    except ProcessLookupError:
                        break
                child.wait()


def _protected(path, *, limit, contents=True):
    path = Path(path)
    if not path.is_absolute():
        _fail('Publisher profile and key paths must be absolute')
    with ExitStack() as stack:
        fd, before = bundle._open_file(stack, path.parent.resolve() / path.name)
        if (before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_nlink != 1
                or before.st_size > limit):
            _fail('Publisher profile or key must be an owner-only regular file')
        if not contents:
            return before.st_size
        data = os.read(fd, limit + 1)
        if len(data) != before.st_size or bundle._signature(os.fstat(fd)) != bundle._signature(before):
            _fail('Publisher profile or key changed')
        return data


def _profile(path, game, step_name):
    config = bundle._json(_protected(path, limit=bundle.MAX_TRUST))
    bundle._fields(config, ('schema', 'repository', 'remote', 'ref', 'actions', 'grants', 'signing_key'))
    if type(config['schema']) is not int or config['schema'] != 1:
        _fail('Unsupported publisher profile')
    repo = Path(config['repository'])
    if not repo.is_absolute() or repo.resolve() != paths.REPO.resolve():
        _fail('Publisher profile does not approve this checkout')
    repo = repo.resolve()
    if Path(path).resolve().is_relative_to(repo):
        _fail('Publisher profile must be outside the checkout')
    remote, ref, actions = config['remote'], config['ref'], config['actions']
    if (type(remote) is not str or not remote or len(remote) > 2048 or remote.startswith('-') or
            any(ord(c) < 32 for c in remote) or not REF.fullmatch(ref) or '..' in ref or
            type(actions) is not list or not actions or len(actions) > 256 or
            any(type(a) is not str or len(a) > 256 for a in actions) or
            f'{game}/{step_name}' not in actions):
        _fail('Publisher profile does not approve this action or remote')
    if not Path(remote).is_absolute():
        endpoint = urlsplit(remote)
        if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username is not None or
                endpoint.password is not None or endpoint.query or endpoint.fragment):
            _fail('Approved remote must be an absolute local path or credential-free HTTPS URL')
    policy = PurePosixPath(config['grants'])
    if (policy.is_absolute() or not policy.parts or '..' in policy.parts or
            str(policy) != config['grants'] or '\\' in str(policy)):
        _fail('Grant policy must be a canonical checkout-relative path')
    key = Path(config['signing_key'])
    if any(key.resolve().is_relative_to(root) for root in
           (repo, paths.build_root().resolve(), paths.cache_dir(create=False).resolve())):
        _fail('Signing key must be outside checkout, build outputs and cache')
    if _protected(key, limit=32, contents=False) != 32:
        _fail('Signing key must be a raw 32-byte Ed25519 seed')
    return repo, remote, ref, repo / policy, key


def _source_state(repo, step, policy, game, revision):
    """Every consumed source must equal an ordinary tracked HEAD blob, even if Git ignores it."""
    required = [*build.required_inputs(step), *TOOL_SUPPORT,
                repo / 'games' / game / 'build.py', repo / 'uv.lock', policy]
    optional = list(step.optional_inputs)
    actual, roots, absent, total = {}, {}, set(), 0
    selected = {Path(os.path.abspath(p)) for p in (*required, *optional)}
    pending = [(Path(p), False) for p in required] + [(Path(p), True) for p in optional]
    while pending:
        path, may_be_absent = pending.pop()
        absolute = Path(os.path.abspath(path))
        if not absolute.is_relative_to(repo) or absolute.parent.resolve() != absolute.parent:
            _fail('Publisher sources must be unlinked checkout paths')
        relative = absolute.relative_to(repo).as_posix()
        if relative in actual or relative in absent:
            continue
        if relative == '.':
            _fail('Publisher input must be narrower than the checkout root')
        if absolute in selected:
            roots.setdefault(relative, False)
        try:
            info = absolute.lstat()
        except FileNotFoundError:
            if not may_be_absent:
                _fail('Required publisher source missing')
            absent.add(relative)
            continue
        if len(actual) + len(absent) >= bundle.MAX_RECORDS:
            _fail('Publisher source record limit exceeded')
        if stat.S_ISDIR(info.st_mode):
            actual[relative] = {'kind': 'directory'}
            if absolute in selected:
                roots[relative] = True
            with os.scandir(absolute) as children:
                for child in children:
                    if len(pending) + len(actual) + len(absent) >= bundle.MAX_RECORDS:
                        _fail('Publisher source record limit exceeded')
                    pending.append((Path(child.path), False))
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES - total:
            _fail('Publisher sources must be bounded regular files')
        total += info.st_size
        with ExitStack() as stack:
            fd, before = bundle._open_file(stack, absolute)
            digest, size = hashlib.sha256(), 0
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > info.st_size:
                    _fail('Publisher source changed')
                digest.update(chunk)
            if size != info.st_size or bundle._signature(os.fstat(fd)) != bundle._signature(before):
                _fail('Publisher source changed')
        actual[relative] = {'kind': 'file', 'size': size, 'sha256': digest.hexdigest()}
    # One metadata query and one object batch, rather than two Git launches per source file.
    expected = {}
    tree = _git(repo, 'ls-tree', '-r', '-t', '-z', revision, '--', *roots)
    directory_roots = {name for name, directory in roots.items() if directory}
    for item in tree.split(b'\0'):
        if not item:
            continue
        metadata, separator, name = item.partition(b'\t')
        name = os.fsdecode(bytes(name))
        if name not in roots and not any(p.as_posix() in directory_roots for p in PurePosixPath(name).parents):
            continue  # ls-tree also emits ancestor directories of selected leaf paths.
        parts = metadata.split()
        if not separator or len(parts) != 3 or parts[0] not in (b'040000', b'100644', b'100755'):
            _fail('Publisher input tree contains unsupported committed entries')
        expected[name] = ('directory' if parts[0] == b'040000' else 'file', parts[2].decode('ascii'))
        if len(expected) > bundle.MAX_RECORDS:
            _fail('Committed publisher input record limit exceeded')
    if set(actual) != set(expected) or any(actual[name]['kind'] != expected[name][0] for name in actual):
        _fail('Publisher source directory membership or optional presence differs from committed tree')
    objects = sorted({oid for kind, oid in expected.values() if kind == 'file'})
    data = _git(repo, 'cat-file', '--batch', request=''.join(oid + '\n' for oid in objects).encode('ascii'),
                limit=MAX_SOURCE_BYTES + bundle.MAX_RECORDS * 128)
    offset, digests = 0, {}
    for oid in objects:
        end = data.find(b'\n', offset)
        header = data[offset:end].split()
        if end < 0 or len(header) != 3 or header[:2] != [oid.encode('ascii'), b'blob']:
            _fail('Committed publisher object batch is invalid')
        size = int(header[2])
        start, offset = end + 1, end + size + 2
        if size < 0 or offset > len(data) or data[offset - 1] != 10:
            _fail('Committed publisher object batch is incomplete')
        digests[oid] = size, hashlib.sha256(memoryview(data)[start:offset - 1]).hexdigest()
    if offset != len(data):
        _fail('Committed publisher object batch has trailing bytes')
    if any((record['size'], record['sha256']) != digests[expected[name][1]]
           for name, record in actual.items() if record['kind'] == 'file'):
        _fail('Publisher source differs from committed bytes')
    return build_products.identity({'records': actual, 'absent': sorted(absent)})


def _revision(repo, remote, ref):
    if Path(os.fsdecode(bytes(_git(repo, 'rev-parse', '--show-toplevel'))).strip()).resolve() != repo:
        _fail('Publisher repository root differs')
    head = _git(repo, 'rev-parse', 'HEAD').decode('ascii').strip()
    if not bundle.COMMIT.fullmatch(head):
        _fail('Publisher requires a recorded source revision')
    if _git(repo, 'status', '--porcelain=v1', '--untracked-files=all', '--ignore-submodules=none'):
        _fail('Publisher requires a clean checkout')
    advertised = _git(repo, 'ls-remote', '--exit-code', remote, ref)
    if advertised != (head + '\t' + ref + '\n').encode('ascii'):
        _fail('Source revision is not the advertised approved ref')
    return head


def _eligible(ctx, game, step_name):
    try:
        plan = build.order(build.load_recipe(game).steps(ctx), [step_name])
    except SystemExit:
        _fail('Publisher action declarations are invalid')
    if len(plan) != 1 or plan[0].name != step_name:
        _fail('Publisher requires exactly one independent action')
    step = plan[0]
    if (step.cache is not True or step.audit is not True or step.heavy is not False or
            len(step.commands) != 1 or type(step.commands[0]) is not build.Python or
            step.needs or step.after or step.reads or step.references or step.queries or
            step.pool_roots or step.cutoff or step.verify is not None or step.batch is not None):
        _fail('Publisher requires one independent audited non-heavy Python action')
    build_cache.roots(ctx, step)
    return step


def _grants(path, game, step):
    with ExitStack() as stack:
        policy = bundle._read_json(stack, path, bundle.MAX_TRUST)
    bundle._fields(policy, ('schema', 'actions'))
    if type(policy['schema']) is not int or policy['schema'] != 1 or type(policy['actions']) is not dict:
        _fail('Invalid committed redistribution policy')
    grants = policy['actions'].get(f'{game}/{step.name}')
    if type(grants) is not dict or set(grants) != {p.name for p in step.products}:
        _fail('Committed grants required for every product')
    for grant in grants.values():
        bundle._fields(grant, ('permission', 'grant'))
        if grant['permission'] not in ('private', 'public') or not bundle.IDENTIFIER.fullmatch(grant['grant']):
            _fail('Invalid committed redistribution grant')
    return grants


def _stamp(path):
    # Host success stamps contain timing floats; signed bundle JSON deliberately does not.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('Duplicate success receipt field')
            result[key] = value
        return result
    with ExitStack() as inputs:
        fd, before = bundle._open_file(inputs, path)
        if before.st_size > bundle.MAX_MANIFEST:
            _fail('Success receipt exceeds limit')
        data = bytearray()
        while len(data) <= bundle.MAX_MANIFEST:
            chunk = os.read(fd, min(65536, bundle.MAX_MANIFEST + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) != before.st_size or bundle._signature(before) != bundle._signature(os.fstat(fd)):
            _fail('Success receipt changed')
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: _fail('Invalid success receipt number'))


def _snapshot(ctx, step, stamp_path, expected):
    stamp = _stamp(stamp_path)
    if stamp != expected:
        _fail('Success receipt does not belong to this publisher execution')
    with ExitStack() as stack:
        report = bundle._read_json(stack, ctx.logs / f'{step.name}.audit.json', bundle.MAX_MANIFEST)
    bundle._fields(report, ('schema', 'step', 'complete', 'passed', 'error', 'accesses', 'violations'))
    fingerprint, state = build.fingerprint_state(step, {})
    products = build_products.records(step)
    receipt = stamp.get('audit_receipt')
    if (stamp.get('fingerprint') != fingerprint or stamp.get('input_state') != state or
            stamp.get('products') != products or 'restored_from' in stamp or stamp.get('touched') or
            type(receipt) is not dict or set(receipt) != {'schema', 'execution', 'run_id', 'report_sha256'} or
            type(receipt['schema']) is not int or receipt['schema'] != 1 or
            receipt['execution'] != 'audited-python-v1' or not re.fullmatch('[0-9a-f]{32}', receipt['run_id']) or
            type(report.get('schema')) is not int or report.get('schema') != 1 or report.get('step') != step.name or
            report.get('complete') is not True or report.get('passed') is not True or
            report.get('error') is not None or report.get('violations') != [] or
            receipt['report_sha256'] != build_products.identity(report) or
            type(report.get('accesses')) is not list or len(report['accesses']) > 20000):
        _fail('Fresh successful audit and current action receipt required')
    for access in report.get('accesses', []):
        if not build_audit.valid_record(access, receipt['run_id']) or access.get('kind') != 'access':
            _fail('Audit report does not match this execution')
    entry = {'schema': 1, 'key': fingerprint, 'products': products}
    bundle._records(entry)
    if build_cache.Store().action(fingerprint).with_suffix('.conflict.json').exists():
        _fail('Conflicting action cannot be exported')
    return entry, state, receipt


def publish(game, step_name, destination: Path, *, profile: Path, echo=print):
    """@cc [owner:fontanierh,label:security] fresh-trusted-python-bundle-issuance
    Only a fresh audited independent non-heavy Python run from clean, committed sources at the
    approved advertised Git ref MAY be signed. Current keys, full inventories, run-bound audit
    receipts and explicit committed grants MUST be checked before key contents are read. Export
    MUST NOT overwrite a destination or imply upload permission, hostile-code isolation or a native guard.
    """
    try:
        if (not bundle.IDENTIFIER.fullmatch(game) or game in ('.', '..') or ':' in game or
                not bundle.IDENTIFIER.fullmatch(step_name)):
            _fail('Invalid publisher action name')
        repo, remote, ref, policy, key_path = _profile(profile, game, step_name)
        destination = Path(destination)
        if (not destination.is_absolute() or destination.is_symlink() or destination.exists() or
                not destination.parent.is_dir() or destination.parent.resolve() != destination.parent or
                destination.is_relative_to(repo) or destination.is_relative_to(paths.build_root().resolve())):
            _fail('Export requires a new directory outside checkout and build outputs')
        echo('Checking approved Git revision')
        revision = _revision(repo, remote, ref)
        ctx = build.Context(game)
        from .build_snapshot import require_complete
        try:
            require_complete(ctx.out, game=game, repo=repo)
        except SystemExit:
            _fail('Approved action cannot run from this build snapshot')
        step = _eligible(ctx, game, step_name)
        echo('Checking committed sources and redistribution grants')
        source_state = _source_state(repo, step, policy, game, revision)
        grants = _grants(policy, game, step)
        echo('Building approved audited Python action for local export')
        stamp_path = ctx.stamps / f'{step.name}.json'
        # Do not accept an old log/receipt if an interrupted or mocked executor returns success.
        stamp_path.unlink(missing_ok=True)
        (ctx.logs / f'{step.name}.audit.json').unlink(missing_ok=True)
        produced = []
        with HashIndex(ctx.out / '.state' / 'file-hashes.sqlite3', verify=True) as index:
            try:
                code = build._build(ctx, [step.name], force=True, touch=False, echo=lambda _: None,
                                    index=index, steps=[step], produced=produced)
            except SystemExit:
                _fail('Approved action cannot run from this build snapshot')
            if code != 0:
                _fail('Approved Python action failed')
        if len(produced) != 1 or produced[0][0] != step.name:
            _fail('Fresh action execution receipt missing')
        expected = produced[0][1]
        echo('Verifying produced inventories and staging local bundle')
        entry, state, audit = _snapshot(ctx, step, stamp_path, expected)
        root_names = {p.name: [Path(root).name for root in p.paths] for p in step.products}
        for names in root_names.values():
            for label in names:
                if (not label or len(label) > 255 or '\\' in label or '\0' in label or
                        len(PurePosixPath(label).parts) != 1 or label in ('.', '..') or
                        label != PurePosixPath(label).as_posix()):
                    _fail('Invalid product root basename')
                bundle._safe_member(PurePosixPath(label))
        payload = {'schema': 2, 'namespace': bundle.NAMESPACE, 'entry': entry,
                   'producer': {'source_commit': revision, 'clean': True, 'pushed': True,
                                'execution': 'audited-python-v1', 'tool_context': state['tools'],
                                'audit_sha256': build_products.identity(audit)},
                   'redistribution': grants, 'root_names': root_names}
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.atelier-export-') as temporary:
            stage = Path(temporary)
            blobs = stage / 'blobs'
            blobs.mkdir()
            for product in step.products:
                inventory = entry['products'][product.name]['inventory']
                for index, relative, item in build_cache.members(inventory, len(product.paths)):
                    if item['kind'] != 'file' or (blobs / item['sha256']).exists():
                        continue
                    source = product.paths[index] / relative
                    with ExitStack() as inputs:
                        fd, before = bundle._open_file(inputs, source)
                        copied, digest = 0, hashlib.sha256()
                        with (blobs / item['sha256']).open('wb') as output:
                            while True:
                                data = os.read(fd, min(1024 * 1024, item['size'] + 1 - copied))
                                if not data:
                                    break
                                copied += len(data)
                                if copied > item['size']:
                                    _fail('Product changed while exporting')
                                digest.update(data)
                                output.write(data)
                        if (copied != item['size'] or digest.hexdigest() != item['sha256'] or
                                bundle._signature(before) != bundle._signature(os.fstat(fd))):
                            _fail('Product changed while exporting')
            echo('Rechecking source revision and action before signing')
            if (_snapshot(ctx, step, stamp_path, expected) != (entry, state, audit) or
                    _source_state(repo, step, policy, game, revision) != source_state or
                    _revision(repo, remote, ref) != revision):
                _fail('Source or action changed before signing')
            # No key material is loaded while recipe execution or source/output validation remains.
            # Publisher IDs and Ed25519 signatures have fixed encoded lengths.
            payload['publisher'] = '0' * 64
            placeholder = {'payload': payload, 'signature': base64.b64encode(bytes(64)).decode('ascii')}
            if len(bundle._canonical(placeholder)) > bundle.MAX_MANIFEST:
                _fail('Signed manifest exceeds limit')
            private = Ed25519PrivateKey.from_private_bytes(_protected(key_path, limit=32))
            public = private.public_key().public_bytes_raw()
            payload['publisher'] = hashlib.sha256(public).hexdigest()
            encoded = bundle._canonical(payload)
            envelope = {'payload': payload, 'signature': base64.b64encode(private.sign(DOMAIN + encoded)).decode('ascii')}
            manifest = bundle._canonical(envelope)
            if len(manifest) > bundle.MAX_MANIFEST:
                _fail('Signed manifest exceeds limit')
            (stage / 'manifest.json').write_bytes(manifest)
            # Claim without replacing anything; manifest-last makes incomplete exports unimportable.
            destination.mkdir(mode=0o700)
            try:
                (stage / 'blobs').rename(destination / 'blobs')
                (stage / 'manifest.json').rename(destination / 'manifest.json')
            except BaseException:
                shutil.rmtree(destination)
                raise
        return {'schema': 2, 'namespace': bundle.NAMESPACE, 'key': entry['key'],
                'publisher': payload['publisher'], 'source_commit': revision,
                'execution': 'audited-python-v1', 'products': sorted(entry['products']),
                'exported': True, 'uploaded': False,
                'public_redistribution_asserted': all(g['permission'] == 'public' for g in grants.values())}
    except PublisherError:
        raise
    except bundle.BundleError as error:
        raise PublisherError(str(error)) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, SyntaxError, RecursionError,
            subprocess.SubprocessError):
        raise PublisherError('Trusted artifact export failed') from None
