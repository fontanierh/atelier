"""Write Mega Park's editing units (assets/adopted/megapark/units.json) for its adoption (DECISIONS D05 group 3, D08).

    uv run python games/yorimichi_v2/tools/migrate/megapark_units.py --donor-content DONOR/games/yorimichi/unreal/Content \
        --donor-build DONOR/build/yorimichi/megapark/build.json

Mega Park's packages are named by content hash, so no name rule groups them. Its source (games/yorimichi/assets/
megapark/map.json) places each of its 50 models and 29 collision meshes in one of 22 stream cells, a bounded 100 m
section of the park. Each section is one editing unit: its render meshes (`SM_MP_<asset id>`), its collision
(`UC_MP_<asset id>_<n>`), and the material instances and textures only that section's meshes use, following the
packages' own references. A material instance several sections share goes to its surface family's unit
(`shared-materials-<family>`: stone, concrete, wood, ... from the donor build's material names), and a shared texture
to the family of the instances using it (`shared-textures-<family>`, or `shared-textures-common` across families), so a
change to one surface's look stays in one unit. The retail base materials are `base-materials`, the standalone level
`standalone-level`, and the footbridge seam `seam`.

Each unit lists its recoverable originals as `sources` (repository paths under games/yorimichi; adopt.py copies them
into the record and pins their hashes, so V2 never reads the old game): a section its geometry and collision npz and
the source images of its own textures, a texture unit its images, and `base-materials` the generator that made every
Mega Park package (the import and restyle scripts, the region scripts, map.json, the restyle images and the
lettering font). Units whose packages that generator made from map.json alone (material instances, the seam, the
level) reference `base-materials`. The same donor content always gives the same file.
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
sys.path.insert(0, str(HERE))
import adopt  # noqa: E402

DONOR = REPO / 'games' / 'yorimichi'
SOURCE = DONOR / 'assets' / 'megapark' / 'map.json'
DONOR_PATH = 'games/yorimichi/assets/megapark/'
# The generator of every Mega Park package (donor build steps world.megapark, world.megapark_restyle, unreal.megapark).
GENERATOR = ('megapark_atomic_build.py', 'tools/megapark_textures.py', 'unreal/Scripts/import_megapark.py',
             'unreal/Scripts/park_atomic_native.py', 'world/regions/hidamari/fonts/NotoSansJP.ttf',
             'assets/megapark/map.json', 'assets/megapark/provenance.json')
GENERATOR_FOLDERS = ('world/regions/megapark', 'assets/megapark/restyle')
OUT = GAME / 'assets' / 'adopted' / 'megapark' / 'units.json'
ROOT = '/Game/MegaPark/'
CELL = re.compile(r'^c(?:Pres|Sim)_(-?\d+)_(-?\d+)_')
FAMILY = re.compile(r'^(?:sur_|mat_)?([A-Za-z]+)')


def cell_name(stream_file: str) -> str:
    """cPres_150_-850_high.xsf -> cell-x150-zm850 (m for minus, so 150_-850 and 150_850 never slug alike)."""
    match = CELL.match(stream_file)
    if not match:
        raise ValueError(f'{stream_file} names no stream cell')
    x, z = (v.replace('-', 'm') for v in match.groups())
    return f'cell-x{x}-z{z}'


def family(material: dict) -> str:
    """A donor material's surface family: sur_DirtGravel_GL_... -> dirtgravel, obj_... -> obj."""
    match = FAMILY.match(material.get('material_name') or material.get('name') or '')
    return match.group(1).lower() if match else 'other'


