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
            'triangles': 15, 'material_package': {}, 'source': {'name': 'SM_BC_Props_3_3.glb', 'sha256': 'a' * 64}}
    return {'parts': {('cannon-west', False): p}, 'tiles': {'Props_3_3': tile},
            'remainders': {'Props_3_3': {'file': rest, 'sha256': 'b' * 64, 'triangles': 5, 'materials': ['BC_rope'],
                                         'slots': [apply.MATERIALS + 'MI_BC_rope'], 'kept': [0, 1, 2, 3, 4], 'total': 15}}}


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
    assert f'{g}/assets/prop/brinecove/props-3-3/src/SM_BC_Props_3_3.carve.json' in paths
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


@pytest.fixture
def accepted_import(tmp_path):
    """A replacement with an accepted import and a separate package companion, without an Unreal process."""
    from types import SimpleNamespace
    game = tmp_path / 'game'
    folder = game / 'assets/prop/brinecove/cannon-west'
    (folder / 'src').mkdir(parents=True)
    source = folder / 'src/part.glb'
    source.write_bytes(b'original source')
    asset = apply.records.Asset(
        id='prop/brinecove/cannon-west', kind='static-mesh', authority='generated',
        owner='shared/brinecove/cannon-west', folder=folder,
        sources=[apply.records.Source('src/part.glb', apply.records.sha256_file(source))],
        recipe={'importer': 'static-mesh', 'version': 1, 'settings': {'triangles': 10}},
        outputs=[apply.records.Output('/Game/Brinecove/Meshes/SM_BC_CannonWest', 'generated')])
    primary = apply.records.package_files(game, asset.outputs[0].package)[0]
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b'accepted package')
    companion = primary.with_suffix('.uexp')
    companion.write_bytes(b'accepted companion')
    receipt = {'schema': apply.records.SCHEMA, 'kind': 'imported', 'engine': 'test',
               'input_fingerprint': apply.records.input_fingerprint(asset, {}),
               'files': {p.relative_to(game).as_posix(): apply.records.sha256_file(p) for p in (primary, companion)}}
    asset.verified.write_text(json.dumps(receipt))
    return SimpleNamespace(game=game, asset=asset, source=source, primary=primary, companion=companion, receipt=receipt)


def test_retirement_accepts_only_the_current_import(accepted_import):
    case = accepted_import
    assert apply.import_problems(case.game, case.asset) == []
    # A second apply pins a changed source but leaves the old import receipt and package bytes in place.
    case.source.write_bytes(b'revised source')
    case.asset.sources = [apply.records.Source('src/part.glb', apply.records.sha256_file(case.source))]
    assert any('import is stale' in p for p in apply.import_problems(case.game, case.asset))


def test_retirement_refuses_a_changed_recipe(accepted_import):
    case = accepted_import
    case.asset.recipe['settings']['triangles'] = 12
    assert any('import is stale' in p for p in apply.import_problems(case.game, case.asset))


@pytest.mark.parametrize('change', ['changed', 'missing', 'missing-companion', 'unrecorded-companion', 'omitted-package',
                                  'editor-receipt', 'missing-receipt'])
def test_retirement_refuses_unaccepted_output_bytes(accepted_import, change):
    case = accepted_import
    if change == 'changed':
        case.primary.write_bytes(b'changed after acceptance')
    elif change == 'missing':
        case.primary.unlink()
    elif change == 'missing-companion':
        case.companion.unlink()
    elif change == 'unrecorded-companion':
        case.primary.with_suffix('.ubulk').write_bytes(b'not in the accepted receipt')
    elif change == 'omitted-package':
        del case.receipt['files'][case.primary.relative_to(case.game).as_posix()]
        case.asset.verified.write_text(json.dumps(case.receipt))
    elif change == 'editor-receipt':
        case.receipt['kind'] = 'editor-saved'
        case.asset.verified.write_text(json.dumps(case.receipt))
    else:
        case.asset.verified.unlink()
    assert apply.import_problems(case.game, case.asset)


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
    assert f'{g}/assets/prop/brinecove/props-3-3/src/SM_BC_Props_3_3.carve.json' in paths
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


