"""Write the Hidamari town-prop editing units (assets/adopted/japan/hidamari/units.json) for the ownership audit.

    uv run python games/yorimichi_v2/tools/migrate/hidamari_units.py [--check]

/Game/Japan/Hidamari holds the materials and textures of the town's 32 props (`MI_HD_P_<prop>`, `T_HD_P_<prop>`), the
shared town surfaces (`MI_HD_<surface>`, `T_HD_<surface>`), and the LODs, materials and textures of the Caldera trees.
Each prop is one unit (`prop-bus-stop`), each surface one (`surface-brick`), each tree one (`tree-caldera-cedar-a`);
the city base material belongs to `generator`.

Sources: a prop unit its model (GLB), concept image and job record under assets/hidamari/props/<prop> and its export
parameters; a surface unit its generated image and settings under assets/hidamari/textures; a tree unit its generated
model and job records under assets/craterpark/trees. `generator` holds the prop build graph, roster, texture tool
and Unreal import scripts. Every other unit references it. A surface with no image of its own (`flat`) stays an open gap.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

OUT = T.GAME / 'assets' / 'adopted' / 'japan' / 'hidamari' / 'units.json'
ROOT = '/Game/Japan/Hidamari'
ASSETS = 'assets/hidamari/'
TREE = re.compile(r'Tree_Caldera_(BlackPine|Cedar)_([AB])')
GENERATOR = ['hidamari_prop_build.py', 'world/regions/hidamari/prop_roster.py', 'tools/hidamari_textures.py',
             'unreal/Scripts/import_hidamari.py', 'unreal/Scripts/city_material.py']


def unit_of(package: str) -> str:
    leaf = package.rsplit('/', 1)[1]
    tree = TREE.search(leaf)
    if tree:
        return f'tree-caldera-{T.kebab(tree.group(1))}-{tree.group(2).lower()}'
    prop = re.fullmatch(r'(?:MI|T)_HD_P_(.+)', leaf)
    if prop:
        return 'prop-' + prop.group(1).replace('_', '-')
    surface = re.fullmatch(r'(?:MI|T)_HD_(.+)', leaf)
    if surface:
        return 'surface-' + surface.group(1)
    if leaf == 'M_HDCity':
        return 'generator'
    raise ValueError(f'{package} fits no Hidamari unit')


def build(game: Path) -> dict:
    unit = {p: unit_of(p) for p in T.packages_of(game, 'adopted/japan/hidamari', ROOT)}
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        sources, about = [], f'Hidamari {name} ({counts[name]} package(s))'
        if name == 'generator':
            about = 'Hidamari prop and surface generator: build graph, roster, texture tool, Unreal import scripts and ' \
                    'the city base material'
        elif name.startswith('prop-'):
            slug = name[len('prop-'):].replace('-', '_')
            about = f'Hidamari town prop {slug}: its material instance and texture'
            sources = T.files_in(T.donor(f'{ASSETS}props/{slug}')) \
                + T.files_in(T.donor(f'{ASSETS}prop-export-parameters/HD_P_{slug}.json'))
        elif name.startswith('surface-'):
            surface = name[len('surface-'):]
            about = f'Hidamari town surface {surface}: material instance and texture'
            sources = [T.rel(p) for ext in ('jpg', 'json') if (p := T.donor(f'{ASSETS}textures/{surface}.{ext}')).is_file()]
        elif name.startswith('tree-'):
            kind, letter = re.fullmatch(r'tree-caldera-(.+)-([ab])', name).groups()
            about = f'Caldera tree {kind} {letter.upper()}: LOD meshes' + (', material and texture' if kind == 'cedar' else '')
            sources = T.files_in(T.donor(f'assets/craterpark/trees/{kind.replace("-", "_")}_{letter}'))
        info[name] = {'about': about, **({'sources': sources} if sources else {})}
    info['generator']['sources'] = T.code_closure(GENERATOR)
    for name, entry in info.items():
        if name != 'generator':
            entry['references'] = ['adopted/japan/hidamari/generator']
    return {'about': 'Hidamari editing units for tools/migrate/adopt.py (written by tools/migrate/hidamari_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    return T.finish(build(T.GAME), OUT, argv, __doc__)


if __name__ == '__main__':
    sys.exit(main())
