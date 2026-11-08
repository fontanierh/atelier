"""Write Brine Cove's editing units (assets/adopted/brinecove/units.json) for its ownership split (DECISIONS D08).

    uv run python games/yorimichi_v2/tools/migrate/brinecove_units.py [--check]

The region generator (games/yorimichi/world/regions/brinecove) bakes its scenery into meshes by feature and 256 m
tile, `SM_BC_<Feature>_<tx>_<ty>[_Soft|_PieceN]` (build.py: a face's centre picks its tile), so each feature tile is
one editing unit with its soft and split pieces: `rocks-3-4`, `townupper-4-4`. The ship tiles that hold one ship
alone are named for it: tile (2, 2) is the broken hull on the western rocks (modules.ships(), the wreck), tile
(3, 3) the galleon Adventure (layout.SHIPS); the other two galleons share tiles 4_2, 4_3 and 5_3. Each plant model
family (`SM_BC_Plant_<Family><n>`) is one unit, and each hero model (`SM_BC_Hero_<Model>_cell...`) one unit with
its own material instances and textures (`MI_BC_hero_<model>_n`, `T_BC_hero_<model>_n`). The shared materials and
textures stay `materials` and `textures`.

Each unit lists its recoverable originals as `sources` (repository paths; adopt.py --repartition copies them into
the record and pins their hashes): a hero unit its model (GLB) and provenance record, `textures` the source images
and their settings, and `materials` the generator that made every Brine Cove package (the region's scripts, the
export parameters, the hero models baked into tiles, the source registry and library). Every other unit references
`materials`. The same adopted records always give the same file.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import records  # noqa: E402

DONOR = REPO / 'games' / 'yorimichi'
ASSETS = 'games/yorimichi/assets/brinecove/'
OUT = GAME / 'assets' / 'adopted' / 'brinecove' / 'units.json'
ROOT = '/Game/Brinecove/'
MESH = re.compile(r'^SM_BC_(?:Hero_([A-Za-z]+)_cell|(Plant_[A-Za-z]+?)\d+$|([A-Za-z]+)_(-?\d+)_(-?\d+)(?:_|$))')
HERO = re.compile(r'^(?:MI|T)_BC_hero_([a-z-]+)_\d+$')
# Ship tiles holding a single ship (modules.ships(): the face centres of each ship alone).
NAMED = {'ships-2-2': 'wreck', 'ships-3-3': 'galleon-adventure'}
ABOUT = {'wreck': 'the broken hull on the western rocks (modules.ships(), tile 2_2 alone)',
         'galleon-adventure': 'the galleon Adventure in the harbour (layout.SHIPS, tile 3_3 alone)'}
# The generator of every Brine Cove package (donor build steps world.brinecove and unreal.brinecove).
GENERATOR = ('world/source_registry.py', 'assets/source-library.json')
GENERATOR_FOLDERS = ('world/regions/brinecove', 'assets/brinecove/export-parameters')


def kebab(camel: str) -> str:
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', camel).lower()


def unit_of(name: str) -> str:
    match = MESH.match(name)
    if match:
        hero, plant, feature, x, y = match.groups()
        if hero:
            return 'hero-' + kebab(hero)
        if plant:
            return kebab(plant.replace('_', ''))
        tile = f'{feature.lower()}-{x.replace("-", "m")}-{y.replace("-", "m")}'
        return NAMED.get(tile, tile)
    match = HERO.match(name)
    if match:
        return 'hero-' + match.group(1)
    if name.startswith('T_'):
        return 'textures'
    if name.startswith(('M_', 'MI_')):
        return 'materials'
    raise ValueError(f'{name} fits no Brine Cove unit')


def donor_files(folder: str) -> list[str]:
    return [f'games/yorimichi/{p.relative_to(DONOR).as_posix()}' for p in sorted((DONOR / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts]


def build(game: Path) -> dict:
    packages = sorted(o.package for a in records.discover(game)[0] if a.id.startswith('adopted/brinecove/')
                      for o in a.outputs)
    unit = {p: unit_of(p.rsplit('/', 1)[1]) for p in packages}
    if any(not p.startswith(ROOT) for p in unit):
        raise ValueError('an adopted/brinecove record owns a package outside /Game/Brinecove')
    counts = collections.Counter(unit.values())
    info = {}
    images = {p.stem: f'{ASSETS}textures/{p.name}' for p in sorted((DONOR / 'assets/brinecove/textures').iterdir())
              if p.suffix in ('.jpg', '.png')}
    heroes = {p.name.split('.')[0] for p in (DONOR / 'assets/brinecove/models').glob('*.glb')}
    for name in sorted(counts):
        if name.startswith('hero-'):
            model = name[len('hero-'):]
            if model not in heroes:
                raise ValueError(f'{name}: no hero model {model}.glb in {ASSETS}models')
            info[name] = {'about': f'Brine Cove hero model {model}: its mesh cells, material instances and textures',
                          'sources': [f'{ASSETS}models/{model}.glb', f'{ASSETS}models/{model}.provenance.json']}
            heroes.discard(model)
        elif name == 'textures':
            stems = [p.rsplit('/', 1)[1][len('T_BC_'):] for p, u in unit.items() if u == 'textures']
            missing = sorted(s for s in stems if s not in images)
            if missing:
                raise ValueError(f'textures {missing[:3]} have no source image in {ASSETS}textures')
            info[name] = {'about': 'Brine Cove shared textures',
                          'sources': sorted({images[s] for s in stems} | {f'{ASSETS}textures/textures.json'})}
        elif name == 'materials':
            info[name] = {'about': 'Brine Cove shared materials, and the region generator that made every Brine Cove '
                                   'package'}
        else:
            info[name] = {'about': ABOUT.get(name, f'Brine Cove {name} ({counts[name]} mesh(es))')}
    # The hero models no unit owns are baked into the feature tiles: the generator's inputs.
    generator = [f'games/yorimichi/{f}' for f in GENERATOR] + [f for folder in GENERATOR_FOLDERS for f in donor_files(folder)]
    generator += [f'{ASSETS}models/{m}.{ext}' for m in sorted(heroes) for ext in ('glb', 'provenance.json')]
    info['materials']['sources'] = sorted(generator)
    for name, about in info.items():
        if name != 'materials':
            about['references'] = ['adopted/brinecove/materials']
    return {'about': 'Brine Cove editing units for tools/migrate/adopt.py (written by tools/migrate/brinecove_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    args = parser.parse_args(argv)
    text = json.dumps(build(GAME), indent=1) + '\n'
    if args.check:
        same = OUT.is_file() and OUT.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    OUT.write_text(text)
    counts = collections.Counter(json.loads(text)['packages'].values())
    print(f'{OUT.relative_to(REPO)}: {sum(counts.values())} packages in {len(counts)} units; largest '
          + ', '.join(f'{u} {n}' for u, n in counts.most_common(4)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
