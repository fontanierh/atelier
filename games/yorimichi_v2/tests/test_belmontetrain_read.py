"""The Belmonte train native reads, compacted to docs/inventory/belmontetrain-read.json, and the planner's agreement with
them. The evidence is what the two read-only editor runs reported, kept to what the records assert; the disagreement
check compares the plan with that evidence. Fake rows prove the check fails on the defects it is meant to catch, and
the donor-backed test runs only with the donor build (YV2_DONOR_BUILD)."""
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import belmontetrain_materials as m  # noqa: E402

EVIDENCE = ROOT / 'docs' / 'inventory' / 'belmontetrain-read.json'
INTERCHANGE = '/InterchangeAssets/gltf/MaterialInstances/MI_Default_Opaque_DS'
CLEAR = '/InterchangeAssets/gltf/MaterialInstances/MI_ClearCoat_Opaque_DS'


def inst(package, parent=INTERCHANGE, textures=None, clearcoat=None, emissive=(0.0, 0.0, 0.0), strength=1.0):
    return {'package': package, 'parent': parent, 'base': [1, 1, 1, 1], 'metallic': 1.0, 'roughness': 0.5,
            'clearcoat': clearcoat, 'emissive': list(emissive), 'emissive_strength': strength, 'two_sided': True,
            'textures': textures or {}}


def plan_with(instances: list, textures: list = ()) -> m.Plan:
    rec = m.MaterialRec('material/belmontetrain/fake-lod0', 'fake', 0, 'shared/belmontetrain/fake', 'SM.glb',
                        instances, sorted({t.id for t in textures}), [i['package'] for i in instances])
    return m.Plan(list(textures), [rec], [], Path('/nowhere'), {})


def read_row(parent: str, states: dict, emissive=(0.0, 0.0, 0.0, 1.0), strength=1.0) -> dict:
    """A read row shaped like report_materials.py's: each switch with its effective and parent values."""
    return {'parent': parent + '.' + parent.rsplit('/', 1)[1],
            'effective': {'scalar': {'RoughnessFactor': 0.5, 'MetallicFactor': 1.0, 'EmissiveStrength': strength},
                          'vector': {'BaseColorFactor': [1, 1, 1, 1], 'EmissiveFactor': list(emissive)},
                          'texture': {'BaseColorTexture': None}},
            'overrides': {},
            'switches': {name: {'effective': eff, 'parent': par, 'override': None, 'value': eff}
                         for name, (eff, par) in states.items()}}


def texture_read() -> dict:
    return {'srgb': True, 'compression': 'TC_DEFAULT', 'lod_group': 'TEXTUREGROUP_WORLD', 'address_x': 'TA_WRAP',
            'address_y': 'TA_WRAP'}


def test_the_plan_states_no_switch_its_parent_lacks():
    """The clear-coat parent has bHasAnisotropyTexture and bHasClearCoatTexture, not ...AndOrRotation; the other parents the
    reverse. bHasSpecularColorTexture is in neither."""
    clear = m.instance_row(inst('/G/M_C', parent=CLEAR, clearcoat=0.5))['switches']
    plain = m.instance_row(inst('/G/M_P'))['switches']
    assert 'bHasAnisotropyTextureAndOrRotation' not in clear and clear['bHasClearCoatTexture'] is False
    assert plain['bHasAnisotropyTextureAndOrRotation'] is False and 'bHasClearCoatTexture' not in plain
    assert 'bHasSpecularColorTexture' not in clear and 'bHasSpecularColorTexture' not in plain


def test_a_stated_switch_the_editor_does_not_have_is_disagreed_with(monkeypatch):
    real = m.instance_row
    monkeypatch.setattr(m, 'instance_row', lambda i: dict(real(i), switches={**real(i)['switches'],
                                                                             'bHasSpecularColorTexture': False}))
    plan = plan_with([inst('/G/M_A')])
    read = {'/G/M_A': read_row(INTERCHANGE, {'bHasBaseColorTexture': (False, True)})}
    assert any('bHasSpecularColorTexture is not read' in d for d in m.disagreements(plan, m.evidence(plan, read, {})))


def test_an_unstated_switch_that_differs_from_its_parent_is_disagreed_with(monkeypatch):
    real = m.instance_row
    monkeypatch.setattr(m, 'instance_row', lambda i: dict(real(i), switches={k: v for k, v in real(i)['switches'].items()
                                                                             if k != 'bHasNormalTexture'}))
    plan = plan_with([inst('/G/M_B')])
    read = {'/G/M_B': read_row(INTERCHANGE, {'bHasNormalTexture': (True, False), 'bHasBaseColorTexture': (False, True)})}
    out = m.disagreements(plan, m.evidence(plan, read, {}))
    assert any('bHasNormalTexture differs from its parent and the row does not state it' in d for d in out)


