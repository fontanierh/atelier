"""Yorimichi runtime data: required files, source paths and staging into Content/Data."""
import importlib.util
import shutil
from pathlib import Path

from atelier import paths

GAME = Path(__file__).resolve().parent
REGIONS = GAME / 'world' / 'regions'
ASSETS = GAME / 'assets'
RACING_COURSES = GAME / 'world/racing/belmonte_courses.json'
RACING_VALIDATOR = GAME / 'world/racing/courses.py'
RACING_RUNTIME = 'racing/belmonte_courses.json'
_courses_spec = importlib.util.spec_from_file_location('racing_courses', RACING_VALIDATOR)
courses = importlib.util.module_from_spec(_courses_spec)
_courses_spec.loader.exec_module(courses)
_spec = importlib.util.spec_from_file_location('character_definition', ASSETS / 'characters/pipeline/definition.py')
definition = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(definition)


# Runtime files the game reads through AtelierDataPath, relative to unreal/Content/Data. Each is also an output of
# data.stage or its explicit migrated leaf, so each owner checks its complete output.
STAGED = ('world.json', 'heightmap.bin', 'hidamari/city.json', 'skatepark/park.json', 'map/map.json', 'map/map_lines.json',
          'map/map.png', 'map/map.jpg', 'map/atlas-serif.ttf',
          *(f'map/atlas/{key}.png' for key in ('world', 'momiji_coast', 'momiji_woods', 'hidamari', 'temple_island',
                                             'northern_foothills', 'volcanic_highlands', 'haras_valley', 'brinecove')),
          'city_surface_tiles/v1_128m/manifest.json','terrain/island.json','southwest/runtime.json','forest_lake/manifest.json','village/atomic-manifest.json','village/pieces.json',
          'treehouse/runtime.json', 'treehouse/pieces.json', 'treehouse/surfaces.json', 'megapark/park.json', 'craterpark/park.json', 'craterpark/cloud.json', 'bike/manifest.json', 'kart/cockpit.json',  # kart import owns this staged output (see staged()).
          'belmonte/runtime.json',
          'brinecove/runtime.json', 'gondola/runtime.json', 'ferry/service/service.json', RACING_RUNTIME,
          # every playable character's bike report: its clips' contact windows and channels (UBikeComponent). The horse
          # reads no rider report; its runtime data, Data/horses/roster.json, is written there by unreal.horses.
          *(f'{c.id}/bike/export.json' for c in definition.movers() if c.playable),
          *(f'{c.id}/portrait.png' for c in definition.movers() if c.playable))


def staged(out):
    # The kart import owns its geometry and matching cockpit data together. It can rebuild
    # without dragging the world, atlas and all character animation exports through data.stage.
    return tuple(rel for rel in STAGED if rel not in ('kart/cockpit.json', RACING_RUNTIME))


def staged_source(out, rel):
    """Where a staged file comes from: build output, except committed park, courses and character portraits."""
    bikes = {f'{c.id}/bike/export.json': out / c.output / 'bike' / 'export.json' for c in definition.movers()}
    portraits = {f'{c.id}/portrait.png': ASSETS / 'characters' / 'portraits' / f'{c.id}.png'
                 for c in definition.movers() if c.playable}
    return {'skatepark/park.json': out / 'skatepark/runtime-park.json',
            'belmonte/runtime.json': out / 'products/belmonte/runtime.json',
            'brinecove/runtime.json': out / 'products/brinecove/runtime.json',
            'map/atlas-serif.ttf': ASSETS / 'ui/fonts/atlas-serif.ttf',
            RACING_RUNTIME: RACING_COURSES, **bikes, **portraits}.get(rel, out / rel)


def stage_data(ctx, log):
    """@cc [owner:fontanierh,label:correctness] remaining-v1-runtime-stage
    Invalid courses MUST still fail before any remaining runtime staging write. The
    controller-owned racing file MUST NOT be copied or owned here. Every still-v1
    file MUST preserve its original copy2 byte/mtime behavior; only the migrated
    leaf has byte/path/normalized-mode semantics without an ambient-mtime promise.
    See test_invalid_courses_fail_before_staging_writes, test_staging_tracks_all_course_inputs
    and test_runtime_data.py. Mixed checkpoint/reader custody is an I1 activation gate.
    """
    courses.load(RACING_COURSES, ASSETS / 'belmonte/source.json')
    data = paths.content_data(ctx.game)
    for rel in staged(ctx.out):
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_source(ctx.out, rel), dst)
        log.write(f'staged {rel}\n')

