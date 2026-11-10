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


def test_a_batch_is_not_applied_again_over_tiles_a_later_batch_cut(tmp_path):
    """A rerun of market1 after town1 recut its tile would put town1's parts back into the tile's remainder."""
    region = tmp_path / 'world' / 'regions' / market._apply().REGION
    region.mkdir(parents=True)
    (region / 'split-market1.json').write_text(json.dumps({'tiles': {'Market_3_4': {}}}))
    (region / 'split-town1.json').write_text(json.dumps({'tiles': {'Market_3_4': {}, 'TownLower_1_2': {}}}))
    assert market.later_tiles(tmp_path, 'market1') == {'Market_3_4', 'TownLower_1_2'}
    assert market.later_tiles(tmp_path, 'town1') == set()
    assert market._apply().later_tiles(tmp_path) == {'Market_3_4', 'TownLower_1_2'}    # batch 1 sees every other batch


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


def test_town_batches_are_disjoint_sized_and_named():
    towns = {k: v for k, v in market.BATCHES.items() if k.startswith('town')}
    assert list(towns) == [f'town{n}' for n in range(1, 10)]
    flat = [n for v in towns.values() for n in v]
    assert len(flat) == len(set(flat)) == 7 + 258
    assert all(n.startswith(('town-lower-', 'town-upper-')) for n in flat)
    assert all(25 <= len(v) <= 45 for k, v in towns.items() if k != 'town1')


@pytest.mark.skipif(not DONOR or not Path(DONOR).is_dir(), reason='needs the donor export (YV2_DONOR_BUILD)')
def test_town_batches_cover_every_donor_lot_once_and_chain_without_conflict():
    donor = Path(DONOR)
    src = market.donor_source(donor)
    glb = donor / 'brinecove' / 'glb'
    lots = set()
    for component in ('TownLower', 'TownUpper'):
        lots |= {o for owners in market.generated_owners(glb, src, component)['owner'].values() for o in owners if o}
    batched = [n for k, v in market.BATCHES.items() if k.startswith('town') for n in v]
    assert sorted(batched) == sorted(lots)
    taken: set = set()
    for name in [k for k in market.BATCHES if k.startswith('town')]:       # each batch against what the earlier ones left
        done = market.compute(glb, src, list(market.BATCHES[name]), set(taken))
        assert done['problems'] == [], name
        taken |= set(market.BATCHES[name])


TOML = '''[[objects]]
id = "object/a"
groups = ["SM_BC_T_1", "SM_BC_T_2"]
model = "adopted/a"
about = "a"

[[objects]]
id = "object/b"
group = "SM_BC_T_1"
model = "adopted/b"
about = "b"

[[objects]]
id = "object/c"
groups = ["SM_BC_T_3"]
model = "adopted/c"
about = "c"
'''


def test_drop_group_edits_group_lists_and_drops_empty_objects():
    out = market.drop_group(TOML, 'SM_BC_T_1')
    assert 'groups = ["SM_BC_T_2"]' in out and 'object/b' not in out and 'object/c' in out
    assert market.drop_group(out, 'SM_BC_T_1') == out                            # idempotent
    assert 'object/a' not in market.drop_group(out, 'SM_BC_T_2')


def test_drop_saved_group():
    body = {'schema': 1, 'objects': {'a': {'groups': ['x', 'y']}, 'b': {'groups': ['x']}, 'c': {'model': 'm'}}}
    out = market.drop_saved_group(body, 'x')
    assert out['objects'] == {'a': {'groups': ['y']}, 'c': {'model': 'm'}}
    assert market.drop_saved_group(out, 'x') == out


def test_emptied_lists_tiles_with_no_remainder():
    assert market.emptied({'remainders': {'B': None, 'A': {'triangles': 3}, 'C': None}}) == ['B', 'C']


def test_the_command_line_parses():
    """Every option is declared once (a duplicate stops the parser before any subcommand runs)."""
    with pytest.raises(SystemExit) as done:
        market.main(['--help'])
    assert done.value.code == 0


def test_retire_writes_under_the_scopes_it_authorized(monkeypatch, tmp_path):
    """The shared execute takes the authorized scopes (keyword-only); a retire without them is a TypeError."""
    import brinecove_split_apply as apply_
    monkeypatch.setattr(apply_, 'EXPECTED', apply_.EXPECTED)   # set_batch points it at the batch; restore after
    calls = {}
    monkeypatch.setattr(market, 'check', lambda *a, **k: [])
    monkeypatch.setattr(market, 'retire_compute', lambda *a, **k: {'writes': {}, 'deletes': []})
    monkeypatch.setattr(market, 'retire_touched', lambda *a, **k: {'paths': ['p'], 'scopes': ['region/w09-brinecove']})
    monkeypatch.setattr(market, 'affected_placements', lambda *a, **k: [])
    monkeypatch.setattr(apply_, 'require_applied_plan', lambda game, plan: calls.setdefault('applied', plan))
    monkeypatch.setattr(apply_.authority, 'authorize', lambda paths, claim, what, scopes: calls.setdefault('auth', scopes))
    monkeypatch.setattr(apply_, 'execute', lambda game, ops, *, scopes, lockable=None: calls.setdefault('scopes', scopes))
    for stage in ('groups', 'records'):
        calls.clear()
        market.retire(tmp_path, {}, 'TASK', 'market1', stage, echo=lambda *_: None)
        assert calls['scopes'] == calls['auth'] == ['region/w09-brinecove'] and calls['applied'] == {}


