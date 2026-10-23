"""The single build/release checkpoint workflow; no alternate fast-build command.

Ordinary builds hydrate an empty generated workspace and retain successful task results.
Releases capture workspace checkpoints in the configured private GitHub repository.
Missing/incompatible checkpoints never silently authorize an expensive cold rebuild.
"""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import uuid

from . import build_products, manifest, paths
from .build_cache import atomic_json
from .checkpoint_store import CheckpointError, JOURNAL, Store, certificates, cold, context, identity, read_json
from .release import PublishError


def configured(ctx):
    directory = getattr(ctx, 'game_dir', None)
    if directory is None or not (directory / 'game.toml').is_file():
        return None
    value = manifest.load(directory / 'game.toml').get('checkpoints')
    if value is None:
        return None
    if (type(value) is not dict or set(value) - {'rebuild_budget_seconds'}
            or type(value.get('rebuild_budget_seconds', 600)) is not int
            or not 1 <= value.get('rebuild_budget_seconds', 600) <= 86400):
        raise CheckpointError('Invalid [checkpoints] configuration in game.toml')
    settings = paths.cache_dir('checkpoints', create=False) / 'settings.json'
    local = read_json(settings) if settings.is_file() else {}
    repository = local.get('repository')
    if repository is not None:
        from .checkpoint_github import Remote
        Remote(repository, ctx.game)  # Validate without network access.
    return {**value, 'repository': repository}


def configure_repository(repository):
    """@cc [owner:fontanierh,label:security] private-cache-local-configuration
    The private cache repository identity MUST be stored only in machine-local configuration,
    never game.toml or tracked source. Configuration MUST NOT expose credentials or invite users.
    """
    from .checkpoint_github import Remote
    Remote(repository, 'configuration').require_private()
    target = paths.cache_dir('checkpoints') / 'settings.json'
    atomic_json(target, dict(repository=repository))
    os.chmod(target, 0o600)
    return {'configured': True, 'scope': 'machine-local'}


def reason(value):
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 300
                              or any(ord(c) < 32 for c in value)):
        raise CheckpointError('Rebuild reason must be a nonempty single line of at most 300 characters')
    return value


def _guard(ctx, operation, key=None):
    """@cc [owner:fontanierh,label:safety] checkpoint-transfer-invocation
    Native-file copies MUST enter the normal owned-child admission/guard lifecycle with
    its required canonical UUID invocation identity. Invalid transfer metadata MUST NOT
    authorize bypassing the guard or publishing a successful restoration.
    """
    from atelier.harness.safety import guarded
    nonce = uuid.uuid4().hex
    folder = ctx.logs / ('checkpoint-' + operation + '-' + nonce + '.guard')
    argv = [sys.executable, '-m', 'atelier.checkpoint_worker', operation, ctx.game, str(folder)]
    if key:
        argv += ['--key', key]
    code = guarded.run(argv, folder, aggregate_tree=True, timeout=3600, progress=25,
                       kind='job', purpose='build checkpoint ' + operation, invocation_id=nonce)
    if code:
        raise CheckpointError(f'Checkpoint {operation} failed (exit {code}); retained evidence: {folder}')
    return read_json(folder / 'result.json')