def test_a_stated_switch_with_the_wrong_effective_value_is_disagreed_with():
    plan = plan_with([inst('/G/M_W')])
    read = {'/G/M_W': read_row(INTERCHANGE, {'bHasBaseColorTexture': (True, True)})}   # the row states False
    assert any('bHasBaseColorTexture reads True not False' in d for d in m.disagreements(plan, m.evidence(plan, read, {})))


def test_an_emissive_alpha_the_read_does_not_confirm_is_disagreed_with():
    plan = plan_with([inst('/G/M_E', emissive=(1.0, 0.93, 0.78), strength=2.0)])
    assert m.instance_row(inst('/G/M_E', emissive=(1.0, 0.93, 0.78), strength=2.0))['vectors']['EmissiveFactor'] == [
        1.0, 0.93, 0.78, 1.0]
    read = {'/G/M_E': read_row(INTERCHANGE, {'bHasBaseColorTexture': (False, False)},
                               emissive=(1.0, 0.93, 0.78, 0.0), strength=2.0)}
    assert any('EmissiveFactor' in d for d in m.disagreements(plan, m.evidence(plan, read, {})))


def test_a_parent_the_read_does_not_confirm_is_disagreed_with():
    plan = plan_with([inst('/G/M_P', parent=INTERCHANGE)])
    read = {'/G/M_P': read_row('/InterchangeAssets/gltf/MaterialInstances/MI_Default_Blend_DS', {})}
    assert any('parent' in d for d in m.disagreements(plan, m.evidence(plan, read, {})))


def test_the_read_enum_tail_is_dropped():
    assert m._enum('TC_DEFAULT: 0>') == 'TC_DEFAULT' and m._enum('TA_WRAP') == 'TA_WRAP'


def _texture_module(monkeypatch):
    stub = types.ModuleType('unreal')
    stub.EditorAssetLibrary = stub
    stub.Texture2D = type('Texture2D', (), {})
    stub.log = lambda message: None
    monkeypatch.setitem(sys.modules, 'unreal', stub)
    spec = importlib.util.spec_from_file_location('report_textures_read_test', ROOT / 'unreal' / 'Scripts' / 'report_textures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_texture_report_strips_the_editor_index_from_an_enum(monkeypatch):
    report = _texture_module(monkeypatch)
    assert report.enum_name('<TextureCompressionSettings.TC_DEFAULT: 0>') == 'TC_DEFAULT'
    assert report.enum_name('TextureAddress.TA_WRAP') == 'TA_WRAP'


def test_a_texture_setting_that_differs_from_the_plan_is_disagreed_with(tmp_path):
    texture = m.TextureRec('texture/belmontetrain/fake-lod0-t', 'fake', 0, '/Game/G/T_T', 'T_T', tmp_path / 'T.png',
                           'a' * 64, True, 'TC_DEFAULT', ['base'])
    plan = plan_with([], [texture])
    assert m.disagreements(plan, m.evidence(plan, {}, {'/Game/G/T_T': texture_read()})) == []
    bad = {'/Game/G/T_T': dict(texture_read(), srgb=False)}
    assert any('srgb' in d for d in m.disagreements(plan, m.evidence(plan, {}, bad)))


def test_the_plan_states_only_the_switches_the_evidence_can_confirm_on_fake_rows():
    """A donor-free check: every switch a planned row states exists in the parent it names, by the parent kind."""
    for row in (m.instance_row(inst('/G/a')), m.instance_row(inst('/G/b', parent=CLEAR, clearcoat=1.0))):
        assert 'bHasSpecularColorTexture' not in row['switches']
        assert set(row['switches']) <= {'bHasBaseColorTexture', 'bHasNormalTexture', 'bHasEmissiveTexture',
                                        'bHasOcclusionTexture', 'bHasMetallicRoughnessTexture', 'bHasSpecularTexture',
                                        'bHasIridescence', 'bHasAnisotropyTextureAndOrRotation', 'bHasClearCoatTexture'}


@pytest.mark.skipif(not os.environ.get('YV2_DONOR_BUILD'), reason='needs the donor build (YV2_DONOR_BUILD) to plan')
def test_the_plan_agrees_with_the_committed_read_evidence():
    donor = Path(os.environ['YV2_DONOR_BUILD']).expanduser() / 'belmonte-train'
    plan = m.plan(ROOT, donor)
    evidence = json.loads(EVIDENCE.read_text())
    assert m.disagreements(plan, evidence) == []
    assert len(evidence['materials']) == 321 and len(evidence['textures']) == 138


def test_the_evidence_keeps_only_what_the_records_assert():
    evidence = json.loads(EVIDENCE.read_text())
    for package, row in evidence['materials'].items():
        assert set(row) == {'parent', 'textures', 'scalars', 'vectors', 'switches'}, package
        assert all(name.startswith('bHas') for name in row['switches']), package
        assert all(v['effective'] is not None for v in row['switches'].values()), package
    for package, row in evidence['textures'].items():
        assert row == texture_read(), package
