"""The game target's receipt: its products and runtime dependencies, and their paths after a restore.

UBT writes $(ProjectDir) and $(EngineDir) variables for the products but absolute paths for the
repository's own plugin descriptors. A result restored from another worktree keeps those donor paths,
so a restore fixes exactly those references; the building checkout's own receipt is never rewritten.
"""
import json
from pathlib import Path


def receipt(ctx):
    return Path(ctx.uproject).parent / 'Binaries/Mac/Yorimichi.target'


def expand(ctx, text):
    project = Path(ctx.uproject).resolve().parent
    engine = Path(ctx.unreal_root).resolve()
    return Path(text.replace('$(ProjectDir)', project.as_posix()).replace('$(EngineDir)', engine.as_posix()))


def verify(ctx, log):
    """Every declared product and every runtime dependency must exist before anything consumes the binary."""
    path = receipt(ctx)
    if not path.is_file():
        raise RuntimeError('the game target did not write ' + path.name)
    data = json.loads(path.read_text())
    products = data.get('BuildProducts') or []
    dependencies = data.get('RuntimeDependencies') or []
    missing = [item['Path'] for item in products if not expand(ctx, item['Path']).exists()]
    missing += [item['Path'] if isinstance(item, dict) else item for item in dependencies
                if not expand(ctx, item['Path'] if isinstance(item, dict) else item).exists()]
    if missing:
        raise RuntimeError('game target products or dependencies are missing: ' + ', '.join(missing[:6]))
    log.write(f'game binary receipt: {len(products)} products, {len(dependencies)} runtime dependencies present\n')


def relocate(ctx, log):
    """A restored receipt still names the donor checkout's plugin descriptors; point them at this one.

    The products already use $(ProjectDir)/$(EngineDir), so only absolute repository paths move.
    """
    from atelier import paths
    path = receipt(ctx)
    if not path.is_file():
        raise RuntimeError('the restored game binary has no .target receipt')
    data = json.loads(path.read_text())
    dependencies = data.get('RuntimeDependencies') or []
    moved = 0
    for item in dependencies:
        text = item.get('Path', '') if isinstance(item, dict) else item
        if not text.startswith('/') or Path(text).is_relative_to(paths.REPO):
            continue
        wanted = next(((paths.REPO / marker.split('/')[1] / text.split(marker, 1)[1]).as_posix()
                       for marker in ('/platform/', '/games/') if marker in text), text)
        if wanted == text:
            continue
        moved += 1
        if isinstance(item, dict):
            item['Path'] = wanted
    if moved:
        data['RuntimeDependencies'] = dependencies
        path.write_text(json.dumps(data) + '\n')
    log.write(f'game binary relocated {moved} repository references\n')
    verify(ctx, log)
