"""The change-set report names every changed file's owner and refuses incomplete, unowned or unclaimed changes.

Each test builds a small Git repository with V2 records and stand-in packages, commits a base on `main`, makes one
change on a branch and reads the report for `main...HEAD`. Plain bytes stand in for most packages; synthetic headers
(and, when the engine is installed, a real template actor) exercise the location-based region mapping.
"""
import base64
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('v2_changeset', TOOLS / 'review' / 'changeset.py')
changeset = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = changeset
spec.loader.exec_module(changeset)

# The platform reader's own header builder, so CI covers headers without engine files.
_builder_spec = importlib.util.spec_from_file_location(
    'v2_changeset_header_builder', REPO / 'platform' / 'studio' / 'tests' / 'test_unreal_package_summary.py')
headers = importlib.util.module_from_spec(_builder_spec)
sys.modules[_builder_spec.name] = headers
_builder_spec.loader.exec_module(headers)

ACTORS = 'unreal/Content/__ExternalActors__/Maps/Island'
BENCH_ACTOR = f'{ACTORS}/0/AB/BENCH01.uasset'
BENCH = 'unreal/Content/Props/SM_Bench.uasset'
PAINT = 'unreal/Content/Materials/M_Painted.uasset'
ISLAND = 'unreal/Content/Maps/Island.umap'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)


def git(root: Path, *args):
    return subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args],
                          cwd=root, check=True, capture_output=True).stdout.decode()


class Game:
    """A games/yorimichi_v2 folder inside a temporary repository."""

    def __init__(self, root: Path):
        self.root, self.path = root, root / 'games' / 'yorimichi_v2'

    def put(self, rel: str, data):
        write(self.path / rel, data)
        return data

    def rm(self, rel: str):
        (self.path / rel).unlink()

    def record(self, rel: str, *, add=None, drop=()):
        """Edit a verification record's file list: add {path: bytes}, drop paths."""
        path = self.path / rel
        data = json.loads(path.read_text())
        for name, content in (add or {}).items():
            data['files'][name] = sha(content)
        for name in drop:
            data['files'].pop(name)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

    def region(self, name, bounds, actors=None):
        folder = f'world/regions/{name}'
        self.put(f'{folder}/region.toml', f'''schema = 1
id = "region/{name}"
bounds_cm = {json.dumps(bounds)}
neighbours = []
maps = ["/Game/Maps/Island"]
''')
        self.verified(f'{folder}/actors.verified.json', f'region/{name}', 'editor-saved', actors or {})

    def verified(self, rel, asset, kind, files):
        for name, content in files.items():
            self.put(name, content)
        body = {'schema': 1, 'kind': kind, 'asset': asset, 'engine': '5.8.0-test',
                'files': {name: sha(content) for name, content in files.items()} or {'placeholder': '0' * 64}}
        if kind == 'imported':
            body['input_fingerprint'] = '0' * 64
        self.put(rel, json.dumps(body, indent=2, sort_keys=True) + '\n')

    def asset(self, folder, asset_id, kind, authority, owner, packages: dict):
        outputs = ''.join(f'[[outputs]]\npackage = "/Game/{p[len("unreal/Content/"):].rsplit(".", 1)[0]}"\n'
                          for p in packages if p.endswith(('.uasset', '.umap')))
        recipe = ''
        if authority == 'generated':
            self.put(f'{folder}/src/source.glb', b'mesh')
            recipe = f'[[sources]]\npath = "src/source.glb"\nsha256 = "{sha(b"mesh")}"\n' \
                     '[recipe]\nimporter = "static-mesh"\nversion = 1\n'
        self.put(f'{folder}/asset.toml', f'schema = 1\nid = "{asset_id}"\nkind = "{kind}"\n'
                                         f'authority = "{authority}"\nowner = "{owner}"\n{recipe}{outputs}')
        self.verified(f'{folder}/verified.json', asset_id,
                      'imported' if authority == 'generated' else 'editor-saved', packages)

    def commit(self, message='change'):
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '--allow-empty', '-m', message)

    def report(self, spec='main...HEAD', **kw):
        result, _, _ = changeset.report(self.path, spec, **kw)
        return result


def codes(result):
    return sorted({p.code for p in result.problems})


def change(result, path):
    return next(c for c in result.changes if c.path == path)


