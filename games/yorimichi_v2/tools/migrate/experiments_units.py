"""Write the Experiments terrain units maps (assets/adopted/experiments/{citysurfaces,islandterrain}/units.json).

    uv run python games/yorimichi_v2/tools/migrate/experiments_units.py [--check]

Both folders hold generated 128 m cell meshes, `<Layer>_cell_<x>_<y>` with optional `_Piece..` slices. A spatial area is
one unit: `<layer>-<ax>-<ay>` with ax = floor(x / 8) and ay = floor(y / 8) (a 1024 m area; negative parts are written
`m1`), layer names without their `HD_` prefix (`north-mountains-0-1`, `farhills-m1-0`). The layers that are not cells
(shops, houses, bushes, lanes and so on) are single objects: each is its own unit (`shop-03`, `bush-azalea`, `road`).
`generator` holds the whole-city sea mesh (citysurfaces) or the sea (islandterrain) and the generator sources. There
are no materials or textures in these two folders.

Sources: only files tracked by git under games/yorimichi. The generator lists the cell scripts, the Unreal import
scripts and the layout closure that feeds them (the same scanner the donor build uses for step inputs). Every other unit
references the folder's `generator`. Cells are generated, so no unit has a model of its own.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

CELL = re.compile(r'(.+?)_cell_(-?\d+)_(-?\d+)(?:_Piece\d+)?$')
CAP = 200
MAPS = {
    'citysurfaces': dict(
        folder='/Game/Experiments/CitySurfaces/v1_128m', generator_package='HD_Sea',
        roots=['world/city_surface_tiles.py', 'world/city_terrain_surface.py', 'unreal/Scripts/import_city_surface_tiles.py',
               'world/terrain_sources.py', 'world/regions/hidamari/build.py', 'world/gen_world.py']),
    'islandterrain': dict(
        folder='/Game/Experiments/IslandTerrain/v1_atomic', generator_package='Sea',
        roots=['island_atomic_products.py', 'island_native_policy.py', 'terrain_atomic_build.py', 'region_exports.py',
               'world/terrain_sources.py', 'unreal/Scripts/import_island_atomic.py', 'unreal/Scripts/import_island_world.py',
               'world/gen_world.py']),
}


def area(x: int, y: int) -> str:
    return '-'.join(str(v // 8).replace('-', 'm') for v in (x, y))


def unit_of(leaf: str, generator_package: str) -> str:
    if leaf == generator_package:
        return 'generator'
    cell = CELL.match(leaf)
    if cell:
        layer, x, y = cell.groups()
        return f'{T.kebab(re.sub(r"^HD_|_HD", "", layer))}-{area(int(x), int(y))}'
    return T.kebab(re.sub(r'^HD_|_HD', '', leaf))


def tracked(paths: list[str]) -> list[str]:
    listed = set(subprocess.run(['git', '-C', str(T.REPO), 'ls-files', '--', 'games/yorimichi'], check=True,
                                capture_output=True, text=True).stdout.splitlines())
    missing = [p for p in paths if p not in listed]
    if missing:
        raise ValueError(f'not tracked by git: {missing[:3]}')
    return paths


def build(game: Path, key: str) -> dict:
    spec = MAPS[key]
    prefix = f'adopted/experiments/{key}'
    packages = T.packages_of(game, prefix, spec['folder'])
    unit = {p: unit_of(p.rsplit('/', 1)[1], spec['generator_package']) for p in packages}
    if len(unit) != len(packages):
        raise ValueError('a package is mapped twice')
    counts = collections.Counter(unit.values())
    if 'generator' not in counts:
        raise ValueError(f'no {spec["generator_package"]} package for the generator')
    if counts.most_common(1)[0][1] > CAP:
        raise ValueError(f'unit {counts.most_common(1)[0][0]} is over {CAP} packages')
    info = {}
    for name in sorted(counts):
        info[name] = {'about': f'Experiments {key} {name} ({counts[name]} package(s))'}
        if name != 'generator':
            # Records sit under the mapped folder's own slug (adopt.partition): adopted/experiments/<key>/v1-128m/...
            folder = re.sub(r'[^a-z0-9]+', '-', spec['folder'].rsplit('/', 1)[1].lower()).strip('-')
            info[name]['references'] = [f'{prefix}/{folder}/generator']
    info['generator']['about'] = ('Experiments %s generator: cell scripts, Unreal import scripts and layout closure, '
                                  'with the %s mesh' % (key, spec['generator_package']))
    info['generator']['sources'] = tracked(T.code_closure(spec['roots'], ('world', 'world/regions', '.', 'unreal/Scripts')))
    return {'about': f'Experiments {key} editing units for tools/migrate/adopt.py (written by tools/migrate/experiments_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    code = 0
    for key in MAPS:
        out = T.GAME / 'assets' / 'adopted' / 'experiments' / key / 'units.json'
        code |= T.finish(build(T.GAME, key), out, argv, __doc__)
    return code


if __name__ == '__main__':
    sys.exit(main())
