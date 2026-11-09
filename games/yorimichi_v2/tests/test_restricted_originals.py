"""Every restricted package is linked to what it was made from: an MD5-checked imported file, the skate bundle its clip
was keyed from, its character's mesh import, or an editor-made class; the originals are pinned and fetched verified."""
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_restricted_originals', ROOT / 'tools/restricted/originals.py')
originals = importlib.util.module_from_spec(spec)
sys.modules['v2_restricted_originals'] = originals
spec.loader.exec_module(originals)

ROLL, CLIP, MAT, TEX, MESH = ('Audio/Skate/A_Roll.uasset', 'SkateRide/Clips/B0/OLLIE.uasset',
                              'Paul/Materials/M_Skin.uasset', 'Paul/Textures/T_Paul_0.uasset', 'Paul/SK_Paul.uasset')
WAV, GLB = b'roll wav', b'paul glb'
BUNDLE = 'build/yorimichi/skate-simulation/package'


def write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def tag(recorded: str, data: bytes) -> bytes:
    """A package header holding the editor's import data for one source file, as Unreal saves it."""
    return (b'header \x00[{ "RelativeFilename" : "' + recorded.encode() + b'", "Timestamp" : "0", '
            b'"FileMD5" : "' + hashlib.md5(data).hexdigest().encode() + b'", "DisplayLabelName" : "" }]\x00 rest')


@pytest.fixture
def world(tmp_path):
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    game.mkdir()
    shutil.copy(ROOT / 'restricted.toml', game / 'restricted.toml')
    content = game / 'unreal/Content'
    # Unreal records the source relative to the package, through whatever checkout imported it.
    write(content / ROLL, tag('../../../../../me/dev/donor/build/yorimichi/audio/skate/roll.wav', WAV))
    write(content / MESH, tag('../../../me/dev/donor/build/yorimichi/paul/fbx/SK_Paul.glb', GLB))
    write(content / CLIP, b'keyed clip, no import data')
    write(content / MAT, b'material')
    write(content / TEX, b'texture, empty import path [{ "RelativeFilename" : "", "FileMD5" : "" }]')
    write(donor / 'build/yorimichi/audio/skate/roll.wav', WAV)
    write(donor / 'build/yorimichi/paul/fbx/SK_Paul.glb', GLB)
    for rel in ('animation/clips/0/OLLIE.skate', 'animation/rig.skate', 'metadata/bank-0.skate'):
        write(donor / BUNDLE / rel, rel.encode())
    for rel in originals.CLIP_CODE:
        write(donor / rel, b'# importer code')
    write(donor / originals.CLIP_STATE, json.dumps({'fingerprint': 'f' * 64, 'clips': {
        'OLLIE': {'asset': '/Game/SkateRide/Clips/B0/OLLIE'}}}).encode())
    files = {rel: {'sha256': records.sha256_file(content / rel), 'size': (content / rel).stat().st_size}
             for rel in (ROLL, MESH, CLIP, MAT, TEX)}
    records.write_json(game / 'restricted.lock.json', {'schema': 1, 'files': files})
    classes = {'/Game/Audio/Skate/A_Roll': 'SoundWave', '/Game/Paul/SK_Paul': 'SkeletalMesh',
               '/Game/SkateRide/Clips/B0/OLLIE': 'AnimSequence', '/Game/Paul/Materials/M_Skin': 'Material',
               '/Game/Paul/Textures/T_Paul_0': 'Texture2D'}
    return game, donor, classes


