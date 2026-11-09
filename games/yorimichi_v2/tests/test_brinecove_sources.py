"""Carved Brine Cove sources: the remainder is derived from the committed original and selection, never committed.

Covers the derived remainder and its import preparation, the fingerprint's dependence on the selection, the converter's
refusal of a record that does not reproduce, and the split tools' writes (the selection, never the remainder)."""
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import carve  # noqa: E402
import records  # noqa: E402
from glb_subset import parse_glb, subset_glb  # noqa: E402
import brinecove_split_apply as apply  # noqa: E402
import brinecove_sources as sources  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_brinecove_split_apply import allow, mini_game, small_plan  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_import_run', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

RID = 'prop/test/carved'
NAME = 'SM_BC_Test.glb'
SEL = 'SM_BC_Test.carve.json'
MODEL = {
    'materials': ['BC_rope', 'BC_wood'], 'material_docs': [{'name': 'BC_rope'}, {'name': 'BC_wood'}],
    'prims': [
        {'material': 0, 'positions': [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0),
                                      (0.0, 0.0, 1.0), (1.0, 0.0, 1.0)],
         'indices': [0, 1, 2, 1, 3, 2, 0, 4, 5], 'NORMAL': [(0.0, 0.0, 1.0)] * 6,
         'TEXCOORD_0': [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.0, 2.0), (1.0, 2.0)]},
        {'material': 1, 'positions': [(2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (2.0, 1.0, 0.0)], 'indices': [0, 1, 2],
         'NORMAL': [(0.0, 0.0, 1.0)] * 3, 'TEXCOORD_0': [(0.0, 0.0)] * 3},
    ]}
KEPT = [0, 2, 3]                       # the remainder keeps triangles 0, 2 and 3 of the four


def original_bytes() -> bytes:
    return subset_glb(MODEL, [0, 1, 2, 3], 'SM_BC_Test')[0]


def committed_remainder(name: str = 'SM_BC_Test') -> bytes:
    """The remainder as the split tools used to commit it: write_subset of the donor model with the kept triangles."""
    return subset_glb(parse_glb(original_bytes(), NAME), KEPT, name)[0]


RECORD = f'''schema = 1
id = "{RID}"
kind = "static-mesh"
authority = "generated"
owner = "shared/test/carved"

[[sources]]
path = "src/{NAME}"
sha256 = "{{original}}"

[[sources]]
path = "src/{SEL}"
sha256 = "{{selection}}"

[derive]
kind = "carve"
version = 1
original = "src/{NAME}"
selection = "src/{SEL}"

[recipe]
importer = "static-mesh"
version = 1

[recipe.settings]
slot_materials = ["/Game/Test/MI_A", "/Game/Test/MI_B"]
triangles = 3

[[outputs]]
package = "/Game/Test/SM_BC_Test"
'''


LEGACY = ('schema = 1\nid = "%s"\nkind = "static-mesh"\nauthority = "generated"\nowner = "shared/test/carved"\n\n'
          '[[sources]]\npath = "src/%s"\nsha256 = "%s"\n\n[recipe]\nimporter = "static-mesh"\nversion = 1\n\n'
          '[recipe.settings]\nslot_materials = ["/Game/Test/MI_A", "/Game/Test/MI_B"]\ntriangles = 3\n\n'
          '[[outputs]]\npackage = "/Game/Test/SM_BC_Test"\n')


def legacy_folder(root: Path, committed: bytes) -> Path:
    """A tile in the old form: its committed source is the remainder."""
    folder = root / 'assets' / RID
    (folder / 'src').mkdir(parents=True)
    (folder / 'src' / NAME).write_bytes(committed)
    (folder / 'asset.toml').write_text(LEGACY % (RID, NAME, carve.sha256(committed)))
    return folder


def carved_folder(root: Path, original: bytes, selection: bytes) -> Path:
    folder = root / 'assets' / RID
    (folder / 'src').mkdir(parents=True)
    (folder / 'src' / NAME).write_bytes(original)
    (folder / 'src' / SEL).write_bytes(selection)
    (folder / 'asset.toml').write_text(RECORD.format(original=carve.sha256(original), selection=carve.sha256(selection)))
    return folder


