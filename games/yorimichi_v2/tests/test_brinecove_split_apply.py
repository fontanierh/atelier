"""Brine Cove split batch 1: the pure parts of the planner (objects.toml and runtime-file edits, placement check)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_split_apply as apply  # noqa: E402


def part(obj, soft=False, tiles=('Props_3_3',), triangles=10):
    return {'object': obj, 'soft': soft, 'record': apply.record_id(obj, soft), 'mesh': apply.mesh_name(obj, soft),
            'package': apply.MESHES + apply.mesh_name(obj, soft), 'triangles': triangles, 'tiles': list(tiles),
            'slots': [apply.MATERIALS + 'MI_BC_wood'], 'sha256': '0' * 64, 'materials': ['BC_wood'], 'min': [0, 0, 0],
            'max': [1, 1, 1], 'share': {t: triangles for t in tiles}}


def group(name, collision=True, translation=(0.0, 0.0, 0.0)):
    return {'asset': f'/Game/Brinecove/Meshes/{name}.{name}', 'collision': collision, 'cull_cm': 120000,
            'materials': ['/Game/Brinecove/Materials/MI_BC_wood.MI_BC_wood', '/Game/Brinecove/Materials/MI_BC_rope.MI_BC_rope'],
            'plant': False, 'shadow': True,
            'transforms': [{'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1], 'translation_cm': list(translation)}]}


def plan():
    return {'parts': {('cannon-west', False): part('cannon-west'), ('crane-west', False): part('crane-west', tiles=('Harbor_2_3',)),
                      ('crane-west', True): part('crane-west', True, tiles=('Harbor_2_3_Soft',))},
            'remainders': {'Props_3_3': {'slots': [apply.MATERIALS + 'MI_BC_rope'], 'triangles': 5},
                           'Harbor_2_3': {'slots': [apply.MATERIALS + 'MI_BC_wood'], 'triangles': 3},
                           'Harbor_2_3_Soft': None,
                           'Ships_4_3': None},
            'tiles': {}}


def test_names():
    assert apply.mesh_name('galleon-nightjar', False) == 'SM_BC_GalleonNightjar'
    assert apply.mesh_name('crane-west', True) == 'SM_BC_CraneWest_Soft'
    assert apply.record_id('crane-west', True) == 'prop/brinecove/crane-west-soft'
    assert apply.tile_record('Harbor_5_3_Soft') == 'prop/brinecove/harbor-5-3-soft'
    assert apply.tile_record('Market_3_4_Piece130') == 'prop/brinecove/market-3-4-piece130'


def test_runtime_edit_adds_parts_updates_remainders_and_drops_retired():
    data = {'groups': [group('SM_BC_Props_3_3'), group('SM_BC_Harbor_2_3'), group('SM_BC_Harbor_2_3_Soft', collision=False),
                       group('SM_BC_Ships_4_3'), group('SM_BC_Other_1_1')]}
    kept = apply.edit_runtime(data, plan())
    assert 'SM_BC_Ships_4_3' in apply.group_names(kept)             # apply keeps what the saved actor still draws
    out = apply.edit_runtime(data, plan(), retire=True)
    names = apply.group_names(out)
    assert 'SM_BC_Ships_4_3' not in names and 'SM_BC_Harbor_2_3_Soft' not in names      # retired tiles
    assert names.count('SM_BC_CannonWest') == 1 and names.count('SM_BC_CraneWest') == 1
    assert names.count('SM_BC_CraneWest_Soft') == 1 and 'SM_BC_Other_1_1' in names
    cannon = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_CannonWest.SM_BC_CannonWest'))
    assert cannon['collision'] is True and cannon['transforms'] == data['groups'][0]['transforms']
    soft = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_CraneWest_Soft.SM_BC_CraneWest_Soft'))
    assert soft['collision'] is False
    tile = next(g for g in out['groups'] if g['asset'].endswith('SM_BC_Props_3_3.SM_BC_Props_3_3'))
    assert tile['materials'] == ['/Game/Brinecove/Materials/MI_BC_rope.MI_BC_rope']        # the remainder's slots


def test_runtime_edit_is_idempotent():
    data = {'groups': [group('SM_BC_Props_3_3'), group('SM_BC_Harbor_2_3'), group('SM_BC_Harbor_2_3_Soft', collision=False)]}
    once = apply.edit_runtime(data, plan())
    assert apply.edit_runtime(once, plan()) == once


HEAD = '''# head
schema = 1
tag = "brinecove"
data = "brinecove/runtime.json"

[[objects]]
id = "object/brinecove/wreck"
group = "SM_BC_Ships_2_2"
model = "prop/brinecove/wreck"
about = "the wreck"

'''
TAIL = apply.MARKER + ''' (rerun to regenerate) ---

[[objects]]
id = "object/brinecove/ships-nightjar-sloop"
groups = ["SM_BC_Ships_4_2", "SM_BC_Ships_4_3"]
model = "adopted/brinecove/ships-nightjar-sloop"
about = "ships"

[[objects]]
id = "object/brinecove/props-3-3"
group = "SM_BC_Props_3_3"
model = "prop/brinecove/props-3-3"
about = "props"
'''


def test_objects_toml_edit_adds_objects_retires_ships_and_is_idempotent():
    import tomllib
    kept = tomllib.loads(apply.edit_objects_toml(HEAD + TAIL, plan()))['objects']
    assert 'object/brinecove/ships-nightjar-sloop' in {i['id'] for i in kept}      # apply leaves the ship actor's entry
    text = apply.edit_objects_toml(HEAD + TAIL, plan(), retire=True)
    items = tomllib.loads(text)['objects']
    ids = [i['id'] for i in items]
    assert 'object/brinecove/ships-nightjar-sloop' not in ids
    assert ids.count('object/brinecove/cannon-west') == 1 and 'object/brinecove/wreck' in ids
    crane = next(i for i in items if i['id'] == 'object/brinecove/crane-west')
    assert crane['groups'] == ['SM_BC_CraneWest', 'SM_BC_CraneWest_Soft']
    assert crane['model'] == ['prop/brinecove/crane-west', 'prop/brinecove/crane-west-soft']
    assert apply.edit_objects_toml(text, plan(), retire=True) == text


def test_expected_shape():
    p = plan()
    p['tiles'] = {'Props_3_3': {'record': 'prop/brinecove/props-3-3', 'package': '/Game/x', 'triangles': 15, 'owner': 'o',
                                'references': [], 'settings': {}, 'material_package': {}}}
    p['remainders'] = {'Props_3_3': {'sha256': 'a', 'triangles': 5, 'materials': ['BC_rope']}}
    p['parts'] = {('cannon-west', False): part('cannon-west', triangles=10)}
    exp = apply.expected(p)
    assert exp['shares']['Props_3_3'] == {'prop/brinecove/cannon-west': 10}
    assert 5 + 10 == exp['tiles']['Props_3_3']['source_triangles']


# --- claim, preflight, journal ------------------------------------------------------------------------------------------

import hashlib  # noqa: E402

import authority  # noqa: E402
import pytest  # noqa: E402


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def mini_game(tmp_path, runtime=True):
    """A game tree with one tile record's worth of files: enough for compute() and the claim checks."""
    game = tmp_path / 'game'
    (game / 'world/regions/w09-brinecove').mkdir(parents=True)
    (game / 'world/regions/w09-brinecove/objects.toml').write_text(HEAD + TAIL)
    (game / 'unreal/Content/Data/brinecove').mkdir(parents=True)
    data_file = game / 'unreal/Content/Data/brinecove/runtime.json'
    if runtime:
        data_file.write_text(json.dumps({'groups': [group('SM_BC_Props_3_3')]}))
    else:
        data_file.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:aa\nsize 5\n')
    (game / 'runtime-data.lock.json').write_text('{}')
    return game


