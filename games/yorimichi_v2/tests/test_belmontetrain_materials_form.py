"""The per-package material-instance form, its import rows, the donor-path scrub check, the texture report job and what
check.py says about a generated record that has no verified.json. Fake data and stub `unreal` only; no editor runs."""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'unreal' / 'Scripts'))
import check  # noqa: E402
import import_settings as s  # noqa: E402
import records  # noqa: E402

REPORT = ROOT / 'unreal' / 'Scripts' / 'report_textures.py'
TEXTURES = ROOT / 'docs' / 'inventory' / 'belmontetrain-texture-packages.txt'
INTERCHANGE = '/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque_DS'


def write_record(folder: Path, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'asset.toml'
    path.write_text(body)
    return path


def material_body(instances: str, outputs: list, inputs: list) -> str:
    out = ''.join(f'\n[[outputs]]\npackage = "{p}"\n' for p in outputs)
    deps = ', '.join(f'"{i}"' for i in inputs)
    return (f'schema = 1\nid = "material/belmontetrain/fake"\nkind = "material-instance"\nauthority = "generated"\n'
            f'owner = "shared/belmontetrain/fake"\ninput_dependencies = [{deps}]\n\n[recipe]\n'
            f'importer = "material-instance"\nversion = 2\n\n[recipe.settings]\n{instances}\n' + out)


ROW_A = ('[[recipe.settings.instances]]\npackage = "/Game/F/M_A"\nparent = "' + INTERCHANGE + '"\n'
         'textures = {BaseColorTexture = "/Game/F/T_A"}\nscalars = {RoughnessFactor = 0.25}\n'
         'vectors = {BaseColorFactor = [1.0, 1.0, 1.0, 1.0]}\n')
ROW_B = ('[[recipe.settings.instances]]\npackage = "/Game/F/M_B"\nparent = "' + INTERCHANGE + '"\n')


def test_the_instances_form_must_name_exactly_the_outputs(tmp_path):
    ok = write_record(tmp_path / 'ok', material_body(ROW_A + ROW_B, ['/Game/F/M_A', '/Game/F/M_B'], ['texture/x-a']))
    asset = records.load_asset(ok)
    assert [r['package'] for r in records.material_rows(asset)] == ['/Game/F/M_A', '/Game/F/M_B']
    with pytest.raises(records.RecordError, match='instances name'):
        records.load_asset(write_record(tmp_path / 'short', material_body(ROW_A, ['/Game/F/M_A', '/Game/F/M_B'], ['texture/x-a'])))
    with pytest.raises(records.RecordError, match='named once'):
        records.load_asset(write_record(tmp_path / 'twice', material_body(ROW_A + ROW_A, ['/Game/F/M_A'], ['texture/x-a'])))


def test_an_interchange_default_parent_needs_no_record_and_a_game_parent_does(tmp_path):
    asset = records.load_asset(write_record(tmp_path / 'a', material_body(ROW_A, ['/Game/F/M_A'], ['texture/x-a'])))
    outputs_of = {'texture/x-a': {'/Game/F/T_A'}}
    assert records.material_inputs(asset) == ['/Game/F/T_A']
    assert records.material_input_problems(asset, outputs_of) == []
    game_parent = ROW_A.replace(INTERCHANGE, '/Game/F/M_Parent')
    asset = records.load_asset(write_record(tmp_path / 'b', material_body(game_parent, ['/Game/F/M_A'], ['texture/x-a'])))
    assert records.material_input_problems(asset, outputs_of) == ['/Game/F/M_Parent is read by material/belmontetrain/fake '
                                                                  'but no input dependency owns it']


def test_a_single_form_record_still_loads_and_needs_its_owners(tmp_path):
    single = ('[recipe.settings]\nparent = "/Game/Japan/Materials/M_Foliage"\n'
              'textures = {Tex = "/Game/Japan/Textures/T_leaf_amber"}\n')
    body = (f'schema = 1\nid = "material/japan/leaf-fake"\nkind = "material-instance"\nauthority = "generated"\n'
            f'owner = "shared/japan/leaf-fake"\ninput_dependencies = ["adopted/japan/materials/foliage"]\n\n[recipe]\n'
            f'importer = "material-instance"\nversion = 2\n\n{single}\n[[outputs]]\npackage = "/Game/Japan/Materials/MI_LeafAmber"\n')
    asset = records.load_asset(write_record(tmp_path / 'leaf', body))
    assert [r['package'] for r in records.material_rows(asset)] == ['/Game/Japan/Materials/MI_LeafAmber']
    assert set(records.material_inputs(asset)) == {'/Game/Japan/Materials/M_Foliage', '/Game/Japan/Textures/T_leaf_amber'}


def test_the_import_rows_follow_the_form_and_refuse_a_mismatch():
    rows = s.material_instances({'instances': [
        {'package': '/Game/A', 'parent': INTERCHANGE, 'vectors': {'BaseColorFactor': [1, 1, 1, 1]}},
        {'package': '/Game/B', 'parent': INTERCHANGE, 'scalars': {'RoughnessFactor': 0.5}}]}, ['/Game/A', '/Game/B'])
    assert [r['package'] for r in rows] == ['/Game/A', '/Game/B']
    assert rows[1]['scalars'] == {'RoughnessFactor': 0.5} and rows[1]['textures'] == {}
    single = s.material_instances({'parent': INTERCHANGE, 'textures': {'Tex': '/Game/T'}}, ['/Game/A', '/Game/B'])
    assert [r['textures'] for r in single] == [{'Tex': '/Game/T'}, {'Tex': '/Game/T'}]
    with pytest.raises(s.SettingError, match='missing'):
        s.material_instances({'instances': [{'package': '/Game/A', 'parent': INTERCHANGE}]}, ['/Game/A', '/Game/B'])
    with pytest.raises(s.SettingError, match='extra'):
        s.material_instances({'instances': [{'package': '/Game/A', 'parent': INTERCHANGE},
                                            {'package': '/Game/Z', 'parent': INTERCHANGE}]}, ['/Game/A'])


def test_a_donor_path_left_in_import_data_is_named_and_a_blank_one_is_not():
    assert s.donor_free(['', '/work/checkout'], '/work/checkout') == []
    assert s.donor_free(['', '/donor-build/belmonte-train/SM_BT_Tender_LOD0.glb'], '/work/checkout') == [
        '/donor-build/belmonte-train/SM_BT_Tender_LOD0.glb']


def _report_module(monkeypatch):
    stub = types.ModuleType('unreal')
    stub.EditorAssetLibrary = stub
    stub.Texture2D = type('Texture2D', (), {})
    stub.log = lambda message: None
    monkeypatch.setitem(sys.modules, 'unreal', stub)
    spec = importlib.util.spec_from_file_location('report_textures_under_test', REPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTexture(types.SimpleNamespace):
    def get_editor_property(self, name):
        return getattr(self, name)


def test_the_texture_row_is_the_five_settings_with_bare_enum_names(monkeypatch):
    report = _report_module(monkeypatch)
    texture = FakeTexture(srgb=True, compression_settings='TextureCompressionSettings.TC_DEFAULT',
                          lod_group='TextureGroup.TEXTUREGROUP_World', address_x='TextureAddress.TA_WRAP',
                          address_y='TextureAddress.TA_WRAP')
    assert report.row(texture) == {'srgb': True, 'compression': 'TC_DEFAULT', 'lod_group': 'TEXTUREGROUP_World',
                                   'address_x': 'TA_WRAP', 'address_y': 'TA_WRAP'}
    assert report.check_coverage({'/T/a': {'srgb': True}, '/T/b': {'error': 'x'}}, ['/T/a', '/T/b', '/T/c']) == (
        ['/T/c'], ['/T/b'])


def test_the_texture_report_is_refused_inside_the_game_tree_even_through_a_link(monkeypatch, tmp_path):
    report = _report_module(monkeypatch)
    game = tmp_path / 'game'
    (game / 'unreal' / 'Content').mkdir(parents=True)
    link = tmp_path / 'link'
    os.symlink(game / 'unreal', link)
    with pytest.raises(ValueError, match='inside'):
        report.report_target(str(link / 'out.json'), game=str(game))
    with pytest.raises(ValueError, match='inside'):
        report.report_target(str(game / 'out.json'), game=str(game))
    assert report.report_target(str(tmp_path / 'reports' / 'out.json'), game=str(game)).endswith('out.json')


def test_the_texture_list_is_the_138_texture_packages_of_the_seven_records():
    listed = TEXTURES.read_text().split()
    assert len(listed) == len(set(listed)) == 138
    assert all(p.startswith('/Game/BelmonteTrain/Source/SM_BT_') and p.rsplit('/', 1)[1].startswith('T_BT_') for p in listed)
    units = ['baggage-van', 'brake-van', 'first-class', 'locomotive', 'restaurant', 'second-class', 'tender']
    recorded = [o.package for u in units for o in
                records.load_asset(ROOT / 'assets' / 'adopted' / 'belmontetrain' / u / 'asset.toml').outputs
                if o.package.rsplit('/', 1)[1].startswith('T_BT_')]
    assert sorted(listed) == sorted(recorded)


def test_check_reports_a_generated_record_without_verified_json_as_fatal(tmp_path):
    """The behaviour the claim must plan for: check.py's RECORD_MISSING (fatal) and UNOWNED on its package file, until a
    verified import writes the record's verified.json. A move without an import leaves the tree failing check."""
    game = tmp_path / 'game'
    (game / 'unreal' / 'Content' / 'BT' / 'Src').mkdir(parents=True)
    (game / 'unreal' / 'Content' / 'BT' / 'Src' / 'T_X.uasset').write_bytes(b'package bytes')
    src = game / 'assets' / 'texture' / 'belmontetrain' / 'x' / 'src'
    src.mkdir(parents=True)
    import hashlib
    data = b'\x89PNG donor'
    (src / 'T_X.png').write_bytes(data)
    write_record(game / 'assets' / 'texture' / 'belmontetrain' / 'x', (
        'schema = 1\nid = "texture/belmontetrain/x"\nkind = "texture"\nauthority = "generated"\n'
        'owner = "shared/belmontetrain/x"\n\n[[sources]]\npath = "src/T_X.png"\n'
        f'sha256 = "{hashlib.sha256(data).hexdigest()}"\n\n[recipe]\nimporter = "texture"\nversion = 1\n\n'
        '[recipe.settings]\nsrgb = true\n\n[[outputs]]\npackage = "/Game/BT/Src/T_X"\n'))
    problems, _ = check.check(game, full=True, write_index=False)
    codes = {p.code: p for p in problems}
    assert 'RECORD_MISSING' in codes and codes['RECORD_MISSING'].subject == 'texture/belmontetrain/x'
    assert 'import/run.py' in codes['RECORD_MISSING'].action
    assert any(p.code == 'UNOWNED' and p.subject.endswith('T_X.uasset') for p in problems)


def test_a_switch_must_be_a_bhas_boolean(tmp_path):
    ok = ROW_A.replace('scalars', 'switches = {bHasBaseColorTexture = true}\nscalars')
    asset = records.load_asset(write_record(tmp_path / 'sw', material_body(ok, ['/Game/F/M_A'], ['texture/x-a'])))
    assert records.material_rows(asset)[0]['switches'] == {'bHasBaseColorTexture': True}
    for bad in ('switches = {Roughness = true}', 'switches = {bHasBaseColorTexture = 1}'):
        body = material_body(ROW_A.replace('scalars', bad + '\nscalars'), ['/Game/F/M_A'], ['texture/x-a'])
        with pytest.raises(records.RecordError, match='switch'):
            records.load_asset(write_record(tmp_path / ('bad' + str(abs(hash(bad)))), body))


def test_the_import_rows_carry_the_switches_and_a_texture_may_keep_only_a_relative_source():
    rows = s.material_instances({'instances': [{'package': '/G/A', 'parent': INTERCHANGE,
                                                'switches': {'bHasBaseColorTexture': True}}]}, ['/G/A'])
    assert rows[0]['switches'] == {'bHasBaseColorTexture': True}
    assert s.donor_named(['games/yorimichi_v2/unreal/Content/x.glb', '', '/work/checkout'], '/work/checkout') == []
    assert s.donor_named(['/donor-build/x.glb'], '/work/checkout') == ['/donor-build/x.glb']


REPORT_MATERIALS = ROOT / 'unreal' / 'Scripts' / 'report_materials.py'


def _materials_module(monkeypatch):
    """report_materials.py under a stub: a material exposes its switch values (switch_values) and the names it has (names);
    a name without a value raises, as an unreadable switch does in the editor."""
    stub = types.ModuleType('unreal')
    stub.EditorAssetLibrary = stub.MaterialEditingLibrary = stub
    stub.MaterialInstance = type('MaterialInstance', (), {})
    stub.MaterialInstanceConstant = type('MaterialInstanceConstant', (stub.MaterialInstance,), {})
    stub.log = lambda message: None

    def value(material, name):
        if name in material.switch_values:
            return material.switch_values[name]
        raise RuntimeError(f'no value for {name}')
    stub.get_material_instance_static_switch_parameter_value = value
    stub.get_material_default_static_switch_parameter_value = value
    stub.get_static_switch_parameter_names = lambda material: list(getattr(material, 'names', material.switch_values))
    monkeypatch.setitem(sys.modules, 'unreal', stub)
    spec = importlib.util.spec_from_file_location('report_materials_switch_test', REPORT_MATERIALS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, stub


def _material(cls, switch_values, names=None):
    material = cls()
    material.switch_values = dict(switch_values)
    if names is not None:
        material.names = list(names)
    return material


def test_the_switch_report_states_the_instance_value_the_parent_value_and_the_effective_one(monkeypatch):
    report, stub = _materials_module(monkeypatch)
    inst = _material(stub.MaterialInstanceConstant, {'bHasBaseColorTexture': True, 'bHasNormalTexture': False,
                                                     'bHasEmissiveTexture': False})
    parent = _material(stub.MaterialInstanceConstant, {'bHasBaseColorTexture': False, 'bHasNormalTexture': False,
                                                       'bHasEmissiveTexture': False})
    out = report._switches(inst, parent)
    assert set(out) == {'bHasBaseColorTexture', 'bHasNormalTexture', 'bHasEmissiveTexture'}
    assert out['bHasBaseColorTexture'] == {'override': None, 'value': True, 'parent': False, 'effective': True}
    assert out['bHasNormalTexture'] == {'override': None, 'value': False, 'parent': False, 'effective': False}


def test_a_switch_the_editor_cannot_read_is_null_not_a_guess(monkeypatch):
    report, stub = _materials_module(monkeypatch)
    inst = _material(stub.MaterialInstanceConstant, {}, names=['bHasIridescence'])
    parent = _material(stub.MaterialInstanceConstant, {})
    row = report._switches(inst, parent)
    assert row['bHasIridescence']['effective'] is None and row['bHasIridescence']['value'] is None


def test_the_material_list_is_the_321_m_bt_packages_of_the_seven_records():
    listed = (ROOT / 'docs' / 'inventory' / 'belmontetrain-material-packages.txt').read_text().split()
    assert len(listed) == len(set(listed)) == 321
    assert all(p.rsplit('/', 1)[1].startswith('M_BT_') for p in listed)
    units = ['baggage-van', 'brake-van', 'first-class', 'locomotive', 'restaurant', 'second-class', 'tender']
    recorded = [o.package for u in units for o in
                records.load_asset(ROOT / 'assets' / 'adopted' / 'belmontetrain' / u / 'asset.toml').outputs
                if o.package.rsplit('/', 1)[1].startswith('M_BT_')]
    assert sorted(listed) == sorted(recorded)


def test_a_version_1_material_recipe_is_refused_in_both_forms(tmp_path):
    """Version 2 is the importer that clears earlier overrides and refuses strays; a version 1 record is not imported by it."""
    single = ('[recipe.settings]\nparent = "/Game/Japan/Materials/M_Foliage"\n'
              'textures = {Tex = "/Game/Japan/Textures/T_leaf_amber"}\n')
    old_form = material_body(ROW_A, ['/Game/F/M_A'], ['texture/x-a']).replace('version = 2', 'version = 1')
    with pytest.raises(records.RecordError, match='version 2'):
        records.load_asset(write_record(tmp_path / 'v1-instances', old_form))
    body = (f'schema = 1\nid = "material/japan/leaf-old"\nkind = "material-instance"\nauthority = "generated"\n'
            f'owner = "shared/japan/leaf-old"\ninput_dependencies = ["adopted/japan/materials/foliage"]\n\n[recipe]\n'
            f'importer = "material-instance"\nversion = 1\n\n{single}\n[[outputs]]\npackage = "/Game/Japan/Materials/MI_LeafAmber"\n')
    with pytest.raises(records.RecordError, match='version 2'):
        records.load_asset(write_record(tmp_path / 'v1-single', body))
