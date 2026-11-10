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
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

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


def test_claim_without_a_donor_is_refused(capsys):
    assert sf.main(['--claim', 'TASK']) == 1
    assert '--donor' in capsys.readouterr().err


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


@pytest.mark.skipif(not real_tree_ready(), reason='family package bytes are not hydrated')
def test_native_read_lists_match_the_records():
    """Each family's package list is the records' packages, and its materials list is the subset a material read takes."""
    result = sf.classify(sf.GAME)
    inventory = sf.GAME / 'docs/inventory'
    for family in sf.FAMILY_ORDER:
        members = sf.FAMILY_GROUPS.get(family, (family,))
        rows = [r for r in result['records'] if r['family'] in members]
        if not rows:
            continue
        packages = sorted({p for r in rows for p in r['packages']})
        listed = inventory / f'small-families-{family}-packages.txt'
        if listed.is_file():
            assert sorted(listed.read_text().split()) == packages, family
        materials = inventory / f'small-families-{family}-materials.txt'
        if materials.is_file():
            names = materials.read_text().split()
            assert set(names) <= set(packages), family
            assert all('/Materials/' in n or n.rsplit('/', 1)[1].startswith(('M_', 'MI_', 'MPC_')) for n in names), family


# --- the claim: fake donor and game trees ---------------------------------------------------------------------------------

OBJECT_TOTE = '''schema = 1
id = "object/hippodrome/tote-board"
kind = "placement"
authority = "editor"
owner = "region/w15-hippodrome"
references = ["adopted/hippodrome/loose_files"]

[[outputs]]
package = "/Game/__ExternalActors__/V2/Maps/Slice/C/Z8/TOTE"
'''


def adopted_text(record_id, owner, packages):
    lines = ['schema = 1', f'id = "{record_id}"', 'kind = "adopted"', 'authority = "editor"', f'owner = "{owner}"',
             'provenance = "fixture"', 'license = "fixture"', '']
    for package in packages:
        lines += ['[[outputs]]', f'package = "{package}"', '']
    return '\n'.join(lines)


@pytest.fixture()
def claim_trees(tmp_path, monkeypatch):
    donor = tmp_path / 'donor'
    files = {}
    for slug, name in sf.HIPPO_CLAIM.values():
        files[f'{sf.GLB_DIR}/{name}.glb'] = f'glb {name}'.encode()
    for png in ('paving.png', 'timber.png'):
        files[f'{sf.PNG_DIR}/{png}'] = f'png {png}'.encode()
    for rel, data in files.items():
        (donor / rel).parent.mkdir(parents=True, exist_ok=True)
        (donor / rel).write_bytes(data)
    (donor / 'build/yorimichi/hippodrome').mkdir(parents=True, exist_ok=True)
    (donor / 'build/yorimichi/hippodrome/import-report.json').write_text(json.dumps(
        {name: {'triangles': 10 + i} for i, name in enumerate(n for _, n in sf.HIPPO_CLAIM.values())}))
    monkeypatch.setattr(sf, 'PINS', {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()})
    game = tmp_path / 'game'
    loose = [p for p in sf.HIPPO_CLAIM]
    (game / 'assets/adopted/hippodrome/loose_files').mkdir(parents=True)
    (game / 'assets/adopted/hippodrome/loose_files/asset.toml').write_text(
        adopted_text('adopted/hippodrome/loose_files', 'shared/hippodrome/loose_files', loose))
    (game / 'assets/adopted/hippodrome/loose_files/verified.json').write_text('{"files": {}}')
    plaza = list(sf.PLAZA_CLAIM)
    (game / 'assets/adopted/japan/textures/plaza-harbor').mkdir(parents=True)
    (game / 'assets/adopted/japan/textures/plaza-harbor/asset.toml').write_text(
        adopted_text('adopted/japan/textures/plaza-harbor', 'shared/japan/textures/plaza-harbor', plaza))
    (game / 'assets/adopted/japan/textures/plaza-harbor/verified.json').write_text('{"files": {}}')
    units = {'packages': {p: {'note': 'fixture'} for p in plaza + ['/Game/Japan/Textures/T_Other']}}
    (game / 'assets/adopted/japan/textures/units.json').write_text(json.dumps(units, indent=1, ensure_ascii=False) + '\n')
    (game / 'assets/object/hippodrome/tote-board').mkdir(parents=True)
    (game / 'assets/object/hippodrome/tote-board/asset.toml').write_text(OBJECT_TOTE)
    return donor, game