def test_scan_links_every_package_by_its_route_and_pins_the_originals(world):
    game, donor, classes = world
    data = originals.scan(game, donor, classes)
    assert data['problems'] == []
    packages = data['packages']
    assert packages[ROLL] == {'route': 'imported', 'class': 'SoundWave',
                              'originals': ['build/yorimichi/audio/skate/roll.wav']}
    assert packages[CLIP]['route'] == 'keyed' and packages[CLIP]['originals'][0] == f'{BUNDLE}/animation/clips/0/OLLIE.skate'
    # The keyed clip links the importer's code beside its data: it can be keyed again from what is pinned.
    assert set(originals.CLIP_CODE) <= set(packages[CLIP]['originals'])
    assert packages[MAT] == {'route': 'authored', 'class': 'Material'}
    assert packages[TEX] == {'route': 'embedded', 'class': 'Texture2D', 'originals': ['build/yorimichi/paul/fbx/SK_Paul.glb']}
    assert data['originals']['build/yorimichi/audio/skate/roll.wav'] == {'sha256': hashlib.sha256(WAV).hexdigest(),
                                                                         'size': len(WAV)}
    assert data['donor_state'] == {'skate_clips': 'f' * 64}
    records.write_json(game / originals.LINKS, data)
    assert originals.check(game) == []
    # No checkout path of the donor machine reaches the committed links.
    assert '/me/' not in (game / originals.LINKS).read_text()


def test_scan_refuses_a_donor_file_that_is_not_the_imported_one(world):
    game, donor, classes = world
    write(donor / 'build/yorimichi/audio/skate/roll.wav', b'rebuilt since')
    data = originals.scan(game, donor, classes)
    assert any('FileMD5 differs' in p for p in data['problems']) and ROLL not in data['packages']


def test_scan_reports_an_imported_class_with_no_record_and_check_fails_on_gaps(world):
    game, donor, classes = world
    classes['/Game/Paul/Materials/M_Skin'] = 'StaticMesh'      # an imported type with no import record
    data = originals.scan(game, donor, classes)
    assert any('not editor-made' in p for p in data['problems'])
    del data['packages'][ROLL]
    data['problems'] = []
    data['originals']['build/yorimichi/stray.wav'] = {'sha256': '0' * 64, 'size': 1}
    records.write_json(game / originals.LINKS, data)
    problems = originals.check(game)
    assert f'{ROLL}: pinned but not linked' in problems
    assert any('unexplained' in p for p in problems)
    assert 'build/yorimichi/stray.wav: pinned but linked by no package' in problems


def test_fetch_copies_each_original_only_as_its_pinned_bytes(world, tmp_path):
    game, donor, classes = world
    records.write_json(game / originals.LINKS, originals.scan(game, donor, classes))
    copied, refused = originals.fetch(game, donor, echo=lambda *_: None)
    assert refused == [] and copied == 5 + len(originals.CLIP_CODE)
    assert (game / originals.DEST / 'build/yorimichi/audio/skate/roll.wav').read_bytes() == WAV
    storage = tmp_path / 'storage'
    write(storage / 'build/yorimichi/audio/skate/roll.wav', b'tampered')
    shutil.rmtree(game / originals.DEST)
    _, refused = originals.fetch(game, storage, echo=lambda *_: None)
    assert any('roll.wav' in r for r in refused)
    assert not (game / originals.DEST / 'build/yorimichi/audio/skate/roll.wav').exists()


def test_the_committed_links_cover_every_pinned_restricted_package():
    # The contract on the real game: CI holds the lock and the links, never the bytes.
    assert originals.check(ROOT) == []


def _glb(materials=(), images=(), animations=()) -> bytes:
    body = json.dumps({'materials': [{'name': n} for n in materials], 'images': [{'name': n} for n in images],
                       'animations': [{'name': n} for n in animations]}).encode()
    body += b' ' * (-len(body) % 4)
    return b'glTF' + (2).to_bytes(4, 'little') + (20 + len(body)).to_bytes(4, 'little') + len(body).to_bytes(4, 'little') + b'JSON' + body


