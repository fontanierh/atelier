"""Brine Cove market/town split: face ownership from the generator's loop bodies, triangle matching and the partition."""
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_market as market  # noqa: E402
import brinecove_split as split  # noqa: E402


def tri(a, b, c, material='BC_wood'):
    return material, (a, b, c)


def test_glb_point_is_float32_and_swaps_axes():
    assert market.glb_point((1.0, 2.0, 3.0)) == (1.0, 3.0, -2.0)
    x = market.glb_point((0.1, 0.2, 0.3))
    assert x[0] == pytest.approx(0.1, abs=1e-7) and x[0] != 0.1             # float32, as the GLB stores it


def test_loop_ranges_find_the_body_by_header_text():
    source = textwrap.dedent('''
        def market():
            for i, (x, y, w, d, cloth) in enumerate(L.MARKET_STALLS):
                a = 1
                b = 2
            for other in range(3):
                pass
    ''')
    found = market.loop_ranges(source, market.SCOPES[:1])
    assert len(found) == 1 and found[0][:2] == (4, 5)
    with pytest.raises(market.MarketError):
        market.loop_ranges('def market():\n    pass\n', market.SCOPES[:1])


def test_owner_match_is_exact_and_triangulation_independent():
    quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    built = {'verts': quad + [(5, 5, 5), (6, 5, 5), (6, 6, 5)], 'mats': ['wood', 'wood'],
             'faces': [(0, 1, 2, 3), (4, 5, 6)], 'owner': ['market-stall-01', None]}
    index = market.face_index(built)
    g = market.glb_point
    # either diagonal of the quad belongs to the stall; the lone triangle to nobody
    assert market.owners_of([tri(g(quad[0]), g(quad[1]), g(quad[2])), tri(g(quad[0]), g(quad[2]), g(quad[3])),
                             tri(g(quad[0]), g(quad[1]), g(quad[3])), tri(g((5, 5, 5)), g((6, 5, 5)), g((6, 6, 5)))],
                            index) == ['market-stall-01'] * 3 + [None]
    with pytest.raises(market.MarketError, match='no generated face'):
        market.owners_of([tri(g((9, 9, 9)), g((8, 9, 9)), g((8, 8, 9)))], index)


def test_identical_triangles_of_two_objects_are_refused():
    t = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    built = {'verts': t + t, 'mats': ['a', 'a'], 'faces': [(0, 1, 2), (3, 4, 5)], 'owner': ['market-stall-01', 'market-stall-02']}
    with pytest.raises(market.MarketError, match='more than one object'):
        market.owners_of([tri(*[market.glb_point(p) for p in t])], market.face_index(built))


def fake_donor(root: Path) -> Path:
    """A miniature donor generator: a market() whose stall loop draws from the shared RNG, plus clutter between stalls."""
    pkg = root / 'world' / 'regions' / 'brinecove'
    (pkg / 'procedural').mkdir(parents=True)
    (root / 'assets' / 'brinecove' / 'export-parameters').mkdir(parents=True)
    (root / 'world' / 'random_stream.py').write_text(textwrap.dedent('''
        import random
        def positioned(seed, words):
            rng = random.Random(seed)
            for _ in range(words):
                rng.getrandbits(32)
            return rng
    '''))
    (root / 'assets' / 'brinecove' / 'export-parameters' / 'Market.json').write_text(
        json.dumps({'asset': 'Market', 'prefix_words': 3, 'schema': 1, 'seed': 7}))
    (pkg / '__init__.py').write_text('')
    (pkg / 'procedural' / '__init__.py').write_text('')
    (pkg / 'procedural' / 'random_state.py').write_text('import random\nRNG = random.Random(0)\n')
    (pkg / 'geom.py').write_text(textwrap.dedent('''
        class Builder:
            def __init__(self, name):
                self.verts, self.faces, self.mats = [], [], []
            def face(self, points, mat, uvs=None, normals=None):
                i = len(self.verts)
                self.verts.extend(points)
                self.faces.append(tuple(range(i, i + len(points))))
                self.mats.append(mat)
            def box(self, c, s, mat):
                x, y, z = c
                for k in range(2):
                    self.face([(x, y, z + k), (x + s, y, z + k), (x + s, y + s, z + k), (x, y + s, z + k)], mat)
    '''))
    (pkg / 'procedural' / 'market.py').write_text(textwrap.dedent('''
        from brinecove.geom import Builder
        from brinecove.procedural.random_state import RNG
        STALLS = [(0, 0, 4, 3, 'c'), (10, 0, 4, 3, 'c'), (20, 0, 4, 3, 'c')]

        def market():
            b = Builder('m')
            b.box((0, 0, 0), 99, 'cobble')
            for i, (x, y, w, d, cloth) in enumerate(L.MARKET_STALLS):
                x += RNG.uniform(-2.5, 2.5)
                b.box((x, y, 1), w, 'canvas')
                b.box((x + 5, y, 1), 1, 'wood')
            b.box((3, 3, 3), 1, 'clutter')
            return b
    '''.replace('L.MARKET_STALLS', 'STALLS')))
    return root


