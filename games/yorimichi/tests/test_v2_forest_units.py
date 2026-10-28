"""unreal.forest as native units: the actual rows and templates, the narrow views, bodies on a fake editor."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_forest_units as forest  # noqa: E402
import v2_geometry_templates as geometry_templates  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(forest.BODY, 'forest_members_test')
body = load(forest.SCRIPT, 'forest_body_test')
SPECIES = forest.roster(ROOT)


def natives():
    shared = [forest.FOLIAGE, forest.PAINTED, forest.WHITE,
              *sorted({f'{forest.MATERIALS}/MI_{v[k]}' for v in SPECIES.values() for k in ('leaf', 'bark')}
                      - {f'{forest.MATERIALS}/MI_{leaf}' for leaf in forest.LEAVES})]
    value = {p: {'unit': 'native.' + p.rsplit('/', 1)[1], 'item': 'asset', 'package': p} for p in shared}
    value[f'{forest.MATERIALS}/MI_Bark']['dependencies'] = [forest.PAINTED]
    return value


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('forest_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['forest_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [*recipe._load_helper_module('forest_atomic_recipe', GAME / 'forest_atomic_build.py').steps(context),
             *(s for s in recipe.steps(context) if s.name in ('unreal.forest', 'world.forest_textures'))]
    names, products = {s.name for s in steps}, {p.name for s in steps for p in s.products}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []
        step.reads = [r for r in step.reads if r in products]
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    return rows, geometry_templates.geometry_templates(rows, checkout=ROOT)


@pytest.fixture(scope='module')
def declared(actual):
    return forest.forest_units(actual[1], rows=actual[0], checkout=ROOT, natives=natives())


def test_every_original_package_has_one_owner(actual, declared):
    rows = {r['id']: r for r in actual[0]}
    product = next(p for p in rows['unreal.forest']['products'] if p['id'] == 'forest.native_assets')
    expected = {'/Game/' + p.removeprefix('games/yorimichi/unreal/Content/').removesuffix('.uasset') for p in product['paths']}
    owned = {p for p, ref in declared['packages'].items() if p.startswith('/Game/') and not ref['unit'].startswith('native.')}
    assert owned == expected and len(expected) == 2 + 8 + 8 * 9
    assert declared['packages'][forest.REPORT]['unit'] == declared['packages'][forest.NATIVE_REPORT]['unit'] == 'unreal.forest.record'
    assert declared['aliases'] == {'unreal.forest': ('unreal.forest.record',)}


def test_raws_follow_their_own_export_child_and_species_owners_take_derived_raws(declared):
    templates = [t for t in declared['geometry']['templates'] if t['unit_prefix'].startswith('world.forest.export.')]
    assert len(templates) == 40 and all(len(t['followers']) == 1 for t in templates)
    raw = templates[0]['followers'][0]['unit']
    assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': '$export', 'item': 'asset'}
    assert raw['params']['fbx'] == forest.FBX and raw['outputs'][0]['destination'] == 'store'
    units = {u['id']: u for u in declared['units']}
    owner = units['unreal.forest.finish.Tree_Tuscan_Olive']
    assert owner['op']['kind'] == 'unreal.author' and len(owner['outputs']) == 5
    levels = owner['params']['args']['levels']['derived_items']['templates']
    assert [t['unit_prefix'] for t in levels] == ['world.forest.export.Tree_Tuscan_Olive',
                                                  *(f'world.forest.export.Tree_Tuscan_Olive_LOD{i}' for i in range(1, 5))]
    assert set(owner['params']['args']['materials']) == {'LeafOlive', 'BarkOlive', 'Tree_Tuscan_Olive_Impostor',
                                                         'Tree_Tuscan_Olive_Crown'}
    names = {i['name']: i['source'] for i in owner['inputs']}
    assert names['material_LeafOlive']['unit'] == 'unreal.forest.material.MI_LeafOlive'
    assert names['entry'] == {'kind': 'item', 'unit': 'forest.species', 'item': 'Tree_Tuscan_Olive'}
    bark = units['unreal.forest.finish.Tree_Forest_Oak']
    assert 'native_Japan_Materials_M_Painted' in {i['name'] for i in bark['inputs']}
    split = units['forest.species']
    assert all(o['kind'] == 'file' for o in split['params']['recipe']['outputs']) and 'whole' in split['inputs'][0]
    atlas = units['unreal.forest.texture.raw.T_Tree_Forest_Pine_normal']
    assert atlas['params']['source_member'] == 'Tree_Forest_Pine_normal.png'
    assert units['unreal.forest.texture.T_Tree_Forest_Pine_normal']['params']['properties'] == forest.ATLAS['normal']
    assert units['unreal.forest.texture.raw.T_ForestNormalDefault']['inputs'][0]['source']['unit'] == \
        'world.forest.impostor.Tree_Tuscan_Cypress'


@pytest.mark.parametrize('damage', ['product', 'template', 'native'])
def test_declaration_drift_refuses(actual, damage):
    rows, geometry, value = deepcopy(actual[0]), deepcopy(actual[1]), natives()
    found = {r['id']: r for r in rows}
    if damage == 'product':
        next(p for p in found['unreal.forest']['products'] if p['id'] == 'forest.native_assets')['paths'].pop()
    elif damage == 'template':
        geometry['templates'] = [t for t in geometry['templates'] if not t['unit_prefix'].endswith('Pine_LOD2')]
    else:
        value.pop(forest.PAINTED)
    with pytest.raises(Unsupported):
        forest.forest_units(geometry, rows=rows, checkout=ROOT, natives=value)


# ---- views ----------------------------------------------------------------------------------------------------------

def tree(name):
    return {'height': 6.2, 'spread': 3., 'leaf': 'LeafOlive', 'triangles': [9000, 4000, 1500, 300, 12],
            'screen_sizes': [1., .24, .075, .018, .0054], 'impostor_slot': name + '_Impostor', 'impostor_bark': 'BarkOlive',
            'crown': {'slot': name + '_Crown', 'colour': [.1, .3, .1]}, 'trunk_hulls': [{'matrix': [], 'vertices': []}],
            'impostor': {'normal_space': 'camera-right-up-outward',
                         'atlases': {'colour': name + '_colour.png', 'normal': name + '_normal.png'}}}


def test_species_view_is_each_entry_after_the_whole_manifest_checks(tmp_path):
    names = sorted(SPECIES)
    (tmp_path / 'trees.json').write_text(json.dumps({n: tree(n) for n in names}))
    members.species(tmp_path / 'trees.json', tmp_path / 'out', names)
    assert json.loads((tmp_path / 'out/Tree_Tuscan_Pine.json').read_text()) == tree('Tree_Tuscan_Pine')
    bad = {n: tree(n) for n in names}; bad['Tree_Tuscan_Pine']['impostor']['atlases']['normal'] = 'other.png'
    (tmp_path / 'trees.json').write_text(json.dumps(bad))
    with pytest.raises(ValueError, match='atlases'):
        members.species(tmp_path / 'trees.json', tmp_path / 'out2', names)
    assert not (tmp_path / 'out2').exists()


def test_leaf_view_requires_exactly_the_committed_leaves(tmp_path):
    library = tmp_path / 'textures'; library.mkdir()
    for leaf in forest.LEAVES:
        (library / f'T_{leaf}.png').write_bytes(leaf.encode())
    (library / 'textures.json').write_text(json.dumps({leaf: {'file': f'T_{leaf}.png'} for leaf in forest.LEAVES}))
    members.leaves(library, tmp_path / 'out', list(forest.LEAVES))
    assert (tmp_path / 'out/T_LeafOak.png').read_bytes() == b'LeafOak'
    (library / 'textures.json').write_text(json.dumps({leaf: {'file': f'T_{leaf}.png'} for leaf in forest.LEAVES[:3]}))
    with pytest.raises(ValueError, match='committed leaves'):
        members.leaves(library, tmp_path / 'out2', list(forest.LEAVES))


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Material(Asset): pass
class MaterialInterface(Asset): pass
class Texture2D(Asset): pass
class MaterialInstanceConstant(MaterialInterface): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves = {}, []
    def create(name, folder, cls, factory):
        assets[f'{folder}/{name}'] = cls(f'{folder}/{name}'); return assets[f'{folder}/{name}']
    M = NS(set_material_instance_parent=lambda mi, p: mi.props.update(parent=p),
           set_material_instance_vector_parameter_value=lambda mi, k, v: mi.props.update({k: v}),
           set_material_instance_texture_parameter_value=lambda mi, k, v: mi.props.update({k: v}),
           update_material_instance=lambda mi: None)
    unreal = NS(Material=Material, MaterialInterface=MaterialInterface, Texture2D=Texture2D,
                MaterialInstanceConstant=MaterialInstanceConstant, MaterialInstanceConstantFactoryNew=lambda: None,
                LinearColor=lambda *c: tuple(c), MaterialEditingLibrary=M,
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(assets=assets, saves=saves, root=tmp_path)


def stage(editor, name, value, file):
    path = editor.root / name; path.mkdir(exist_ok=True)
    (path / file).write_text(json.dumps(value))
    return str(path)


def test_leaf_instance_is_m_foliage_with_its_own_texture(editor):
    editor.assets[forest.FOLIAGE] = MaterialInterface(forest.FOLIAGE)
    editor.assets[f'{forest.TEXTURES}/T_LeafOak'] = Texture2D(f'{forest.TEXTURES}/T_LeafOak')
    context = NS(job_dir=str(editor.root), outputs=[f'{forest.MATERIALS}/MI_LeafOak'], inputs={'parent': 'x', 'texture': 'x'},
                 packages={'parent': [forest.FOLIAGE], 'texture': [f'{forest.TEXTURES}/T_LeafOak']},
                 params={'args': {'action': 'leaf', 'slot': 'LeafOak', 'parent': 'parent', 'texture': 'texture'}, 'settings': []})
    mi = body.run(context)
    assert mi.props['parent'].path == forest.FOLIAGE and mi.props['Tex'].path == f'{forest.TEXTURES}/T_LeafOak'
    assert editor.saves == [f'{forest.MATERIALS}/MI_LeafOak']


def test_impostor_instance_binds_its_own_atlases_and_tint(editor):
    name = 'Tree_Forest_Ginkgo'
    editor.assets[body.MASTER] = Material(body.MASTER)
    for kind in ('colour', 'normal'):
        editor.assets[f'{forest.TEXTURES}/T_{name}_{kind}'] = Texture2D(f'{forest.TEXTURES}/T_{name}_{kind}')
    context = NS(job_dir=str(ROOT), outputs=[f'{forest.MATERIALS}/MI_{name}_Impostor'],
                 inputs={'entry': stage(editor, 'entry', tree(name), name + '.json'), 'master': 'x', 'colour': 'x', 'normal': 'x'},
                 packages={'entry': [], 'master': [body.MASTER], 'colour': [f'{forest.TEXTURES}/T_{name}_colour'],
                           'normal': [f'{forest.TEXTURES}/T_{name}_normal']},
                 params={'args': {'action': 'impostor', 'name': name, 'entry': 'entry', 'master': 'master',
                                  'colour': 'colour', 'normal': 'normal'}, 'settings': []})
    with pytest.raises(ValueError, match='job-local'):
        body.run(context)   # the entry is staged outside this job directory
    context.job_dir = str(editor.root)
    (editor.root / forest.SCRIPTS).mkdir(parents=True)
    (editor.root / forest.SCRIPTS / 'forest_impostor_material.py').write_text("TINTS={'Tree_Forest_Ginkgo':(1.,.85,.5)}\n")
    mi = body.run(context)
    assert mi.props['Tint'] == (1., .85, .5, 1.) and mi.props['NormalTex'].path.endswith('_normal')


def test_species_owner_refuses_an_incomplete_raw_roster(editor):
    name = 'Tree_Tuscan_Oak'
    context = NS(job_dir=str(editor.root), outputs=[f'{forest.ASSETS}/{name}', *(f'{forest.LODS}/{name}_LOD{i}' for i in range(1, 5))],
                 inputs={'entry': stage(editor, 'entry', tree(name), name + '.json')}, packages={'entry': []},
                 params={'args': {'action': 'species', 'name': name, 'entry': 'entry', 'materials': {},
                                  'levels': {'derived_items': {'root': 'r', 'members': [{'piece': name, 'slot': 'd0', 'root': 'r'}]}}}})
    with pytest.raises(ValueError, match='five raw levels'):
        body.run(context)