def _publish_restoration(ctx, steps, store, key, record):
    """@cc [owner:fontanierh,label:correctness] post-guard-checkpoint-publication
    Receiving certificates MUST publish only after successful guarded child exit, cleanup and
    admission close. The original journal/key, fresh input identities and restored output
    metadata (size, mode, mtime; bytes for post-import outputs) MUST still agree. Failure MUST retain the launch barrier and MUST NOT retain certificates.
    """
    journal = ctx.out / JOURNAL
    expected = dict(schema=1, key=key, game=ctx.game)
    if read_json(journal) != expected or record.get('key') != key:
        raise CheckpointError('Checkpoint restore completion does not match its journal')
    saved = store.load(key)
    candidates = record.get('stamps')
    known = {**saved['stamps'], **saved.get('incremental_stamps', {})}
    if not isinstance(candidates, dict) or any(known.get(n) != s for n, s in candidates.items()):
        raise CheckpointError('Checkpoint restore completion contains foreign certificates')
    try:
        for name, stamp in candidates.items():
            atomic_json(ctx.stamps / (name + '.json'), stamp)
        incremental_environment(ctx)
        from .checkpoint_store import RESTORED_HASHES, unchanged
        if certificates(ctx, steps, include_incremental=True, hashes=ctx.out / RESTORED_HASHES) != candidates:
            raise CheckpointError('Checkpoint receiver changed before certificate publication')
        # Revalidate all copied bytes at the publication boundary, not just named products.
        from .checkpoint_store import roots, safe_destination
        same_path = saved['checkout'] == identity(str(paths.REPO.resolve()))
        allowed = roots(ctx)
        post_import = record.get('post_import', {})
        from .build_hashes import HashIndex
        hashes = HashIndex(ctx.out / RESTORED_HASHES)
        if set(post_import) - {'cooked/Mac/ue.projectstore'}:
            raise CheckpointError('Unexpected mutable Zen checkpoint output')
        for member, entry in saved['files'].items():
            label, _, name = member.partition('/')
            root, bound = allowed[label]
            if bound and not same_path:
                continue
            path = safe_destination(root, name)
            expected_digest = post_import.get(member, entry.get('sha256'))
            if entry['kind'] == 'file' and (path.is_symlink() or not path.is_file()
                    or path.stat().st_mode & 0o777 != entry['mode']
                    or (member in post_import and build_products.file_digest(path) != expected_digest)
                    or (member not in post_import and not unchanged(path, entry)
                        and hashes.digest(path) != entry['sha256'])):
                raise CheckpointError('Checkpoint output changed before certificate publication')
            if entry['kind'] == 'link':
                if entry['target'].startswith('member:'):
                    target_label, _, target_name = entry['target'][7:].partition('/')
                    target = safe_destination(allowed[target_label][0], target_name)
                else:
                    target = ctx.unreal_root / entry['target'][7:]
                if not path.is_symlink() or os.readlink(path) != os.path.relpath(target, path.parent):
                    raise CheckpointError('Checkpoint link changed before certificate publication')
            if entry['kind'] == 'directory' and (path.is_symlink() or not path.is_dir()):
                raise CheckpointError('Checkpoint directory changed before certificate publication')
        hashes.close()
        journal.unlink()
    except BaseException:
        for name in candidates:
            (ctx.stamps / (name + '.json')).unlink(missing_ok=True)
        raise


def prepare(ctx, steps, *, echo=print):
    settings = configured(ctx)
    if settings is None:
        return None
    store = Store(ctx.game)
    incremental_environment(ctx)
    journal = ctx.out / JOURNAL
    if journal.exists():
        pending = read_json(journal)
        if pending.get('operation') == 'action':
            from .checkpoint_actions import load, valid_outputs
            step = next((s for s in steps if s.name == pending['task']), None)
            if step is None:
                raise CheckpointError('Interrupted task was removed from the recipe')
            result = _guard(ctx, 'restore-action', pending['key'])
            value = load(store, pending['key'])
            if result.get('key') != pending['key'] or not valid_outputs(ctx, step, value):
                raise CheckpointError('Interrupted task restoration did not complete')
            journal.unlink()
            return store
        if 'units' in pending:
            hydrate(ctx, steps, store, echo=echo, resume=pending)
            return store
        key = pending['key']
        result = _guard(ctx, 'restore', key)
        _publish_restoration(ctx, steps, store, key, result)
        return store
    if not cold(ctx):
        hydrate(ctx, steps, store, echo=echo)
        return store
    expected_context, ownership = context(ctx), {s.name for s in steps}
    for key, saved in store.latest():
        if not saved.get('workspace_only') and saved['context'] == expected_context and set(saved.get('steps', ())) <= ownership:
            echo('Restoring a local build checkpoint; source edits are preserved')
            result = _guard(ctx, 'restore', key)
            _publish_restoration(ctx, steps, store, key, result)
            return store
    from .checkpoint_github import Remote
    if not settings.get('repository'):
        echo('No remote checkpoint configured. Use `atelier cache configure --repository OWNER/REPOSITORY`.')
        return store
    remote = Remote(settings['repository'], ctx.game, echo=echo)
    try:
        with remote.transaction(), tempfile.TemporaryDirectory(dir=store.directory) as temporary:
            for item in remote.candidates():
                data = remote.descriptor(item, Path(temporary))
                saved = data['checkpoint']
                if saved['context'] != expected_context or not set(saved.get('steps', ())) <= ownership:
                    continue
                echo('Downloading the latest compatible playtest build checkpoint')
                key = remote.fetch(item, data, store)
                result = _guard(ctx, 'restore', key)
                _publish_restoration(ctx, steps, store, key, result)
                return store
    except (OSError, ValueError, KeyError, TypeError, PublishError) as error:
        echo(f'Checkpoint unavailable: {error}. Cold rebuilds still require an explicit reason.')
    return store