@pytest.fixture
def cli_batch(tmp_path, monkeypatch):
    """Real tiny GLBs and records exercise separate planner/CLI calls; only claim admission and native imports are faked."""
    from types import SimpleNamespace
    game, donor, stage = mini_game(tmp_path), tmp_path / 'donor', tmp_path / 'stage'
    allow(monkeypatch)
    objects = {
        'cannon-west': dict(x=0, y=0, radius=2, tiles=('Props_3_3',)),
        'sloop-east': dict(x=0, y=0, radius=2, tiles=('Ships_4_3',)),
        'crane-west': dict(x=0, y=0, radius=2, tiles=('Harbor_2_3', 'Harbor_2_3_Soft'))}
    monkeypatch.setattr(apply.split, 'OBJECTS', objects)
    groups = []
    for stem, count, material in [('Props_3_3', 2, 'BC_wood'), ('Ships_4_3', 1, 'BC_wood'),
                                  ('Harbor_2_3', 2, 'BC_wood'), ('Harbor_2_3_Soft', 1, 'BC_rope')]:
        positions = [(x + dx, y, z) for x in range(0, count * 10, 10)
                     for dx, y, z in [(0, 1, 0), (1, 1, 0), (0, 2, 1)]]
        model = {'materials': [material], 'prims': [{'material': 0, 'positions': positions,
                                                   'indices': list(range(count * 3))}]}
        source = donor / 'brinecove/glb' / f'SM_BC_{stem}.glb'
        source.parent.mkdir(parents=True, exist_ok=True)
        apply.split.write_subset(model, range(count), source)
        gen = apply.recover.Generated(id=apply.tile_record(stem), kind='static-mesh', owner='shared/brinecove',
            package=apply.MESHES + f'SM_BC_{stem}', source=source, references=[], about='fixture tile',
            settings={'slot_materials': [apply.MATERIALS + 'MI_' + material], 'triangles': count})
        text, name = apply.record_files(gen)
        folder = game / 'assets' / gen.id
        (folder / 'src').mkdir(parents=True)
        (folder / 'asset.toml').write_text(text)
        (folder / 'src' / name).write_bytes(source.read_bytes())
        groups.append(group(f'SM_BC_{stem}', collision=not stem.endswith('_Soft')))
    (game / 'unreal/Content/Data/brinecove/runtime.json').write_text(json.dumps({'groups': groups}))

    def accept():
        for path in apply.records.record_paths(game):
            asset = apply.records.load_asset(path)
            if asset.kind != 'static-mesh':
                continue
            fingerprint = apply.records.input_fingerprint(asset, {})
            package = apply.records.package_files(game, asset.outputs[0].package)[0]
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_bytes(('accepted ' + fingerprint).encode())
            apply.records.write_json(asset.verified, {'schema': 1, 'kind': 'imported', 'engine': 'test',
                'input_fingerprint': fingerprint,
                'files': {package.relative_to(game).as_posix(): apply.records.sha256_file(package)}})

    def actor(oid):
        folder = game / 'assets' / oid
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(f'schema = 1\nid = "{oid}"\nkind = "placement"\nauthority = "editor"\n'
            'owner = "region/w09-brinecove"\n[[outputs]]\npackage = "/Game/__ExternalActors__/V2/Maps/Slice/1/AB/ACTOR"\n')
        package = game / 'unreal/Content/__ExternalActors__/V2/Maps/Slice/1/AB/ACTOR.uasset'
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(b'saved actor')
        (game / f'world/regions/{apply.REGION}/objects.saved.json').write_text(json.dumps({'objects': {oid: {}}}))
        return package

    def run(command, selection):
        return apply.main([command, '--game', str(game), '--donor', str(donor), '--stage', str(stage),
                           '--only', selection, '--claim', 'T'])
    return SimpleNamespace(game=game, donor=donor, objects=objects, accept=accept, actor=actor, run=run)


def test_cli_retirement_refuses_a_different_applied_selection(cli_batch, capsys):
    case = cli_batch
    assert case.run('apply', 'cannon-west') == 0
    case.accept()
    case.actor(apply.RETIRED_OBJECT)
    before = snapshot(case.game)
    assert case.run('retire', 'sloop-east') == 1
    assert 'differs from the applied selection' in capsys.readouterr().err
    assert snapshot(case.game) == before               # B's exhausted tile and old actor survive A's accepted imports


def test_cli_handoff_preserves_pending_removals_until_success(cli_batch, monkeypatch):
    case = cli_batch
    assert case.run('apply', 'crane-west') == 0
    case.accept()
    actor = case.actor('object/brinecove/crane-west')
    stale = case.game / 'unreal/Content/Brinecove/Meshes/SM_BC_CraneWest_Soft.uasset'
    case.objects['crane-west']['exclude_materials'] = ['BC_rope']       # palm correction drops the old soft part
    assert case.run('apply', 'crane-west') == 0
    case.accept()
    pending = json.loads((case.game / apply.EXPECTED).read_text())['pending']
    assert [p['record'] for p in pending['stale']] == ['prop/brinecove/crane-west-soft']
    assert pending['resave'] == ['object/brinecove/crane-west']
    before = snapshot(case.game)
    assert case.run('apply', 'cannon-west') == 1        # one manifest cannot discard an outstanding batch's cleanup
    assert snapshot(case.game) == before
    real_unlink = Path.unlink

    def fail_removal(path, *args, **kwargs):
        if path == stale:
            raise PermissionError('retirement interrupted')
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', fail_removal)
    with pytest.raises(PermissionError, match='retirement interrupted'):
        case.run('retire', 'crane-west')
    assert snapshot(case.game) == before              # journal restores pending state and every deletion
    monkeypatch.setattr(Path, 'unlink', real_unlink)
    assert case.run('retire', 'crane-west') == 0        # fresh CLI/build still has the pending stale/resave work
    assert not stale.exists() and not actor.exists()
    saved = json.loads((case.game / apply.EXPECTED).read_text())
    assert saved['pending'] == {'stale': [], 'resave': []} and saved['retired'] is True
    assert case.run('apply', 'cannon-west') == 0        # the next batch is now allowed


