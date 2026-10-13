"""Stage the rider's contact data without invalidating the island's data stage."""
import shutil
from atelier import paths


def stage(ctx, log):
    rel = 'paul/bike/export.json'
    dst = paths.content_data(ctx.game) / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ctx.out / rel, dst)
    log.write(f'staged {rel}\n')
