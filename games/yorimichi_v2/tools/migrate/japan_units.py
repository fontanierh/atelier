"""Write the units maps of /Game/Japan/{Materials,Textures,FoliageLODs,Audio} for the ownership audit.

    uv run python games/yorimichi_v2/tools/migrate/japan_units.py [--check]

Writes assets/adopted/japan/{materials,textures,foliagelods,audio}/units.json.

- Materials: the 27 parent materials and the wind collection form `base-materials`, which holds the generator (the
  shared-material and texture scripts). The 51 instances go to one unit per surface family (`bark`, `foliage`, `ground`,
  `rock-concrete`, `buildings`, `water`, `sky-wind`, `vehicles`), the tree impostors to one unit per species.
- Textures: one unit per tree species (colour and normal), per surface family (`leaf-atlases`, `bark`, `ground`,
  `rock`, `plaza-harbor`, `sky-water`). A texture's source images are the inputs its catalogue entry names
  (world/texture_catalog.py) or its generated leaf and rock images; the rest are made by `base-materials`' scripts.
- FoliageLODs: one unit per tree or plant family with its LODs and crown material; sources are the family's
  generator settings (assets/foliage, assets/forest/export-parameters).
- Audio: one unit per footstep surface bank, plus `generator` for the two loose assets. The banks are cut from licensed
  Sonniss masters that are not in the repository (restricted route, restricted.toml): no audio is copied; the bank
  record is the pinned copy, and `generator` lists the bank, fetch and slice scripts and the licence text.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unit_tools as T  # noqa: E402

ADOPTED = T.GAME / 'assets' / 'adopted' / 'japan'
SHARED = 'adopted/japan/materials/base-materials'
GENERATOR = ['world/gen_textures.py', 'world/texture_catalog.py', 'world/material_specs.py', 'world/asset_catalog.py',
             'unreal/Scripts/shared_materials.py', 'unreal/Scripts/foliage_material.py',
             'unreal/Scripts/forest_impostor_material.py', 'unreal/Scripts/forest_lake_material.py',
             'unreal/Scripts/mountain_material.py', 'unreal/Scripts/plaza_material.py', 'unreal/Scripts/import_forest.py',
             'unreal/Scripts/import_foliage.py', 'unreal/Scripts/import_foliage_lods.py', 'world/build_foliage_lods.py',
             'world/foliage_geometry.py', 'world/forest_source.py', 'world/forest_parameters.py',
             'world/assemble_forest.py', 'world/bake_forest_tree.py', 'world/forest_impostors.py',
             'world/foliage_selected_source.py', 'world/export_foliage_piece.py', 'forest_atomic_build.py']
IMAGES = 'assets/environment/textures/'

MATERIAL_FAMILY = [
    (r'M_|MPC_', 'base-materials'), (r'MI_Bark', 'bark'),
    (r'MI_(Leaf|Flower|Feather|Grass|FarForest)', 'foliage'),
    (r'MI_(Ground|Road|Sand|Litter|Moss)', 'ground'),
    (r'MI_(Rock|Stone|Concrete|NorthRockCaps|Coast)', 'rock-concrete'),
    (r'MI_(Plaster|Paint|Tile|RoofTile|Wood|Lattice|Metal|Vermilion)', 'buildings'),
    (r'MI_Water', 'water'), (r'MI_Sky', 'sky-wind')]
TEXTURE_FAMILY = [
    (r'T_(Leaf|leaf_)', 'leaf-atlases'), (r'T_bark', 'bark'),
    (r'T_(ground|road|litter|grass|flower|ForestNormalDefault)', 'ground'),
    (r'T_(CoastRock|VolcanicRock|NorthCrater|NorthSnow|concrete|rooftile)', 'rock'),
    (r'T_(Arcade|Harbor)', 'plaza-harbor'), (r'T_(water|sky|cloudmask|white)', 'sky-water')]
TREE = re.compile(r'(?:MI_|T_)?Tree_(Forest|Tuscan)_([A-Za-z]+?)(?:_|$)')
LEAF_IMAGE = {'T_LeafCypress': 'leaf-cypress', 'T_LeafOak': 'leaf-oak', 'T_LeafOlive': 'leaf-olive',
              'T_LeafStonePine': 'leaf-pine', 'T_VolcanicRock': 'volcanic-rock'}


def family(leaf: str, table, what: str) -> str:
    tree = TREE.match(leaf)
    if tree:
        return f'tree-{tree.group(1).lower()}-{tree.group(2).lower()}'
    for pattern, unit in table:
        if re.match(pattern, leaf):
            return unit
    raise ValueError(f'{leaf} fits no {what} unit')


def tree_settings(info: dict) -> None:
    """A tree unit's generator settings: assets/forest/export-parameters/Tree_<Kind>_<Species>.json."""
    for name, entry in info.items():
        tree = re.fullmatch(r'tree-(forest|tuscan)-([a-z]+)', name)
        if tree:
            path = T.donor(f'assets/forest/export-parameters/Tree_{tree.group(1).capitalize()}_{tree.group(2).capitalize()}.json')
            if path.is_file():
                entry['sources'] = [T.rel(path)]