@pytest.fixture
def adventure(tmp_path):
    """Three open adopted records, and a donor holding the Adventure report, a character glb, a glider glb and the scripts."""
    game, donor = tmp_path / 'game', tmp_path / 'donor'
    outputs = {'adopted/adventure/reference': ['Reference/SK_Reference', 'Reference/SKEL_Reference',
                                              'Reference/A_Reference_Idle', 'Reference/Glider/SK_ReferenceGlider',
                                              'Reference/Glider/SKEL_ReferenceGlider', 'Reference/Glider/Mt_Parastole',
                                              'Reference/Glider/Item_Parastole2_Alb', 'Reference/Mystery'],
               'adopted/adventure/loose_files': ['M_AdventureCharacter'],
               'adopted/japan/animation': ['../Japan/Animation/CharacterCompression']}
    for record_id, names in outputs.items():
        text = (f'schema = 1\nid = "{record_id}"\nkind = "adopted"\nauthority = "editor"\nowner = "shared/x"\n'
                'provenance = "t"\nlicense = "t"\n')
        text += ''.join(f'\n[[outputs]]\npackage = "/Game/Adventure/{n}"\n' if not n.startswith('..') else
                        f'\n[[outputs]]\npackage = "/Game/{n[3:]}"\n' for n in names)
        write(game / 'assets' / record_id / 'asset.toml', text.encode())
    base = donor / originals.ADVENTURE
    write(base / 'glb/Reference.glb', _glb(animations=['Idle']))
    write(base / 'glb/ReferenceGlider.glb', _glb(['Mt_Parastole'], ['Item_Parastole2_Alb'], ['Float']))
    write(base / 'export.json', json.dumps({'characters': [{'name': 'Reference', 'glb': 'glb/Reference.glb', 'moves': {
        'equipment': {'glider': {'glb': 'glb/ReferenceGlider.glb', 'clip': 'Float'}}}}]}).encode())
    write(base / 'unreal_import.json', json.dumps({'characters': [{
        'name': 'Reference', 'mesh': '/Game/Adventure/Reference/SK_Reference.SK_Reference',
        'skeleton': '/Game/Adventure/Reference/SKEL_Reference.SKEL_Reference',
        'clips': {'Idle': {'path': '/Game/Adventure/Reference/A_Reference_Idle.A_Reference_Idle'}},
        'moves': {'equipment': {'glider': {
            'mesh': '/Game/Adventure/Reference/Glider/SK_ReferenceGlider.SK_ReferenceGlider',
            'clip': '/Game/Adventure/Reference/Glider/A_ReferenceGlider_Float.A_ReferenceGlider_Float'}}}}]}).encode())
    scripts = donor / originals.ADVENTURE_SCRIPTS
    write(scripts / 'import_adventure.py', b"masters = {False: master('M_AdventureCharacter', False)}")
    write(scripts / 'animation_compression.py', b"name = 'CharacterCompression'")
    return game, donor


def test_open_adventure_packages_link_to_the_glb_report_or_script_that_makes_them(adventure):
    game, donor = adventure
    found = originals.link_open(game, donor)
    packages = found['open_packages']
    route = lambda rel: (packages[rel]['route'], packages[rel]['class'])
    assert route('Adventure/Reference/A_Reference_Idle.uasset') == ('reported', 'AnimSequence')
    assert route('Adventure/Reference/SK_Reference.uasset') == ('reported', 'SkeletalMesh')
    assert route('Adventure/Reference/Glider/SKEL_ReferenceGlider.uasset') == ('embedded', 'Skeleton')
    assert route('Adventure/Reference/Glider/Mt_Parastole.uasset') == ('embedded', 'MaterialInstanceConstant')
    assert route('Adventure/Reference/Glider/Item_Parastole2_Alb.uasset') == ('embedded', 'Texture2D')
    assert route('Adventure/M_AdventureCharacter.uasset') == ('scripted', 'Material')
    assert route('Japan/Animation/CharacterCompression.uasset') == ('scripted', 'AnimBoneCompressionSettings')
    assert packages['Adventure/Reference/A_Reference_Idle.uasset']['originals'] == [
        'build/yorimichi/adventure/glb/Reference.glb', 'build/yorimichi/adventure/unreal_import.json']
    # What nothing in the donor makes is reported, never relabelled as editor-owned.
    assert 'Adventure/Reference/Mystery.uasset' not in packages
    assert any('Mystery' in p and 'recover or replace' in p for p in found['problems'])
    assert 'games/yorimichi/unreal/Scripts/import_adventure.py' in found['originals']