def test_prepare_derives_a_byte_identical_remainder(tmp_path, monkeypatch):
    selection = carve.selection_text(4, KEPT).encode()
    folder = carved_folder(tmp_path / 'game', original_bytes(), selection)
    asset = records.load_asset(folder / 'asset.toml')
    assert asset.derive == {'kind': 'carve', 'version': 1, 'original': f'src/{NAME}', 'selection': f'src/{SEL}'}
    build = tmp_path / 'build'
    monkeypatch.setattr(run, 'BUILD', build)
    out = carve.materialize(asset, build)
    assert out == build / 'derived' / RID / NAME
    assert out.read_bytes() == committed_remainder()                    # the bytes the old form committed
    assert carve.materialize(asset, build) == out                       # a rerun is the same file
    assert (folder / 'src' / NAME).read_bytes() == original_bytes()     # the source stays the original
    # a selection keeping every triangle is the original's own bytes
    assert carve.remainder_bytes(original_bytes(), NAME, [0, 1, 2, 3], 4) == original_bytes()


def test_import_plan_uses_the_derived_remainder_and_its_fingerprint_covers_both_pins(tmp_path, monkeypatch):
    selection = carve.selection_text(4, KEPT).encode()
    folder = carved_folder(tmp_path / 'game', original_bytes(), selection)
    asset = records.load_asset(folder / 'asset.toml')
    build = tmp_path / 'build'
    monkeypatch.setattr(run, 'BUILD', build)
    by_id = {asset.id: asset}
    plan_file = tmp_path / 'plan.json'
    run.write_plan(tmp_path / 'game', asset, by_id, ('static-mesh', 1), 'T', [], plan_file)
    plan = json.loads(plan_file.read_text())
    assert plan['sources'] == [str(build / 'derived' / RID / NAME)]
    assert plan['portable_sources'] == [f'build/yorimichi_v2/derived/{RID}/{NAME}']
    assert Path(plan['sources'][0]).read_bytes() == committed_remainder()

    hashes = run.current_source_hashes(asset)
    fingerprint = run.fingerprint_with_sources(asset, hashes, {})
    assert fingerprint == records.input_fingerprint(asset, {})
    other = dataclasses.replace(asset, sources=[asset.sources[0], records.Source(asset.sources[1].path, 'f' * 64)])
    assert records.input_fingerprint(other, {}) != fingerprint          # the selection's hash is an input
    changed = dict(hashes, **{f'src/{SEL}': 'f' * 64})
    assert run.fingerprint_with_sources(asset, changed, {}) != fingerprint
    original_changed = dict(hashes, **{f'src/{NAME}': 'e' * 64})
    assert run.fingerprint_with_sources(asset, original_changed, {}) != fingerprint     # and the original's


def test_converter_refuses_a_record_that_does_not_reproduce(tmp_path, monkeypatch):
    original = original_bytes()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))
    # same triangles, but named for another mesh: the bytes differ, so the proof refuses
    other = committed_remainder('SM_BC_Other')
    legacy_folder(tmp_path / 'named', other)
    result = sources.convert(tmp_path / 'named', RID, {carve.sha256(other)})
    assert result['status'] == 'refused' and 'not byte-identical' in result['why'] and result['writes'] == {}
    # a triangle the original does not have: refused as unmatched, naming the count
    bent = parse_glb(original, NAME)
    bent['prims'][0]['positions'] = [(x + 0.5, y, z) for x, y, z in bent['prims'][0]['positions']]
    committed = subset_glb(bent, KEPT, 'SM_BC_Test')[0]
    legacy_folder(tmp_path / 'bent', committed)
    result = sources.convert(tmp_path / 'bent', RID, {carve.sha256(committed)})
    assert result['status'] == 'refused' and 'not triangles of the original' in result['why']
    # a committed remainder that is not one an expectation lists is refused before any proof
    result = sources.convert(tmp_path / 'bent', RID, {'0' * 64})
    assert result['status'] == 'refused' and 'expectation' in result['why']


