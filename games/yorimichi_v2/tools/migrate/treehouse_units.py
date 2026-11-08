"""Write the Tree House editing units (assets/adopted/japan/treehouse/units.json) for the ownership audit.

    uv run python games/yorimichi_v2/tools/migrate/treehouse_units.py [--check]

/Game/Japan/Treehouse holds the materials and textures of the tree house's 13 dressing props (`MI_TH_P_<prop>`,
`T_TH_P_<prop>`), its shared surfaces (`MI_TH_<surface>`, `T_TH_<surface>`), and the generated structure and dressing
mesh pieces, named for the 128 m cell that holds them (`TH_Dressing_cell_<x>_<y>[_PieceN]`). Each prop is one unit
(`prop-barrel`), each surface one (`surface-bark`), each cell's pieces one (`dressing-m2-2`, `structure-m1-1`); the two
base materials belong to `generator`.

Sources: a prop unit its model, concept and job records under assets/treehouse/props/<prop> and its export parameters;
a surface unit its generated image, prompt and provenance under assets/treehouse/textures. The cell pieces are
generated from the layout, so they reference `generator`, which holds the build graph, the region scripts, the texture
and prop tools and the Unreal import scripts. A surface with no image of its own stays an open gap.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

OUT = T.GAME / 'assets' / 'adopted' / 'japan' / 'treehouse' / 'units.json'
ROOT = '/Game/Japan/Treehouse'
ASSETS = 'assets/treehouse/'
CELL = re.compile(r'TH_(Dressing|Structure)_cell_(-?\d+)_(-?\d+)')
GENERATOR = ['treehouse_atomic_build.py', 'treehouse_pieces.py', 'world/regions/treehouse', 'tools/treehouse_textures.py',
             'tools/treehouse_props.py', 'unreal/Scripts/import_treehouse.py', 'unreal/Scripts/import_treehouse_pieces.py',
             'unreal/Scripts/treehouse_atomic_native.py']


def unit_of(package: str) -> str:
    leaf = package.rsplit('/', 1)[1]
    cell = CELL.match(leaf)
    if cell:
        kind, x, y = cell.groups()
        return f'{kind.lower()}-{x.replace("-", "m")}-{y.replace("-", "m")}'
    prop = re.fullmatch(r'(?:MI|T)_TH_P_(.+)', leaf)
    if prop:
        return 'prop-' + prop.group(1).replace('_', '-')
    surface = re.fullmatch(r'(?:MI|T)_TH_(.+)', leaf)
    if surface:
        return 'surface-' + surface.group(1).replace('_', '-')
    if leaf in ('M_TH_Light', 'M_TreeHouse'):
        return 'generator'
    raise ValueError(f'{package} fits no Tree House unit')


def build(game: Path) -> dict:
    unit = {p: unit_of(p) for p in T.packages_of(game, 'adopted/japan/treehouse', ROOT)}
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        sources, about = [], f'Tree House {name} ({counts[name]} package(s))'
        if name == 'generator':
            about = 'Tree House generator: build graph, region scripts, texture and prop tools, Unreal import scripts and ' \
                    'the base materials'
        elif name.startswith('prop-'):
            slug = name[len('prop-'):].replace('-', '_')
            about = f'Tree House dressing prop {slug}: its material instance and texture'
            sources = T.files_in(T.donor(f'{ASSETS}props/{slug}')) \
                + T.files_in(T.donor(f'{ASSETS}export-parameters/TH_P_{slug}.json'))
        elif name.startswith('surface-'):
            surface = name[len('surface-'):].replace('-', '_')
            about = f'Tree House surface {surface}: material instance and texture'
            sources = [T.rel(p) for p in sorted(T.donor(ASSETS + 'textures').glob(surface + '.*'))]
        else:
            about = f'Tree House {name.split("-")[0]} mesh pieces of one cell (generated from the layout)'
        info[name] = {'about': about, **({'sources': sources} if sources else {})}
    info['generator']['sources'] = T.code_closure(GENERATOR)
    for name, entry in info.items():
        if name != 'generator':
            entry['references'] = ['adopted/japan/treehouse/generator']
    return {'about': 'Tree House editing units for tools/migrate/adopt.py (written by tools/migrate/treehouse_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    return T.finish(build(T.GAME), OUT, argv, __doc__)


if __name__ == '__main__':
    sys.exit(main())
