"""Yorimichi runtime data: required files, source paths and staging into Content/Data."""
import importlib.util
import shutil
from pathlib import Path

from atelier import paths

GAME = Path(__file__).resolve().parent
REGIONS = GAME / 'world' / 'regions'
ASSETS = GAME / 'assets'
_spec = importlib.util.spec_from_file_location('character_definition', ASSETS / 'characters/pipeline/definition.py')
definition = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(definition)


# Runtime files the game reads through AtelierDataPath, relative to unreal/Content/Data. Each is also an output of
# data.stage, so a file missing there (a renamed folder, a new entry) makes the step run.
STAGED = ('world.json', 'heightmap.bin', 'hidamari/city.json', 'skatepark/park.json', 'map/map.json', 'map/map_lines.json',
          'map/map.png', 'map/map.jpg', 'city_surface_tiles/v1_128m/manifest.json',
          'treehouse/runtime.json', 'megapark/park.json', 'craterpark/park.json', 'bike/manifest.json', 'belmonte/runtime.json',
          # every playable character's bike report: its clips' contact windows and channels (UBikeComponent). The horse
          # reads no rider report; its runtime data, Data/horses/roster.json, is written there by unreal.horses.
          *(f'{c.id}/bike/export.json' for c in definition.movers() if c.playable))


def staged(out):
    return STAGED


def staged_source(out, rel):
    """Where a staged file comes from: build output, except the committed park."""
    bikes = {f'{c.id}/bike/export.json': out / c.output / 'bike' / 'export.json' for c in definition.movers()}
    return {'skatepark/park.json': REGIONS / 'skatepark' / 'park.json', **bikes}.get(rel, out / rel)


def stage_data(ctx, log):
    """Copy the runtime files the game reads into unreal/Content/Data."""
    data = paths.content_data(ctx.game)
    for rel in staged(ctx.out):
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_source(ctx.out, rel), dst)
        log.write(f'staged {rel}\n')