def small_plan(tmp_path):
    staged = tmp_path / 'stage'
    staged.mkdir(exist_ok=True)
    glb = staged / 'SM_BC_CannonWest.glb'
    glb.write_bytes(b'glTF-part')
    rest = staged / 'SM_BC_Props_3_3.glb'
    rest.write_bytes(b'glTF-rest')
    p = part('cannon-west')
    p.update({'file': glb, 'tile': {'settings': {'collision': 'complex'}, 'references': ['adopted/brinecove/materials']}})
    tile = {'record': 'prop/brinecove/props-3-3', 'owner': 'shared/brinecove/props-3-3', 'package': '/Game/Brinecove/Meshes/SM_BC_Props_3_3',
            'references': ['adopted/brinecove/materials'], 'settings': {'collision': 'complex', 'triangles': 15},
            'triangles': 15, 'material_package': {}}
    return {'parts': {('cannon-west', False): p}, 'tiles': {'Props_3_3': tile},
            'remainders': {'Props_3_3': {'file': rest, 'sha256': 'b' * 64, 'triangles': 5, 'materials': ['BC_rope'],
                                         'slots': [apply.MATERIALS + 'MI_BC_rope']}}}


def allow(monkeypatch, seen=None):
    def fake(paths, claim, what, *, scopes=(), repo=None):
        if seen is not None:
            seen.update(paths=list(paths), claim=claim, scopes=list(scopes))
    monkeypatch.setattr(apply.authority, 'authorize', fake)