def test_claim_writes_records_moves_outputs_and_rewrites_referencers(claim_trees):
    donor, game = claim_trees
    ops = sf.claim_ops(game, donor)
    writes, deletes = ops['writes'], ops['deletes']
    assert 'assets/prop/hippodrome/tote-board/asset.toml' in writes
    assert 'assets/prop/hippodrome/tote-board/src/SM_HD_ToteBoard.glb' in writes
    assert 'assets/texture/japan/harbor-timber/src/T_Harbor_timber.png' in writes
    assert 'assets/adopted/hippodrome/loose_files/asset.toml' in deletes
    assert 'assets/adopted/hippodrome/loose_files/verified.json' in deletes
    assert 'assets/adopted/japan/textures/plaza-harbor/asset.toml' in deletes
    rewritten = writes['assets/object/hippodrome/tote-board/asset.toml'].decode()
    for slug in ('finish-post', 'grandstand', 'judges-tower', 'tote-board'):
        assert f'"prop/hippodrome/{slug}"' in rewritten
    assert 'adopted/hippodrome/loose_files' not in rewritten
    units = json.loads(writes['assets/adopted/japan/textures/units.json'].decode())
    assert sorted(units['packages']) == ['/Game/Japan/Textures/T_Other']


def test_each_new_record_text_loads_as_a_v2_record(claim_trees, tmp_path):
    donor, game = claim_trees
    ops = sf.claim_ops(game, donor)
    for rel, data in ops['writes'].items():
        if not rel.endswith('asset.toml') or 'adopted' in rel or 'object' in rel:
            continue
        path = tmp_path / rel.replace('/', '__')
        path.write_bytes(data)
        asset = records.load_asset(path)
        assert asset.authority == 'generated' and asset.sources and asset.recipe is not None
        assert asset.license == sf.LICENSE


def test_claim_refuses_a_donor_file_that_is_not_its_pin(claim_trees):
    donor, game = claim_trees
    (donor / sf.GLB_DIR / 'SM_HD_Grandstand.glb').write_bytes(b'changed')
    with pytest.raises(sf.PlanError):
        sf.claim_ops(game, donor)


def test_paths_are_claim_paths_and_scopes(claim_trees, capsys):
    donor, game = claim_trees
    sf.print_paths(game, donor)
    out = capsys.readouterr().out.splitlines()
    assert out[-1].startswith('scopes: ')
    assert 'shared/hippodrome/tote-board' in out[-1]
    assert 'shared/japan/arcade-paving' in out[-1]


@pytest.mark.skipif(DONOR is None or not (DONOR / sf.GLB_DIR / 'SM_HD_ToteBoard.glb').is_file(), reason='no donor checkout')
def test_real_donor_claim_pins_match():
    for rel, sha in sf.PINS.items():
        assert sf.sha256_file(DONOR / rel) == sha, rel
    assert all(len(sha) == 64 for sha in sf.PINS.values())


# --- the tree house textures: held until the read confirms, then claimed with their instances kept ----------------------

TREE_PNGS = {'flat.png': b'tree flat', 'glass.png': b'tree glass', 'rope.png': b'tree rope'}