def test_open_links_are_checked_against_their_records_and_pins(adventure):
    game, donor = adventure
    found = originals.link_open(game, donor)
    records.write_json(game / originals.LINKS, {'schema': 1, 'packages': {}, 'originals': found['originals'],
                                                'open_packages': found['open_packages'], 'problems': []})
    restricted = game / 'restricted.toml'
    shutil.copy(ROOT / 'restricted.toml', restricted)
    records.write_json(game / 'restricted.lock.json', {'schema': 1, 'files': {}})
    problems = originals.check(game)
    assert problems == ['Adventure/Reference/Mystery.uasset: owned by an open record but not linked']
    del found['originals']['build/yorimichi/adventure/unreal_import.json']
    records.write_json(game / originals.LINKS, {'schema': 1, 'packages': {}, 'originals': found['originals'],
                                                'open_packages': found['open_packages'], 'problems': []})
    assert any('unreal_import.json is not pinned' in p for p in originals.check(game))


def test_a_hydrated_package_that_names_another_file_is_refused(adventure):
    game, donor = adventure
    content = game / 'unreal/Content'
    glb = (donor / originals.ADVENTURE / 'glb/Reference.glb').read_bytes()
    write(content / 'Adventure/Reference/A_Reference_Idle.uasset',
          tag('../../x/build/yorimichi/adventure/glb/Reference.glb', glb))
    assert not any('Idle' in p for p in originals.link_open(game, donor)['problems'])
    write(content / 'Adventure/Reference/A_Reference_Idle.uasset', tag('../../x/build/yorimichi/adventure/glb/Other.glb', glb))
    assert any('Idle' in p and 'not the pinned glb' in p for p in originals.link_open(game, donor)['problems'])


@pytest.mark.parametrize('has_open_link', [True, False], ids=['linked-mismatch', 'empty-failure'])
def test_restricted_rescan_preserves_open_failure_until_link_open_succeeds(world, tmp_path, monkeypatch, has_open_link):
    game, donor, classes = world
    classes_file = tmp_path / 'classes.json'
    records.write_json(classes_file, classes)
    scan = ['--game', str(game), 'scan', '--donor', str(donor), '--classes', str(classes_file)]
    link = ['--game', str(game), 'link-open', '--donor', str(donor)]
    check = ['--game', str(game), 'check']
    assert originals.main(scan) == 0

    record_id = 'adopted/adventure/reference'
    package = 'Adventure/Reference/A_Reference_Idle.uasset'
    write(game / 'assets' / record_id / 'asset.toml', '''schema = 1
id = "adopted/adventure/reference"
kind = "adopted"
authority = "editor"
owner = "shared/x"
provenance = "test"
license = "test"
[[outputs]]
package = "/Game/Adventure/Reference/A_Reference_Idle"
'''.encode())
    monkeypatch.setattr(originals, 'OPEN_RECORDS', (record_id,))
    linked = {package: {'route': 'reported', 'class': 'AnimSequence',
                       'originals': ['build/yorimichi/paul/fbx/SK_Paul.glb']}}
    opened = linked if has_open_link else {}
    problem = f'{package}: its import data names Other.glb, not the pinned glb'
    result = {'open_packages': opened, 'originals': {}, 'problems': [problem]}
    # The collector's mismatch check is covered above; exercise its persisted CLI result across commands here.
    monkeypatch.setattr(originals, 'link_open', lambda *args: result)
    assert originals.main(link) == 1
    assert originals.main(scan) == 0             # this command only rescans the restricted packages
    saved = json.loads((game / originals.LINKS).read_text())
    assert saved['open_packages'] == opened and saved['open_problems'] == [problem]
    assert f'scan problem: {problem}' in originals.check(game)
    assert originals.main(check) == 1

    result['open_packages'] = linked
    result['problems'] = []                    # a successful new open result replaces the old failure
    assert originals.main(link) == 0
    assert json.loads((game / originals.LINKS).read_text())['open_problems'] == []
    assert originals.main(check) == 0