def test_touched_set_lists_records_sources_packages_and_data(tmp_path):
    game = mini_game(tmp_path)
    info = apply.touched(game, small_plan(tmp_path))
    paths = set(info['paths'])
    g = apply.GAME_REL
    assert f'{g}/assets/prop/brinecove/cannon-west/asset.toml' in paths
    assert f'{g}/assets/prop/brinecove/cannon-west/src/SM_BC_CannonWest.glb' in paths
    assert f'{g}/unreal/Content/Brinecove/Meshes/SM_BC_CannonWest.uasset' in paths          # the part's generated package
    assert f'{g}/unreal/Content/Brinecove/Meshes/SM_BC_Props_3_3.uasset' in paths           # the changed tile's package
    assert f'{g}/assets/prop/brinecove/props-3-3/src/SM_BC_Props_3_3.glb' in paths
    assert {f'{g}/unreal/Content/Data/brinecove/runtime.json', f'{g}/runtime-data.lock.json',
            f'{g}/world/regions/w09-brinecove/objects.toml', f'{g}/world/regions/w09-brinecove/split-batch1.json'} <= paths
    assert info['paths'] == sorted(info['paths']) and 'region/w09-brinecove' in info['scopes']
    assert ('asset/prop/brinecove/cannon-west', 'shared/brinecove/cannon-west') in info['scopes']


def test_default_batch_holds_back_the_ships_and_only_selects_exactly():
    names = list(apply.select())
    assert 'galleon-nightjar' not in names and 'sloop-east' not in names and 'cannon-west' in names
    assert len(names) == 11
    assert list(apply.select(['sloop-east'])) == ['sloop-east']
    with pytest.raises(apply.SplitError):
        apply.select(['no-such-object'])


def test_apply_without_a_claim_leaves_the_tree_byte_identical(tmp_path, monkeypatch):
    game = mini_game(tmp_path)
    before = snapshot(game)
    monkeypatch.delenv('ATELIER_AGENT', raising=False)       # no claim and not the D04 writer: the authority path refuses
    with pytest.raises(apply.SplitError):
        apply.run_step(game, small_plan(tmp_path), None)
    assert snapshot(game) == before and not (game / apply.JOURNAL).exists()


def test_apply_with_an_unverified_claim_leaves_the_tree_byte_identical(tmp_path, monkeypatch):
    game = mini_game(tmp_path)
    before = snapshot(game)

    def refuse(paths, claim, what, *, scopes=(), repo=None):
        raise authority.Unauthorized('claim T does not exactly cover these paths with verified locks')
    monkeypatch.setattr(apply.authority, 'authorize', refuse)
    with pytest.raises(apply.SplitError, match='verified locks'):
        apply.run_step(game, small_plan(tmp_path), 'T')
    assert snapshot(game) == before


def test_missing_runtime_input_leaves_the_tree_byte_identical(tmp_path, monkeypatch):
    allow(monkeypatch)
    game = mini_game(tmp_path, runtime=False)
    before = snapshot(game)
    with pytest.raises(apply.SplitError, match='not hydrated'):
        apply.run_step(game, small_plan(tmp_path), 'T')
    assert snapshot(game) == before
    (game / 'unreal/Content/Data/brinecove/runtime.json').write_text('{"nope": 1}')
    before = snapshot(game)
    with pytest.raises(apply.SplitError, match='not a valid'):
        apply.run_step(game, small_plan(tmp_path), 'T')
    assert snapshot(game) == before


def test_claimed_apply_writes_everything_once_and_never_deletes(tmp_path, monkeypatch):
    seen = {}
    allow(monkeypatch, seen)
    game = mini_game(tmp_path)
    pkg = game / 'unreal/Content/Brinecove/Meshes'
    pkg.mkdir(parents=True)
    (pkg / 'SM_BC_Props_3_3.uasset').write_bytes(b'old-tile-package')
    plan = small_plan(tmp_path)
    done = apply.run_step(game, plan, 'T', lockable=lambda g, rels: [])
    assert seen['claim'] == 'T' and f'{apply.GAME_REL}/unreal/Content/Data/brinecove/runtime.json' in seen['paths']
    assert 'assets/prop/brinecove/cannon-west/src/SM_BC_CannonWest.glb' in done['written'] and not done['deleted']
    assert (pkg / 'SM_BC_Props_3_3.uasset').read_bytes() == b'old-tile-package'      # the package waits for its import
    names = apply.group_names(json.loads((game / 'unreal/Content/Data/brinecove/runtime.json').read_text()))
    assert names.count('SM_BC_CannonWest') == 1 and names.count('SM_BC_Props_3_3') == 1
    assert not (game / apply.JOURNAL).exists()
    after = snapshot(game)
    assert apply.run_step(game, plan, 'T', lockable=lambda g, rels: [])['written'] == []       # a rerun changes nothing
    assert snapshot(game) == after