@pytest.fixture
def game(tmp_path):
    git(tmp_path, 'init', '-q', '-b', 'main')
    g = Game(tmp_path)
    g.asset('assets/props/bench', 'prop/bench', 'static-mesh', 'generated', 'region/w04-skatepark',
            {BENCH: b'bench v1'})
    g.asset('assets/materials/painted', 'material/painted', 'material', 'editor', 'shared/material/painted',
            {PAINT: b'paint v1'})
    g.asset('assets/maps/island', 'map/island', 'map', 'editor', 'shared/map/island', {ISLAND: b'island v1'})
    g.region('w04-skatepark', [0, 0, 10000, 10000], {BENCH_ACTOR: b'actor v1', f'{ACTORS}/0/AB/RAIL01.uasset': b'rail'})
    g.region('w05-harbour', [10000, 0, 20000, 10000], {f'{ACTORS}/1/EF/HARBOUR01.uasset': b'harbour v1'})
    g.put('tools/helper.py', 'print("v1")\n')
    g.commit('base')
    git(tmp_path, 'checkout', '-q', '-b', 'work')
    return g


def test_no_change_is_ok(game):
    result = game.report()
    assert result.changes == [] and result.problems == []


def test_add_an_actor_with_its_region_record(game):
    rel = f'{ACTORS}/3/CD/NEWACTOR.uasset'
    game.record('world/regions/w04-skatepark/actors.verified.json', add={rel: game.put(rel, b'new actor')})
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == []
    c = change(result, rel)
    assert (c.change, c.kind, c.owner, c.scopes) == ('add', 'external package', 'region/w04-skatepark',
                                                     ['region/w04-skatepark'])
    assert 'header not read' in c.note


def test_new_actor_nobody_owns_is_unowned_and_out_of_scope(game):
    rel = f'{ACTORS}/3/CD/STRAY.uasset'
    game.put(rel, b'stray')
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == ['OUT_OF_SCOPE', 'UNOWNED']


def test_edit_a_generated_package_with_and_without_its_record(game):
    game.record('assets/props/bench/verified.json', add={BENCH: game.put(BENCH, b'bench v2')})
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == []
    c = change(result, BENCH)
    assert (c.change, c.kind, c.owner, c.writer) == ('edit', 'generated package', 'prop/bench', 'generated')

    game.put(BENCH, b'bench v3')                      # a second edit, record left behind
    game.commit()
    assert codes(game.report(scopes=['region/w04-skatepark'])) == ['RECORD_MISMATCH']
    assert codes(game.report('HEAD~1...HEAD')) == ['PACKAGE_WITHOUT_RECORD']


def test_record_changed_without_its_package(game):
    game.record('assets/props/bench/verified.json', add={BENCH: b'bench v2 never committed'})
    game.commit()
    assert codes(game.report()) == ['RECORD_WITHOUT_PACKAGE']


def test_delete_an_actor_and_its_record_entry(game):
    game.rm(BENCH_ACTOR)
    game.record('world/regions/w04-skatepark/actors.verified.json', drop=[BENCH_ACTOR])
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == []
    c = change(result, BENCH_ACTOR)
    assert (c.change, c.owner) == ('delete', 'region/w04-skatepark')


def test_deleted_actor_still_recorded_fails(game):
    game.rm(BENCH_ACTOR)
    game.commit()
    assert codes(game.report()) == ['PACKAGE_WITHOUT_RECORD', 'RECORD_MISMATCH']


def test_rename_a_package_with_its_record(game):
    renamed = 'unreal/Content/Props/SM_BenchLong.uasset'
    toml = game.path / 'assets/props/bench/asset.toml'
    toml.write_text(toml.read_text().replace('/Game/Props/SM_Bench"', '/Game/Props/SM_BenchLong"'))
    (game.path / BENCH).rename(game.path / renamed)
    game.record('assets/props/bench/verified.json', add={renamed: b'bench v1'}, drop=[BENCH])
    game.commit()
    result = game.report(scopes=['asset/prop/bench'])
    assert codes(result) == []
    c = change(result, renamed)
    assert (c.change, c.old_path, c.owner) == ('rename', BENCH, 'prop/bench')


def test_deleted_package_still_named_by_a_record(game):
    game.rm(BENCH)
    game.rm('assets/props/bench/verified.json')
    game.commit()
    result = game.report()
    assert codes(result) == ['REFERENCED_DELETION']
    assert 'assets/props/bench/asset.toml' in result.problems[0].detail


def test_deleting_a_map_its_regions_and_actors_still_use_fails(game):
    shutil.rmtree(game.path / 'assets/maps/island')
    game.rm(ISLAND)
    game.commit()
    result = game.report()
    assert codes(result) == ['ORPHAN_ACTOR', 'REFERENCED_DELETION']
    named = sorted(p.detail for p in result.problems if p.code == 'REFERENCED_DELETION')
    assert len(named) == 2 and 'w04-skatepark/region.toml' in named[0] and 'w05-harbour/region.toml' in named[1]