def build(content: Path, source: dict, donor_build: dict) -> dict:
    files = sorted(p for p in (content / 'MegaPark').rglob('*') if p.suffix in ('.uasset', '.umap'))
    refs = {adopt.package_name(content, p): {r for r in adopt.references(p) if r.startswith(ROOT)} for p in files}
    unit: dict[str, str] = {}
    info: dict[str, dict] = {}
    sources = collections.defaultdict(lambda: {'models': [], 'collision': []})
    for model in source['models']:
        cell = cell_name(model['stream_file'])
        unit[f'{ROOT}Meshes/SM_MP_{model["asset_id"][2:].upper()}'] = cell
        sources[cell]['models'].append(model)
    for mesh in source['collision']:
        cell = cell_name(mesh['stream_file'])
        unit[f'{ROOT}Meshes/UC_MP_{mesh["id"].upper()}'] = cell
        sources[cell]['collision'].append(mesh)
    for cell, found in sources.items():
        x, z = cell[len('cell-x'):].replace('m', '-').split('-z')
        files = sorted(m['npz'] for m in found['models'] + found['collision'])
        info[cell] = {'about': f'Mega Park section at stream cell ({x}, {z}): {len(found["models"])} model(s), '
                               f'{len(found["collision"])} collision mesh(es), their own materials and textures',
                      'provenance': 'donor build of games/yorimichi (unreal.megapark) from games/yorimichi/assets/megapark/'
                                    + ', '.join(files) + ' (map.json ' + ', '.join(sorted({m['asset_id'] for m in
                                                                                           found['models'] + found['collision']}))
                                    + ')'}
    users = collections.defaultdict(set)
    for package, targets in refs.items():
        for target in targets:
            users[target].add(package)

    # build.json keys materials M_<key>; import_megapark.py names their instances MI_<key>.
    families = {f'{ROOT}Materials/MI_{key[2:]}': family(m) for key, m in donor_build['materials'].items()}

    def place(packages, shared):
        for package in packages:
            if package in unit:
                continue
            cells = {unit.get(u) for u in users[package]}
            unit[package] = cells.pop() if len(cells) == 1 and None not in cells else shared(package)
    for package in refs:
        if package in (ROOT + 'Meshes/SM_MP_Seam', ROOT + 'Meshes/UC_MP_Seam'):
            unit[package] = 'seam'
    materials = sorted(p for p in refs if p.startswith(ROOT + 'Materials/'))
    for package in materials:
        if package.rsplit('/', 1)[1].startswith('M_Retail'):
            unit[package] = 'base-materials'
    place(materials, lambda package: f'shared-materials-{families.get(package, "other")}')
    textures = sorted(p for p in refs if p.startswith(ROOT + 'Textures/'))
    for package in textures:
        if users[package] and all(unit.get(u) == 'base-materials' for u in users[package]):
            unit[package] = 'base-materials'

    def texture_family(package):
        found = {families.get(u, 'other') for u in users[package] if u.startswith(ROOT + 'Materials/MI_')}
        return f'shared-textures-{found.pop()}' if len(found) == 1 else 'shared-textures-common'
    place(textures, texture_family)
    for package in refs:
        if package.startswith(ROOT + 'Maps/'):
            unit[package] = 'standalone-level'
    for name in sorted(n for n in set(unit.values()) if n.startswith('shared-')):
        what = name.split('-', 2)
        info[name] = {'about': f'Mega Park {what[1]} shared by more than one section, surface family {what[2]}'}
    missing = sorted(set(refs) - set(unit))
    if missing:
        raise ValueError(f'{len(missing)} Mega Park package(s) fall in no unit, e.g. {missing[0]}')
    stray = sorted(set(unit) - set(refs))
    if stray:
        raise ValueError(f'map.json names {len(stray)} package(s) the donor build lacks, e.g. {stray[0]}')
    info.update({
        'base-materials': {'about': 'Mega Park retail base materials (opaque, masked, translucent) and their textures'},
        'standalone-level': {'about': 'the standalone Super Ultra Mega Park level (F26)'},
        'seam': {'about': 'the seam meshes (render and collision) joining the park to the zeppelin footbridge'}})
    # Recoverable originals, as repository paths: section meshes and collision, then each unit's texture images. One
    # generator (base-materials' sources) made every package, the restyled textures from its images, so every other
    # unit references it.
    for cell, found in sources.items():
        info[cell]['sources'] = sorted({DONOR_PATH + m['npz'] for m in found['models'] + found['collision']})
    for tid, texture in source['textures'].items():
        package = f'{ROOT}Textures/T_{tid[2:]}'
        if package in unit:
            info[unit[package]].setdefault('sources', []).append(DONOR_PATH + texture['png'])
    generator = [f'games/yorimichi/{f}' for f in GENERATOR]
    for folder in GENERATOR_FOLDERS:
        generator += [f'games/yorimichi/{p.relative_to(DONOR).as_posix()}' for p in sorted((DONOR / folder).rglob('*'))
                      if p.is_file() and '__pycache__' not in p.parts]
    info['base-materials']['sources'] = sorted(set(generator + info['base-materials'].get('sources', [])))
    for name, about in info.items():
        if name != 'base-materials':
            if 'sources' in about:
                about['sources'] = sorted(set(about['sources']))
            about['references'] = ['adopted/megapark/base-materials']
    return {'about': 'Mega Park editing units for tools/migrate/adopt.py (written by tools/migrate/megapark_units.py)',
            'units': dict(sorted(info.items())), 'packages': dict(sorted(unit.items()))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--donor-content', type=Path, required=True)
    parser.add_argument('--donor-build', type=Path, required=True, help="the donor's megapark build.json (material names)")
    parser.add_argument('--check', action='store_true', help='exit 1 when the committed file differs')
    args = parser.parse_args(argv)
    text = json.dumps(build(args.donor_content.resolve(), json.loads(SOURCE.read_text()),
                            json.loads(args.donor_build.read_text())), indent=1) + '\n'
    if args.check:
        same = OUT.is_file() and OUT.read_text() == text
        print('units.json', 'matches' if same else 'differs')
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    counts = collections.Counter(json.loads(text)['packages'].values())
    print(f'{OUT.relative_to(REPO)}: {sum(counts.values())} packages in {len(counts)} units; largest '
          + ', '.join(f'{u} {n}' for u, n in counts.most_common(4)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
