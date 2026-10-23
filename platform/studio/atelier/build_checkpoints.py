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


def _guard(ctx, operation, key=None, units=()):
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
    for unit in units:
        argv += ['--unit', unit]
    code = guarded.run(argv, folder, aggregate_tree=True, timeout=3600, progress=25,
                       kind='job', purpose='build checkpoint ' + operation, invocation_id=nonce)
    if code:
        raise CheckpointError(f'Checkpoint {operation} failed (exit {code}); retained evidence: {folder}')
    return read_json(folder / 'result.json')


def _publish_restoration(ctx, steps, store, key, record):
    """@cc [owner:fontanierh,label:correctness] post-guard-checkpoint-publication
    Receiving certificates MUST publish only after successful guarded child exit, cleanup and
    admission close. The original journal/key, fresh input identities and actual output bytes
    MUST still agree. Failure MUST retain the launch barrier and MUST NOT retain certificates.
    """
    journal = ctx.out / JOURNAL
    expected = dict(schema=1, key=key, game=ctx.game)
    pending = read_json(journal)
    units = pending.get('units') if isinstance(pending, dict) else None
    if units is not None:
        expected.update(units=units, stamps=pending.get('stamps'))
    if pending != expected or record.get('key') != key:
        raise CheckpointError('Checkpoint restore completion does not match its journal')
    saved = store.load(key)
    candidates = record.get('stamps')
    known = {**saved['stamps'], **saved.get('incremental_stamps', {})}
    if not isinstance(candidates, dict) or any(known.get(n) != s for n, s in candidates.items()):
        raise CheckpointError('Checkpoint restore completion contains foreign certificates')
    if units is not None and not set(candidates) <= set(expected['stamps']):
        raise CheckpointError('Checkpoint hydration would replace receiver certificates')
    try:
        for name, stamp in candidates.items():
            atomic_json(ctx.stamps / (name + '.json'), stamp)
        incremental_environment(ctx)
        current = certificates(ctx, steps, include_incremental=True)
        if units is not None:
            current = {n: s for n, s in current.items() if n in expected['stamps']}
        if current != candidates:
            raise CheckpointError('Checkpoint receiver changed before certificate publication')
        # Revalidate all copied bytes at the publication boundary, not just named products.
        from .checkpoint_store import roots, safe_destination
        same_path = saved['checkout'] == identity(str(paths.REPO.resolve()))
        allowed = roots(ctx)
        post_import = record.get('post_import', {})
        if set(post_import) - {'cooked/Mac/ue.projectstore'}:
            raise CheckpointError('Unexpected mutable Zen checkpoint output')
        for member, entry in saved['files'].items():
            label, _, name = member.partition('/')
            root, bound = allowed[label]
            if bound and not same_path or units is not None and not any(member.startswith(u) for u in units):
                continue
            path = safe_destination(root, name)
            expected_digest = post_import.get(member, entry.get('sha256'))
            if entry['kind'] == 'file' and (path.is_symlink() or not path.is_file()
                    or path.stat().st_mode & 0o777 != entry['mode']
                    or (member not in post_import and path.stat().st_size != entry['size'])
                    or build_products.file_digest(path) != expected_digest):
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


SMALL_ROOT = 256


