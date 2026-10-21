"""The single build/release checkpoint workflow; no alternate fast-build command.

Ordinary builds hydrate an empty generated workspace and retain successful task results.
Releases capture workspace checkpoints in the configured private GitHub repository.
Missing/incompatible checkpoints never silently authorize an expensive cold rebuild.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

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
    """Native-file copies use one normal owned-child admission/guard lifecycle."""
    from atelier.harness.safety import guarded
    nonce = os.urandom(12).hex()
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
    admission close. The original journal/key, fresh input identities and actual output bytes
    MUST still agree. Failure MUST retain the launch barrier and MUST NOT retain certificates.
    """
    journal = ctx.out / JOURNAL
    expected = dict(schema=1, key=key, game=ctx.game)
    if read_json(journal) != expected or record.get('key') != key:
        raise CheckpointError('Checkpoint restore completion does not match its journal')
    saved = store.load(key)
    candidates = record.get('stamps')
    if not isinstance(candidates, dict) or any(saved['stamps'].get(n) != s for n, s in candidates.items()):
        raise CheckpointError('Checkpoint restore completion contains foreign certificates')
    try:
        for name, stamp in candidates.items():
            atomic_json(ctx.stamps / (name + '.json'), stamp)
        if certificates(ctx, steps) != candidates:
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
            if bound and not same_path:
                continue
            path = safe_destination(root, name)
            expected_digest = post_import.get(member, entry.get('sha256'))
            if entry['kind'] == 'file' and (path.is_symlink() or not path.is_file()
                    or (member not in post_import and path.stat().st_size != entry['size'])
                    or build_products.file_digest(path) != expected_digest):
                raise CheckpointError('Checkpoint output changed before certificate publication')
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
        return store
    expected_context, ownership = context(ctx), {s.name for s in steps}
    for key, saved in store.latest():
        if saved['context'] == expected_context and set(saved.get('steps', ())) <= ownership:
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
        with tempfile.TemporaryDirectory(dir=store.directory) as temporary:
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
    from .build import Call, UnrealCompile
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


def publish(source, game, tag, revision, *, revalidate, echo=print):
    """Run the controller's checkpoint worker against the producer's source and existing outputs."""
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
    remote = Remote(repository, game, echo=echo)
    remote.require_private()  # Refuse before any snapshot/export work.
    folder = paths.build_dir(game) / 'checkpoint-publish'
    from atelier.harness.safety import guarded
    bootstrap = ('import atelier,runpy,sys; atelier.__path__.insert(0,sys.argv.pop(1)); '
                 'runpy.run_module("atelier.checkpoint_worker",run_name="__main__")')
    argv = [sys.executable, '-c', bootstrap, str(Path(source) / 'platform/studio/atelier'), 'capture', game, str(folder),
            '--source', str(source), '--release']
    if guarded.run(argv, folder, aggregate_tree=True, timeout=3600, progress=25,
                   kind='job', purpose='retain playtest build checkpoint'):
        raise CheckpointError('Playtest checkpoint capture failed; public release was not published')
    key = read_json(folder / 'result.json')['key']
    revalidate()
    return remote.publish(Store(game), key, tag, revision=revision, revalidate=revalidate)


def estimate(stamp):
    """Restore duration is never evidence that regenerating the artifact is cheap."""
    if 'checkpoint_build_seconds' in stamp:
        return stamp['checkpoint_build_seconds']
    if stamp.get('restored_from') or stamp.get('restore_source'):
        return None
    return stamp.get('seconds')
