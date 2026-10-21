"""Owned guarded checkpoint worker. No compilation, cooking or game/editor launch."""
import argparse
from pathlib import Path

from . import paths
from .build_cache import atomic_json


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['capture', 'restore', 'restore-action'])
    parser.add_argument('game')
    parser.add_argument('report', type=Path)
    parser.add_argument('--key')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--release', action='store_true')
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
    ctx = build.Context(args.game, cook_mode=mode)
    steps = build.load_recipe(args.game).steps(ctx)
    store = checkpoint_store.Store(args.game)
    args.report.mkdir(parents=True, exist_ok=True)
    result = args.report / 'result.json'
    result.unlink(missing_ok=True)
    if args.operation == 'capture':
        from .build_snapshot import require_complete
        require_complete(ctx.out, game=args.game)
        from .build_checkpoints import incremental_environment
        incremental_environment(ctx)
        from . import checkpoint_zen
        checkpoint_zen.export(ctx)
        key = checkpoint_store.capture(ctx, steps, store, allow_seed=args.release)
        if args.release and ctx.uproject and 'unreal.cook' not in store.load(key)['stamps']:
            print('Retained compatible incremental workspace state without inventing producer tool proof', flush=True)
        atomic_json(result, dict(key=key))
    elif args.operation == 'restore-action':
        from .checkpoint_actions import restore_worker
        request = checkpoint_store.read_json(ctx.out / '.state/action-requests' / (args.key + '.json'))
        step = next(s for s in steps if s.name == request['task'])
        restore_worker(ctx, step, store, args.key)
        atomic_json(result, dict(key=args.key))
    else:
        if not args.key:
            parser.error('restoration requires --key')
        stamps = checkpoint_store.restore(ctx, steps, store, args.key)
        from . import checkpoint_zen
        post_import = checkpoint_zen.import_(ctx)
        atomic_json(result, dict(key=args.key, stamps=stamps, post_import=post_import))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