def test_only_the_held_lockable_files_become_writable(tmp_path, monkeypatch):
    allow(monkeypatch)
    game = mini_game(tmp_path)
    runtime = game / 'unreal/Content/Data/brinecove/runtime.json'
    other = game / 'world/regions/w09-brinecove/objects.toml'
    runtime.chmod(0o444)
    other.chmod(0o444)                                         # read-only and not lockable: apply must not unlock it
    before = snapshot(game)
    with pytest.raises(PermissionError):
        apply.run_step(game, small_plan(tmp_path), 'T', lockable=lambda g, rels: [r for r in rels if r.endswith('runtime.json')])
    assert not runtime.stat().st_mode & 0o200 and not other.stat().st_mode & 0o200      # modes restored with the bytes
    assert snapshot(game) == before                            # the failure restored everything the journal held
    other.chmod(0o644)
    apply.run_step(game, small_plan(tmp_path), 'T', lockable=lambda g, rels: [r for r in rels if r.endswith('runtime.json')])
    assert 'SM_BC_CannonWest' in runtime.read_text()


def test_a_failed_write_restores_every_file(tmp_path, monkeypatch):
    allow(monkeypatch)
    game = mini_game(tmp_path)
    before = snapshot(game)
    real = Path.write_bytes
    calls = {'n': 0}

    def flaky(self, data):
        calls['n'] += 1
        if calls['n'] == 4:
            raise PermissionError('locked')
        return real(self, data)
    monkeypatch.setattr(Path, 'write_bytes', flaky)
    with pytest.raises(PermissionError):
        apply.run_step(game, small_plan(tmp_path), 'T', lockable=lambda g, rels: [])
    monkeypatch.setattr(Path, 'write_bytes', real)
    assert snapshot(game) == before and not (game / apply.JOURNAL).exists()


def test_paths_list_only_what_changes(tmp_path, monkeypatch):
    allow(monkeypatch)
    game = mini_game(tmp_path)
    plan = small_plan(tmp_path)
    apply.run_step(game, plan, 'T', lockable=lambda g, rels: [])
    assert apply.touched(game, plan)['paths'] == []                 # applied and unchanged: nothing to claim
    assert apply.run_step(game, plan, 'T') == {'written': [], 'deleted': []}   # and no claim check, no write
    plan['remainders']['Props_3_3']['file'].write_bytes(b'glTF-rest-2')        # the remainder changes
    plan['remainders']['Props_3_3']['triangles'] = 4
    paths = set(apply.touched(game, plan)['paths'])
    g = apply.GAME_REL
    assert f'{g}/assets/prop/brinecove/props-3-3/src/SM_BC_Props_3_3.glb' in paths
    assert f'{g}/unreal/Content/Brinecove/Meshes/SM_BC_Props_3_3.uasset' in paths
    assert not any('cannon-west' in p for p in paths)               # the unchanged part is not touched