def test_cli_check_uses_completed_ship_retirement(cli_batch):
    case = cli_batch
    case.actor(apply.RETIRED_OBJECT)
    assert case.run('apply', 'sloop-east') == 0
    case.accept()
    assert case.run('retire', 'sloop-east') == 0
    assert (case.game / 'assets' / apply.RETIRED_OBJECT).is_dir()   # empty record folders are harmless
    assert case.run('check', 'sloop-east') == 0
    runtime = case.game / 'unreal/Content/Data/brinecove/runtime.json'
    body = json.loads(runtime.read_text())
    body['groups'].append(group('SM_BC_Ships_4_3'))               # a retired tile drawn again is still a defect
    runtime.write_text(json.dumps(body))
    assert case.run('check', 'sloop-east') == 1


@pytest.fixture
def interrupted_split(tmp_path):
    from types import SimpleNamespace
    game = mini_game(tmp_path)
    old = game / 'assets/prop/brinecove/cannon-west/asset.toml'
    new = game / 'unreal/Content/Brinecove/Meshes/SM_BC_CannonWest.uasset'
    old.parent.mkdir(parents=True)
    old.write_bytes(b'original record')
    scopes = {'region/w09-brinecove', ('asset/prop/brinecove/cannon-west', 'shared/brinecove/cannon-west')}
    rels = [p.relative_to(game).as_posix() for p in (old, new)]
    journal = apply.Journal(game)
    journal.begin(rels, scopes=scopes)
    old.write_bytes(b'partial record, not parseable')
    new.parent.mkdir(parents=True)
    new.write_bytes(b'partial new package')
    return SimpleNamespace(game=game, old=old, new=new, scopes=scopes, rels=rels, journal=journal)


@pytest.mark.parametrize('claim', [None, 'stale', 'unrelated'])
def test_journal_recovery_refusal_preserves_every_byte(interrupted_split, monkeypatch, claim):
    case = interrupted_split
    before = snapshot(case.game)
    calls = []

    def refuse(paths, current_claim, what, *, scopes=(), repo=None):
        calls.append((set(paths), current_claim, set(scopes)))
        raise authority.Unauthorized('recovery claim does not cover the journal')
    monkeypatch.setattr(apply.authority, 'authorize', refuse)
    with pytest.raises(apply.SplitError, match='does not cover the journal'):
        apply.run_step(case.game, {}, claim)
    assert calls == [({f'{apply.GAME_REL}/{p}' for p in case.rels}, claim, case.scopes)]
    assert snapshot(case.game) == before             # no rollback chmod/write/delete, and backups remain available


def test_journal_recovery_uses_persisted_scopes_before_reading_partial_records(interrupted_split, monkeypatch):
    case = interrupted_split
    calls = []

    def authorize(paths, claim, what, *, scopes=(), repo=None):
        assert case.old.read_bytes() == b'partial record, not parseable' and case.new.exists()
        calls.append((set(paths), claim, set(scopes)))
    monkeypatch.setattr(apply.authority, 'authorize', authorize)

    def compute(game, plan, retire):
        assert case.old.read_bytes() == b'original record' and not case.new.exists()
        assert not case.journal.manifest.exists()
        return {'writes': {}, 'deletes': []}
    monkeypatch.setattr(apply, 'compute', compute)

    def build(*args):
        assert case.old.read_bytes() == b'original record' and not case.new.exists()
        return {}
    monkeypatch.setattr(apply, 'build', build)
    monkeypatch.setattr(apply, 'report', lambda plan: 'recovered plan')
    assert apply.main(['apply', '--game', str(case.game), '--donor', str(case.game), '--claim', 'RECOVER']) == 0
    assert calls == [({f'{apply.GAME_REL}/{p}' for p in case.rels}, 'RECOVER', case.scopes)]


def test_journal_recovery_refuses_legacy_scopeless_journal(interrupted_split, monkeypatch):
    case = interrupted_split
    legacy = json.loads(case.journal.manifest.read_text())
    del legacy['scopes']
    case.journal.manifest.write_text(json.dumps(legacy))
    before = snapshot(case.game)
    with pytest.raises(apply.SplitError, match='no valid owning scopes'):
        apply.run_step(case.game, {}, 'RECOVER')
    assert snapshot(case.game) == before