STAGED = '.state/hydration-stamps'


def hydration_plan(ctx, steps, store):
    """The largest compatible local checkpoint, compared file by file with this workspace.

    Only cached summaries and one manifest are read; existence is checked, nothing is hashed.
    Certificates are only staged: the build adopts one when its own fingerprint matches.
    """
    from .checkpoint_store import declared, declared_member, roots
    allowed = roots(ctx)
    outputs = declared(ctx, steps)
    expected, ownership = identity(context(ctx)), {s.name for s in steps}
    here = identity(str(paths.REPO.resolve()))
    summaries = store.summaries()
    usable = lambda summary, label: (label in allowed and label not in ('zen', 'cooked')
                                     and not (allowed[label][1] and summary['checkout'] != here))
    candidates = [(sum(c for u, c in summary['units'].items() if u.count('/') == 1 and usable(summary, u[:-1])), -age, key, summary)
                  for age, (key, summary) in enumerate(summaries)
                  if not summary['workspace_only'] and summary['context'] == expected
                  and set(summary['steps']) <= ownership and {u.partition('/')[0] for u in summary['units']} <= set(allowed)]
    if not candidates:
        return None, len(summaries), 0
    _, _, key, summary = max(candidates)
    files = json.loads((store.manifests / (key + '.json')).read_bytes())['files']
    missing, labels = 0, set()
    bases = {label: str(root) + '/' for label, (root, _) in allowed.items()}
    for member in files:
        label, _, name = member.partition('/')
        if not usable(summary, label) or label == 'generated' and not declared_member(name, outputs):
            continue
        labels.add(label + '/')
        if not os.path.lexists(bases[label] + name):
            missing += 1
    present = {p.stem for p in ctx.stamps.glob('*.json')} if ctx.stamps.is_dir() else set()
    staged = {p.stem for p in (ctx.out / STAGED).glob('*.json')}
    lacking = sorted(n for n in summary['stamps'] if n not in present and n not in staged)
    token = identity([key, missing, lacking])
    checks = ctx.out / '.state/hydration-futile.json'
    try:
        futile = read_json(checks).get('token') == token if checks.is_file() else False
    except (OSError, ValueError, CheckpointError):
        futile = False
    if not (missing or lacking) or futile:
        return None, len(summaries), len(candidates)
    return (dict(key=key, units=sorted(labels), missing=missing, stamps=lacking, outputs=sorted(outputs), token=token),
            len(summaries), len(candidates))


def hydrate(ctx, steps, store, *, echo=print, resume=None):
    """Clone generated files this workspace lacks and stage the checkpoint's certificates.

    A hydration never fails the build: on any refusal its journal is cleared, since it only
    ever added missing generated files and published no certificate.
    """
    from .checkpoint_store import HYDRATION_REQUEST, declared
    started = time.monotonic()
    if resume is not None:
        plan = dict(key=resume['key'], units=resume['units'], missing=None, stamps=resume.get('stamps', []),
                    outputs=sorted(declared(ctx, steps)), token=None)
        echo(f'Resuming checkpoint hydration from {plan["key"][:12]}')
    else:
        plan, total, scanned = hydration_plan(ctx, steps, store)
        echo(f'checkpoint reuse scan: {total} checkpoints, {scanned} candidates, {time.monotonic() - started:.1f} s')
        if plan is None:
            return None
        echo(f'Hydrating from local checkpoint {plan["key"][:12]}: {plan["missing"]} missing files, '
             f'{len(plan["stamps"])} certificates staged for fingerprint checks; existing files are kept')
    started = time.monotonic()
    journal = ctx.out / JOURNAL
    try:
        atomic_json(ctx.out / HYDRATION_REQUEST, dict(key=plan['key'], units=plan['units'], stamps=plan['stamps'],
                                                      outputs=plan['outputs']))
        result = _guard(ctx, 'hydrate', plan['key'])
        pending = read_json(journal)
        if result.get('key') != plan['key'] or pending.get('key') != plan['key'] or 'units' not in pending:
            raise CheckpointError('Checkpoint hydration completion does not match its journal')
        saved = json.loads((store.manifests / (plan['key'] + '.json')).read_bytes())
        known = {**saved['stamps'], **saved.get('incremental_stamps', {})}
        staged = ctx.out / STAGED
        for name in pending.get('stamps', []):
            if name in known and not (ctx.stamps / (name + '.json')).exists():
                atomic_json(staged / (name + '.json'), dict(source=plan['key'], stamp=known[name]))
        journal.unlink()
    except (OSError, ValueError, KeyError, TypeError, CheckpointError) as error:
        echo(f'checkpoint hydration skipped: {error}')
        if journal.is_file() and 'units' in read_json(journal):
            journal.unlink()
        return None
    placed = result.get('placed', 0)
    echo(f'checkpoint restore: {placed} files hydrated, {len(plan["stamps"])} certificates staged, '
         f'{time.monotonic() - started:.1f} s')
    if plan['token'] and not placed:
        atomic_json(ctx.out / '.state/hydration-futile.json', dict(token=plan['token']))
    return plan