def test_retire_refuses_a_plan_that_is_not_the_applied_batch(monkeypatch, tmp_path):
    """A batch name reused with another --only selection must not retire tiles whose replacements were never imported."""
    import brinecove_split_apply as apply_
    monkeypatch.setattr(apply_, 'EXPECTED', apply_.EXPECTED)   # set_batch points it at the batch; restore after
    monkeypatch.setattr(market, 'check', lambda *a, **k: [])
    monkeypatch.setattr(apply_, 'execute', lambda *a, **k: pytest.fail('retire wrote without the applied plan'))
    with pytest.raises(apply_.SplitError, match='differs from the applied selection'):
        market.retire(tmp_path, {'parts': {}, 'tiles': {}, 'selection': ['market-stall-01']}, 'TASK', 'market1',
                      echo=lambda *_: None)


def test_a_negative_coordinate_and_its_twin_take_distinct_meshes():
    """apply.mesh_name drops the minus (town1 saved town-lower-hall--1-2-1 as SM_BC_TownLowerHall121); the twin gets P."""
    assert market.part_mesh('town-lower-hall--1-2-1', False) == 'SM_BC_TownLowerHall121'
    assert market.part_mesh('town-lower-hall-1-2-1', False) == 'SM_BC_TownLowerHallP121'
    assert market.part_mesh('town-lower-hall-1-2-1', True) == 'SM_BC_TownLowerHallP121_Soft'
    assert market.part_mesh('market-stall-01', False) == 'SM_BC_MarketStall01'
    names = [market.part_mesh(o, soft) for o in market.ALL_OBJECTS for soft in (False, True)]
    assert len(names) == len(set(names))


def test_a_part_never_takes_another_records_package(tmp_path):
    import brinecove_split_apply as apply_
    record = tmp_path / 'assets/prop/brinecove/town-lower-hall--1-2-1/asset.toml'
    record.parent.mkdir(parents=True)
    record.write_text('id = "prop/brinecove/town-lower-hall--1-2-1"\n[[outputs]]\n'
                      'package = "/Game/Brinecove/Meshes/SM_BC_TownLowerHall121"\n')
    part = {'record': 'prop/brinecove/town-lower-hall-1-2-1', 'package': '/Game/Brinecove/Meshes/SM_BC_TownLowerHall121'}
    with pytest.raises(apply_.SplitError, match='would overwrite'):
        market.check_packages(tmp_path, {('town-lower-hall-1-2-1', False): part})
    with pytest.raises(apply_.SplitError, match='both name the package'):
        market.check_packages(tmp_path, {1: part, 2: {**part, 'record': 'prop/brinecove/other'}})
    market.check_packages(tmp_path, {1: {**part, 'record': 'prop/brinecove/town-lower-hall--1-2-1'}})


# --- the placements stage: found after the groups stage, deleted once, idempotent ---------------------------------------------

PLACEMENT = 'object/brinecove/townlower-1-2'
PACKAGE = '/Game/__ExternalActors__/V2/Maps/Slice/1/H9/PLACEMENT01'


def placement_game(tmp_path: Path, record_refs: list[str], objects_toml: str = '') -> Path:
    """A minimal game: one saved placement record (the real record's shape) and the region's objects.toml."""
    import brinecove_split_apply as apply_
    folder = tmp_path / 'assets' / 'object' / 'brinecove' / 'townlower-1-2'
    folder.mkdir(parents=True)
    refs = ', '.join(f'"{r}"' for r in record_refs)
    (folder / 'asset.toml').write_text(
        'schema = 1\n'
        f'id = "{PLACEMENT}"\nkind = "placement"\nauthority = "editor"\nowner = "region/{apply_.REGION}"\n'
        f'references = [{refs}]\n\n[[outputs]]\npackage = "{PACKAGE}"\n')
    (folder / 'verified.json').write_text('{}\n')
    region = tmp_path / 'world' / 'regions' / apply_.REGION
    region.mkdir(parents=True)
    (region / 'objects.toml').write_text(objects_toml)
    return tmp_path