SCOPE = (dict(component='Market', module='market', loop='for i, (x, y, w, d, cloth) in enumerate(STALLS):',
              key="'stall-%02d' % (i + 1)"),)


def test_replay_tags_every_face_of_a_loop_body_and_replays_the_rng(tmp_path):
    src = fake_donor(tmp_path / 'donor')
    a = market.replay(src, 'Market', SCOPE)
    b = market.replay(src, 'Market', SCOPE)
    assert a['verts'] == b['verts']                                          # same stream position, same jitter
    owners = a['owner']
    assert owners[:2] == [None, None]                                        # the cobble box
    assert [owners.count(f'stall-0{n}') for n in (1, 2, 3)] == [4, 4, 4]     # stall and its crate: 2 boxes x 2 faces
    assert owners[-2:] == [None, None]                                       # clutter after the loop is nobody's
    assert len(owners) == len(a['faces'])
    xs = [v[0] for v in a['verts'][8:12]]
    assert len(set(round(x, 6) for x in xs)) > 1 and a['verts'][8][0] != 0.0   # jittered, not on the grid


def test_object_naming():
    assert market.object_name('Market', 'stall-03') == 'market-stall-03'
    assert market.object_name('TownLower', 'Hall_1') == 'town-lower-hall-1'
    assert market.component_of('town-upper-x') == 'TownUpper'
    assert market.object_name('Market', 'south-west') == 'market-stall-south-west'
    assert set(market.BATCHES['market1']) <= {f'market-stall-{n:02d}' for n in range(1, 20)}
    assert all(market.component_of(n) == 'Market' for b in ('market1', 'market2', 'market3') for n in market.BATCHES[b])
    flat = [n for b in market.BATCHES.values() for n in b]
    assert len(flat) == len(set(flat))                                       # no object in two batches


def test_prior_objects_come_from_other_split_files(tmp_path):
    (tmp_path / 'split-batch1.json').write_text(json.dumps({'parts': {'a': {'object': 'market-well'}}}))
    (tmp_path / 'split-market1.json').write_text(json.dumps({'parts': {'b': {'object': 'market-stall-01'}}}))
    assert market.prior_objects(tmp_path, 'split-market1.json') == {'market-well'}
    assert market.prior_objects(tmp_path, 'split-batch2.json') == {'market-well', 'market-stall-01'}


def test_compute_partitions_with_an_earlier_batch(tmp_path, monkeypatch):
    """Tile = stall parts + remainder + earlier batch, and a stall triangle already taken earlier is a problem."""
    g = market.glb_point
    sq = lambda x, y, z: [(x, y, z), (x + 1, y, z), (x + 1, y + 1, z)]            # noqa: E731
    pts = {'s1': sq(0, 0, 0), 's2': sq(5, 0, 0), 'rest': sq(9, 9, 9), 'other': sq(20, 0, 0)}
    owners = ['market-stall-01', 'market-stall-02', None, 'market-stall-03']      # stall 02: an earlier batch's
    tris = [tri(*[g(p) for p in pts[k]]) for k in ('s1', 's2', 'rest', 'other')]

    def fake(glb_dir, src, component):
        return {'models': {'Market_1_1': {}}, 'tris': {'Market_1_1': tris}, 'owner': {'Market_1_1': owners}}
    monkeypatch.setattr(market, 'generated_owners', fake)
    done = market.compute(tmp_path, tmp_path, ['market-stall-01'], {'market-stall-02'})
    assert done['problems'] == []
    owned = done['owned']['Market_1_1']
    assert owned['market-stall-01'] == [0] and owned[''] == [2, 3] and done['prior']['Market_1_1'] == 1
    done = market.compute(tmp_path, tmp_path, ['market-stall-01', 'market-stall-02'], {'market-stall-02'})
    assert done['problems'] and 'already taken' in done['problems'][0]


DONOR = os.environ.get('YV2_DONOR_BUILD')


@pytest.mark.skipif(not DONOR or not Path(DONOR).is_dir(), reason='needs the donor export (YV2_DONOR_BUILD)')
def test_donor_market_is_matched_completely_and_stalls_do_not_overlap_batch1():
    donor = Path(DONOR)
    src = market.donor_source(donor)
    gen = market.generated_owners(donor / 'brinecove' / 'glb', src, 'Market')
    counts = {}
    for owners in gen['owner'].values():
        for o in owners:
            if o:
                counts[o] = counts.get(o, 0) + 1
    assert len(counts) == 21 and counts['market-stall-06'] == 4752
    done = market.compute(donor / 'brinecove' / 'glb', src, list(market.BATCHES['market1']), {'market-well', 'market-auction-block'})
    assert done['problems'] == []
