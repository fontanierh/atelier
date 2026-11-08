"""Write the Belmonte train editing units (assets/adopted/belmontetrain/units.json) for the ownership audit.

    uv run python games/yorimichi_v2/tools/migrate/belmontetrain_units.py [--check]

/Game/BelmonteTrain holds seven rolling-stock models (locomotive, tender, first and second class, restaurant, baggage
and brake vans), 16 furniture models and the carriage door panels. Each rolling-stock model is one unit
(`first-class`) with its LOD0 materials and textures, its mesh and its door panels (`SM_BTD_<Model>_*`); each furniture
model is one unit (`canteen-counter`) with its mesh, materials and textures. The two shared materials belong to
`generator`.

Sources: a furniture unit its fitted GLB and fit report (assets/vehicles/belmonte-train/furniture). The carriages
are generated from the layout by the carriage scripts, so each references `generator`, which holds those scripts, the
source record, the livery and detail images, the line data and the Unreal import script.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

OUT = T.GAME / 'assets' / 'adopted' / 'belmontetrain' / 'units.json'
ROOT = '/Game/BelmonteTrain'
ASSETS = 'assets/vehicles/belmonte-train/'
GENERATOR = ['world/train/construct_carriage.py', 'world/train/export_carriage.py', 'world/train/carriage_mesh.py',
             'world/train/carriage_request.py', 'world/train/carriage_source.py', 'world/train/plan_carriage.py',
             'world/train/fittings.py', 'world/train/furniture.py', 'world/train/fit_furniture.py',
             'world/train/lod_furniture.py', 'world/train/prepare_livery.py', 'world/train/textures.py',
             'world/train/parts.py', 'world/train/service_meshes.py', 'world/train/consist.py',
             'world/train/budgets.py', 'world/train/collision.py', 'world/train/access.py', 'world/train/build.py',
             'train_carriage_build.py', 'train_carriage_products.py', 'unreal/Scripts/import_belmonte_train.py']


def unit_of(package: str) -> str:
    rest = package[len(ROOT) + 1:]
    if rest.startswith('Materials/'):
        return 'generator'
    if rest.startswith('Doors/'):
        return T.kebab(re.match(r'Doors/SM_BTD_([A-Za-z]+)_', rest).group(1))
    if rest.startswith('Furniture/SM_BTF_'):
        return T.kebab(rest[len('Furniture/SM_BTF_'):])
    source = re.match(r'Source/SM_BT(F?)_([A-Za-z]+)/', rest)
    if source:
        return T.kebab(source.group(2))
    if rest.startswith('SM_BT_') and '/' not in rest:
        return T.kebab(rest[len('SM_BT_'):])
    raise ValueError(f'{package} fits no Belmonte train unit')


def build(game: Path) -> dict:
    unit = {p: unit_of(p) for p in T.packages_of(game, 'adopted/belmontetrain', ROOT)}
    furniture = {T.kebab(p.stem): p for p in T.donor(ASSETS + 'furniture').glob('*.glb')}
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        if name == 'generator':
            info[name] = {'about': 'Belmonte train generator: carriage and furniture scripts, source record, livery and '
                                   'detail images, line data, Unreal import script and the shared materials'}
        elif name in furniture:
            glb = furniture[name]
            info[name] = {'about': f'Belmonte train furniture {name}: mesh, materials and textures',
                          'sources': [T.rel(glb), T.rel(glb.with_suffix('.json'))]}
        else:
            info[name] = {'about': f'Belmonte train {name.replace("-", " ")}: body mesh, LOD0 materials, textures'
                                   f' and door panels ({counts[name]} packages); generated from the carriage scripts'}
    inputs = T.files_in(T.donor(ASSETS + 'textures')) + [T.rel(T.donor(ASSETS + f)) for f in
                                                          ('README.md', 'source.toml', 'line.json',
                                                           'planning/furniture-dimensions.json')]
    info['generator']['sources'] = sorted(set(T.code_closure(GENERATOR)) | set(inputs))
    for name, entry in info.items():
        if name != 'generator':
            entry['references'] = ['adopted/belmontetrain/generator']
    return {'about': 'Belmonte train editing units for tools/migrate/adopt.py (written by tools/migrate/belmontetrain_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    return T.finish(build(T.GAME), OUT, argv, __doc__)


if __name__ == '__main__':
    sys.exit(main())