def stale_plan(tmp_path, game):
    plan = small_plan(tmp_path)
    plan['stale'] = [{'record': 'prop/brinecove/crane-west-soft', 'mesh': 'SM_BC_CraneWest_Soft',
                      'package': apply.MESHES + 'SM_BC_CraneWest_Soft', 'object': 'crane-west'}]
    plan['resave'] = ['object/brinecove/crane-west']
    (game / 'assets/prop/brinecove/crane-west-soft/src').mkdir(parents=True)
    (game / 'assets/prop/brinecove/crane-west-soft/asset.toml').write_text(
        'schema = 1\nid = "prop/brinecove/crane-west-soft"\nkind = "static-mesh"\nauthority = "generated"\n'
        'owner = "shared/brinecove/crane-west-soft"\n[[sources]]\npath = "src/x.glb"\nsha256 = "' + '0' * 64 + '"\n'
        '[recipe]\nimporter = "static-mesh"\nversion = 1\n[[outputs]]\npackage = "/Game/Brinecove/Meshes/SM_BC_CraneWest_Soft"\n')
    (game / 'assets/prop/brinecove/crane-west-soft/src/x.glb').write_bytes(b'x')
    (game / 'assets/object/brinecove/crane-west').mkdir(parents=True)
    (game / 'assets/object/brinecove/crane-west/asset.toml').write_text(
        'schema = 1\nid = "object/brinecove/crane-west"\nkind = "placement"\nauthority = "editor"\n'
        'owner = "region/w09-brinecove"\n[[outputs]]\npackage = "/Game/__ExternalActors__/V2/Maps/Slice/1/AB/ACTOR"\n')
    pkg = game / 'unreal/Content/Brinecove/Meshes'
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / 'SM_BC_CraneWest_Soft.uasset').write_bytes(b'soft')
    actor = game / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/1/AB'
    actor.mkdir(parents=True)
    (actor / 'ACTOR.uasset').write_bytes(b'actor')
    (game / 'world/regions/w09-brinecove/objects.saved.json').write_text(
        json.dumps({'schema': 1, 'objects': {'object/brinecove/crane-west': {'id': 'x'}, 'object/brinecove/other': {}}}))
    return plan


def test_apply_keeps_stale_parts_and_retire_removes_them_with_the_resaved_object(tmp_path, monkeypatch):
    allow(monkeypatch)
    game = mini_game(tmp_path)
    plan = stale_plan(tmp_path, game)
    apply.run_step(game, plan, 'T', lockable=lambda g, rels: [])
    assert (game / 'assets/prop/brinecove/crane-west-soft/asset.toml').is_file()          # apply deletes nothing
    assert (game / 'unreal/Content/Brinecove/Meshes/SM_BC_CraneWest_Soft.uasset').is_file()
    info = apply.touched(game, plan, retire=True)
    g = apply.GAME_REL
    assert {f'{g}/assets/prop/brinecove/crane-west-soft/asset.toml', f'{g}/assets/object/brinecove/crane-west/asset.toml',
            f'{g}/unreal/Content/Brinecove/Meshes/SM_BC_CraneWest_Soft.uasset',
            f'{g}/unreal/Content/__ExternalActors__/V2/Maps/Slice/1/AB/ACTOR.uasset',
            f'{g}/world/regions/w09-brinecove/objects.saved.json'} <= set(info['paths'])
    done = apply.run_step(game, plan, 'T', retire=True, lockable=lambda g, rels: [])
    assert not (game / 'assets/prop/brinecove/crane-west-soft').exists() or not any(
        (game / 'assets/prop/brinecove/crane-west-soft').rglob('*.*'))
    assert not (game / 'unreal/Content/Brinecove/Meshes/SM_BC_CraneWest_Soft.uasset').exists()
    assert not (game / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/1/AB/ACTOR.uasset').exists()
    saved = json.loads((game / 'world/regions/w09-brinecove/objects.saved.json').read_text())['objects']
    assert list(saved) == ['object/brinecove/other']                                       # only the resaved object left it
    assert 'SM_BC_CraneWest_Soft' not in apply.group_names(
        json.loads((game / 'unreal/Content/Data/brinecove/runtime.json').read_text()))
    assert done['deleted']


def test_objects_step_needs_one_claim_with_both_regions(tmp_path):
    step = apply.objects_step(mini_game(tmp_path), small_plan(tmp_path))
    assert step['scopes'] == {'region/w09-brinecove', 'region/w00-island'}
    assert f'{apply.GAME_REL}/world/regions/w09-brinecove/objects.saved.json' in step['paths']


def test_a_tile_nothing_takes_from_any_more_goes_back_to_its_donor_record_text():
    tile = {'record': 'prop/brinecove/harbor-2-3-soft', 'owner': 'shared/brinecove/harbor-2-3-soft',
            'package': '/Game/Brinecove/Meshes/SM_BC_Harbor_2_3_Soft', 'references': ['adopted/brinecove/materials'],
            'settings': {'slot_materials': [apply.MATERIALS + 'MI_BC_palm_frond'], 'triangles': 90, 'full_precision_uvs': True}}
    rem = {'file': Path('x.glb'), 'triangles': 90, 'slots': tile['settings']['slot_materials'], 'restored': True}
    gen = apply.tile_generated('Harbor_2_3_Soft', tile, rem)
    assert gen.about == 'SM_BC_Harbor_2_3_Soft: one Brine Cove mesh (90 triangles)'
    assert list(gen.settings) == ['slot_materials', 'triangles', 'full_precision_uvs']
