"""Character generated membership through FileSet templates: actual rows, projection bodies, derived rosters."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'tests')]
import v2_character_units as characters  # noqa: E402
import v2_character_templates as templates  # noqa: E402
from test_v2_character_units import body, editor, mesh_case, recipe  # noqa: E402,F401

spec = importlib.util.spec_from_file_location('character_members_v2', ROOT / templates.BODY)
members = importlib.util.module_from_spec(spec); spec.loader.exec_module(members)
MOVERS = characters._definition(ROOT).movers()
NATIVES = {'compression': {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': characters.COMPRESSION},
           'see_through': {'unit': 'unreal.material.MPC_SeeThrough', 'item': 'asset', 'package': '/Game/SeeThrough/MPC_SeeThrough'}}


@pytest.fixture(scope='module')
def rows():
    steps = [s for c in MOVERS for s in (recipe.mover_export_steps(c, ROOT / 'build/yorimichi')[:1]
                                         + recipe.mover_import_steps(c, ROOT / 'build/yorimichi')[:1])]
    names = {s.name for s in steps}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = [n for n in step.after if n in names]; step.reads = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return templates.character_templates(rows, checkout=ROOT, natives=NATIVES)


def test_committed_groups_follow_the_export_rates_and_hooks():
    found = {c.id: (templates.rates(c), templates.cloth(c)) for c in MOVERS}
    assert found == {'cairo': ([60], False), 'modori': ([], True), 'nox': ([], False), 'paul': ([], False),
                     'sword-trainer': ([30], False)}


def test_projectors_read_the_whole_actual_export_product(declared):
    units = {u['id']: u for u in declared['units']}
    assert set(declared['groups']) == {f'characters.{k}.members.{kind}' for k, kinds in {
        'cairo': ('materials', 'textures', 'clips_60'), 'modori': ('materials', 'textures'), 'nox': ('materials', 'textures'),
        'paul': ('materials', 'textures'), 'sword_trainer': ('materials', 'textures', 'clips_30')}.items() for kind in kinds}
    projector = units['characters.cairo.members.clips_60']
    assert projector['inputs'][0]['source'] == {'kind': 'item', 'unit': 'characters.cairo', 'item': 'product0'}
    assert projector['params']['recipe']['paths'] == {
        'build/yorimichi/cairo/export.json': 'inputs/export/products/0-0.tree.tar',
        'build/yorimichi/cairo/fbx': 'inputs/export/products/0-1.tree.tar',
        'build/yorimichi/cairo/textures': 'inputs/export/products/0-2.tree.tar'}
    assert projector['params']['recipe']['commands'][0]['call']['defaults'][4:] == ['clips_60', 'Cairo', False, [60]]
    assert projector['params']['recipe']['file_group']['extensions'] == ['.fbx']
    assert projector['output_groups'][0]['encoding'] == 'file_set'
    raw = units['unreal.character.cairo.raw']
    assert raw['params']['source_member'] == 'Cairo.fbx'
    assert raw['params']['input_roots'] == {'source': {'archive_member': 'products/0-1.tree.tar', 'name': 'fbx'}}


def test_templates_and_fixed_units_bind_actual_derived_items(declared):
    keys = {(t['producer'], t['group'], t['unit_prefix']): t for t in declared['templates']}
    def check(token):
        for source in token['derived_items']['templates']:
            template = keys[(source['producer'], source['group'], source['unit_prefix'])]
            follower = template['followers'][source['follower']]['unit']
            assert source['item'] in {o['id'] for o in follower['outputs']}
    for k, token in declared['tokens'].items():
        for value in token.values():
            check(value)
    clip = keys[('characters.cairo.members.clips_60', 'members', 'unreal.character.cairo.clips_60')]
    raw, finish = (f['unit'] for f in clip['followers'])
    assert raw['params']['fbx']['custom_sample_rate'] == 60 and raw['params']['fbx']['delete_existing_morph_target_curves']
    assert raw['params']['input_roots'] == {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}
    assert finish['inputs'][0]['source'] == {'kind': 'item', 'unit': '$previous', 'item': 'raw_animation'}
    assert finish['params']['args']['closure']['materials'] == declared['tokens']['cairo']['materials']
    material = keys[('characters.cairo.members.materials', 'members', 'unreal.character.cairo.materials')]['followers'][0]['unit']
    assert material['params']['args']['textures'] == declared['tokens']['cairo']['textures']
    assert material['outputs'][0]['logical_path'] == '/Game/Cairo/$piece'
    units = {u['id']: u for u in declared['units']}
    assert units['unreal.character.cairo.mesh']['params']['args']['materials'] == declared['tokens']['cairo']['materials']
    assert units['unreal.character.cairo.base']['params']['args']['clips'] == declared['tokens']['cairo']['clips']
    assert units['unreal.character.paul.base']['params']['args']['clips'] == {}
    assert 'PA_Modori_Cloth' in {o['logical_path'].rsplit('/', 1)[1] for o in units['unreal.character.modori.mesh']['outputs']}
    assert not any('Cloth' in o['logical_path'] for o in units['unreal.character.nox.mesh']['outputs'])
    assert declared['runtime_refusals'][0]['unit_prefix'] == 'unreal.character.cairo.clips_60'


def test_see_through_runs_inside_each_matching_material_owner(declared):
    keys = {t['unit_prefix']: t for t in declared['templates']}
    cairo = keys['unreal.character.cairo.materials']['followers'][0]['unit']
    assert cairo['params']['args']['see_through'] == {'prefixes': ['M_Cairo'], 'collection': 'see_through'}
    assert cairo['inputs'][-1]['source'] == {'kind': 'item', 'unit': 'unreal.material.MPC_SeeThrough', 'item': 'asset'}
    assert 'games/yorimichi/unreal/Scripts/see_through.py' in cairo['code']
    nox = keys['unreal.character.nox.materials']['followers'][0]['unit']
    assert 'see_through' not in nox['params']['args'] and len(nox['inputs']) == 1


@pytest.mark.parametrize('damage', ['product', 'compression', 'producer', 'see_through'])
def test_declaration_drift_refuses(rows, damage):
    rows, natives = deepcopy(rows), deepcopy(NATIVES)
    found = {r['id']: r for r in rows}
    if damage == 'product':
        found['characters.nox']['products'][0]['paths'].pop()
    elif damage == 'compression':
        natives['compression']['package'] = '/Game/Other'
    elif damage == 'see_through':
        natives.pop('see_through')
    else:
        found['characters.paul']['commands'][0]['script'] = {'path': 'games/yorimichi/other.py'}
    with pytest.raises(ValueError):
        templates.character_templates(rows, checkout=ROOT, natives=natives)


# ---- projection bodies ----------------------------------------------------------------------------------------------

def export_tree(tmp_path, *, cloth=None, rate=60):
    root = tmp_path / 'export'; (root / 'fbx').mkdir(parents=True); (root / 'textures').mkdir()
    config = {'materials': {'M_Body': {'texture': 'textures/T_Body.png', 'two_sided': False},
                            'M_Coat': {'texture': 'textures/T_Coat.jpg', 'two_sided': True},
                            'M_Eyes': {'texture': None, 'two_sided': False}},
              'clips': {'Wave': {'sample_rate': rate, 'duration': 1.}}, 'cloth': cloth}
    (root / 'export.json').write_text(json.dumps(config))
    for name in ('Hero.fbx', 'A_Wave.fbx'):
        (root / 'fbx' / name).write_bytes(name.encode())
    for name in ('T_Body.png', 'T_Coat.jpg', 'T_Unused.png'):
        (root / 'textures' / name).write_bytes(name.encode())
    return root


def project(root, tmp_path, kind, **kw):
    output = tmp_path / 'out' / kind
    members.project(root / 'export.json', root / 'fbx', root / 'textures', output, kind,
                    kw.get('name', 'Hero'), kw.get('cloth', False), kw.get('rates', (60,)))
    return output


def test_projection_emits_actual_members_as_file_sets(tmp_path):
    root = export_tree(tmp_path)
    found = {}
    for kind, extensions in (('materials', ['.json']), ('textures', ['.jpg', '.png']), ('clips_60', ['.fbx'])):
        output = project(root, tmp_path, kind)
        manifest = emit(output, tmp_path / 'files' / kind, parent='Hero_' + kind, extensions=extensions)
        found[kind] = sorted((p['name'], p['payload']) for p in manifest['pieces'])
    assert found == {'materials': [('M_Body', 'M_Body.json'), ('M_Coat', 'M_Coat.json'), ('M_Eyes', 'M_Eyes.json')],
                     'textures': [('T_Body', 'T_Body.png'), ('T_Coat', 'T_Coat.jpg')], 'clips_60': [('Wave', 'Wave.fbx')]}
    assert (tmp_path / 'files/clips_60/Wave.fbx').read_bytes() == b'A_Wave.fbx'
    assert json.loads((tmp_path / 'out/materials/M_Coat.json').read_text()) == {'texture': 'textures/T_Coat.jpg', 'two_sided': True}


@pytest.mark.parametrize('damage', ['cloth', 'rate', 'clip', 'texture', 'body', 'empty'])
def test_projection_refuses_an_export_that_differs(tmp_path, damage):
    root = export_tree(tmp_path, cloth={'mesh': 'Coat'} if damage == 'cloth' else None, rate=240 if damage == 'rate' else 60)
    kw = {}
    if damage == 'clip':
        (root / 'fbx/A_Wave.fbx').unlink()
    elif damage == 'texture':
        (root / 'textures/T_Coat.jpg').unlink()
    elif damage == 'body':
        kw['name'] = 'Other'
    elif damage == 'empty':
        kw['rates'] = (60, 30)
    with pytest.raises(ValueError):
        project(root, tmp_path, 'materials', **kw)
    assert not (tmp_path / 'out').exists()


def test_select_packages_one_member_with_its_export_receipt(tmp_path):
    selected = tmp_path / 'selected'; selected.mkdir(); (selected / 'T_Coat.jpg').write_bytes(b'coat')
    members.select(selected, tmp_path / 'member', 'T_Coat')
    receipt = json.loads((tmp_path / 'member/export.json').read_text())
    assert receipt == {'primary': 'T_Coat.jpg', 'sha256': hashlib.sha256(b'coat').hexdigest()}
    with pytest.raises(ValueError):
        members.select(selected, tmp_path / 'other', 'T_Body')


# ---- derived rosters in the bodies ----------------------------------------------------------------------------------

def derived(**slots):
    return {'derived_items': {'root': 'build/v2-derived/x', 'members': [
        {'piece': piece, 'slot': slot, 'root': 'build/v2-derived/x/' + piece} for piece, slot in slots.items()]}}


def test_roster_reads_resolved_derived_items_and_refuses_unresolved():
    assert body._roster(derived(M_Body='derived_0')) == {'M_Body': 'derived_0'}
    assert body._roster({'M_Body': 'material_M_Body'}) == {'M_Body': 'material_M_Body'}
    with pytest.raises(ValueError):
        body._roster({'derived_items': {'root': 'x', 'templates': []}})


def test_mesh_finish_binds_derived_materials(editor):
    context = mesh_case(editor, physics=False)
    context.params['args']['materials'] = derived(M_Body='material_M_Body')
    mesh = body.run(context)
    assert mesh.materials[0].material_interface.path == '/Game/Paul/M_Body'
    context = mesh_case(editor, physics=False)
    context.params['args']['materials'] = derived()
    with pytest.raises(ValueError):
        body.run(context)


class Fake:
    def __init__(self, **values): self.__dict__.update(values)
    def __getattr__(self, name): return name


def material_job(tmp_path, monkeypatch, name, calls):
    from types import SimpleNamespace as NS
    from test_v2_character_units import Asset
    export = tmp_path / 'inputs/export'; export.mkdir(parents=True)
    (export / 'export.json').write_text(json.dumps({'materials': {name: {
        'texture': None, 'two_sided': False, 'base_color': [1, 1, 1, 1], 'roughness': 1, 'metallic': 0, 'specular': 0}}}))
    scripts = tmp_path / body.SCRIPTS; scripts.mkdir(parents=True)
    (scripts / 'see_through.py').write_text(
        'import unreal\n'
        'def collection(): unreal.calls.append("collection")\n'
        'def character(m): unreal.calls.append("character"); return True\n'
        'def save(m): unreal.calls.append("cut.save"); return True\n')
    assets = {}
    def create(asset, folder, cls, factory):
        assets[folder + '/' + asset] = Asset(folder + '/' + asset); return assets[folder + '/' + asset]
    library = Fake(delete_all_material_expressions=lambda m: None, create_material_expression=lambda m, cls: Asset('/Game/n'),
                   connect_material_property=lambda *a: True, connect_material_expressions=lambda *a: True,
                   recompile_material=lambda m: calls.append('recompile'))
    unreal = Fake(calls=calls, Material=Asset, MaterialFactoryNew=lambda: None, MaterialEditingLibrary=library,
                  LinearColor=lambda *v: v, BlendMode=Fake(), MaterialProperty=Fake(),
                  AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                  EditorAssetLibrary=NS(does_asset_exist=lambda p: p in assets,
                                        save_loaded_asset=lambda a, d=True: calls.append('save') or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(job_dir=str(tmp_path), inputs={'export': str(export), 'see_through': 'x'},
              packages={'see_through': ['/Game/SeeThrough/MPC_SeeThrough']}, outputs=['/Game/Cairo/' + name],
              params={'args': {'action': 'material', 'name': name, 'dest': '/Game/Cairo', 'morphs': False, 'export': 'export',
                               'textures': derived(), 'see_through': {'prefixes': ['M_Cairo'], 'collection': 'see_through'}},
                      'settings': []})


@pytest.mark.parametrize('name,expected', [('M_Cairo_Skin', ['recompile', 'collection', 'character', 'cut.save']),
                                           ('M_Bokken', ['recompile', 'save'])])
def test_material_owner_applies_the_original_see_through_patch(tmp_path, monkeypatch, name, expected):
    calls = []
    body.run(material_job(tmp_path, monkeypatch, name, calls))
    assert calls == expected


def test_see_through_refuses_another_collection(tmp_path, monkeypatch):
    context = material_job(tmp_path, monkeypatch, 'M_Cairo_Skin', [])
    context.packages['see_through'] = ['/Game/Other/MPC']
    with pytest.raises(ValueError):
        body.run(context)
