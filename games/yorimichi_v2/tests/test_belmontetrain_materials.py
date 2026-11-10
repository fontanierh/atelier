"""The residual Belmonte train texture and material planner (tools/migrate/belmontetrain_materials.py).

Fake data first: synthetic GLBs, a fake donor folder and a fake game tree, so the plan, the texture naming, the parent
choice and the claim's write set are pinned without the real donor. The real-tree tests run only when the donor build
(YV2_DONOR_BUILD) and the committed package bytes are present, and skip otherwise."""
import hashlib
import json
import os
import struct
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import belmontetrain_materials as m  # noqa: E402
import records  # noqa: E402

WALNUT = b'\x89PNG walnut grain'
IVORY = b'\xff\xd8 ivory swatch'


def glb(doc: dict, body: bytes = b'') -> bytes:
    """A binary glTF: the JSON chunk, then the binary chunk when there is one."""
    text = json.dumps(doc).encode()
    text += b' ' * (-len(text) % 4)
    padded = body + b'\0' * (-len(body) % 4)
    total = 12 + 8 + len(text) + (8 + len(padded) if body else 0)
    out = b'glTF' + struct.pack('<II', 2, total) + struct.pack('<II', len(text), 0x4E4F534A) + text
    if body:
        out += struct.pack('<II', len(padded), 0x004E4942) + padded
    return out


