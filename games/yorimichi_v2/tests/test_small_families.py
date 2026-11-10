"""The small-family source plan (tools/migrate/small_families.py): fake records and donor files for the rules, and the real
tree for the counts. The real-tree tests skip unless the family package bytes are hydrated, and the donor tests skip
unless a donor checkout is given with V2_FAMILIES_DONOR."""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import small_families as sf  # noqa: E402

POINTER = b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'0' * 64 + b'\nsize 12\n'
DONOR = Path(os.environ['V2_FAMILIES_DONOR']) if os.environ.get('V2_FAMILIES_DONOR') else None


def glb(names):
    doc = json.dumps({'asset': {'version': '2.0'}, 'materials': [{'name': n} for n in names]}).encode()
    doc += b' ' * (-len(doc) % 4)
    chunk = struct.pack('<I4s', len(doc), b'JSON') + doc
    return b'glTF' + struct.pack('<II', 2, 12 + len(chunk)) + chunk


def test_glb_material_names_are_read_from_the_json_chunk(tmp_path):
    path = tmp_path / 'SM_HD_FinishPost.glb'
    path.write_bytes(glb(['HD_FinishPost', 'HD_Rail']))
    assert sf.glb_materials(path) == ['HD_FinishPost', 'HD_Rail']


def test_a_non_glb_is_refused(tmp_path):
    path = tmp_path / 'x.glb'
    path.write_bytes(b'not a glb at all')
    with pytest.raises(sf.FamilyError):
        sf.glb_materials(path)


def test_package_refs_drop_self_and_folders(tmp_path):
    path = tmp_path / 'MI_X.uasset'
    path.write_bytes(b'\0/Game/Japan/Materials/MI_X\0/Game/Japan/Materials/M_Painted\0/Game/Japan/Textures/T_white.T_white\0'
                     b'/Game/Japan/Textures/\0')
    assert sf.package_refs(path, '/Game/Japan/Materials/MI_X') == [
        '/Game/Japan/Materials/M_Painted', '/Game/Japan/Textures/T_white']


def test_pointer_and_sha_problems_are_reported(tmp_path):
    game = tmp_path / 'game'
    record = game / 'assets/adopted/fake/one'
    record.mkdir(parents=True)
    good = game / 'unreal/Content/Fake/Good.uasset'
    good.parent.mkdir(parents=True)
    good.write_bytes(b'bytes')
    pointer = game / 'unreal/Content/Fake/Pointer.uasset'
    pointer.write_bytes(POINTER)
    files = {
        'unreal/Content/Fake/Good.uasset': hashlib.sha256(b'bytes').hexdigest(),
        'unreal/Content/Fake/Pointer.uasset': hashlib.sha256(b'other').hexdigest(),
    }
    (record / 'verified.json').write_text(json.dumps({'files': files}))
    problems = sf.byte_problems(game, 'adopted/fake/one')
    assert problems == ['unreal/Content/Fake/Pointer.uasset: LFS pointer (not hydrated)']
    pointer.write_bytes(b'changed bytes')
    assert sf.byte_problems(game, 'adopted/fake/one') == [
        'unreal/Content/Fake/Pointer.uasset: sha256 differs from verified.json']


def test_hippodrome_meshes_plan_from_a_fake_donor(tmp_path):
    donor = tmp_path / 'donor'
    region = donor / 'build/yorimichi/hippodrome/region/glb'
    region.mkdir(parents=True)
    (donor / 'build/yorimichi/hippodrome/import-report.json').write_text(
        json.dumps({'SM_HD_ToteBoard': {'triangles': 42}}))
    (region / 'SM_HD_ToteBoard.glb').write_bytes(glb(['HD_ToteBoard']))
    rows = {r['package']: r for r in sf.hippodrome_meshes(sf.GAME, donor)}
    assert len(rows) == 4
    tote = rows['/Game/Hippodrome/SM_HD_ToteBoard']
    assert tote['triangles'] == 42
    assert tote['glb_materials'] == ['HD_ToteBoard']
    assert tote['glb_sha256'] == hashlib.sha256(region.joinpath('SM_HD_ToteBoard.glb').read_bytes()).hexdigest()
    assert rows['/Game/Hippodrome/SM_HD_FinishPost']['glb_sha256'] is None


