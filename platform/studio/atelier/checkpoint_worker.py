"""Owned guarded checkpoint worker. No compilation, cooking or game/editor launch."""
import argparse
from pathlib import Path

from . import paths
from .build_cache import atomic_json


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['capture', 'restore-action', 'export-zen'])
    parser.add_argument('game')
    parser.add_argument('report', type=Path)
    parser.add_argument('--key')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--release', action='store_true')
    parser.add_argument('--read-only', action='store_true', help='candidate catalogue only; no producer metadata or Zen writes')
    args = parser.parse_args(argv)
    if args.source:
        paths.REPO = args.source.resolve()
        paths.PLATFORM = paths.REPO / 'platform'
        paths.STUDIO = paths.PLATFORM / 'studio'
        paths.GAMES = paths.REPO / 'games'
        paths.ENGINE_PLUGINS = paths.PLATFORM / 'engine/Plugins'
    from . import build, checkpoint_store
    mode = None
    previous_cook = paths.build_root() / args.game / 'logs/unreal.cook.guard/cook-observation.json'
    if previous_cook.is_file():
        previous = checkpoint_store.read_json(previous_cook)
        if previous.get('requested') in ('modern-incremental', 'modern-full'):
            mode = previous['requested']
    ctx = build.Context(args.game, cook_mode=mode, create=not args.read_only)
    recipe_free = args.operation == 'restore-action' and 'labels' in (
        checkpoint_store.read_json(ctx.out / '.state/action-requests' / (args.key + '.json')))
    steps = build.load_recipe(args.game).steps(ctx) if not recipe_free else None
    store = checkpoint_store.Store(args.game)
    args.report.mkdir(parents=True, exist_ok=True)
    result = args.report / 'result.json'
    result.unlink(missing_ok=True)
    if args.operation == 'export-zen':
        from . import checkpoint_zen
        checkpoint_zen.export(ctx)
        atomic_json(result, dict(exported=True))
    elif args.operation == 'capture':
        from .build_snapshot import require_complete
        require_complete(ctx.out, game=args.game)
        from .build_checkpoints import incremental_environment
        incremental_environment(ctx, record=not args.read_only)
        from . import checkpoint_zen
        if not args.read_only:
            checkpoint_zen.export(ctx)
        print("checkpoint capture: validating existing results, then copying verified outputs; no build requested", flush=True)
        key = checkpoint_store.capture(ctx, steps, store, echo=lambda message: print(message, flush=True), allow_seed=args.release,
                                       candidate_only=args.read_only, scratch=args.report / 'capture-hashes.sqlite3' if args.read_only else None)
        if args.release and not args.read_only and ctx.uproject and 'unreal.cook' not in store.load(key)['stamps']:
            print('Retained compatible incremental workspace state without inventing producer tool proof', flush=True)
        atomic_json(result, dict(key=key))
    elif args.operation == 'restore-action':
        from .checkpoint_actions import restore_worker
        request = checkpoint_store.read_json(ctx.out / '.state/action-requests' / (args.key + '.json'))
        if 'labels' in request:
            restore_worker(ctx, None, store, args.key, labels=request['labels'])
        else:
            restore_worker(ctx, next(s for s in steps if s.name == request['task']), store, args.key)
        atomic_json(result, dict(key=args.key))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