def staged_certificate(ctx, step, fingerprint):
    """A hydrated checkpoint certificate whose fingerprint equals the build's own; else None."""
    path = ctx.out / STAGED / (step.name + '.json')
    try:
        value = read_json(path) if path.is_file() else None
    except (OSError, ValueError, CheckpointError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get('stamp'), dict):
        return None
    stamp = value['stamp']
    return (value.get('source'), stamp) if stamp.get('fingerprint') == fingerprint and not stamp.get('touched') else None


def protect(ctx, step, *, estimate=None, echo=print):
    """@cc [owner:fontanierh,label:performance] no-silent-cold-rebuild
    A configured build MUST attempt normal cache restoration before spending native work.
    An unknown cold native job or native work exceeding the retained rebuild budget MUST stop
    before command preparation/admission unless this invocation records an explicit rebuild reason.
    Cache hits/current steps MUST NOT spend the rebuild budget. No override may weaken guards.
    """
    settings = getattr(ctx, 'checkpoint_settings', None)
    if settings is None or not step.heavy:
        return
    from .build import Call
    if not any(not isinstance(c, Call) for c in step.commands):
        return
    recorded_reason = getattr(ctx, 'rebuild_reason', None)
    if estimate is None:
        retained = ctx.out / '.state/checkpoint.json' if hasattr(ctx, 'out') else None
        if retained is not None and retained.is_file():
            estimate = read_json(retained).get('estimates', {}).get(step.name)
    known = estimate if type(estimate) in (int, float) and estimate >= 0 else None
    unknown_cold = known is None
    spent = getattr(ctx, 'checkpoint_rebuild_seconds', 0.)
    estimated = known if known is not None else 0.
    exceeds = spent + estimated > settings.get('rebuild_budget_seconds', 600)
    if (unknown_cold or exceeds) and not recorded_reason:
        duration = 'unknown cold cost' if unknown_cold else f'{spent + estimated:.0f}s retained rebuild estimate'
        raise CheckpointError(f'{step.name}: stopped before a costly rebuild ({duration}). '
                              'Run the same build with --plan --explain to inspect invalidation. '
                              'Repair checkpoint access, or rerun with --rebuild-reason "why this rebuild is necessary". '
                              'No native work was launched for this task.')
    ctx.checkpoint_rebuild_seconds = spent + estimated
    if recorded_reason:
        ctx.logs.mkdir(parents=True, exist_ok=True)
        with (ctx.logs / 'rebuild-decisions.jsonl').open('a') as handle:
            handle.write(json.dumps(dict(step=step.name, reason=recorded_reason, time=time.time(),
                                         estimated_seconds=known)) + '\n')


