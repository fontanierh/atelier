"""Archive generated content outside the current game recipe before identity generation and cooking.

Unreal's cook includes every asset and stages all of Data. Incremental checkouts therefore need to move retired
imports out of Content as well as stop producing them. Archives stay under build/.
"""
import importlib.util
import json
import shutil
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location('character_definition', Path(__file__).parent / 'assets/characters/pipeline/definition.py')
definition = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(definition)
MOVERS = definition.movers()   # every character with the merged move set, the donor first


def folder(path):
    """The Content folder an Unreal path starts in: '/Game/Modori/Adventure' -> 'Modori'."""
    return path.removeprefix('/Game/').split('/')[0]


# Each mover's imports: its body, its move set and, if playable, its bike clips (/Game/<Name>Bike).
CHARACTER_ROOTS = ({folder(p) for c in MOVERS for p in (c.unreal_path, c.adventure['dest'])}
                   | {folder(c.unreal_path) + 'Bike' for c in MOVERS if c.playable})
ASSET_ROOTS = frozenset({
    'Adventure', 'AtelierValidation', 'Audio', 'Belmonte', 'Collections', 'CraterPark', 'Data', 'Developers',
    'Experiments', 'FX', 'FoxHunter', 'Hippodrome', 'Japan', 'MegaPark', 'SeeThrough', 'SkateMotion', 'SkatePark',
    'SkateRide', 'SkateRuntime', 'Wanderer',
} | CHARACTER_ROOTS)
DATA_ROOTS = frozenset({
    'Network', 'SkateRide', 'adventure', 'belmonte', 'bike', 'city_surface_tiles', 'craterpark', 'heightmap.bin',
    'hidamari', 'hippodrome', 'map', 'megapark', 'skatepark', 'treehouse', 'world.json',
} | {c.id for c in MOVERS})
# Each mover's runtime data: its move record, its readiness record and bike report if playable and its posed grips if
# committed.
CHARACTER_DATA = {
    **{c.id: {'adventure.json'} | ({'character.json', 'bike'} if c.playable else set())
       | ({'grips.json'} if (c.folder.parent / 'grips' / c.id).is_dir() else set()) for c in MOVERS},
    'hippodrome': {'hippodrome.json'},
}
# The folders inside a mover's own folder, when its move set is imported there.
CHARACTER_ASSET_DIRECTORIES = {folder(c.unreal_path): {c.adventure['dest'].rsplit('/', 1)[1], 'Textures'}
                               for c in MOVERS if c.adventure['dest'].startswith(c.unreal_path + '/')}

DONOR = MOVERS[0]
DONOR_CLIPS = frozenset('A_' + clip for clip in DONOR.donor['clips'] + DONOR.donor['gestures'])


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
    # Incremental imports can leave the donor's former movement/combat set beside its body and donor clips.
    donor = content / folder(DONOR.unreal_path)
    for parent in (donor, donor / 'Textures'):
        if not parent.is_dir():
            continue
        for path in sorted(parent.iterdir()):
            name = path.stem
            if ((name.startswith('A_') and name not in DONOR_CLIPS) or
                    name.startswith(('BS_', 'SM_Bokken', 'M_Bokken', 'T_M_Bokken')) or name == f'DA_{DONOR.name}'):
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