def emptied_plan(stem: str, record: str) -> dict:
    return {'remainders': {stem: None}, 'tiles': {stem: {'record': record, 'owner': 'region/w09-brinecove',
                                                        'package': '/Game/Brinecove/Meshes/SM_BC_X'}}}


def test_placements_are_found_from_their_records_after_the_groups_stage(tmp_path):
    """The groups stage drops the emptied group from objects.toml; the record still names the tile, so the placement is found."""
    game = placement_game(tmp_path, ['prop/brinecove/town-lower-1-2', 'prop/brinecove/town-lower-1-2-soft'],
                          objects_toml='[[objects]]\nid = "' + PLACEMENT + '"\ngroups = ["SM_BC_TownLower_1_2_Piece00"]\n')
    plan = emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')
    assert market.affected_placements(game, plan) == [PLACEMENT]
    other = emptied_plan('TownLower_9_9', 'prop/brinecove/town-lower-9-9')
    assert market.affected_placements(game, other) == []                   # a record of another tile is not touched


def test_placements_listed_only_in_objects_toml_are_found_before_the_groups_stage(tmp_path):
    game = placement_game(tmp_path, [], objects_toml='[[objects]]\nid = "' + PLACEMENT + '"\ngroups = ["SM_BC_TownLower_1_2"]\n')
    assert market.affected_placements(game, emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')) == [PLACEMENT]


def test_a_placement_on_two_batches_is_listed_once(tmp_path):
    game = placement_game(tmp_path, ['prop/brinecove/town-lower-1-2', 'prop/brinecove/town-lower-2-2'])
    plans = [('town2', emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')),
             ('town3', emptied_plan('TownLower_2_2', 'prop/brinecove/town-lower-2-2'))]
    assert market.placement_ids(game, plans) == [PLACEMENT]


def test_placements_touch_the_record_folder_and_its_packages_then_nothing(tmp_path):
    """Deletes are the placement's folder files and its actor package files that exist; a rerun finds nothing to delete."""
    game = placement_game(tmp_path, ['prop/brinecove/town-lower-1-2'])
    info = market.placements_touched(game, [PLACEMENT])
    assert f'games/yorimichi_v2/assets/object/brinecove/townlower-1-2/asset.toml' in info['paths']
    assert f'games/yorimichi_v2/assets/object/brinecove/townlower-1-2/verified.json' in info['paths']
    assert ('asset/' + PLACEMENT, 'region/w09-brinecove') in info['scopes']
    assert all(p.startswith('games/yorimichi_v2/') for p in info['paths'])
    # a package file that exists is deleted; the absent companions are not listed as deletes
    package = (tmp_path / 'unreal' / 'Content' / PACKAGE.removeprefix('/Game/')).with_suffix('.umap')
    package.parent.mkdir(parents=True)
    package.write_bytes(b'x')
    ops = market.placements_compute(game, market.placements_touched(game, [PLACEMENT]))
    assert ops['writes'] == {}
    assert 'games/yorimichi_v2' not in ''.join(ops['deletes'])               # the game-relative form, not the repo's
    assert set(ops['deletes']) >= {'assets/object/brinecove/townlower-1-2/asset.toml',
                                   'assets/object/brinecove/townlower-1-2/verified.json',
                                   'unreal/Content/__ExternalActors__/V2/Maps/Slice/1/H9/PLACEMENT01.umap'}
    for rel in ops['deletes']:
        (game / rel).unlink()
    assert market.affected_placements(game, emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')) == []
    assert market.placements_compute(game, market.placements_touched(game, [PLACEMENT]))['deletes'] == []


def test_batches_with_nothing_emptied_are_a_no_op(monkeypatch, tmp_path):
    import brinecove_split_apply as apply_
    monkeypatch.setattr(market, 'check', lambda *a, **k: pytest.fail('checked a batch with nothing emptied'))
    monkeypatch.setattr(apply_, 'execute', lambda *a, **k: pytest.fail('wrote a batch with nothing emptied'))
    plan = {'remainders': {'A': {'triangles': 3}}, 'tiles': {}}
    assert market.retire_placements(tmp_path, [('market1', plan)], 'TASK', None, echo=lambda *_: None) == {'written': [], 'deleted': []}


def test_placements_refuse_before_the_groups_stage(monkeypatch, tmp_path):
    import brinecove_split_apply as apply_
    monkeypatch.setattr(apply_, 'EXPECTED', apply_.EXPECTED)   # set_batch points it at the batch; restore after
    monkeypatch.setattr(market, 'check', lambda *a, **k: [])
    monkeypatch.setattr(apply_, 'require_applied_plan', lambda game, plan: None)
    monkeypatch.setattr(market, 'groups_retired', lambda game, plan: False)
    monkeypatch.setattr(apply_, 'execute', lambda *a, **k: pytest.fail('deleted before the groups stage'))
    plan = emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')
    with pytest.raises(apply_.SplitError, match='groups stage is not done'):
        market.retire_placements(tmp_path, [('town2', plan)], 'TASK', None, echo=lambda *_: None)


def test_groups_stage_done_is_read_from_objects_toml_and_runtime(tmp_path):
    import brinecove_split_apply as apply_
    game = placement_game(tmp_path, [], objects_toml='[[objects]]\nid = "x"\ngroups = ["SM_BC_TownLower_1_2"]\n')
    runtime = tmp_path / 'unreal' / 'Content' / apply_.RUNTIME
    runtime.parent.mkdir(parents=True)
    runtime.write_text(json.dumps({'groups': [{'asset': '/Game/Brinecove/Meshes/SM_BC_TownLower_1_2.SM_BC_TownLower_1_2'}]}))
    plan = emptied_plan('TownLower_1_2', 'prop/brinecove/town-lower-1-2')
    assert market.groups_retired(game, plan) is False
    (game / 'world' / 'regions' / apply_.REGION / 'objects.toml').write_text('')
    assert market.groups_retired(game, plan) is False                       # the runtime file still draws it
    runtime.write_text(json.dumps({'groups': []}))
    assert market.groups_retired(game, plan) is True


def test_check_for_the_groups_stage_allows_the_tile_record_to_remain(monkeypatch, tmp_path):
    """After the groups stage the emptied tile record still exists: only the records stage (`retired`) may demand its removal."""
    import brinecove_split_apply as apply_
    monkeypatch.setattr(apply_, 'EXPECTED', apply_.EXPECTED)   # set_batch points it at the batch; restore after
    monkeypatch.setattr(apply_, 'check', lambda game, donor: [])
    region = tmp_path / 'world' / 'regions' / apply_.REGION
    region.mkdir(parents=True)
    (region / 'split-market1.json').write_text(json.dumps({'tiles': {'A': {'remainder': None, 'record': 'prop/x'}}, 'parts': {}}))
    (tmp_path / 'assets' / 'prop' / 'x').mkdir(parents=True)
    (tmp_path / 'assets' / 'prop' / 'x' / 'asset.toml').write_text('schema = 1\n')
    runtime = tmp_path / 'unreal' / 'Content' / apply_.RUNTIME
    runtime.parent.mkdir(parents=True)
    runtime.write_text(json.dumps({'groups': []}))
    assert market.check(tmp_path, None, 'market1', groups=True) == []
    assert any('should be retired' in p for p in market.check(tmp_path, None, 'market1', retired=True))


def test_batch_names_all_lists_and_checks_names():
    names = market.batch_names('all')
    assert names[:4] == ['market1', 'market2', 'market3', 'town1'] and names[-2:] == ['town9', 'props1'] and len(names) == 13
    assert market.batch_names('town2, market1,town2') == ['town2', 'market1']
    with pytest.raises(market.MarketError, match='unknown batch town99'):
        market.batch_names('town99')


def test_the_props1_batch_names_each_harbour_prop_once():
    """The props1 objects are the rowboat, buoy and potted-palm loop bodies of procedural/props.py, named by side and |x|."""
    names = market.BATCHES['props1']
    assert len(names) == len(set(names)) == 13
    assert all(market.component_of(n) == 'Props' for n in names)
    assert market.object_name('Props', 'rowboat-w155') == 'props-rowboat-w155'
    assert sum(n.startswith('props-rowboat-') for n in names) == 4
    assert sum(n.startswith('props-buoy-') for n in names) == 3
    assert sum(n.startswith('props-potted-palm-') for n in names) == 6


@pytest.mark.skipif(not DONOR or not Path(DONOR).is_dir(), reason='needs the donor export (YV2_DONOR_BUILD)')
def test_donor_props1_parts_are_whole_and_leave_the_batch1_cuts_alone():
    """Every props1 object is matched in the donor tiles (each palm a hard part and its fronds' Soft part) and the tiles
    still partition with batch 1's cannon, anchor and net-rack cuts taken first."""
    donor = Path(DONOR)
    src = market.donor_source(donor)
    prior = {'cannon-west', 'cannon-east', 'quay-anchor', 'net-rack-west', 'net-rack-east'}
    done = market.compute(donor / 'brinecove' / 'glb', src, list(market.BATCHES['props1']), prior)
    assert done['problems'] == []
    counts = {}
    for owned in done['owned'].values():
        for name, members in owned.items():
            if name:
                counts[name] = counts.get(name, 0) + len(members)
    assert counts['props-rowboat-w155'] == 96 and counts['props-buoy-w90'] == 100
    assert counts['props-potted-palm-w300'] == 206 + 30