def capture_local(source, game, *, read_only=False, deadline_seconds=900):
    """@cc [owner:fontanierh,label:correctness] retain-existing-build-work
    Local retention MUST copy only existing generated work through the normal checkpoint guard.
    It MUST NOT build, cook, change source or manufacture stamps for the merge revision. A failed
    guard MUST report failure. Published keys MUST remain based on actual inputs and tools,
    independent of the PR or Git merge commit. No remote repository is required or uploaded here.
    """
    source = Path(source).resolve()
    if read_only and (type(deadline_seconds) is not int or not 60 <= deadline_seconds <= 900):
        raise CheckpointError('Read-only capture deadline must be 60–900 seconds including queue and cleanup')
    import subprocess
    from . import provenance
    def clean_revision():
        if not (source / '.git').exists():
            return None
        try:
            if read_only:
                argv = ['git', '--no-optional-locks', '-C', str(source)]
                revision = subprocess.check_output([*argv, 'rev-parse', 'HEAD'], text=True, timeout=15).strip()
                dirty = subprocess.check_output([*argv, 'status', '--porcelain=v1', '-z', '--untracked-files=all'], timeout=30)
                return revision if not dirty else None
            state = provenance.source_revision(root=source)
            return state['head_sha'] if not state['dirty'] else None
        except (OSError, subprocess.SubprocessError):
            return None
    source_revision = clean_revision()
    if read_only and source_revision is None:
        raise CheckpointError('Read-only candidate capture requires clean producer source')
    if not (source / 'games' / game / 'game.toml').is_file():
        raise CheckpointError('Cannot retain artifacts without a game manifest')
    folder = paths.build_dir(game) / 'logs' / ('checkpoint-retain-' + os.urandom(12).hex() + '.guard')
    from atelier.harness.safety import guarded
    bootstrap = ('import atelier,runpy,sys; atelier.__path__.insert(0,sys.argv.pop(1)); '
                 'runpy.run_module("atelier.checkpoint_worker",run_name="__main__")')
    if read_only:
        bootstrap = ('import atelier,sys,importlib; import atelier.checkpoint_worker as worker; '
                     'atelier.__path__.insert(0,sys.argv.pop(1)); import atelier.build; '
                     'atelier.__path__.pop(0); '
                     'modules=[importlib.import_module("atelier."+n) for n in '
                     '("checkpoint_store","build_checkpoints","checkpoint_actions","checkpoint_candidates")]; '
                     'assert all(__import__("pathlib").Path(m.__file__).parent == '
                     '__import__("pathlib").Path(worker.__file__).parent for m in modules), "Foreign capture implementation"; '
                     'worker.main()')
    argv = [sys.executable, *(['-u', '-B'] if read_only else []), '-c', bootstrap, str(source / 'platform/studio/atelier'), 'capture', game, str(folder),
            '--source', str(source), '--release']
    if read_only:
        argv.append('--read-only')
    if guarded.run(argv, folder, aggregate_tree=True, timeout=deadline_seconds if read_only else 3600, progress=25,
                   kind='job', purpose='retain existing build artifacts'):
        raise CheckpointError('Local checkpoint capture failed; preserve producer outputs and retry')
    key = read_json(folder / 'result.json')['key']
    store = Store(game)
    from .checkpoint_candidates import original
    saved = original(store, key) if read_only else store.load(key)
    if source_revision is not None:
        if clean_revision() != source_revision:
            raise CheckpointError('Producer source changed during checkpoint capture')
        # Annotate only a proved clean producer, including when its original worker predates
        # this metadata. The original task/tool stamps are preserved without reinterpretation.
        value = dict(saved, source_revision=source_revision)
        if read_only:
            key = identity(value)
            atomic_json(store.directory / 'candidate-sources' / (key + '.json'), value)
        else:
            key = store.save(value)
    return key


def retain(source=None, games=(), *, echo=print):
    """Save completed work before a merge, including partial builds; never start work to fill gaps."""
    import re
    source = Path(source or paths.REPO).resolve()
    if (not (source / 'games').is_dir() or not (source / '.git').exists()
            or not (source / 'platform/studio/atelier/build.py').is_file()):
        raise CheckpointError('Artifact source must be an existing Atelier Git checkout')
    selected = list(games) or sorted(p.parent.name for p in (source / 'games').glob('*/game.toml'))
    retained = {}
    build_root = Path(os.environ.get('ATELIER_BUILD_ROOT') or source / 'build')
    for game in selected:
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]*', game):
            raise CheckpointError('Invalid game ID for local retention')
        if not (source / 'games' / game / 'game.toml').is_file():
            raise CheckpointError('Cannot retain artifacts without a game manifest')
        stamps = build_root / game / 'stamps'
        if not any(stamps.glob('*.json')):
            echo(f'{game}: no existing build stamps; no build or cook requested')
            continue
        echo(f'{game}: retaining existing artifacts locally; no build or cook requested')
        from .checkpoint_manifest import retain as retain_manifest
        retained[game] = retain_manifest(source, build_root / game, game)
        echo(f'{game}: local checkpoint {retained[game]}')
    return retained