@pytest.fixture()
def tree_trees(claim_trees, monkeypatch):
    donor, game = claim_trees
    for name, data in TREE_PNGS.items():
        (donor / sf.TREE_DIR / name).parent.mkdir(parents=True, exist_ok=True)
        (donor / sf.TREE_DIR / name).write_bytes(data)
    pins = {f'{sf.TREE_DIR}/{name}': hashlib.sha256(data).hexdigest() for name, data in TREE_PNGS.items()}
    monkeypatch.setattr(sf, 'PINS', {**sf.PINS, **pins})
    for slug in ('flat', 'glass', 'rope'):
        materials = f'/Game/Japan/Treehouse/Materials/MI_TH_{slug}'
        texture = f'/Game/Japan/Treehouse/Textures/T_TH_{slug}'
        record = f'adopted/japan/treehouse/surface-{slug}'
        folder = game / 'assets' / record
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(adopted_text(record, f'shared/japan/treehouse/surface-{slug}', [materials, texture]))
        files = {f'unreal/Content/Japan/Treehouse/Materials/MI_TH_{slug}.uasset': 'aa',
                 f'unreal/Content/Japan/Treehouse/Textures/T_TH_{slug}.uasset': 'bb'}
        (folder / 'verified.json').write_text(json.dumps({'asset': record, 'files': files}, indent=2, sort_keys=True) + '\n')
    return donor, game


def write_tree_read(game, max_size=1024):
    rows = {package: {**sf.TREE_SETTINGS, 'max_texture_size': max_size} if max_size != 1024 else dict(sf.TREE_SETTINGS)
            for package in sf.TREE_CLAIM}
    path = game / sf.TREE_READ
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1, sort_keys=True))


def test_the_tree_house_is_held_without_the_read(tree_trees, capsys):
    donor, game = tree_trees
    confirmed, reason = sf.treehouse_status(game)
    assert not confirmed and sf.TREE_READ in reason
    ops = sf.claim_ops(game, donor)
    assert not any('treehouse' in rel for rel in list(ops['writes']) + ops['deletes'])
    sf.print_paths(game, donor)
    assert 'not claimed' in capsys.readouterr().out


def test_a_read_that_disagrees_holds_the_tree_house(tree_trees):
    donor, game = tree_trees
    write_tree_read(game, max_size=2048)
    confirmed, reason = sf.treehouse_status(game)
    assert not confirmed and 'max_texture_size' in reason


def test_a_confirmed_read_claims_the_textures_and_keeps_the_instances(tree_trees, tmp_path):
    donor, game = tree_trees
    write_tree_read(game)
    assert sf.treehouse_status(game)[0]
    ops = sf.claim_ops(game, donor)
    writes = ops['writes']
    record_text = writes['assets/texture/japan/treehouse-flat/asset.toml'].decode()
    assert 'max_texture_size = 1024' in record_text and 'lod_group = "TEXTUREGROUP_WORLD"' in record_text
    assert 'srgb = true' in record_text
    assert 'assets/texture/japan/treehouse-flat/src/T_TH_flat.png' in writes
    kept = tmp_path / 'surface-flat.toml'
    kept.write_bytes(writes['assets/adopted/japan/treehouse/surface-flat/asset.toml'])
    outputs = [o.package for o in records.load_asset(kept).outputs]
    assert outputs == ['/Game/Japan/Treehouse/Materials/MI_TH_flat']
    assert 'assets/adopted/japan/treehouse/surface-flat/asset.toml' not in ops['deletes']
    verified = json.loads(writes['assets/adopted/japan/treehouse/surface-flat/verified.json'].decode())
    assert list(verified['files']) == ['unreal/Content/Japan/Treehouse/Materials/MI_TH_flat.uasset']


def test_the_real_tree_house_verified_files_are_in_adoption_form():
    for slug in ('flat', 'glass', 'rope'):
        path = sf.GAME / f'assets/adopted/japan/treehouse/surface-{slug}/verified.json'
        text = path.read_text()
        assert json.dumps(json.loads(text), indent=2, sort_keys=True) + '\n' == text, slug