def fake_doc() -> dict:
    """Tender LOD0 in miniature: one image used twice (Walnut, Walnut1), one Ivory image, three materials."""
    return {
        'images': [{'name': 'T_BT_Walnut', 'bufferView': 0, 'mimeType': 'image/png'},
                   {'name': 'T_BT_Ivory', 'bufferView': 1, 'mimeType': 'image/jpeg'}],
        'bufferViews': [{'byteOffset': 0, 'byteLength': len(WALNUT)},
                        {'byteOffset': len(WALNUT), 'byteLength': len(IVORY)}],
        'textures': [{'source': 0}, {'source': 0}, {'source': 1}],
        'materials': [
            {'name': 'M_BT_Wood', 'doubleSided': True,
             'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'roughnessFactor': 0.4}},
            {'name': 'M_BT_Walnut2', 'doubleSided': True,
             'pbrMetallicRoughness': {'baseColorTexture': {'index': 1}, 'roughnessFactor': 0.4}},
            {'name': 'M_BT_Ivory', 'doubleSided': False,
             'pbrMetallicRoughness': {'baseColorFactor': [0.5, 0.25, 0.125, 1], 'baseColorTexture': {'index': 2},
                                      'roughnessFactor': 0.25}},
        ],
    }


def write_donor(donor: Path, unit: str, lod: int, doc: dict, body: bytes, pin: dict) -> None:
    name = f'SM_BT_Tender_LOD{lod}.glb'
    (donor / unit).mkdir(parents=True, exist_ok=True)
    data = glb(doc, body)
    (donor / unit / name).write_bytes(data)
    pin[name] = hashlib.sha256(data).hexdigest()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A donor folder with one unit (tender, LOD0) and a game tree whose adopted record lists its six packages."""
    monkeypatch.setattr(m, 'UNITS', {'tender': 'Tender'})
    monkeypatch.setattr(m, 'LODS', (0,))
    monkeypatch.setattr(m, 'SCOPES', ['shared/belmontetrain/tender'])
    donor = tmp_path / 'donor' / 'belmonte-train'
    (donor / 'textures').mkdir(parents=True)
    (donor / 'textures' / 'T_BT_Walnut.png').write_bytes(WALNUT)
    (donor / 'textures' / 'T_BT_Ivory.jpg').write_bytes(IVORY)
    pin = {}
    write_donor(donor, 'tender', 0, fake_doc(), WALNUT + IVORY, pin)
    (donor / 'service').mkdir()
    (donor / 'service' / 'import-report.json').write_text(json.dumps(
        {'vehicles': {'SM_BT_Tender': {'sources': pin}}, 'furniture': {}}))
    game = tmp_path / 'game'
    folder = 'SM_BT_Tender/LOD0/'
    packages = [f'/Game/BelmonteTrain/Source/{folder}{n}' for n in
                ('M_BT_Wood', 'M_BT_Walnut2', 'M_BT_Ivory', 'T_BT_Walnut', 'T_BT_Walnut1', 'T_BT_Ivory')]
    adopted = game / 'assets' / 'adopted' / 'belmontetrain'
    (adopted / 'tender').mkdir(parents=True)
    outputs = ''.join(f'\n[[outputs]]\npackage = "{p}"\n' for p in packages)
    (adopted / 'tender' / 'asset.toml').write_text(
        '# Adopted once from the donor (tools/migrate/adopt.py); editor-owned from now on.\n'
        '# Ownership unit: Belmonte train tender (fake)\n'
        'schema = 1\nid = "adopted/belmontetrain/tender"\nkind = "adopted"\nauthority = "editor"\n'
        'owner = "shared/belmontetrain/tender"\nprovenance = "fake"\nlicense = "fake"\n' + outputs)
    (adopted / 'tender' / 'verified.json').write_text(json.dumps({
        'asset': 'adopted/belmontetrain/tender', 'dependencies': {}, 'engine': 'fake', 'kind': 'editor-saved', 'schema': 1,
        'files': {f'unreal/Content/BelmonteTrain/Source/{folder}M_BT_Wood.uasset': 'aa'}}, indent=2, sort_keys=True) + '\n')
    units = {'about': 'fake', 'units': {}, 'packages': {p: 'tender' for p in packages}}
    (adopted / 'units.json').write_text(json.dumps(units, indent=1, ensure_ascii=False) + '\n')
    prop = game / 'assets' / 'prop' / 'belmontetrain' / 'tender'
    prop.mkdir(parents=True)
    (prop / 'asset.toml').write_text('schema = 1\nid = "prop/belmontetrain/tender"\nkind = "static-mesh"\n'
                                     'authority = "generated"\nowner = "shared/belmontetrain/tender"\n'
                                     'references = ["adopted/belmontetrain/tender"]\n')
    return {'donor': donor, 'game': game, 'packages': packages, 'prop': prop / 'asset.toml'}


# --- naming, roles and parents ----------------------------------------------------------------------------------------

def test_a_repeated_image_names_its_second_texture_with_a_suffix():
    assert m.texture_packages(fake_doc()) == [('T_BT_Walnut', 0), ('T_BT_Walnut1', 0), ('T_BT_Ivory', 1)]


def test_texture_roles_map_to_srgb_and_compression_and_mixed_roles_are_refused():
    assert m.texture_settings({'base'}) == (True, 'TC_DEFAULT')
    assert m.texture_settings({'emissive'}) == (True, 'TC_DEFAULT')
    assert m.texture_settings({'normal'}) == (False, 'TC_NORMALMAP')
    assert m.texture_settings({'metallic_roughness', 'occlusion'}) == (False, 'TC_MASKS')
    assert m.texture_settings({'base', 'normal'}) is None
    assert m.texture_settings(set()) is None


def test_the_parent_follows_alpha_mode_clear_coat_and_sidedness():
    base = '/InterchangeAssets/gltf/MaterialInstances/'
    assert m.parent_of('OPAQUE', False, True) == base + 'MI_Default_Opaque_DS'
    assert m.parent_of('OPAQUE', False, False) == base + 'MI_Default_Opaque'
    assert m.parent_of('BLEND', False, True) == base + 'MI_Default_Blend_DS'
    assert m.parent_of('OPAQUE', True, True) == base + 'MI_ClearCoat_Opaque_DS'


def test_a_glb_image_read_back_is_the_donor_bytes(tmp_path):
    path = tmp_path / 'tender.glb'
    path.write_bytes(glb(fake_doc(), WALNUT + IVORY))
    doc, body = m.read_glb(path)
    assert m.image_bytes(doc, body, 0) == WALNUT and m.image_bytes(doc, body, 1) == IVORY


# --- the plan on fake data -------------------------------------------------------------------------------------------------

def test_plan_binds_every_package_and_groups_the_materials(fake):
    p = m.plan(fake['game'], fake['donor'])
    assert p.unmapped == []
    assert sorted(p.packages) == sorted(fake['packages'])
    assert sorted(t.name for t in p.textures) == ['T_BT_Ivory', 'T_BT_Walnut', 'T_BT_Walnut1']
    walnut1 = next(t for t in p.textures if t.name == 'T_BT_Walnut1')
    assert walnut1.donor_file.name == 'T_BT_Walnut.png' and walnut1.sha == hashlib.sha256(WALNUT).hexdigest()
    assert walnut1.id == 'texture/belmontetrain/tender-lod0-walnut1' and walnut1.compression == 'TC_DEFAULT'
    (group,) = p.materials
    assert group.id == 'material/belmontetrain/tender-lod0' and len(group.instances) == 3
    assert group.inputs == sorted(t.id for t in p.textures)
    assert all(not t.source_name.endswith('.glb') for t in p.textures)
    ivory = next(i for i in group.instances if i['package'].endswith('M_BT_Ivory'))
    assert ivory['parent'].endswith('MI_Default_Opaque') and ivory['base'] == [0.5, 0.25, 0.125, 1]
    assert ivory['textures'] == {'base': '/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Ivory'}


def test_a_pin_mismatch_is_refused(fake):
    report = fake['donor'] / 'service' / 'import-report.json'
    data = json.loads(report.read_text())
    data['vehicles']['SM_BT_Tender']['sources']['SM_BT_Tender_LOD0.glb'] = '0' * 64
    report.write_text(json.dumps(data))
    with pytest.raises(m.PlanError, match='not the donor report'):
        m.plan(fake['game'], fake['donor'])


def test_an_output_no_glb_material_binds_is_reported(fake):
    adopted = fake['game'] / 'assets' / 'adopted' / 'belmontetrain' / 'tender' / 'asset.toml'
    adopted.write_text(adopted.read_text() + '\n[[outputs]]\npackage = "/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/M_BT_Ghost"\n')
    p = m.plan(fake['game'], fake['donor'])
    assert any('M_BT_Ghost' in u for u in p.unmapped)


def test_the_planned_texture_and_material_text_load_as_records(fake, tmp_path):
    p = m.plan(fake['game'], fake['donor'])
    for rec in p.textures:
        folder = tmp_path / 'assets' / rec.id
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(m.texture_text(rec))
        asset = records.load_asset(folder / 'asset.toml')
        assert asset.id == rec.id and asset.owner == rec.owner and asset.kind == 'texture'
        assert [o.package for o in asset.outputs] == [rec.package]
    (group,) = p.materials
    folder = tmp_path / 'assets' / group.id
    folder.mkdir(parents=True)
    (folder / 'asset.toml').write_text(m.material_text(group))
    asset = records.load_asset(folder / 'asset.toml')
    assert asset.kind == 'material-instance' and asset.sources == []
    assert sorted(o.package for o in asset.outputs) == sorted(group.outputs)
    assert sorted(asset.input_dependencies) == group.inputs
    outputs_of = {t.id: {t.package} for t in p.textures}
    assert records.material_input_problems(asset, outputs_of) == []
    settings = tomllib.loads(m.material_text(group))['recipe']['settings']
    rows = {r['package']: r for r in settings['instances']}
    assert set(rows) == set(group.outputs)
    assert {r['parent'].rsplit('/', 1)[1] for r in rows.values()} == {'MI_Default_Opaque_DS', 'MI_Default_Opaque'}
    ivory = rows[next(k for k in rows if k.endswith('M_BT_Ivory'))]
    assert ivory['textures'] == {'BaseColorTexture': '/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Ivory'}
    assert ivory['vectors'] == {'BaseColorFactor': [0.5, 0.25, 0.125, 1]}
    assert ivory['scalars'] == {'MetallicFactor': 1.0, 'RoughnessFactor': 0.25}
    assert all('ClearCoatFactor' not in r['scalars'] for r in rows.values())   # a fact a material does not have is left out


def test_the_claim_writes_the_records_moves_the_outputs_and_repoints_the_prop(fake):
    p = m.plan(fake['game'], fake['donor'])
    ops = m.build_writes(fake['game'], p)
    w = ops['writes']
    assert 'assets/adopted/belmontetrain/tender/asset.toml' in ops['deletes']
    assert 'assets/adopted/belmontetrain/tender/verified.json' in ops['deletes']
    assert 'assets/texture/belmontetrain/tender-lod0-walnut1/src/T_BT_Walnut.png' in w
    assert w['assets/texture/belmontetrain/tender-lod0-walnut1/src/T_BT_Walnut.png'] == WALNUT
    assert json.loads(w['assets/adopted/belmontetrain/units.json'].decode())['packages'] == {}
    prop_key = 'assets/prop/belmontetrain/tender/asset.toml'
    refs = tomllib.loads(w[prop_key].decode())['references']
    assert refs == sorted(p.record_ids('tender'))
    assert all(not r.startswith('adopted/') for r in refs)


def test_the_plan_writes_nothing(fake):
    before = {path: path.read_bytes() for path in fake['game'].rglob('*') if path.is_file()}
    m.plan(fake['game'], fake['donor'])
    after = {path: path.read_bytes() for path in fake['game'].rglob('*') if path.is_file()}
    assert before == after


# --- the real tree (skipped without the donor build or the committed bytes) ----------------------------------------------

REAL_DONOR = os.environ.get('YV2_DONOR_BUILD')
REAL_GAME = ROOT
RESIDUAL_SKIP = pytest.mark.skipif(
    not REAL_DONOR or not (Path(REAL_DONOR).expanduser() / 'belmonte-train' / 'service' / 'import-report.json').is_file(),
    reason='needs the donor build (YV2_DONOR_BUILD)')


def real_donor() -> Path:
    return Path(REAL_DONOR).expanduser() / 'belmonte-train'


@RESIDUAL_SKIP
def test_real_tree_plans_all_459_packages_without_unmapped_ones():
    p = m.plan(REAL_GAME, real_donor())
    assert p.unmapped == []
    assert len(p.textures) == 138 and len(p.materials) == 21
    assert sum(len(r.instances) for r in p.materials) == 321
    assert len(p.packages) == 459


@RESIDUAL_SKIP
def test_real_tree_committed_bytes_confirm_the_material_facts_and_leave_the_texture_sRGB_read():
    p = m.plan(REAL_GAME, real_donor())
    packages = [i['package'] for r in p.materials for i in r.instances] + [t.package for t in p.textures]
    pointers = [pk for pk in packages if records.is_lfs_pointer(REAL_GAME / 'unreal' / 'Content' / (pk[len('/Game/'):] + '.uasset'))]
    if pointers:
        pytest.skip(f'{len(pointers)} package(s) are LFS pointers: run git lfs pull first')
    checks = m.byte_check(REAL_GAME, p)
    materials = [pk for r in p.materials for pk in [i['package'] for i in r.instances]]
    assert all(checks[pk][0] == 'determined' for pk in materials), [pk for pk in materials if checks[pk][0] != 'determined'][:3]
    for t in p.textures:
        status, notes = checks[t.package]
        assert status == 'read' and notes[-1].startswith('sRGB flag'), (t.package, notes)
        assert all('is not in the bytes' not in n for n in notes), (t.package, notes)
