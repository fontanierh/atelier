"""Write the Horses editing units (assets/adopted/horses/units.json) for the ownership audit.

    uv run python games/yorimichi_v2/tools/migrate/horses_units.py [--check]

/Game/Horses holds six breeds, each with one skeletal horse (mesh, skeleton, its eleven-plus rigged clips, materials and
base-colour images), seven saddle and seven rein sets, plus the shared coat masks and coat variants. Each breed is one
unit (`arabian`), each tack piece its own (`arabian-saddle-03`, `arabian-reins-05`), the coat masks one unit and every
coat variant one (`coat-bay-tobiano`). The shared horse materials belong to `generator`.

Sources (games/yorimichi/assets/horses, pinned by adopt.py --repartition): a breed unit its `horse.glb` (rig, clips,
textures inside), a tack piece its GLB, a coat variant its palette image and JSON, the masks their PNGs. `generator`
holds the manifest, the build and rider scripts that measure the rig and sample the clips, and the Unreal import
scripts. Every other unit references it.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

OUT = T.GAME / 'assets' / 'adopted' / 'horses' / 'units.json'
ROOT = '/Game/Horses'
TACK = re.compile(r'^/Game/Horses/([A-Za-z]+)/Tack/(Saddle|Reins)_(\d+)/')
ASSETS = 'assets/horses/'


def unit_of(package: str) -> str:
    rest = package[len(ROOT) + 1:]
    tack = TACK.match(package)
    if tack:
        return f'{tack.group(1).lower()}-{tack.group(2).lower()}-{tack.group(3)}'
    if rest.startswith('Coats/Masks/'):
        return 'coat-masks'
    if rest.startswith('Coats/Variants/'):
        return 'coat-' + rest.rsplit('/', 1)[1]
    if '/' in rest:
        return rest.split('/')[0].lower()
    if rest.startswith('M_Horse'):
        return 'generator'
    raise ValueError(f'{package} fits no Horses unit')


def build(game: Path) -> dict:
    unit = {p: unit_of(p) for p in T.packages_of(game, 'adopted/horses/', ROOT)}
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        about, sources = None, []
        tack = re.fullmatch(r'([a-z]+)-(saddle|reins)-(\d+)', name)
        if name == 'generator':
            about = 'Horses generator: the manifest, rig measurement and clip sampling scripts, the Unreal import ' \
                    'scripts and the shared horse materials'
        elif tack:
            breed, kind, number = tack.groups()
            about = f'{breed.capitalize()} {kind} set {number} with its materials and images'
            sources = [f'games/yorimichi/{ASSETS}{breed}/tack/{kind.capitalize()}_{number}.glb']
        elif name == 'coat-masks':
            about = 'Horse coat masks'
            sources = [T.rel(p) for p in sorted(T.donor(ASSETS + 'coats').glob('T_Coat_*_Mask.png'))]
        elif name.startswith('coat-'):
            variant = name[len('coat-'):]
            about = f'Horse coat variant {variant}'
            sources = [T.rel(T.donor(f'{ASSETS}coats/variants/kestrel/{variant}.{ext}')) for ext in ('png', 'json')]
        else:
            about = f'{name.capitalize()} horse: skeletal mesh, skeleton, clips, materials and images'
            sources = [T.rel(T.donor(f'{ASSETS}{name}/horse.glb'))]
        info[name] = {'about': about, 'sources': sources} if sources else {'about': about}
    info['generator']['sources'] = sorted(
        {T.rel(T.donor(ASSETS + f)) for f in ('build.py', 'rider.py', 'turn.py', 'manifest.json', 'coats/variants/manifest.json')}
        | {T.rel(T.donor('unreal/Scripts/import_horses.py')), T.rel(T.donor('unreal/Scripts/horse_data.py'))})
    for name, entry in info.items():
        if name != 'generator':
            entry['references'] = ['adopted/horses/generator']
    return {'about': 'Horses editing units for tools/migrate/adopt.py (written by tools/migrate/horses_units.py)',
            'units': info, 'packages': unit}


def main(argv=None) -> int:
    return T.finish(build(T.GAME), OUT, argv, __doc__)


if __name__ == '__main__':
    sys.exit(main())
