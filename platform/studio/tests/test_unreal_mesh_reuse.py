"""Native adapter ownership and refusal paths, without launching an editor."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from atelier import native_candidates as checkpoint_candidates, mesh_reuse, paths, unreal_mesh_reuse as native


@pytest.fixture
def scene(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'; repo.mkdir()
    monkeypatch.setattr(paths, 'REPO', repo)
    ctx = SimpleNamespace(out=repo / 'build/game', uproject=repo / 'games/game/unreal/Game.uproject',
                          unreal_root=repo / 'engine', game='game')
    ctx.out.mkdir(parents=True); ctx.uproject.parent.mkdir(parents=True)
    script = repo / 'import.py'; script.write_text('def build(): return 1\n')
    current = {'engine': 'engine', 'sdk': 'sdk'}
    monkeypatch.setattr(native, 'context', lambda _: current)
    from atelier import native_protocol
    monkeypatch.setattr(native_protocol, 'context', lambda _: current)
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'e' * 24)
    monkeypatch.setattr(mesh_reuse, 'revision_source', lambda *a: script.read_text())
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda *a: script.read_text())
    source = ctx.out / 'mesh.glb'; source.write_bytes(b'expected mesh source')
    hull = ctx.out / 'hull.glb'; hull.write_bytes(b'expected collision source')
    files, staged = {}, {}
    packages = ['/Game/Region/Mesh', '/Game/Region/Hull']
    for package in packages:
        for member in mesh_reuse.package_members(package)[:3]:
            file = repo / 'staging' / member; file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('candidate:' + member).encode())
            staged[member] = file
            files[member] = dict(path='files/' + member, sha256=mesh_reuse.digest(file),
                                 size=file.stat().st_size, mode=0o644)
    report = repo / 'report.json'; report.write_text('{"meshes":[]}')
    staged['generated/report.json'] = report
    bundle = dict(checkpoint='a' * 64, donor_task='unreal.region', donor_fingerprint='b' * 64,
                  source_revision='c' * 40, provenance='compatibility-only', files=files,
                  donor_stamp={'fingerprint': 'b' * 64, 'input_state': {'inputs': {'<repo>/import.py': 'd' * 64}}})
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *a: [bundle])
    def member(*args, bundle=None):
        return staged.get(args[2])
    monkeypatch.setattr(checkpoint_candidates, 'member_path', member)
    content = ctx.uproject.parent / 'Content'
    tags = {package: json.dumps([{'FileMD5': hashlib.md5(file.read_bytes()).hexdigest()}])
            for package, file in zip(packages, (source, hull))}
    scans, removals, unloads = [], [], []
    objects, registered = {}, set()
    def scan(names, force):
        scans.append(names)
        registered.update(packages)
    def rescan(names):
        removals.append(names)
        registered.difference_update(p for p in packages
            if not (content / mesh_reuse.package_members(p)[0].removeprefix('content/')).exists())
    def unload(values):
        unloads.append([v.get_name() for v in values])
        objects.clear()
    def asset_data(object_path, disk_only):
        assert disk_only is True and '.' in object_path
        package, object_name = object_path.rsplit('.', 1)
        assert object_name == package.rsplit('/', 1)[1]
        return SimpleNamespace(get_tag_value=lambda name: tags[package] if name == 'AssetImportData' else None)
    registry = SimpleNamespace(scan_files_synchronous=scan, scan_modified_asset_files=rescan,
                               k2_get_asset_by_object_path=asset_data)
    def load(package):
        for required in packages:
            assert (content / mesh_reuse.package_members(required)[0].removeprefix('content/')).exists()
        mesh = SimpleNamespace(package=package)
        objects[package] = SimpleNamespace(get_name=lambda: package)
        objects[package + '.' + package.rsplit('/', 1)[1]] = mesh
        return mesh
    unreal = SimpleNamespace(
        EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_content_packages=lambda: [], unload_packages=unload),
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda p:
            p in registered or (content / mesh_reuse.package_members(p)[0].removeprefix('content/')).exists()),
        AssetRegistryHelpers=SimpleNamespace(
            create_asset_data=lambda mesh: SimpleNamespace(
                get_tag_value=lambda name: tags[mesh.package] if name == 'AssetImportData' else None),
            get_asset_registry=lambda: registry),
        SoftObjectPath=lambda value: value, find_object=lambda outer, name: objects.get(name), load_asset=load)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    def adapter():
        return native.MeshReuse(ctx, 'unreal.region', script, ('build',), report_member='generated/report.json')
    sources = [(packages[0], source, mesh_reuse.digest(source)), (packages[1], hull, mesh_reuse.digest(hull))]
    return SimpleNamespace(ctx=ctx, adapter=adapter, sources=sources, package=packages[0], tags=tags,
                           staged=staged, content=content, scans=scans, bundle=bundle, unreal=unreal,
                           objects=objects, unloads=unloads, removals=removals, registered=registered)


def acquire(scene, adapter, **kwargs):
    return adapter.acquire('Mesh', scene.package, geometry={'source': 'same'},
                           donor_geometry=kwargs.pop('donor_geometry', {'source': 'same'}),
                           sources=scene.sources, **kwargs)


def test_admits_complete_collision_group_then_records_only_after_validation(scene):
    adapter = scene.adapter()
    mesh = acquire(scene, adapter)
    assert mesh and len(scene.scans[0]) == 2
    assert not adapter.receipts.path.exists()
    adapter.validated('Mesh')
    assert not adapter.receipts.path.exists()
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    record = json.loads(adapter.receipts.path.read_text())['meshes']['Mesh']
    assert len(record['packages']) == 6
    assert record['provenance']['kind'] == 'compatibility-only'
    copied = scene.content / 'Region/Mesh.uasset'; copied.write_bytes(b'independent modification')
    assert scene.staged['content/Region/Mesh.uasset'].read_bytes() != copied.read_bytes()


def test_different_geometry_is_ordinary_import_without_content_copy(scene):
    adapter = scene.adapter()
    assert acquire(scene, adapter, donor_geometry={'source': 'changed'}) is None
    assert not scene.content.exists() and not adapter.receipts.path.exists()


def test_chooses_complete_group_from_second_donor_with_its_own_report_and_provenance(scene, monkeypatch):
    from copy import deepcopy
    primary = deepcopy(scene.bundle)
    primary['checkpoint'] = '1' * 64
    primary['files'] = {n: e for n, e in primary['files'].items() if '/Hull.' not in n}
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [primary, scene.bundle])
    adapter = scene.adapter()
    # The preferred donor is incomplete for this source + collision group.
    assert acquire(scene, adapter, donor_geometry=lambda report: {'source': 'same'})
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert len(scene.scans[0]) == 2
    adapter.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    record = json.loads(adapter.receipts.path.read_text())['meshes']['Mesh']
    assert record['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert len(record['packages']) == 6


def test_reports_are_projected_independently_without_splicing_package_groups(scene, monkeypatch):
    from copy import deepcopy
    primary = deepcopy(scene.bundle)
    primary['checkpoint'] = '1' * 64
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [primary, scene.bundle])
    first_report = scene.ctx.out / 'old-report.json'
    first_report.write_text('{"source":"old"}')
    second_report = scene.ctx.out / 'new-report.json'
    second_report.write_text('{"source":"same"}')
    original = checkpoint_candidates.member_path
    def member(*args, bundle=None):
        if args[2] == 'generated/report.json':
            return first_report if bundle is primary else second_report
        return original(*args, bundle=bundle)
    monkeypatch.setattr(checkpoint_candidates, 'member_path', member)
    adapter = scene.adapter()
    assert acquire(scene, adapter, donor_geometry=lambda report: report)
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']


def test_two_partial_donors_cannot_invent_complete_collision_group(scene, monkeypatch):
    from copy import deepcopy
    primary, secondary = deepcopy(scene.bundle), deepcopy(scene.bundle)
    primary['files'] = {n: e for n, e in primary['files'].items() if '/Hull.' not in n}
    secondary['files'] = {n: e for n, e in secondary['files'].items() if '/Mesh.' not in n}
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [primary, secondary])
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    assert adapter.miss_reasons == {'candidate_package_missing': 1}
    assert not scene.content.exists()


def test_donor_corruption_after_constructor_does_not_hide_other_complete_group(scene, monkeypatch, tmp_path):
    from copy import deepcopy
    primary = deepcopy(scene.bundle)
    primary['checkpoint'] = '1' * 64
    copies = {}
    for member, source in scene.staged.items():
        path = tmp_path / 'first' / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
        copies[member] = path
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [primary, scene.bundle])
    original = checkpoint_candidates.member_path
    def member(*args, bundle=None):
        if bundle is primary:
            path = copies.get(args[2])
            expected = primary['files'].get(args[2])
            if expected and mesh_reuse.digest(path) != expected['sha256']:
                return None
            return path
        return original(*args, bundle=bundle)
    monkeypatch.setattr(checkpoint_candidates, 'member_path', member)
    adapter = scene.adapter()
    copies['content/Region/Mesh.uasset'].write_bytes(b'late corruption')
    assert acquire(scene, adapter)
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert (scene.content / 'Region/Mesh.uasset').read_bytes() == scene.staged['content/Region/Mesh.uasset'].read_bytes()


def test_late_copy_corruption_tries_next_donor_before_any_package_install(scene, monkeypatch):
    from copy import deepcopy
    primary = deepcopy(scene.bundle)
    primary['checkpoint'] = '1' * 64
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [primary, scene.bundle])
    adapter = scene.adapter()
    copy = native.shutil.copyfile
    calls = []
    def corrupted_once(source, target):
        calls.append(source)
        if len(calls) == 1:
            assert not list(scene.content.glob('Region/*'))
            Path(target).write_bytes(b'changed during copy')
        else:
            return copy(source, target)
    monkeypatch.setattr(native.shutil, 'copyfile', corrupted_once)
    assert acquire(scene, adapter)
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert (scene.content / 'Region/Mesh.uasset').read_bytes() == scene.staged['content/Region/Mesh.uasset'].read_bytes()


def test_missing_native_import_hash_never_certifies_captured_bytes(scene, monkeypatch):
    scene.tags[scene.package] = '[]'
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    assert not list(scene.content.glob('Region/*'))
    monkeypatch.setattr(scene.unreal, 'load_asset', lambda _: None)
    adapter.validated('Mesh')
    assert not adapter.receipts.path.exists()
    assert adapter.counts['reused_candidate'] == 0


def test_loaded_registry_uses_engine_import_data_key_and_rejects_changed_source(scene):
    # UObject::SourceFileTagName() emits AssetImportData in UE5.8. The fake
    # deliberately returns no value for arbitrary tag names, as the engine does.
    mesh = SimpleNamespace(package=scene.package)
    source = scene.sources[0][1]
    assert native.imported_source_matches(mesh, source)
    source.write_bytes(b'different current geometry')
    assert not native.imported_source_matches(mesh, source)


def test_changed_source_or_corrupt_copy_cannot_publish_candidate_receipt(scene):
    adapter = scene.adapter()
    scene.sources[0][1].write_bytes(b'changed source')
    with pytest.raises(ValueError, match='generator report'):
        acquire(scene, adapter)
    assert not scene.content.exists()
    scene.sources[0][1].write_bytes(b'expected mesh source')
    scene.staged['content/Region/Mesh.uasset'].write_bytes(b'corrupt staged bytes')
    assert acquire(scene, adapter) is None
    assert not (scene.content / 'Region/Mesh.uasset').exists()


def test_warm_receipt_reuses_and_changed_package_refuses(scene):
    first = scene.adapter(); assert acquire(scene, first)
    first.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    second = scene.adapter(); assert acquire(scene, second)
    assert second.counts['reused_local'] == 1
    (scene.content / 'Region/Mesh.ubulk').write_bytes(b'changed saved geometry')
    third = scene.adapter()
    # An old whole-task stamp cannot override a failed, finer package receipt.
    third.local_compatible = True
    third.previous_fingerprint = 'd' * 64
    assert acquire(scene, third) is None


def test_fresh_import_after_candidate_refusal_records_current_provenance(scene):
    scene.tags[scene.package] = '[]'
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    adapter.imported('Mesh')
    assert adapter.pending['Mesh']['provenance'] == {'kind': 'current-native-import'}


def test_receiving_observation_refuses_later_engine_sdk_change(tmp_path):
    ctx = SimpleNamespace(out=tmp_path / 'build', uproject=tmp_path / 'game/Game.uproject',
                          unreal_root=tmp_path / 'engine')
    for path in (ctx.unreal_root / 'Engine/Binaries/Mac/UnrealEditor.modules',
                 ctx.uproject.parent / 'Binaries/Mac/UnrealEditor.modules'):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{"BuildId":"same"}')
    assert native.observed_environment(ctx, {'engine': 'same', 'sdk': 'first'})
    assert not native.observed_environment(ctx, {'engine': 'same', 'sdk': 'changed'})


@pytest.mark.parametrize('suffix', ['.uasset', '.ubulk', '.upayload'])
def test_registry_invisible_disk_members_refuse_copy(scene, suffix):
    target = scene.content / ('Region/Mesh' + suffix)
    target.parent.mkdir(parents=True); target.write_bytes(b'unproved existing output')
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    assert target.read_bytes() == b'unproved existing output'


def test_matching_property_does_not_dirty_asset():
    writes = []
    asset = SimpleNamespace(get_editor_property=lambda _: 1,
                            set_editor_property=lambda *args: writes.append(args))
    native.set_if_changed(asset, 'setting', 1)
    assert writes == []


def test_material_group_publishes_only_after_parent_and_preserves_unchanged_bytes(tmp_path, monkeypatch):
    from atelier import native_protocol
    repo = tmp_path.resolve(); monkeypatch.setattr(paths, 'REPO', repo)
    ctx = SimpleNamespace(out=repo / 'build/game', uproject=repo / 'games/game/unreal/Game.uproject')
    script = ctx.uproject.parent / 'Scripts/importer.py'; script.parent.mkdir(parents=True)
    script.write_text('def materials(): return 1\n')
    texture = ctx.out / 'paint.png'; texture.parent.mkdir(parents=True); texture.write_bytes(b'paint')
    content = ctx.uproject.parent / 'Content/Region/Material.uasset'
    content.parent.mkdir(parents=True); content.write_bytes(b'saved native material')
    monkeypatch.setattr(native, 'context', lambda _: {})
    monkeypatch.setattr(native_protocol, 'context', lambda _: {})
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'a' * 24)
    saves = []
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(
        EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_content_packages=lambda: []), load_asset=lambda p: p,
        EditorAssetLibrary=SimpleNamespace(save_loaded_asset=lambda asset, **kw: saves.append(asset) or True)))
    group = native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture])
    packages = ['/Game/Region/Material']
    assert not group.matches(packages)
    group.validated(packages)
    assert not group.book.path.exists()  # a failed native child leaves no reuse receipt
    mesh_reuse.finalize_pending(ctx, 'unreal.region', 'a' * 24)
    again = native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture])
    assert again.matches(packages) and saves == packages
    texture.write_bytes(b'changed paint')
    assert not native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={'colour': 1}, sources=[texture]).matches(packages)


@pytest.mark.parametrize('saved', [None, [], {}, {'context': {}}])
def test_malformed_receiving_environment_is_a_miss(tmp_path, saved):
    ctx = SimpleNamespace(out=tmp_path)
    file = tmp_path / 'native-imports/environment.json'; file.parent.mkdir()
    file.write_text(json.dumps(saved))
    assert not native.observed_environment(ctx, {})


@pytest.mark.parametrize('shared', [False, True])
def test_current_common_receipt_binds_owner_finishing_and_support(scene, monkeypatch, shared):
    owner = scene.ctx.uproject.parent / 'Scripts/owner.py'; owner.parent.mkdir()
    helper = paths.REPO / 'platform/shared/finishing.py' if shared else owner.with_name('finishing.py')
    helper.parent.mkdir(parents=True, exist_ok=True); helper.write_text('SETTING=1\n')
    owner.write_text('from finishing import SETTING\ndef main(): return SETTING\n')
    script = paths.REPO / 'import.py'
    monkeypatch.setattr(mesh_reuse, 'revision_source', lambda repo, revision, name: (repo / name).read_text())
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda repo, name, recorded: (repo / name).read_text())
    def adapter():
        return native.MeshReuse(scene.ctx, 'unreal.region', script, ('build',), owner_script=owner, owner_roots=(helper.parent,))
    first = adapter(); assert acquire(scene, first)
    first.validated('Mesh'); mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    assert acquire(scene, adapter())
    helper.write_text('SETTING=2\n')
    assert acquire(scene, adapter()) is None
    helper.write_text('SETTING=1\n'); owner.write_text('from finishing import SETTING\ndef main(): return SETTING+1\n')
    assert acquire(scene, adapter()) is None


def test_unsupported_material_policy_runs_builder_without_publishing_receipt(tmp_path, monkeypatch):
    ctx = SimpleNamespace(out=tmp_path / 'build/game', uproject=tmp_path / 'games/game/unreal/Game.uproject')
    script = ctx.uproject.parent / 'Scripts/importer.py'; script.parent.mkdir(parents=True)
    script.write_text('class Unsupported: pass\ndef materials(): return 1\n')
    monkeypatch.setattr(native, 'context', lambda _: {})
    monkeypatch.setenv('ATELIER_MESH_REUSE_NONCE', 'a' * 24)
    saves = []
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(
        EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_content_packages=lambda: []), load_asset=lambda p: p,
        EditorAssetLibrary=SimpleNamespace(save_loaded_asset=lambda asset, **kw: saves.append(asset) or True)))
    group = native.AssetGroup(ctx, 'unreal.region', script, ('materials',), parameters={})
    assert not group.matches(['/Game/Region/Material'])
    group.validated(['/Game/Region/Material'])
    assert saves == ['/Game/Region/Material']
    assert not group.book.path.exists() and not (ctx.out / '.state/mesh-import-pending').exists()


def test_candidate_uses_original_task_policy_not_capture_head(scene, monkeypatch):
    script = paths.REPO / 'import.py'
    monkeypatch.setattr(mesh_reuse, 'revision_source', lambda *args: pytest.fail('capture HEAD is not producer proof'))
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda *args: 'def build(): return 2\n')
    reuse = native.MeshReuse(scene.ctx, 'unreal.region', script, ('build',))
    assert acquire(scene, reuse) is None and reuse.counts['reused_candidate'] == 0


def test_candidate_missing_original_task_evidence_misses(scene):
    scene.bundle.pop('donor_stamp')
    reuse = native.MeshReuse(scene.ctx, 'unreal.region', paths.REPO / 'import.py', ('build',))
    assert acquire(scene, reuse) is None


def test_dirty_loaded_mesh_refuses_otherwise_valid_disk_receipt(scene, monkeypatch):
    reuse = scene.adapter(); assert acquire(scene, reuse)
    reuse.validated('Mesh'); mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    monkeypatch.setattr(sys.modules['unreal'].EditorLoadingAndSavingUtils, 'get_dirty_content_packages',
                        lambda: [SimpleNamespace(get_name=lambda: scene.package)])
    again = scene.adapter()
    assert acquire(scene, again) is None
    assert again.counts['reused_local'] == 0


def test_missing_dirty_package_readback_misses(scene, monkeypatch):
    monkeypatch.delattr(sys.modules['unreal'], 'EditorLoadingAndSavingUtils')
    assert acquire(scene, scene.adapter()) is None


def validation_scene(scene, monkeypatch, *, geometry_changed=False):
    script = paths.REPO / 'import.py'
    old = 'def build(): return 2\n' if geometry_changed else 'def build(): return 1\n'
    script.write_text('def build(): return 1\ndef validate(mesh): return bool(mesh)\n')
    previous = dict(fingerprint='f' * 64, time=1., input_state={'inputs': {'<repo>/import.py': 'd' * 64}})
    monkeypatch.setattr(mesh_reuse, 'saved_source', lambda *a: old)
    monkeypatch.setattr(mesh_reuse, 'prior_stamp', lambda *a: previous)
    monkeypatch.setattr(mesh_reuse, 'historical_packages_match', lambda *a: True)
    monkeypatch.setattr(native, 'observed_environment', lambda *a: True)
    for member, file in scene.staged.items():
        if member.startswith('content/'):
            target = scene.content / member.removeprefix('content/')
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(file.read_bytes())
    return lambda **kw: native.MeshReuse(scene.ctx, 'unreal.region', script, ('build',),
                                         validation_functions=('validate',), **kw)


def test_new_validator_absent_in_old_source_adopts_warm_packages_after_current_checks(scene, monkeypatch, capsys):
    adapter = validation_scene(scene, monkeypatch)()
    assert adapter.local_compatible
    assert acquire(scene, adapter, validator=lambda mesh: bool(mesh))
    assert 'NATIVE MESH HISTORICAL COMPATIBILITY ' in capsys.readouterr().out
    adapter.validated('Mesh')
    assert not adapter.receipts.path.exists()
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    assert adapter.receipts.path.exists()


@pytest.mark.parametrize('failure', ['source', 'validator'])
def test_failed_historical_validation_does_not_log_an_admission(scene, monkeypatch, capsys, failure):
    adapter = validation_scene(scene, monkeypatch)()
    if failure == 'source':
        scene.tags[scene.package] = None
    assert acquire(scene, adapter, validator=lambda mesh: failure != 'validator') is None
    assert adapter.counts['reused_local'] == 0
    assert 'NATIVE MESH HISTORICAL COMPATIBILITY ' not in capsys.readouterr().out


def test_separate_current_validator_never_weakens_historical_geometry_equality(scene, monkeypatch):
    adapter = validation_scene(scene, monkeypatch, geometry_changed=True)()
    assert not adapter.local_compatible
    assert acquire(scene, adapter, validator=lambda mesh: True) is None


def test_validator_change_rekeys_current_receipts_without_changing_geometry_policy(scene, monkeypatch):
    make = validation_scene(scene, monkeypatch)
    first = make(); assert acquire(scene, first, validator=lambda mesh: True)
    first.validated('Mesh'); mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    script = paths.REPO / 'import.py'
    script.write_text('def build(): return 1\ndef validate(mesh): return mesh is not None\n')
    second = make()
    assert second.policy == first.policy
    assert second.receipts.header['policy'] != first.receipts.header['policy']
    assert acquire(scene, second, validator=lambda mesh: True) is None


@pytest.mark.parametrize('failure', ['false', 'exception', 'missing'])
def test_invalid_current_validator_is_an_ordinary_warm_miss(scene, monkeypatch, failure):
    make = validation_scene(scene, monkeypatch)
    if failure == 'missing':
        (paths.REPO / 'import.py').write_text('def build(): return 1\n')
    adapter = make()
    def validator(mesh):
        if failure == 'exception':
            raise RuntimeError('readback unavailable')
        return False
    assert acquire(scene, adapter, validator=validator) is None
    assert not adapter.receipts.path.exists()


def test_current_validator_support_code_and_explicit_script_are_bound(scene, monkeypatch):
    make = validation_scene(scene, monkeypatch)
    script = paths.REPO / 'validator.py'
    helper = paths.REPO / 'support.py'; helper.write_text('EXPECTED=1\n')
    script.write_text('import support\ndef validate(mesh): return support.EXPECTED\n')
    first = make(validation_script=script)
    helper.write_text('EXPECTED=2\n')
    second = make(validation_script=script)
    assert second.policy == first.policy
    assert second.receipts.header['policy'] != first.receipts.header['policy']


def test_declared_validation_cannot_adopt_without_running_its_callback(scene, monkeypatch):
    adapter = validation_scene(scene, monkeypatch)()
    assert adapter.local_compatible
    assert acquire(scene, adapter) is None
    assert adapter.counts['reused_local'] == 0


@pytest.mark.parametrize('failure,reason', [
    ('policy', 'unsupported_policy'),
    ('callback', 'required_validator_missing'),
    ('dirty', 'dirty_loaded_package'),
    ('history', 'no_compatible_package_history'),
    ('geometry', 'candidate_geometry_mismatch'),
    ('source', 'recorded_source_mismatch'),
    ('validator', 'current_validator_rejected'),
    ('exception', 'current_validator_exception'),
])
def test_miss_diagnostics_report_the_refusal_without_counting_reuse(scene, monkeypatch, failure, reason):
    adapter = scene.adapter()
    options = {}
    if failure == 'policy': adapter.enabled = False
    if failure == 'callback': adapter.requires_validator = True
    if failure == 'dirty':
        monkeypatch.setattr(native, 'packages_clean', lambda _: False)
    if failure == 'history': adapter.compatible = False
    if failure == 'geometry': options['donor_geometry'] = {'source': 'changed'}
    if failure == 'source': scene.tags[scene.package] = None
    if failure == 'validator': options['validator'] = lambda _: False
    if failure == 'exception':
        def validator(_):
            raise RuntimeError('private exception text must not enter diagnostics')
        options['validator'] = validator
    assert acquire(scene, adapter, **options) is None
    assert adapter.miss_reasons == {reason: 1}
    assert adapter.counts == dict(imported=0, reused_local=0, reused_candidate=0)
    assert not (adapter.receipts.path.parent / 'summary.json').exists()


def test_disabled_mesh_policy_finalizes_import_diagnostics_without_a_reusable_receipt(scene):
    adapter = scene.adapter()
    adapter.enabled = False
    assert acquire(scene, adapter) is None
    adapter.imported('Mesh')
    adapter.validated('Mesh')
    summary = adapter.receipts.path.parent / 'summary.json'
    assert not summary.exists() and not adapter.receipts.path.exists()
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    value = json.loads(summary.read_text())
    assert value['invocation'] == 'e' * 24 and value['finalized_after_native_success'] is True
    assert value['counts'] == dict(imported=1, reused_local=0, reused_candidate=0)
    assert value['miss_reasons'] == {'unsupported_policy': 1}
    assert not adapter.receipts.path.exists()


def test_successful_candidate_has_no_miss_diagnostic(scene):
    adapter = scene.adapter()
    assert acquire(scene, adapter)
    adapter.validated('Mesh')
    mesh_reuse.finalize_pending(scene.ctx, 'unreal.region', 'e' * 24)
    value = json.loads((adapter.receipts.path.parent / 'summary.json').read_text())
    assert value['counts']['reused_candidate'] == 1 and value['miss_reasons'] == {}


def two_donors(scene, monkeypatch):
    from copy import deepcopy
    first = deepcopy(scene.bundle)
    first['checkpoint'] = '1' * 64
    monkeypatch.setattr(checkpoint_candidates, 'load_all', lambda *_: [first, scene.bundle])
    return first


def test_registry_source_rejection_retries_without_loading_or_unloading(scene, monkeypatch):
    two_donors(scene, monkeypatch)
    registry = scene.unreal.AssetRegistryHelpers.get_asset_registry()
    real = registry.k2_get_asset_by_object_path
    monkeypatch.setattr(registry, 'k2_get_asset_by_object_path', lambda p, disk:
        SimpleNamespace(get_tag_value=lambda _: None) if len(scene.scans) == 1 else real(p, disk))
    adapter = scene.adapter()
    assert acquire(scene, adapter)
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert len(scene.scans) == 2 and len(scene.removals) == 1 and scene.unloads == []
    assert adapter.counts['reused_candidate'] == 1 and not adapter.receipts.path.exists()


@pytest.mark.parametrize('failure', ['load_null', 'load_exception', 'source', 'validator', 'validator_exception'])
def test_native_rejection_unloads_only_attempt_then_admits_later_donor(scene, monkeypatch, failure):
    two_donors(scene, monkeypatch)
    real = scene.unreal.load_asset
    def load(package):
        value = real(package)  # Model an asset loaded even when its wrapper fails.
        if len(scene.scans) == 1 and package == scene.package:
            if failure == 'load_null':
                return None
            if failure == 'load_exception':
                raise RuntimeError('native failed')
        return value
    monkeypatch.setattr(scene.unreal, 'load_asset', load)
    original = native.imported_source_matches
    monkeypatch.setattr(native, 'imported_source_matches', lambda mesh, source:
        False if failure == 'source' and len(scene.scans) == 1 else original(mesh, source))
    def validate(mesh):
        if len(scene.scans) == 1 and failure == 'validator_exception':
            raise RuntimeError('validator failed')
        return not (len(scene.scans) == 1 and failure == 'validator')
    adapter = scene.adapter()
    assert acquire(scene, adapter, validator=validate)
    assert adapter.pending['Mesh']['provenance']['checkpoint'] == scene.bundle['checkpoint']
    assert len(scene.unloads) == 1 and set(scene.unloads[0]) <= {p for p, _, _ in scene.sources}
    assert len(scene.removals) == 1 and len(scene.scans) == 2
    assert adapter.counts == dict(reused_local=0, reused_candidate=1, imported=0)
    assert not adapter.receipts.path.exists()


@pytest.mark.parametrize('refusal', ['dirty', 'changed', 'retained', 'registry', 'new_sidecar'])
def test_uncertain_attempt_cleanup_stops_import_without_overwrite_or_receipt(scene, monkeypatch, refusal):
    two_donors(scene, monkeypatch)
    target = scene.content / 'Region/Mesh.uasset'
    def validate(mesh):
        if refusal == 'dirty':
            monkeypatch.setattr(scene.unreal.EditorLoadingAndSavingUtils, 'get_dirty_content_packages',
                lambda: [SimpleNamespace(get_name=lambda: scene.package)])
        if refusal == 'changed':
            target.write_bytes(b'owner-modified package')
        if refusal == 'new_sidecar':
            target.with_suffix('.upayload').write_bytes(b'new owner output')
        return False
    if refusal == 'retained':
        monkeypatch.setattr(scene.unreal.EditorLoadingAndSavingUtils, 'unload_packages', lambda _: True)
    if refusal == 'registry':
        registry = scene.unreal.AssetRegistryHelpers.get_asset_registry()
        monkeypatch.setattr(registry, 'scan_modified_asset_files', lambda _: None)
    adapter = scene.adapter()
    with pytest.raises(RuntimeError, match='cleanup refused'):
        acquire(scene, adapter, validator=validate)
    assert len(scene.scans) == 1
    assert adapter.counts['reused_candidate'] == 0 and not adapter.receipts.path.exists()
    if refusal != 'registry':
        assert target.exists()
    if refusal == 'changed':
        assert target.read_bytes() == b'owner-modified package'
    assert scene.staged['content/Region/Mesh.uasset'].read_bytes().startswith(b'candidate:')


def test_live_registry_invisible_asset_is_not_replaced(scene):
    scene.objects[scene.package + '.Mesh'] = SimpleNamespace(package=scene.package)
    adapter = scene.adapter()
    assert acquire(scene, adapter) is None
    assert not scene.content.exists() and scene.scans == []


def test_all_native_rejections_leave_no_registry_or_disk_scope_for_ordinary_import(scene):
    adapter = scene.adapter()
    assert acquire(scene, adapter, validator=lambda _: False) is None
    assert scene.registered == set() and scene.objects == {}
    assert not list(scene.content.glob('Region/*'))
    assert adapter.pending['Mesh']['provenance'] == {'kind': 'current-native-import'}
    assert adapter.counts['reused_candidate'] == 0