def test_move_an_actor_between_regions_needs_both_scopes(game):
    game.put(BENCH_ACTOR, b'actor v2 moved east')
    game.record('world/regions/w04-skatepark/actors.verified.json', drop=[BENCH_ACTOR])
    game.record('world/regions/w05-harbour/actors.verified.json', add={BENCH_ACTOR: b'actor v2 moved east'})
    game.commit()
    result = game.report(scopes=['region/w05-harbour'])
    c = change(result, BENCH_ACTOR)
    assert (c.change, c.old_owner, c.owner) == ('move', 'region/w04-skatepark', 'region/w05-harbour')
    assert codes(result) == ['OUT_OF_SCOPE']
    assert 'region/w04-skatepark' in result.problems[0].detail
    assert codes(game.report(scopes=['region/w04-skatepark', 'region/w05-harbour'])) == []
    assert codes(game.report(scopes=['region'])) == []                       # a parent scope covers both


def test_missing_and_orphan_companions(game):
    rock, bulk = 'unreal/Content/Props/SM_Rock.uasset', 'unreal/Content/Props/SM_Rock.ubulk'
    game.asset('assets/props/rock', 'prop/rock', 'static-mesh', 'editor', 'region/w04-skatepark',
               {rock: b'rock', bulk: b'rock bulk'})
    game.rm(bulk)                                     # recorded, but never committed
    game.commit()
    assert codes(game.report()) == ['MISSING_COMPANION']

    game.put(bulk, b'rock bulk')
    game.commit()
    assert codes(game.report('HEAD~1...HEAD')) == ['COMPANION']          # companion alone, package untouched

    game.rm(rock)
    game.record('assets/props/rock/verified.json', drop=[rock])
    toml = game.path / 'assets/props/rock/asset.toml'
    toml.write_text(toml.read_text().replace('/Game/Props/SM_Rock', '/Game/Props/SM_Rock2'))
    game.commit()
    assert 'ORPHAN_COMPANION' in codes(game.report('HEAD~1...HEAD'))


def test_out_of_scope_shared_material_and_path_claims(game):
    game.record('assets/materials/painted/verified.json', add={PAINT: game.put(PAINT, b'paint v2')})
    game.put('tools/helper.py', 'print("v2")\n')
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == ['OUT_OF_SCOPE']
    subjects = {p.subject for p in result.problems}
    assert subjects == {PAINT, 'assets/materials/painted/verified.json', 'tools/helper.py'}
    assert codes(game.report(scopes=['shared/material'], paths=['games/yorimichi_v2/tools'])) == []
    assert codes(game.report(scopes=['asset/material/painted'], paths=['tools/helper.py'])) == []
    assert codes(game.report()) == []                 # nothing declared: scopes are reported, not checked
    assert game.report().required_scopes() == ['shared/material/painted']


def test_unowned_package(game):
    game.put('unreal/Content/Stray/SM_Stray.uasset', b'stray')
    game.commit()
    result = game.report()
    assert codes(result) == ['UNOWNED']
    assert change(result, 'unreal/Content/Stray/SM_Stray.uasset').kind == 'package'


def test_staged_change(game):
    game.put(BENCH, b'bench staged')
    git(game.root, 'add', '-A')
    result = game.report(None, staged=True)
    assert codes(result) == ['PACKAGE_WITHOUT_RECORD']
    assert change(result, BENCH).change == 'edit'


