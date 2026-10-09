"""Archive generated content outside the current game recipe before identity generation and cooking.

Unreal's cook includes every asset and stages all of Data. Incremental checkouts therefore need to move retired
imports out of Content as well as stop producing them. Archives stay under build/.
"""
import json
import shutil
import time
import tomllib
from pathlib import Path

ASSET_ROOTS = frozenset({
    'Adventure', 'AtelierValidation', 'Audio', 'Cairo', 'CairoAdventure', 'CairoBike', 'Collections', 'CommunityPark',
    'Data', 'Developers', 'Experiments', 'FX', 'FoxHunter', 'Hippodrome', 'Japan', 'MegaPark', 'Modori', 'ModoriBike',
    'SeeThrough', 'SkateMotion', 'SkatePark', 'SkateRide', 'SwordTrainer', 'Wanderer',
})
DATA_ROOTS = frozenset({
    'Network', 'SkateNative', 'SkateRide', 'adventure', 'bike', 'cairo', 'city_surface_tiles', 'communitypark',
    'heightmap.bin', 'hidamari', 'hippodrome', 'map', 'megapark', 'modori', 'skatepark', 'sword-trainer', 'treehouse',
    'world.json',
})
CHARACTER_DATA = {
    'cairo': {'adventure.json', 'bike'},
    'modori': {'adventure.json', 'bike', 'grips.json'},
    'sword-trainer': {'adventure.json'},
    'hippodrome': {'hippodrome.json'},
}
CHARACTER_ASSET_DIRECTORIES = {
    'Modori': {'Adventure', 'Textures'},
    'SwordTrainer': {'Adventure', 'Textures'},
}

DONOR = tomllib.loads((Path(__file__).parent / 'assets/characters/cairo/adventure.toml').read_text())['donor']
CAIRO_CLIPS = frozenset('A_' + clip for clip in DONOR['clips'] + DONOR['gestures'])


def retired(content):
    """Unknown generated imports at owned recipe boundaries; no traversal inside committed source data."""
    boundaries = [(content, ASSET_ROOTS), (content / 'Data', DATA_ROOTS),
                  (content / 'Audio', {'Bike', 'Combat', 'Skate'})]
    boundaries.extend((content / 'Data' / name, names) for name, names in CHARACTER_DATA.items())
    for parent, allowed in boundaries:
        if parent.is_dir():
            yield from sorted(p for p in parent.iterdir() if p.name not in allowed and not p.name.startswith('.'))
    # Renamed move folders can survive beside the body's current imports in an incremental checkout.
    for name, allowed in CHARACTER_ASSET_DIRECTORIES.items():
        parent = content / name
        if parent.is_dir():
            yield from sorted(p for p in parent.iterdir()
                              if p.is_dir() and p.name not in allowed and not p.name.startswith('.'))
    # Incremental imports can leave the old movement/combat set beside the retained body and donor clips.
    cairo = content / 'Cairo'
    for parent in (cairo, cairo / 'Textures'):
        if not parent.is_dir():
            continue
        for path in sorted(parent.iterdir()):
            name = path.stem
            if ((name.startswith('A_') and name not in CAIRO_CLIPS) or
                    name.startswith(('BS_', 'SM_Bokken', 'M_Bokken', 'T_M_Bokken')) or name == 'DA_Cairo'):
                yield path


def archive(ctx, log):
    content = ctx.game_dir / 'unreal/Content'
    archive_root = ctx.out / 'retired-content' / str(time.time_ns())
    moved = []
    for path in list(retired(content)):
        relative = path.relative_to(content)
        destination = archive_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        moved.append(str(relative))
        log.write(f'archived retired content {relative}\n')
    report = ctx.out / 'runtime-content.json'
    report.write_text(json.dumps({'archived': moved}, indent=2) + '\n')
    if moved:
        print(f'WARNING: archived {len(moved)} retired Content entries to {archive_root}; details in {report}', flush=True)
