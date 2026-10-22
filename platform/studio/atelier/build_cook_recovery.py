"""Same-checkout recovery of certification after an affirmatively completed guarded cook.

These receipts are local execution evidence, not portable cache objects or signed attestations.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

from . import paths, provenance


@dataclass(frozen=True)
class CookRecovery:
    snapshot: object
    certify: object
    native_inputs: object
    link_owners: object = ()


@dataclass(frozen=True)
class NativeCookInputs:
    """One discovery result binds consumed roots and link ownership to the same selection."""
    roots: object
    link_owners: object
    selection: object
    repeat_chmod_files: object = ()


def require(value, message):
    if not value:
        raise RuntimeError('Cook recovery: ' + message)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


SESSION_ENVIRONMENT = frozenset({
    # Prepared before the exact launch binding; bookkeeping is not a reusable cook input.
    'ATELIER_OWNED_LAUNCH_NONCE',
    'ATELIER_OWNED_LAUNCH_ANCESTORS',
    'TERM_SESSION_ID', 'TERM_PROGRAM_SESSION_ID', 'ITERM_SESSION_ID', 'SSH_AUTH_SOCK',
    'SHLVL', 'OLDPWD', 'PWD', '_', 'ATELIER_AGENT', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID',
    'CODEX_TOOL_CALL_ID', 'CLAUDE_SESSION_ID', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_PID',
    'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDE_CODE_MESSAGING_TOKEN', 'CLAUDE_CODE_WORKER_EPOCH',
    'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_CODE_SESSION_ATTENDED', 'CLAUDECODE',
})


def consumed_environment(environment):
    """Keep unknown/build/tool variables exact; omit only enumerated session bookkeeping.

    The actual working directory is separately bound, so a shell's PWD spelling is not an input.
    Original launch-to-guard binding still hashes the entire unmodified environment.
    """
    return {key: identity(value) for key, value in environment.items() if key not in SESSION_ENVIRONMENT}


def require_environment(before, environment):
    expected, actual = before['environment'], consumed_environment(environment)
    changed = sorted(key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key))
    require(not changed, 'consumed environment differs: ' + ', '.join(changed))


def require_snapshot(ctx, step, argv, before, message):
    environment = ctx.env()
    require_environment(before, environment)  # Name keys, never values, before expensive input checks.
    require(snapshot(ctx, step, argv, environment) == before, message)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    os.link(temporary, path)  # Publish a complete immutable journal file without replacing prior evidence.
    temporary.unlink()
    sync_directory(path.parent)


def directory_identity(path):
    try:
        info = path.stat()
        return (info.st_dev, info.st_ino) if stat.S_ISDIR(info.st_mode) else None
    except (FileNotFoundError, NotADirectoryError):
        return None


def covered_path(path, directories):
    return any(directory_identity(parent) in directories for parent in path.parents)


def inventory_roots(roots):
    """Collapse only actual directory ancestry; inode comparisons also handle APFS case aliases."""
    normalized = []
    for original in roots:
        root = Path(original)
        require(not root.is_symlink(), 'input/archive root is a symlink')
        normalized.append(root.parent.resolve() / root.name)
    directories = {token for root in normalized if (token := directory_identity(root)) is not None}
    # A complete directory inventory already observes all descendant roots, including absent
    # leaves. Keep their declarations in snapshot.roots, but walk and charge each leaf only once.
    queue, seen = [], set()
    for root in dict.fromkeys(normalized):
        token = directory_identity(root)
        if covered_path(root, directories) or (token is not None and token in seen):
            continue
        queue.append(root)
        if token is not None:
            seen.add(token)
    return queue, seen


def inventory(roots, *, hashes, hasher=None, link_owners=(), repeat_chmod_files=()):
    """Complete membership, including absent roots and internal relative links; reject escaped reads."""
    result, observed = {}, []
    spoken = started = time.monotonic()
    queue, covered_directories = inventory_roots(roots)
    included = set(queue)
    owners = [Path(owner).resolve(strict=True) for owner in link_owners]
    chmod_files = {Path(path).resolve(strict=True) for path in repeat_chmod_files}
    require(not chmod_files or hashes, 'repeat-chmod inputs require actual content hashes')
    chmod_seen = set()
    for root_index, original in enumerate(queue):
        root = Path(original)
        require(not root.is_symlink(), 'input/archive root is a symlink')
        root = root.parent.resolve() / root.name
        included.add(root)
        if not root.exists():
            result[str(root)] = {'absent': True}
            observed.append((root, None))
            continue
        pending = [root]
        while pending:
            require(time.monotonic() - started < 2700, 'input/archive inventory exceeded 45 minutes')
            require(len(result) < 500000, 'input/archive inventory exceeds 500000 entries')
            path = pending.pop()
            info = path.lstat()
            token = [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
            observed.append((path, token))
            entry = dict(identity=token)
            if stat.S_ISLNK(info.st_mode):
                link = os.readlink(path)
                target = path.resolve(strict=True)
                inside = target.is_relative_to(root)
                owned = any(target.is_relative_to(owner) for owner in owners)
                require((inside and not Path(link).is_absolute()) or owned, 'external/absolute symlink')
                entry['link'] = link
                if not inside:
                    entry['resolved_owned_target'] = str(target)
                    if target not in included and not covered_path(target, covered_directories):
                        included.add(target)
                        queue.append(target)
                        token = directory_identity(target)
                        if token is not None:
                            covered_directories.add(token)
            elif stat.S_ISDIR(info.st_mode):
                pending.extend(reversed(sorted(path.iterdir())))
            elif stat.S_ISREG(info.st_mode):
                if path in chmod_files:
                    # SetupDotnet repeats chmod u+x even when the executable bit is already set.
                    # Keep full ctime in read stability and HashIndex validation; omit ONLY this
                    # tool's ctime from the cross-checkpoint proof. Bytes/mode/inode/mtime stay exact.
                    entry['identity'] = token[:-1]
                    chmod_seen.add(path)
                if hashes:
                    if hasher is not None:
                        entry['sha256'] = hasher(path)
                        result[f'{root_index}/{path.relative_to(root)}'] = entry
                        if time.monotonic() - spoken >= 25:
                            print(f'cook recovery: checking input identities; {len(result)} leaves observed', flush=True)
                            spoken = time.monotonic()
                        continue
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024**2), b''):
                            digest.update(block)
                            if time.monotonic() - spoken >= 25:
                                print(f'cook recovery: checking {path.name}; {len(result)} leaves observed', flush=True)
                                spoken = time.monotonic()
                    entry['sha256'] = digest.hexdigest()
            else:
                raise RuntimeError('Cook recovery: unsupported native input/archive leaf')
            result[f'{root_index}/{path.relative_to(root)}'] = entry
    for path, before in observed:
        if before is None:
            require(not path.exists() and not path.is_symlink(), 'an absent input appeared')
        else:
            info = path.lstat()
            require(before == [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns],
                    'input/archive changed during inventory')
    require(chmod_seen == chmod_files, 'repeat-chmod input is not an inventoried regular file')
    return result


def snapshot(ctx, step, argv, environment):
    """@cc [owner:fontanierh,label:correctness] deferred-cook-source-observation
    A cook capture MUST use the same selected deferred observation for its declared source
    inventory and action fingerprint. Each new capture MUST observe membership afresh so recovery
    still refuses changed inputs; deferred declarations MUST NOT prevent recording a normal cook.
    """
    from .build import load_recipe, fingerprint, outputs_present, result
    from .build_products import records, feed_results
    from .build_plan import read_stamp
    from .build_products import Graph
    from .build_hashes import HashIndex
    graph = Graph(load_recipe(ctx.game).steps(ctx))
    done, roots = {}, []
    for item in graph.select([step.name]):
        if item.name == step.name:
            continue
        stamp = read_stamp(ctx.stamps / (item.name + '.json'))
        with HashIndex(ctx.out / '.state/cook-input-hashes.sqlite3') as index:
            key = fingerprint(item, done, index=index)
            require(stamp.get('fingerprint') == key and outputs_present(item), 'prerequisite is not current/complete: ' + item.name)
            require(not stamp.get('touched'), 'prerequisite was manually touched: ' + item.name)
            if stamp.get('restored_from'):
                from .build_cache import roots as portable_roots
                require(item.cache and item.products, 'restored prerequisite lacks portable product proof: ' + item.name)
                require(stamp['restored_from'] == key, 'restored prerequisite action key differs: ' + item.name)
                portable_roots(ctx, item)  # Enforce existing Python/Blender portable-only declarations.
            if item.products:
                actual = records(item, hasher=index.digest)
                require(actual == stamp.get('products', {}), 'prerequisite product bytes changed: ' + item.name)
                feed_results(done, actual)
        done[item.name] = result(item, key, stamp)
        roots.extend(map(Path, item.outputs))
        for product in item.products:
            roots.extend(map(Path, product.roots()))
    source_status = provenance.status()
    require(not any(line.startswith('??') for line in source_status.splitlines()), 'untracked source must be recorded first')
    from .build import required_inputs
    from .build_deferred import observe
    from .build_inputs import SKIP_PARTS, SKIP_SUFFIXES
    observation = observe(step)
    # Pin source leaves with the established source/output boundary. UAT may legitimately
    # write Binaries/Intermediate under a declared plugin source root. Consumed editor and
    # ThirdParty native inputs are selected separately by the recipe's native policy.
    declared = []
    for root in map(Path, required_inputs(step, observation=observation)):
        if root.is_dir():
            declared.extend(p for p in sorted(root.rglob('*'))
                            if not SKIP_PARTS.intersection(p.relative_to(root).parts)
                            and p.suffix not in SKIP_SUFFIXES and (p.is_file() or p.is_symlink()))
        else:
            declared.append(root)
    native = step.cook_recovery.native_inputs(ctx)
    if isinstance(native, NativeCookInputs):
        roots.extend(map(Path, native.roots))
        owners, selection = list(native.link_owners), native.selection
        repeat_chmod_files = list(native.repeat_chmod_files)
    else:
        require(isinstance(native, (list, tuple)) and all(isinstance(path, (str, os.PathLike)) for path in native),
                'native inputs must be canonical NativeCookInputs or an explicit list/tuple of paths')
        roots.extend(map(Path, native))
        owners = step.cook_recovery.link_owners
        owners = list(owners(ctx) if callable(owners) else owners)
        selection = None
        repeat_chmod_files = []
    # Actual adapter and guard implementation are part of the retained execution identity.
    roots.extend([Path(__file__), Path(__file__).with_name('build.py'),
                  Path(__file__).with_name('build_cook.py'), Path(__file__).with_name('build_zen.py'),
                  Path(sys.executable).resolve()])
    from atelier.harness import safety
    roots.extend(sorted(Path(safety.__file__).parent.glob('*.py')))
    roots = list(dict.fromkeys(roots))
    from .build_hashes import HashIndex
    # Local continuity proof shares the existing stat/ctime-validated hash hint. Archive
    # certification itself still hashes real bytes twice without consulting this index.
    with HashIndex(ctx.out / '.state/cook-input-hashes.sqlite3') as index:
        inputs = inventory(roots, hashes=True, hasher=index.digest, link_owners=owners,
                           repeat_chmod_files=repeat_chmod_files)
        declared_inputs = inventory(declared, hashes=True, hasher=index.digest)
    return dict(schema=2, checkout=str(paths.REPO.resolve()), cwd=str(Path.cwd().resolve()), game=ctx.game, step=step.name,
                source=step.cook_recovery.snapshot(ctx), revision=provenance.head(),
                patch_sha256=hashlib.sha256(provenance.git('diff', '--binary', 'HEAD').encode()).hexdigest(),
                action_fingerprint=fingerprint(step, done, observation=observation), argv=argv, environment=consumed_environment(environment),
                roots=list(map(str, roots)), link_owners=list(map(str, owners)), native_selection=selection,
                repeat_chmod_files=list(map(str, repeat_chmod_files)),
                inputs=inputs, declared_members=list(map(str, declared)), declared_inputs=declared_inputs)


def read(path):
    from .build_hashes import signature
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                'journal must be an owned private regular file')
        require(info.st_size <= 512 * 1024**2, 'journal exceeds size bound')
        raw = stream.read(512 * 1024**2 + 1)
        require(len(raw) <= 512 * 1024**2 and signature(info) == signature(os.fstat(stream.fileno())), 'journal changed while reading')
    return json.loads(raw)


def begin(ctx, step, command, argv, environment):
    """Prepare only a small private launch request; expensive capture runs in the guarded adapter."""
    require(step.heavy and step.cook_recovery is not None, 'only an opted-in guarded cook can record an attempt')
    require(not command.archive.exists() and not command.archive.is_symlink(),
            'prepare must remove the previous archive before recording native execution')
    require(isinstance(ctx.cook_source, dict), 'recipe must prepare its source identity first')
    folder = ctx.out / 'cook-attempts' / uuid.uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    sync_directory(folder.parent)
    sync_directory(ctx.out)
    adapter = [sys.executable, '-m', 'atelier.build_cook_recovery', 'prepare-exec', str(folder)]
    request = dict(schema=1, game=ctx.game, step=step.name, checkout=str(paths.REPO.resolve()),
                   source=ctx.cook_source, argv=argv, adapter_argv=adapter,
                   environment_sha256=identity(environment))
    write(folder / 'launch-request.json', request)
    print(f'cook recovery attempt: {folder.name}', flush=True)
    return folder, adapter


def prepare_exec(folder):
    """Run inside the normal guarded/gated root, then replace that same PID with original UAT."""
    from .build import Context, load_recipe, UnrealPackage
    folder = Path(folder)
    require(uuid.UUID(folder.name).hex == folder.name and not folder.is_symlink(), 'invalid private attempt directory')
    request = read(folder / 'launch-request.json')
    require(request['checkout'] == str(paths.REPO.resolve()) and request['environment_sha256'] == identity(dict(os.environ)),
            'adapter checkout/environment differs from original launch')
    ctx = Context(request['game'], record_cook_recovery=True)
    require(folder.resolve() == (ctx.out / 'cook-attempts' / folder.name).resolve(), 'attempt is outside this checkout')
    step = next(item for item in load_recipe(ctx.game).steps(ctx) if item.name == request['step'])
    require(step.cook_recovery is not None, 'current recipe no longer supports recording')
    command = next(item for item in step.commands if isinstance(item, UnrealPackage))
    require(command.argv(ctx) == request['argv'] and step.cook_recovery.snapshot(ctx) == request['source'],
            'original source/action changed before guarded capture')
    require(not command.archive.exists() and not command.archive.is_symlink(), 'archive appeared before UAT')
    before = snapshot(ctx, step, request['argv'], dict(os.environ))
    require(before['source'] == request['source'] and read(folder / 'launch-request.json') == request,
            'source/request changed during guarded capture')
    write(folder / 'prepared.json', dict(schema=1, snapshot=before, request_sha256=identity(request)))
    os.execvpe(request['argv'][0], request['argv'], dict(os.environ))


def complete(ctx, step, attempt, observation):
    folder, adapter = attempt
    prepared = read(folder / 'prepared.json')
    before = prepared['snapshot']
    request = read(folder / 'launch-request.json')
    require(prepared['request_sha256'] == identity(request) and request['adapter_argv'] == adapter, 'launch request changed')
    proof = read(folder / 'guarded-success.json')
    require(proof.get('kind') == 'guarded-success' and proof.get('returncode') == 0
            and proof.get('cleanup_and_capacity_close') is True and proof.get('invocation_id') == folder.name,
            'missing positive guarded completion')
    require(proof['command_sha256'] == identity(adapter)
            and proof['environment_sha256'] == request['environment_sha256'], 'guarded command differs')
    require(observation.get('command_succeeded') is True, 'cook observation is not successful')
    command = next(c for c in step.commands if type(c).__name__ == 'UnrealPackage')
    archive = command.archive
    require(archive.resolve().is_relative_to(ctx.out.resolve()) and archive.is_dir(), 'archive is not owned by this checkout')
    # The pre-command prepare removed the previous archive; retain the current tree identity BEFORE
    # expensive certification hashes. This is local filesystem continuity, not a preexisting content hash.
    metadata = inventory([archive], hashes=False)
    require_snapshot(ctx, step, before['argv'], before, 'consumed inputs changed during cook')
    require(inventory([archive], hashes=False) == metadata, 'archive changed while checking consumed inputs')
    write(folder / 'completed.json', dict(schema=1, prepared_sha256=identity(prepared),
          guarded_sha256=identity(proof), archive=str(archive.resolve()), metadata=metadata,
          observation=observation))


def recover(ctx, step, identifier, log):
    """@cc [owner:fontanierh,label:correctness] guarded-cook-certification-recovery
    Recovery MUST require this checkout's durable pre-command consumed-input identity and positive
    post-cleanup guarded success. Current recipe, prerequisites, native inputs, tools, environment and
    complete archive identity MUST match before certification. No missing proof, text-only UAT success,
    failed guard or diagnostic timing MAY certify a cook. Recovery MUST NOT run native work or invent
    native execution metrics; interrupted archive hashing MAY be repeated against frozen identity.
    """
    require(type(identifier) is str and uuid.UUID(identifier).hex == identifier, 'attempt ID must be UUID hex')
    folder = ctx.out / 'cook-attempts' / identifier
    prepared = read(folder / 'prepared.json')
    before = prepared['snapshot']
    request = read(folder / 'launch-request.json')
    completed = read(folder / 'completed.json')
    proof = read(folder / 'guarded-success.json')
    require(prepared['request_sha256'] == identity(request), 'launch request changed')
    require(proof['command_sha256'] == identity(request['adapter_argv']) and proof['environment_sha256'] == request['environment_sha256'], 'guarded launch differs')
    require(completed['prepared_sha256'] == identity(prepared) and completed['guarded_sha256'] == identity(proof), 'attempt evidence changed')
    require(proof.get('kind') == 'guarded-success' and proof.get('invocation_id') == identifier
            and proof.get('returncode') == 0 and proof.get('cleanup_and_capacity_close') is True, 'positive guarded success is absent')
    terminal = proof['terminal']
    require([terminal.get('owner'), terminal.get('owner_started')] == proof['root']
            and terminal.get('state') == 'child_exited' and terminal.get('cleanup_complete') is True,
            'terminal guard does not match the positively waited root')
    command = next(c for c in step.commands if type(c).__name__ == 'UnrealPackage')
    argv = command.argv(ctx)
    require_snapshot(ctx, step, argv, before, 'current recipe/source/native inputs/tools/environment differ')
    archive = command.archive
    require(str(archive.resolve()) == completed['archive'] and inventory([archive], hashes=False) == completed['metadata'],
            'archive changed since guarded completion')
    ctx.cook_source = before['source']
    ctx.cook_observation = completed['observation']
    try:
        step.cook_recovery.certify(ctx, log)
        require_snapshot(ctx, step, argv, before, 'inputs changed during recovery')
        require(inventory([archive], hashes=False) == completed['metadata'], 'archive changed during recovery')
    except BaseException:
        # A failed post-check must not leave a newly published receipt consumable by assembly.
        for output in step.outputs:
            Path(output).unlink(missing_ok=True)
        raise
    return dict(attempt_id=identifier, guarded_sha256=completed['guarded_sha256'], scope='certification recovery only')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare-exec'])
    parser.add_argument('attempt', type=Path)
    args = parser.parse_args(argv)
    prepare_exec(args.attempt)


if __name__ == '__main__':
    # Recipes import NativeCookInputs from this canonical module. Execute there too:
    # -m otherwise creates a second __main__ class and defeats the typed input record.
    from . import build_cook_recovery
    build_cook_recovery.main()