def test_converter_reproduces_and_writes_the_new_form(tmp_path, monkeypatch):
    original = original_bytes()
    committed = committed_remainder()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))
    game = tmp_path / 'game'
    folder = legacy_folder(game, committed)
    old = records.load_asset(folder / 'asset.toml')
    (folder / 'verified.json').write_text(json.dumps({
        'schema': 1, 'kind': 'imported', 'asset': RID, 'engine': '5.8.2-1', 'tool': 'static-mesh@1', 'files': {},
        'input_fingerprint': records.input_fingerprint(old, {}), 'dependencies': {}}))
    result = sources.convert(game, RID, {carve.sha256(committed)})
    assert result['status'] == 'converted', result['why']
    writes = result['writes']
    assert writes[f'assets/{RID}/src/{NAME}'] == original                  # the fused original is committed again
    assert writes[f'assets/{RID}/src/{SEL}'] == carve.selection_text(4, KEPT).encode()
    for rel, data in writes.items():
        (game / rel).parent.mkdir(parents=True, exist_ok=True)
        (game / rel).write_bytes(data)
    new = records.load_asset(folder / 'asset.toml')
    assert new.derive is not None and carve.derive(folder, new.derive) == committed   # byte-identical, nothing to re-import
    verified = json.loads((folder / 'verified.json').read_text())
    assert verified['input_fingerprint'] == records.input_fingerprint(new, {}) != records.input_fingerprint(old, {})
    # a second run finds the record already in the new form
    assert sources.convert(game, RID, {carve.sha256(committed)})['status'] == 'done'


def test_converter_refuses_a_stale_import(tmp_path, monkeypatch):
    original = original_bytes()
    committed = committed_remainder()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))
    folder = legacy_folder(tmp_path / 'game', committed)
    (folder / 'verified.json').write_text(json.dumps({
        'schema': 1, 'kind': 'imported', 'asset': RID, 'engine': '5.8.2-1', 'tool': 'static-mesh@1', 'files': {},
        'input_fingerprint': 'a' * 64, 'dependencies': {}}))
    result = sources.convert(tmp_path / 'game', RID, {carve.sha256(committed)})
    assert result['status'] == 'refused' and 'not current' in result['why']


def test_split_tools_write_the_selection_and_never_the_remainder_into_src(tmp_path):
    game = mini_game(tmp_path)
    writes = apply.compute(game, small_plan(tmp_path))['writes']
    tile = 'assets/prop/brinecove/props-3-3'
    assert f'{tile}/src/SM_BC_Props_3_3.carve.json' in writes
    assert f'{tile}/src/SM_BC_Props_3_3.glb' not in writes                 # the original stays as committed
    text = writes[f'{tile}/asset.toml'].decode()
    assert '[derive]' in text and 'src/SM_BC_Props_3_3.carve.json' in text
    assert 'assets/prop/brinecove/cannon-west/src/SM_BC_CannonWest.glb' in writes   # a cut-out part keeps its own source
    record = tmp_path / 'record' / 'asset.toml'
    record.parent.mkdir()
    record.write_text(text)
    assert records.load_asset(record).derive['selection'] == 'src/SM_BC_Props_3_3.carve.json'


def test_a_tile_in_the_old_form_cannot_be_materialized(tmp_path):
    with pytest.raises(carve.CarveError):
        carve.materialize(SimpleNamespace(id=RID, derive=None), tmp_path)


def test_a_donor_tile_nothing_was_cut_from_is_untouched(tmp_path, monkeypatch):
    original = original_bytes()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))
    folder = legacy_folder(tmp_path / 'game', original)                 # the committed "remainder" is the whole tile
    result = sources.convert(tmp_path / 'game', RID, {carve.sha256(original)})
    assert result['status'] == 'untouched' and result['writes'] == {}
    assert 'derive' not in (folder / 'asset.toml').read_text()