def test_megapark_report_names_follow_the_importer_key_rule(tmp_path):
    donor = tmp_path / 'donor'
    (donor / 'build/yorimichi/megapark').mkdir(parents=True)
    (donor / 'build/yorimichi/megapark/build.json').write_text(json.dumps({'materials': {
        'M_0047072464533c3a': {'alpha_mode': 0},
        'M_0297e420658d668d': {'alpha_mode': 1, 'seam': True},
    }}))
    report = sf.megapark_report(donor)
    assert report['names'] == ['MI_0047072464533c3a', 'MI_0297e420658d668d']
    assert report['parents'] == {'M_RetailOpaque': 1, 'M_RetailMasked': 1}
    assert report['seam_rows'] == 1


def test_registry_rows_are_consistent():
    families = {row[0] for row in sf.REGISTRY.values()}
    assert families == set(sf.FAMILY_ORDER)
    assert {row[3] for row in sf.REGISTRY.values()} <= {'planned', 'need-read', 'blocked', 'unreal-authored'}
    for record_id, row in sf.REGISTRY.items():
        assert record_id.startswith('adopted/')
        assert row[3] != 'planned' or row[4], record_id + ' names what is still missing'


def test_claim_is_refused(capsys):
    assert sf.main(['--claim', 'TASK']) == 2
    assert 'refused' in capsys.readouterr().err


def real_tree_ready():
    for record_id in sf.REGISTRY:
        verified = sf.GAME / f'assets/{record_id}/verified.json'
        if not verified.is_file():
            return False
        for rel in json.loads(verified.read_text()).get('files', {}):
            if not (sf.GAME / rel).is_file() or sf.is_pointer(sf.GAME / rel):
                return False
    return True


@pytest.mark.skipif(not real_tree_ready(), reason='family package bytes are not hydrated')
def test_real_tree_counts_and_bytes():
    result = sf.classify(sf.GAME)
    assert result['packages'] == 90
    assert result['problems'] == []
    expect = {'megapark': (4, 25), 'hippodrome': (3, 23), 'treehouse': (5, 8), 'skatepark': (2, 8), 'belmonte': (2, 7),
              'fx': (1, 7), 'plaza': (1, 4), 'bike': (1, 2), 'swordcamp': (1, 2), 'hidamari': (1, 1), 'racing': (1, 1),
              'seethrough': (1, 1), 'skateruntime': (1, 1)}
    got = {f: (v['records'], v['packages']) for f, v in result['families'].items()}
    assert got == expect


@pytest.mark.skipif(DONOR is None or not (DONOR / 'build/yorimichi/megapark/build.json').is_file(), reason='no donor checkout')
def test_real_donor_megapark_names_cover_the_family_instances():
    report = sf.megapark_report(DONOR)
    assert report['materials'] == 523
    family = {o.package.rsplit('/', 1)[1] for r in sf.REGISTRY if r.startswith('adopted/megapark/')
              for o in sf.records.load_asset(sf.GAME / f'assets/{r}/asset.toml').outputs if '/MI_' in o.package}
    assert family <= set(report['names'])


def test_treehouse_textures_take_their_donor_png_pins(tmp_path):
    donor = tmp_path / 'donor'
    textures = donor / 'build/yorimichi/treehouse/textures'
    textures.mkdir(parents=True)
    (textures / 'flat.png').write_bytes(b'same')
    (textures / 'glass.png').write_bytes(b'same')
    (textures / 'rope.png').write_bytes(b'other')
    rows = {r['package']: r for r in sf.treehouse_textures(sf.GAME, donor)}
    assert rows['/Game/Japan/Treehouse/Textures/T_TH_flat']['png_sha256'] == \
        rows['/Game/Japan/Treehouse/Textures/T_TH_glass']['png_sha256']
    assert rows['/Game/Japan/Treehouse/Textures/T_TH_rope']['png_sha256'] == hashlib.sha256(b'other').hexdigest()


@pytest.mark.skipif(DONOR is None or not (DONOR / 'build/yorimichi/treehouse/textures/rope.png').is_file(),
                    reason='no donor checkout')
def test_real_donor_treehouse_pins():
    rows = {r['package'].rsplit('/', 1)[1]: r for r in sf.treehouse_textures(sf.GAME, DONOR)}
    assert rows['T_TH_flat']['png_sha256'].startswith('10b379bb6586c9e9')
    assert rows['T_TH_glass']['png_sha256'] == rows['T_TH_flat']['png_sha256']
    assert rows['T_TH_rope']['png_sha256'].startswith('13d328aea5ed6186')