def test_command_line_markdown_and_json(game, capsys):
    game.put(BENCH, b'bench v2')
    game.commit()
    args = ['main...HEAD', '--game', str(game.path), '--scopes', 'region/w04-skatepark']
    assert changeset.main(args) == 1
    out = capsys.readouterr().out
    assert '**FAIL**' in out and 'PACKAGE_WITHOUT_RECORD' in out and '| edit | generated package |' in out
    assert changeset.main(args + ['--json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['ok'] is False and report['changes'][0]['owner'] == 'prop/bench'
    assert changeset.main(['nonexistent...HEAD', '--game', str(game.path)]) == 2


# -- actors identified from their headers ---------------------------------------------------------------------------

def synthetic_actor(location, label='Harbour bench'):
    return headers.actor_package(label=label, metadata={'location': location})


SYNTH = f'{ACTORS}/5/PQ/PI85JOOOY2R6IWIS0B5ZV5.uasset'


def test_actor_region_comes_from_its_location(game):
    data = game.put(SYNTH, synthetic_actor((1500.0, 5300.0, 450.0)))
    game.record('world/regions/w04-skatepark/actors.verified.json', add={SYNTH: data})
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == []
    c = change(result, SYNTH)
    assert (c.owner, c.map, c.actor_label, c.actor_guid) == (
        'region/w04-skatepark', '/Game/Maps/Island', 'Harbour bench', '5511878F4A993B5BB7436D78F81A56A5')
    assert c.location == [1500.0, 5300.0, 450.0] and c.actor_class == '/Script/Engine.StaticMeshActor'

    moved = game.put(SYNTH, synthetic_actor((15000.0, 5300.0, 450.0)))   # dragged into the harbour
    game.commit()
    result = game.report('HEAD~1...HEAD', scopes=['region/w04-skatepark', 'region/w05-harbour'])
    c = change(result, SYNTH)
    assert (c.change, c.old_owner, c.owner) == ('move', 'region/w04-skatepark', 'region/w05-harbour')
    assert 'REGION_MISMATCH' in codes(result) and 'PACKAGE_WITHOUT_RECORD' in codes(result)

    game.record('world/regions/w04-skatepark/actors.verified.json', drop=[SYNTH])
    game.record('world/regions/w05-harbour/actors.verified.json', add={SYNTH: moved})
    game.commit()
    assert codes(game.report('HEAD~2...HEAD', scopes=['region/w04-skatepark', 'region/w05-harbour'])) == []


def test_deleted_lfs_actor_is_identified_through_smudge(game, monkeypatch):
    real = synthetic_actor((1500.0, 5300.0, 450.0), label='Old kiosk')
    pointer = (b'version https://git-lfs.github.com/spec/v1\noid sha256:' + sha(real).encode()
               + f'\nsize {len(real)}\n'.encode())
    game.put(SYNTH, pointer)
    game.record('world/regions/w04-skatepark/actors.verified.json', add={SYNTH: real})
    game.commit('pointer')
    git(game.root, 'branch', '-f', 'main', 'HEAD')
    game.rm(SYNTH)
    game.record('world/regions/w04-skatepark/actors.verified.json', drop=[SYNTH])
    game.commit()
    monkeypatch.setattr(changeset.Git, 'smudge', lambda self, rel, data: real if data == pointer else None)
    c = change(game.report(), SYNTH)
    assert (c.change, c.actor_label, c.owner) == ('delete', 'Old kiosk', 'region/w04-skatepark')
    monkeypatch.setattr(changeset.Git, 'smudge', lambda self, rel, data: None)
    c = change(game.report(), SYNTH)
    assert c.note == 'header not read: LFS content unavailable' and c.owner == 'region/w04-skatepark'


ENGINE_ACTOR = headers.KNOWN_ACTOR


@pytest.mark.skipif(not ENGINE_ACTOR.is_file(), reason='Unreal Engine 5.8 templates are not installed')
def test_real_template_actor_added_moved_and_deleted(game):
    for name in ('w04-skatepark', 'w05-harbour'):
        toml = game.path / f'world/regions/{name}/region.toml'
        toml.write_text(toml.read_text().replace('/Game/Maps/Island', '/Game/Variant_Platforming/Lvl_Platforming'))
    game.commit('regions read the template level')
    git(game.root, 'branch', '-f', 'main', 'HEAD')
    rel = 'unreal/Content/__ExternalActors__/Variant_Platforming/Lvl_Platforming/5/PQ/PI85JOOOY2R6IWIS0B5ZV5.uasset'
    data = game.put(rel, ENGINE_ACTOR.read_bytes())
    game.record('world/regions/w04-skatepark/actors.verified.json', add={rel: data})
    game.commit()
    result = game.report(scopes=['region/w04-skatepark'])
    assert codes(result) == []
    c = change(result, rel)
    assert (c.change, c.owner, c.actor_label, c.map) == (
        'add', 'region/w04-skatepark', 'SM_QuarterCylinder17', '/Game/Variant_Platforming/Lvl_Platforming')
    assert c.actor_guid == '5511878F4A993B5BB7436D78F81A56A5'

    # Drag it east: rewrite the descriptor's location in place (same length, so the header stays valid).
    package = changeset.ups.parse(data)
    tag = package.assets[0].tags['ActorMetaData']
    blob = bytearray(base64.b64decode(tag))
    at = blob.find(struct.pack('<3d', *package.actor.location))
    blob[at:at + 8] = struct.pack('<d', 15000.0)
    moved = data.replace(tag.encode(), base64.b64encode(bytes(blob)))
    assert changeset.ups.parse(moved).actor.location[0] == 15000.0
    game.put(rel, moved)
    game.record('world/regions/w04-skatepark/actors.verified.json', drop=[rel])
    game.record('world/regions/w05-harbour/actors.verified.json', add={rel: moved})
    game.commit()
    result = game.report('HEAD~1...HEAD', scopes=['region/w05-harbour'])
    c = change(result, rel)
    assert (c.change, c.old_owner, c.owner) == ('move', 'region/w04-skatepark', 'region/w05-harbour')
    assert codes(result) == ['OUT_OF_SCOPE']

    game.rm(rel)
    game.record('world/regions/w05-harbour/actors.verified.json', drop=[rel])
    game.commit()
    c = change(game.report('HEAD~1...HEAD'), rel)
    assert (c.change, c.owner, c.actor_label) == ('delete', 'region/w05-harbour', 'SM_QuarterCylinder17')
