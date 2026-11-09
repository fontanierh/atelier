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