def hydration_plan(ctx, steps, store):
    """Best compatible local checkpoint for the units this workspace lacks; nothing is read twice.

    Units are whole generated roots and per-task native import receipts. A unit qualifies when it is
    empty locally, or holds only a few files whose names, kinds and sizes match the checkpoint
    (restore then verifies their bytes). Large or differing units are reported, never replaced.
    """
    from itertools import islice
    from .checkpoint_store import members, roots
    allowed = roots(ctx)
    expected, ownership = identity(context(ctx)), {s.name for s in steps}
    here = identity(str(paths.REPO.resolve()))
    present = {p.stem for p in ctx.stamps.glob('*.json')} if ctx.stamps.is_dir() else set()
    local = {}
    def found(unit):
        if unit not in local:
            label, _, prefix = unit.partition('/')
            root = allowed[label][0]
            local[unit] = [(p.relative_to(root).as_posix(), p.lstat())
                           for p in islice(members(root / prefix if prefix else root), SMALL_ROOT + 1)]
        return local[unit]
    scanned, best, blocked = 0, None, []
    summaries = store.summaries()
    for age, (key, summary) in enumerate(summaries):
        if (summary['workspace_only'] or summary['context'] != expected or not set(summary['steps']) <= ownership
                or not set(summary['roots']) <= set(allowed)):
            continue
        scanned += 1
        counts = summary['roots']
        candidate = {}
        for label, count in counts.items():
            if label in ('zen', 'cooked') or allowed[label][1] and summary['checkout'] != here:
                continue
            existing = found(label + '/')
            if not existing:
                candidate[label + '/'] = count
            elif len(existing) <= SMALL_ROOT:
                candidate[label + '/'] = (count, existing)
            elif label == 'generated':
                candidate['generated'] = count  # Large root: per-task receipt units, resolved below.
            else:
                blocked.append((key, label, count))
        stamps = sum(1 for n in summary['stamps'] if n not in present)
        rough = sum(c if type(c) is int else c[0] - len(c[1]) for u, c in candidate.items() if u != 'generated')
        if best is None or (rough, stamps) > best[0]:
            best = ((rough, stamps), age, key, candidate)
    plan = None
    if best is not None and (best[0][0] or best[0][1] or 'generated' in best[3]):
        key, candidate = best[2], best[3]
        saved = store.load(key)
        files = saved['files']
        selected = {}
        for unit, value in candidate.items():
            if unit == 'generated':
                for task in {m.split('/')[2] for m in files if m.startswith('generated/native-imports/')
                             and m.count('/') > 2}:
                    prefix = 'generated/native-imports/' + task + '/'
                    if not found(prefix):
                        selected[prefix] = sum(1 for m in files if m.startswith(prefix))
                continue
            if type(value) is int:
                selected[unit] = value
                continue
            count, existing = value
            label = unit.partition('/')[0]
            if all((e := files.get(label + '/' + name)) is not None and e['kind'] == 'file'
                   and stat.S_ISREG(info.st_mode) and info.st_size == e['size'] for name, info in existing):
                if count > len(existing):
                    selected[unit] = count - len(existing)
            else:
                blocked.append((key, label, count))
        lacking = [n for n in {**saved['stamps'], **saved.get('incremental_stamps', {})} if n not in present]
        if selected:
            plan = dict(key=key, units=sorted(selected), files=sum(selected.values()), stamps=len(lacking))
    blocked = [b for b in blocked if plan is None or b[0] != plan['key'] or b[1] + '/' not in plan['units']]
    return plan, len(summaries), scanned, blocked


def hydrate(ctx, steps, store, *, echo=print):
    """Fill generated units this workspace lacks from the best compatible local checkpoint."""
    started = time.monotonic()
    plan, total, scanned, blocked = hydration_plan(ctx, steps, store)
    echo(f'checkpoint reuse scan: {total} checkpoints, {scanned} candidates, {time.monotonic() - started:.1f} s')
    if blocked:
        key, label, count = max(blocked, key=lambda b: b[2])
        echo(f'checkpoint {key[:12]} holds {count} {label} files, but local {label} differs and is kept; '
             f'empty it to hydrate from that checkpoint')
    if plan is None:
        return None
    echo(f'Hydrating {plan["files"]} files ({", ".join(u.rstrip("/") for u in plan["units"])}) from local '
         f'checkpoint {plan["key"][:12]}; existing work is kept')
    started = time.monotonic()
    try:
        result = _guard(ctx, 'restore', plan['key'], plan['units'])
    except CheckpointError as error:
        if (ctx.out / JOURNAL).exists():
            raise
        echo(f'checkpoint hydration skipped: {error}')
        return None
    _publish_restoration(ctx, steps, store, plan['key'], result)
    echo(f'checkpoint restore: {len(result.get("stamps", {}))} certificates, {time.monotonic() - started:.1f} s')
    return plan


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