def expectation(game: Path, committed: bytes) -> None:
    """A split expectation on the tree that lists the record's committed remainder."""
    region = game / 'world' / 'regions' / 'w09-brinecove'
    region.mkdir(parents=True, exist_ok=True)
    (region / 'split-batch1.json').write_text(json.dumps({'tiles': {'Test': {
        'record': RID, 'remainder': {'sha256': carve.sha256(committed), 'triangles': 3}}}}))


def test_tampered_original_is_refused_by_its_first_pin(tmp_path, monkeypatch):
    original = original_bytes()
    tampered = original.replace(b'\x00\x00\x80\x3f', b'\x00\x00\x00\x40', 1)    # one coordinate changed
    assert tampered != original

    def fake_git(*args):
        if args[0] == 'show' and args[1].endswith('asset.toml'):
            return f'[[sources]]\npath = "src/{NAME}"\nsha256 = "{carve.sha256(original)}"\n'.encode()
        if args[0] == 'show':
            return tampered
        return b'abc123\n'
    monkeypatch.setattr(sources, 'git', fake_git)
    with pytest.raises(sources.ConvertError, match='does not match its pin'):
        sources.original_of(f'games/yorimichi_v2/assets/{RID}', 'abc123')
    monkeypatch.setattr(sources.apply.authority, 'authorize', lambda *a, **k: None)
    game = tmp_path / 'game'
    legacy_folder(game, committed_remainder())
    result = sources.convert(game, RID, {carve.sha256(committed_remainder())})
    assert result['status'] == 'refused' and 'does not match its pin' in result['why']


def test_interrupted_conversion_is_recovered_then_converted(tmp_path, monkeypatch):
    original = original_bytes()
    committed = committed_remainder()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))
    monkeypatch.setattr(sources.apply.authority, 'authorize', lambda *a, **k: None)
    game = tmp_path / 'game'
    folder = legacy_folder(game, committed)
    expectation(game, committed)
    legacy_text = (folder / 'asset.toml').read_text()
    # an earlier run was interrupted after its journal began: the record holds a partly converted file
    apply_journal = sources.apply.Journal(game)
    apply_journal.begin([f'assets/{RID}/asset.toml'], scopes=[[f'asset/{RID}', 'shared/test/carved']])
    (folder / 'asset.toml').write_text('partly converted, not a record')
    restored, results, written = sources.claimed(game, 'T')
    assert restored == [f'assets/{RID}/asset.toml'] and written == 3
    assert results[0]['status'] == 'converted'
    assert not apply_journal.dir.exists()                                 # the retry closed its own journal
    new = records.load_asset(folder / 'asset.toml')
    assert new.derive is not None and carve.derive(folder, new.derive) == committed
    assert legacy_text != (folder / 'asset.toml').read_text()


def test_retry_without_a_valid_claim_refuses_and_keeps_the_journal(tmp_path, monkeypatch):
    original = original_bytes()
    committed = committed_remainder()
    monkeypatch.setattr(sources, 'git', lambda *args: b'abc123\n')
    monkeypatch.setattr(sources, 'original_of', lambda rel, commit: (NAME, carve.sha256(original), original))

    def refuse(*args, **kwargs):
        raise sources.apply.authority.Unauthorized('no valid claim')
    monkeypatch.setattr(sources.apply.authority, 'authorize', refuse)
    game = tmp_path / 'game'
    folder = legacy_folder(game, committed)
    expectation(game, committed)
    journal = sources.apply.Journal(game)
    journal.begin([f'assets/{RID}/asset.toml'], scopes=[[f'asset/{RID}', 'shared/test/carved']])
    (folder / 'asset.toml').write_text('partly converted, not a record')
    with pytest.raises(sources.apply.SplitError):
        sources.claimed(game, 'WRONG')
    assert journal.manifest.is_file()                                     # the journal survives the refusal
    assert (folder / 'asset.toml').read_text() == 'partly converted, not a record'
    assert journal.dir.joinpath('before', f'assets/{RID}/asset.toml').is_file()
