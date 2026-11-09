"""The Belmonte train LOD retirement (tools/migrate/belmontetrain_lods.py) on a small fixture tree: the plan finds the 14
packages, a referencing package or a Git LFS pointer refuses before any write, and a rerun after the retirement is a no-op."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import belmontetrain_lods as lods  # noqa: E402

POINTER = b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'0' * 64 + b'\nsize 418344\n'


def record_text(unit, vehicle):
    base = f'/Game/BelmonteTrain/Source/SM_BT_{vehicle}'
    outputs = [f'{base}/LOD0/M_BT_Test', f'{base}/SM_BT_{vehicle}_LOD1', f'{base}/SM_BT_{vehicle}_LOD2']
    return ('schema = 1\n'
            f'id = "adopted/belmontetrain/{unit}"\nkind = "adopted"\nauthority = "editor"\n'
            f'owner = "shared/belmontetrain/{unit}"\nprovenance = "fixture"\nlicense = "fixture"\n'
            'references = ["adopted/belmontetrain/generator"]\n\n'
            + ''.join(f'[[outputs]]\npackage = "{p}"\n\n' for p in outputs))


def sha(_name):
    return 'a' * 64


@pytest.fixture
def game(tmp_path):
    """A fixture game: seven records with their LOD1/LOD2 outputs, verified entries, package files, and units.json."""
    root = tmp_path / 'game'
    units_packages = {}
    for unit, vehicle in lods.UNITS.items():
        folder = root / lods.RECORDS / unit
        folder.mkdir(parents=True)
        (folder / 'asset.toml').write_text(record_text(unit, vehicle))
        files = {f'unreal/Content/BelmonteTrain/Source/SM_BT_{vehicle}/LOD0/M_BT_Test.uasset': sha(unit)}
        for package in lods.EXPECTED[unit]:
            rel = 'unreal/Content' + package[len('/Game'):] + '.uasset'
            files[rel] = sha(package)
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'UASSET-FIXTURE ' + package.encode())
            units_packages[package] = unit
        verified = {'asset': f'adopted/belmontetrain/{unit}', 'dependencies': {}, 'engine': 'fixture', 'files': files}
        (folder / 'verified.json').write_text(json.dumps(verified, indent=2, sort_keys=True) + '\n')
    units = {'about': 'fixture', 'units': {}, 'packages': {'/Game/BelmonteTrain/SM_BT_Keep': 'first-class',
                                                          **units_packages}}
    (root / lods.UNITS_REL).write_text(json.dumps(units, indent=1, ensure_ascii=False) + '\n')
    return root


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


@pytest.fixture
def allow(monkeypatch):
    monkeypatch.setattr(lods.authority, 'authorize', lambda *a, **k: None)


def test_plan_finds_exactly_the_14_packages(game):
    assert lods.state(game) == 'unretired'
    plan = lods.build(game)
    deleted = [p for p in plan.deletes if p.endswith('.uasset')]
    assert len(deleted) == 14
    assert sorted(lods.PACKAGES) == sorted(
        f'/Game/BelmonteTrain/Source/SM_BT_{v}/SM_BT_{v}_LOD{n}' for v in lods.UNITS.values() for n in (1, 2))
    assert len(lods.SCOPES) == 7 and all(s.startswith('shared/belmontetrain/') for s in lods.SCOPES)


def test_a_referencing_package_refuses_and_writes_nothing(game, allow):
    other = game / 'unreal/Content/BelmonteTrain/Props/SM_Other.uasset'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'IMPORT ' + lods.PACKAGES[3].encode() + b' END')
    before = snapshot(game)
    with pytest.raises(lods.LodError, match='SM_Other'):
        lods.retire(game, 'TASK', lockable=lambda g, r: [])
    assert snapshot(game) == before


def test_a_referencing_package_in_utf16_refuses(game, allow):
    other = game / 'unreal/Content/BelmonteTrain/Props/SM_Wide.uasset'
    other.parent.mkdir(parents=True)
    other.write_bytes(lods.PACKAGES[0].encode('utf-16-le'))
    with pytest.raises(lods.LodError, match='SM_Wide'):
        lods.retire(game, 'TASK', lockable=lambda g, r: [])


def test_a_text_file_naming_a_package_refuses(game, allow):
    (game / 'docs.md').write_text(f'see {lods.PACKAGES[0]}\n')
    before = snapshot(game)
    with pytest.raises(lods.LodError, match='docs.md'):
        lods.retire(game, 'TASK', lockable=lambda g, r: [])
    assert snapshot(game) == before


def test_a_pointer_file_refuses_and_writes_nothing(game, allow):
    pointer = game / 'unreal/Content' / (lods.PACKAGES[5][len('/Game/'):] + '.uasset')
    pointer.write_bytes(POINTER)
    before = snapshot(game)
    with pytest.raises(lods.LodError, match='LFS pointer'):
        lods.retire(game, 'TASK', lockable=lambda g, r: [])
    assert snapshot(game) == before


def test_retirement_removes_only_the_14_and_a_rerun_is_a_no_op(game, allow):
    lods.retire(game, 'TASK', lockable=lambda g, r: [])
    assert lods.state(game) == 'retired'
    for package in lods.PACKAGES:
        assert not (game / 'unreal/Content' / (package[len('/Game/'):] + '.uasset')).exists()
    for unit in lods.UNITS:
        asset = lods.records.load_asset(game / lods.RECORDS / unit / 'asset.toml')
        assert [o.package for o in asset.outputs] == [f'/Game/BelmonteTrain/Source/SM_BT_{lods.UNITS[unit]}/LOD0/M_BT_Test']
        verified = json.loads((game / lods.RECORDS / unit / 'verified.json').read_text())
        assert list(verified['files']) == [f'unreal/Content/BelmonteTrain/Source/SM_BT_{lods.UNITS[unit]}/LOD0/M_BT_Test.uasset']
    units = json.loads((game / lods.UNITS_REL).read_text())
    assert units['packages'] == {'/Game/BelmonteTrain/SM_BT_Keep': 'first-class'}
    after = snapshot(game)
    assert lods.retire(game, 'TASK', lockable=lambda g, r: []) == 'retired'
    assert snapshot(game) == after


def test_paths_name_every_changed_file_and_the_seven_scopes(game):
    plan = lods.build(game)
    paths = plan.paths()
    assert f'{lods.RECORDS}/first-class/asset.toml' in paths and lods.UNITS_REL in paths
    assert sum(p.endswith('.uasset') for p in paths) == 14
    assert len(paths) == 7 + 7 + 1 + 14
