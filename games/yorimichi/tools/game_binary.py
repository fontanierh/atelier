"""The game target's receipt: its products and runtime dependencies, and a checkout-independent form.

UBT writes $(ProjectDir) and $(EngineDir) variables for the products but absolute paths for the
repository's own plugin descriptors. Those are rewritten to $(ProjectDir) right after the build, so a
stored result is byte-identical in every checkout and a restore needs no rewriting of its own.
"""
import json
import os
from pathlib import Path


def receipt(ctx):
    return Path(ctx.uproject).parent / 'Binaries/Mac/Yorimichi.target'


def expand(ctx, text):
    project = Path(ctx.uproject).resolve().parent
    engine = (Path(ctx.unreal_root) / 'Engine').resolve()  # $(EngineDir) is the engine folder, not its root
    return Path(text.replace('$(ProjectDir)', project.as_posix()).replace('$(EngineDir)', engine.as_posix()))


def verify(ctx, log):
    """Every declared product and every runtime dependency must exist before anything consumes the binary."""
    path = receipt(ctx)
    if not path.is_file():
        raise RuntimeError('the game target did not write ' + path.name)
    data = json.loads(path.read_text())
    if portable(ctx, data):          # UBT writes the repository's own plugin descriptors absolutely
        path.write_text(json.dumps(data) + '\n')
    products = data.get('BuildProducts') or []
    dependencies = data.get('RuntimeDependencies') or []
    missing = [item['Path'] for item in products if not expand(ctx, item['Path']).exists()]
    missing += [item['Path'] if isinstance(item, dict) else item for item in dependencies
                if not expand(ctx, item['Path'] if isinstance(item, dict) else item).exists()]
    if missing:
        raise RuntimeError('game target products or dependencies are missing: ' + ', '.join(missing[:6]))
    log.write(f'game binary receipt: {len(products)} products, {len(dependencies)} runtime dependencies present\n')


def portable(ctx, data):
    """Rewrite absolute paths inside this repository as $(ProjectDir) so the bytes do not depend on the checkout.

    Without this a restored result differs from its stored entry and the store refuses it. Products already use the
    variable; the repository plugin descriptors in RuntimeDependencies do not.
    """
    from atelier import paths
    project = Path(ctx.uproject).resolve().parent
    changed = False
    for item in data.get('RuntimeDependencies') or []:
        text = item.get('Path', '') if isinstance(item, dict) else item
        if not text.startswith('/'):
            continue
        target = Path(text)
        if not target.is_relative_to(paths.REPO):
            continue
        wanted = '$(ProjectDir)/' + os.path.relpath(target, project).replace(os.sep, '/')
        if isinstance(item, dict):
            item['Path'] = wanted
        changed = True
    return changed


def relocate(ctx, log):
    """A restored receipt must carry no checkout-specific path; check it in this checkout and log where it points."""
    verify(ctx, log)
    log.write('game binary receipt relocated to this checkout\n')