def finish_map(prefix: str, folder: str, unit: dict, info: dict, generator: str, out: Path) -> dict:
    tree_settings(info)
    for name, entry in info.items():
        if name != generator:
            entry['references'] = [SHARED if prefix != 'audio' else f'adopted/japan/audio/{generator}']
    return {'about': f'{folder} editing units for tools/migrate/adopt.py (written by tools/migrate/japan_units.py)',
            'units': info, 'packages': unit}


def leaf_of(package: str) -> str:
    return package.rsplit('/', 1)[1]


def materials(game: Path) -> dict:
    unit = {p: family(leaf_of(p), MATERIAL_FAMILY, 'material') for p in
            T.packages_of(game, 'adopted/japan/materials', '/Game/Japan/Materials')}
    counts = collections.Counter(unit.values())
    info = {n: {'about': f'Japan {n} materials ({counts[n]} package(s))'} for n in sorted(counts)}
    info['base-materials']['about'] = 'Japan parent materials and the wind collection, and the generator: shared ' \
                                      'material, texture and foliage scripts that made the materials, textures and foliage LODs'
    info['base-materials']['sources'] = T.code_closure(GENERATOR, ('world', 'world/regions', 'unreal/Scripts', '.'))
    return finish_map('materials', 'Japan materials', unit, info, 'base-materials', ADOPTED / 'materials' / 'units.json')


def textures(game: Path) -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location('texture_catalog', T.donor('world/texture_catalog.py'))
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    extras = {v[0].rsplit('.', 1)[0]: v[2] for v in catalog.TEXTURES.values()}
    unit = {p: family(leaf_of(p), TEXTURE_FAMILY, 'texture') for p in
            T.packages_of(game, 'adopted/japan/textures', '/Game/Japan/Textures')}
    counts = collections.Counter(unit.values())
    info = {n: {'about': f'Japan {n} textures ({counts[n]} package(s))'} for n in sorted(counts)}
    for package, name in unit.items():
        leaf = leaf_of(package)
        files = [IMAGES + e for e in extras.get(leaf, ())]
        if leaf in LEAF_IMAGE:
            files += [IMAGES + LEAF_IMAGE[leaf] + ext for ext in ('.jpg', '.provenance.json')]
        if files:
            info[name].setdefault('sources', [])
            info[name]['sources'] = sorted(set(info[name]['sources']) | {T.rel(T.donor(f)) for f in files})
    return finish_map('textures', 'Japan textures', unit, info, '', ADOPTED / 'textures' / 'units.json')


def foliage(game: Path) -> dict:
    root = '/Game/Japan/FoliageLODs'
    unit = {}
    for p in T.packages_of(game, 'adopted/japan/foliagelods', root):
        rest = p[len(root) + 1:]
        first = rest.split('/')[0]
        tree = TREE.match(first)
        if tree:
            unit[p] = f'tree-{tree.group(1).lower()}-{tree.group(2).lower()}'
        elif first.startswith(('Bush_', 'Grass_')):
            unit[p] = T.kebab(re.sub(r'_[AB]$', '', first))
        else:
            unit[p] = T.kebab(first)
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        members = sorted({p[len(root) + 1:].split('/')[0] for p, u in unit.items() if u == name})
        names = sorted({re.sub(r'^MI_', '', m).split('_Crown')[0] for m in members})
        files = []
        for member in names:
            for folder in ('assets/foliage', 'assets/forest/export-parameters'):
                path = T.donor(f'{folder}/{member}.json')
                if path.is_file():
                    files.append(T.rel(path))
        info[name] = {'about': f'Japan foliage {name} ({counts[name]} package(s)): LODs and crown material',
                      **({'sources': files} if files else {})}
    return finish_map('foliagelods', 'Japan FoliageLODs', unit, info, '', ADOPTED / 'foliagelods' / 'units.json')


def audio(game: Path) -> dict:
    root = '/Game/Japan/Audio'
    unit = {}
    for p in T.packages_of(game, 'adopted/japan/audio', root):
        rest = p[len(root) + 1:]
        unit[p] = 'footsteps-' + T.kebab(rest.split('/')[1]) if rest.startswith('Footsteps/') else 'generator'
    counts = collections.Counter(unit.values())
    info = {}
    for name in sorted(counts):
        info[name] = {'about': f'Japan footstep bank {name[len("footsteps-"):]} ({counts[name]} one-shots), cut from '
                               f'licensed masters kept out of the repository'} if name != 'generator' else \
            {'about': 'Footstep bank generator and licence: bank record, fetch and slice scripts, Sonniss licence text, '
                      'import script, plus the loose footstep assets'}
    info['generator']['sources'] = sorted(
        T.files_in(T.donor('assets/audio/footsteps')) + [T.rel(T.donor('assets/audio/SONNISS-LICENSE.txt')),
                                                         T.rel(T.donor('docs/FOOTSTEPS.md')),
                                                         T.rel(T.donor('unreal/Scripts/import_footsteps.py'))])
    return finish_map('audio', 'Japan Audio', unit, info, 'generator', ADOPTED / 'audio' / 'units.json')


MAPS = {'materials': materials, 'textures': textures, 'foliagelods': foliage, 'audio': audio}


def main(argv=None) -> int:
    code = 0
    for name, fn in MAPS.items():
        code |= T.finish(fn(T.GAME), ADOPTED / name / 'units.json', argv, __doc__)
    return code


if __name__ == '__main__':
    sys.exit(main())