def prepare_publication(source, game, tag, revision, *, revalidate, public_repository, echo=print):
    """Retain locally and persist a backup request; never upload before public success."""
    # Source may be a different checkout from the release controller. The worker rebases paths
    # before loading its recipe; it never runs a game build, cook or source migration.
    game_manifest = Path(source) / 'games' / game / 'game.toml'
    if not game_manifest.is_file():
        return None
    data = manifest.load(game_manifest)
    if 'checkpoints' not in data:
        # Retain an older playtest without updating or rebuilding its frozen producer.
        # Policy comes from this controller; provenance stays bound to the producer.
        controller = paths.game_dir(game) / 'game.toml'
        policy = manifest.load(controller).get('checkpoints') if controller.is_file() else None
        if policy is None:
            return None
        data['checkpoints'] = policy
    from .checkpoint_github import Remote
    settings = paths.cache_dir('checkpoints', create=False) / 'settings.json'
    repository = read_json(settings).get('repository') if settings.is_file() else None
    if repository is None:
        raise CheckpointError('Configure the private build cache locally with `atelier cache configure --repository OWNER/REPOSITORY` '
                              'before publishing a playtest; never put its identity in tracked source')
    Remote(repository, game)  # Local syntax only; private network checks belong to the detached worker.
    from . import checkpoint_backup
    store = Store(game)
    target = checkpoint_backup.record_path(store, tag)
    if target.exists():
        key = read_json(target)['key']
    else:
        key = capture_local(source, game)
    revalidate()
    return checkpoint_backup.queue(store, repository, key, tag, revision, public_repository=public_repository)


def estimate(stamp):
    """Restore duration is never evidence that regenerating the artifact is cheap."""
    if 'checkpoint_build_seconds' in stamp:
        return stamp['checkpoint_build_seconds']
    if stamp.get('restored_from') or stamp.get('restore_source'):
        return None
    return stamp.get('seconds')


def incremental_environment(ctx, *, record=True):
    """@cc [owner:fontanierh,label:correctness] incremental-state-compatibility
    Pre-key state MAY continue under its existing source/output checks and compatible native
    engine/SDK. Observed tools MUST be recorded locally; a subsequent change MUST invalidate
    this allowance. Such state MUST NOT acquire or publish a produced task/tool certificate.
    """
    observed = context(ctx)
    project = getattr(ctx, 'uproject', None)
    compatible = True
    if project is not None:
        from .checkpoint_actions import compile_present
        from .build import Step, UnrealCompile
        target = project.stem + 'Editor'
        compatible = compile_present(ctx, Step('compatibility', [UnrealCompile(target)]))
        if compatible and observed.get('toolchain'):
            import subprocess
            developer = Path(subprocess.check_output(['xcode-select', '-p'], text=True, timeout=10).strip())
            sdk = read_json(developer / 'Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/SDKSettings.json')
            receipt = read_json(project.parent / 'Binaries/Mac' / (target + '.target'))
            versions = [p.get('Value') for p in receipt.get('AdditionalProperties', []) if p.get('Name') == 'SDK']
            compatible = versions == [sdk.get('Version')]
    from . import build_products
    blender = getattr(ctx, 'blender', None)
    if blender and Path(blender).is_file():
        observed['blender'] = build_products.file_digest(Path(blender))
    observed['python'] = build_products.file_digest(Path(sys.executable).resolve())
    lock = paths.REPO / 'uv.lock'
    if lock.is_file():
        observed['lock'] = build_products.file_digest(lock)
    ctx.checkpoint_observed_context = identity(observed)
    marker = ctx.out / '.state/incremental-environment.json'
    if marker.exists():
        compatible = compatible and read_json(marker).get('context') == observed
    elif compatible and record:
        atomic_json(marker, dict(context=observed))
    ctx.checkpoint_incremental_compatible = compatible
