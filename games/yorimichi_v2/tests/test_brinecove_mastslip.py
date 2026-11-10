"""Brine Cove signal mast and stone shipyard slip: owner replay from the generator's source blocks, claim paths and the
plan's GLB matching. The generator replays are pure Python (no bpy); the donor GLBs are synthetic, written from the
generator's own triangles, so no LFS data is needed."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_mastslip as mast  # noqa: E402
import brinecove_market as market  # noqa: E402
import brinecove_split as split  # noqa: E402

SRC = ROOT.parent / 'yorimichi'
_CACHE: dict = {}


def built(name: str) -> dict:
    if name not in _CACHE:
        _CACHE[name] = mast.replay(SRC, name)
    return _CACHE[name]


def test_soft_prefixes_are_the_generators():
    assert mast.soft_prefixes() == ('leaf_', 'palm_', 'waterfall', 'mist', 'spray', 'foam', 'water', 'vine', 'flower',
                                    'grass', 'fern', 'cover_')


def test_mast_block_is_found_by_its_comment_and_must_be_unique():
    source = ('def market():\n    a = 1\n'
              "    # Signal mast, crossyard, rigging, bunting and a crow's nest.\n"
              '    b = 2\n    c = 3\n    # Well.\n')
    assert mast.block_lines(source) == (4, 5)
    with pytest.raises(mast.MastSlipError, match='found 0 times'):
        mast.block_lines('def market():\n    pass\n')
    with pytest.raises(mast.MastSlipError, match='Well'):
        mast.block_lines("def market():\n    # Signal mast, crossyard, rigging, bunting and a crow's nest.\n")


def test_real_signal_mast_is_250_faces_in_the_two_market_tiles():
    info = mast.summary(built('signal-mast'))['signal-mast']
    assert info['faces'] == 250 and info['triangles'] == 508
    assert info['tiles'] == {'Market_3_4': 132, 'Market_4_4': 376}
    assert set(info['materials']) == {'cream', 'flag_red', 'roof_teal', 'rope', 'wood', 'wood_dark'}


def test_real_signal_mast_bounds_are_the_mast_and_nothing_else():
    b = built('signal-mast')
    pts = [b['verts'][i] for f, o in zip(b['faces'], b['owner']) if o == 'signal-mast' for i in f]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    assert lo == pytest.approx([-18.02, 151.972, 4.9], abs=0.01)
    assert hi == pytest.approx([18.02, 164.028, 27.9], abs=0.01)


def test_real_slip_is_the_stone_faces_of_slipway_in_harbor_5_3():
    info = mast.summary(built('shipyard-slip'))
    slip = info['shipyard-slip']
    assert slip['faces'] == 24 and slip['triangles'] == 48
    assert slip['tiles'] == {'Harbor_5_3': 48}
    assert all(m.startswith('stone') for m in slip['materials'])
    ways = info['shipyard-ways']
    assert ways['tiles'] == {'Harbor_5_3': 332, 'Harbor_5_4': 28}
    assert not set(ways['materials']) & {'stone', 'stone_dark', 'stone_light'}


def test_real_slip_bounds():
    b = built('shipyard-slip')
    pts = [b['verts'][i] for f, o in zip(b['faces'], b['owner']) if o == 'shipyard-slip' for i in f]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    assert lo == pytest.approx([346.8, 21.974, -5.5], abs=0.01)
    assert hi == pytest.approx([357.2, 65.026, 4.943], abs=0.01)


def test_ranges_are_half_open_and_merged():
    assert mast.ranges([5, 1, 2, 3, 9, 3]) == [[1, 4], [5, 6], [9, 10]]
    assert mast.ranges([]) == []


def test_expand_takes_the_tile_and_its_pieces_only():
    stems = ['Market_3_4_Piece10', 'Market_3_4_Soft', 'Market_3_40', 'Market_3_4_Piece2']
    assert mast.expand('Market_3_4', stems) == ['Market_3_4_Piece10', 'Market_3_4_Piece2']
    assert mast.expand('Market_9_9', stems) == ['Market_9_9']


def test_tile_records_are_the_split_tools_record_ids():
    assert mast.tile_record('Market_3_4_Piece10') == 'prop/brinecove/market-3-4-piece10'
    assert mast.tile_record('Harbor_5_3') == 'prop/brinecove/harbor-5-3'
    assert (ROOT / 'assets' / 'prop' / 'brinecove' / 'harbor-5-3' / 'src' / 'SM_BC_Harbor_5_3.carve.json').is_file()


def test_claim_set_names_both_records_tiles_scopes_and_the_lock():
    summaries = {}
    for name in mast.OBJECTS:
        summaries.update(mast.summary(built(name)))
    info = mast.claim_set(None, summaries)
    paths = set(info['paths'])
    for want in ('games/yorimichi_v2/assets/prop/brinecove/signal-mast/',
                 'games/yorimichi_v2/assets/prop/brinecove/signal-mast/src/SM_BC_SignalMast.glb',
                 'games/yorimichi_v2/assets/prop/brinecove/shipyard-slip/src/SM_BC_ShipyardSlip.glb',
                 'games/yorimichi_v2/assets/prop/brinecove/harbor-5-3/src/SM_BC_Harbor_5_3.carve.json',
                 'games/yorimichi_v2/world/regions/w09-brinecove/split-mastslip.json',
                 'games/yorimichi_v2/world/regions/w09-brinecove/objects.toml',
                 'games/yorimichi_v2/runtime-data.lock.json'):
        assert want in paths, want
    assert info['residual_tiles'] == ['Harbor_5_3', 'Market_3_4', 'Market_4_4']
    assert info['locks'] == ['games/yorimichi_v2/runtime-data.lock.json']
    assert 'region/w09-brinecove' in info['scopes'] and 'region/w00-island' in info['scopes']
    assert info['paths'] == sorted(info['paths'])
    assert not any(p.startswith('/') or p.startswith('~') for p in paths)    # repository-relative only


def test_paths_command_prints_claim_lines(capsys):
    assert mast.main(['paths']) == 0
    out = capsys.readouterr().out
    assert '# claim paths' in out and '# scopes' in out and '# locks:' in out
    assert 'games/yorimichi_v2/assets/prop/brinecove/signal-mast/' in out
    assert not any(line.startswith('/') for line in out.splitlines())    # repository-relative only


def test_plan_needs_a_donor(capsys):
    with pytest.raises(SystemExit):
        mast.main(['plan'])


def _tile_model(entries):
    """A GLB model (split.read_glb's shape) of the generator's faces in `entries`: [(built, face index)]."""
    materials, prims = [], {}
    for b, i in entries:
        mat = b['mats'][i]
        if mat not in materials:
            materials.append(mat)
        prim = prims.setdefault(mat, {'material': materials.index(mat), 'positions': [], 'indices': []})
        pts = [market.glb_point(b['verts'][v]) for v in b['faces'][i]]
        for k in range(1, len(pts) - 1):
            for p in (pts[0], pts[k], pts[k + 1]):
                prim['indices'].append(len(prim['positions']))
                prim['positions'].append(p)
    return {'materials': materials, 'prims': list(prims.values()), 'material_docs': [{'name': m} for m in materials]}


def _write_tile(path, b, indices):
    model = _tile_model([(b, i) for i in indices])
    split.write_subset(model, range(sum(len(p['indices']) // 3 for p in model['prims'])), path)


def test_plan_matches_synthetic_donor_tiles_to_the_generator(tmp_path):
    glb = tmp_path / 'brinecove' / 'glb'
    glb.mkdir(parents=True)
    mast_b = built('signal-mast')
    slip_b = built('shipyard-slip')
    mast_faces = [i for i, o in enumerate(mast_b['owner']) if o == 'signal-mast' and mast.tile_of(mast_b, mast_b['faces'][i]) == (3, 4)]
    _write_tile(glb / 'SM_BC_Market_3_4.glb', mast_b, mast_faces)
    harbor_faces = [i for i, f in enumerate(slip_b['faces']) if slip_b['mats'][i] and mast.tile_of(slip_b, f) == (5, 3)
                    and not slip_b['mats'][i].startswith(mast.soft_prefixes())]
    _write_tile(glb / 'SM_BC_Harbor_5_3.glb', slip_b, harbor_faces)
    assert len(mast_faces) == 66 and len(harbor_faces) > 0    # 66 quads = the 132 triangles of Market_3_4
    result = mast.plan(tmp_path, SRC)
    assert result['objects']['signal-mast']['triangles'] == 132
    assert list(result['objects']['signal-mast']['files']) == ['Market_3_4']
    assert result['objects']['shipyard-slip']['triangles'] == 48
    assert list(result['objects']['shipyard-slip']['files']) == ['Harbor_5_3']
    assert result['shipyard_ways_triangles'] == 332
    assert result['trimmed']['Harbor_5_3']['removed'] == 48
    assert result['trimmed']['Harbor_5_3']['kept'] == result['trimmed']['Harbor_5_3']['triangles'] - 48


def test_plan_refuses_a_donor_triangle_no_generator_face_makes(tmp_path):
    glb = tmp_path / 'brinecove' / 'glb'
    glb.mkdir(parents=True)
    stray = {'materials': ['wood'], 'prims': [{'material': 0, 'positions': [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                                                             (0.0, 1.0, 0.0)], 'indices': [0, 1, 2]}],
             'material_docs': [{'name': 'wood'}]}
    split.write_subset(stray, range(1), glb / 'SM_BC_Harbor_5_3.glb')
    with pytest.raises(market.MarketError, match='no generated face'):
        mast.plan(tmp_path, SRC)
