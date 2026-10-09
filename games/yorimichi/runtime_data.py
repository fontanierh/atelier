"""Yorimichi runtime data: required files, source paths and staging into Content/Data."""
import shutil
from pathlib import Path

from atelier import paths

GAME = Path(__file__).resolve().parent
REGIONS = GAME / 'world' / 'regions'
ASSETS = GAME / 'assets'


# Runtime files the game reads through AtelierDataPath, relative to unreal/Content/Data. Each is also an output of
# data.stage, so a file missing there (a renamed folder, a new entry) makes the step run.
STAGED = ('world.json', 'heightmap.bin', 'hidamari/city.json', 'skatepark/park.json', 'map/map.json', 'map/map_lines.json',
          'map/map.png', 'map/map.jpg', 'city_surface_tiles/v1_128m/manifest.json',
          'treehouse/runtime.json', 'megapark/park.json', 'bike/manifest.json', 'cairo/bike/export.json',
          'modori/bike/export.json')


def communitypark(out):
    """The committed community park library scene (docs/COMMUNITY_PARK.md)."""
    source = ASSETS / 'communitypark' / 'megapark-textured.glb'
    return source if source.is_file() else None


def staged(out):
    return STAGED + (('communitypark/park.json',) if communitypark(out) else ())


def staged_source(out, rel):
    """Where a staged file comes from: build output, except the committed park."""
    return {'skatepark/park.json': REGIONS / 'skatepark' / 'park.json'}.get(rel, out / rel)


def stage_data(ctx, log):
    """Copy the runtime files the game reads into unreal/Content/Data."""
    data = paths.content_data(ctx.game)
    for rel in staged(ctx.out):
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_source(ctx.out, rel), dst)
        log.write(f'staged {rel}\n')
    if not communitypark(ctx.out):
        (data / 'communitypark' / 'park.json').unlink(missing_ok=True)

