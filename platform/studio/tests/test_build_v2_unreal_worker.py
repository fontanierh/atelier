"""Unit checks of the build-v2 Unreal job loop's own rules (no editor; the session runs in tests/unreal.rs)."""
import json
import os
from pathlib import Path
import sys
import types

import pytest

from atelier.build_v2 import unreal_worker
from atelier.build_v2.unreal_worker import Editor, JobRefused, StartRefused, Worker


def test_protocol_descriptors_must_appear_once_and_be_pipes(tmp_path):
    read, write = os.pipe()
    try:
        assert unreal_worker.protocol_fds(f'x.uproject -stdout --request-fd {read} --response-fd {write}') == (read, write)
        assert not os.get_inheritable(read) and not os.get_inheritable(write)
        for line in (f'--request-fd {read}', f'--request-fd {read} --request-fd {read} --response-fd {write}',
                     f'--request-fd x --response-fd {write}'):
            with pytest.raises(StartRefused):
                unreal_worker.protocol_fds(line)
        with open(tmp_path / 'file', 'w') as regular:
            with pytest.raises(StartRefused, match='not a pipe'):
                unreal_worker.protocol_fds(f'--request-fd {regular.fileno()} --response-fd {write}')
    finally:
        os.close(read)
        os.close(write)


def test_package_names_come_only_from_primary_files_under_the_content_root():
    assert unreal_worker.package_of('content/Game/Meshes/Rock.uasset', 'content/Game/') == '/Game/Meshes/Rock'
    assert unreal_worker.package_of('content/Game/Maps/Crater.umap', 'content/Game/') == '/Game/Maps/Crater'
    assert unreal_worker.package_of('content/Game/Meshes/Rock.ubulk', 'content/Game/') is None
    assert unreal_worker.package_of('other/Rock.uasset', 'content/Game/') is None
    # Ownership covers companion files: every package file names the package whose save made it.
    assert unreal_worker.package_owning('content/Game/Meshes/Rock.ubulk', 'content/Game/') == '/Game/Meshes/Rock'
    assert unreal_worker.package_owning('content/Game/Meshes/Rock.uexp', 'content/Game/') == '/Game/Meshes/Rock'
    assert unreal_worker.package_owning('content/Game/Meshes/Rock.txt', 'content/Game/') is None
    for path in ('', '/abs', 'a/../b', 'a//b', 'a\\b', './a'):
        with pytest.raises(JobRefused):
            unreal_worker._job_relative(path, 'output')


class Unloading:
    """An editor whose unload call says it unloaded everything while one package stays referenced. As in the
    editor, SystemLibrary.collect_garbage only schedules a collection; only the plugin's call collects."""

    def __init__(self, survivor, imported=()):
        self.alive = {'/Game/A', '/Game/B'}
        self.unloaded = set()
        self.survivor = survivor
        self.held = set(imported)  # as after an import: the first unload frees nothing
        library = types.SimpleNamespace(collect_garbage_now=self.collect)
        unreal = types.SimpleNamespace(
            AtelierBuildWorkerLibrary=library,
            find_object=lambda outer, name: name if name in self.alive else None,
            EditorLoadingAndSavingUtils=types.SimpleNamespace(unload_packages=self.unload_packages),
            SystemLibrary=types.SimpleNamespace(collect_garbage=lambda: None))
        self.editor = Editor(unreal)

    def unload_packages(self, objects):
        held, self.held = self.held & set(objects), set()
        self.unloaded |= set(objects) - {self.survivor} - held
        return True  # "any" were unloaded

    def collect(self):
        self.alive -= self.unloaded


def test_unload_collects_synchronously_and_checks_every_package_by_name():
    assert Unloading(survivor=None).editor.unload(['/Game/A', '/Game/B']) == []
    assert Unloading(survivor='/Game/B').editor.unload(['/Game/A', '/Game/B']) == ['/Game/B']
    # Imported packages survive the first pass and are gone after the second.
    assert Unloading(survivor=None, imported={'/Game/A', '/Game/B'}).editor.unload(['/Game/A', '/Game/B']) == []
    assert Unloading(survivor=None, imported={'/Game/A'}).editor.unload(['/Game/A', '/Game/B'], passes=1) == ['/Game/A']


def test_python_state_is_restored_and_job_modules_are_dropped(tmp_path):
    job = tmp_path / 'job'
    (job / 'ops').mkdir(parents=True)
    (job / 'ops/helper_c3_unit.py').write_text('VALUE = 1\n')
    state = unreal_worker._PythonState()
    sys.path.insert(0, str(job / 'ops'))
    os.environ['ATELIER_C3_UNIT'] = '1'
    import helper_c3_unit  # noqa: F401
    unreal_worker._PythonState.restore(state, job)
    assert str(job / 'ops') not in sys.path
    assert 'ATELIER_C3_UNIT' not in os.environ
    assert 'helper_c3_unit' not in sys.modules


class Fake:
    """Just enough editor for `Worker.execute` to reach its job checks."""

    def __init__(self, project):
        self.project = project

    def project_dir(self):
        return self.project


def worker(tmp_path):
    project = tmp_path / 'project'
    (project / 'Content').mkdir(parents=True)
    return Worker(Fake(project), None, None), project


def job(tmp_path, outputs, **extra):
    folder = tmp_path / 'job'
    (folder / 'output').mkdir(parents=True, exist_ok=True)
    return {'job_id': 'j', 'job_dir': str(folder), 'script': 'ops/op.py', 'code': ['ops/op.py'], 'inputs': [],
            'params': {}, 'outputs': [{'path': path, 'required': True} for path in outputs], **extra}


@pytest.mark.parametrize('path', ['content/Game/Rock.txt', 'output/Game/Rock.uasset', 'content/Engine/Rock.uasset'])
def test_outputs_must_be_package_files_under_the_game_content_root(tmp_path, path):
    loop, _ = worker(tmp_path)
    with pytest.raises(JobRefused, match='is not a package file') as refusal:
        loop.execute(job(tmp_path, [path]), set(), [])
    assert refusal.value.kind == 'protocol'


def test_a_job_never_starts_on_a_non_empty_game_folder_or_output(tmp_path):
    loop, project = worker(tmp_path)
    request = job(tmp_path, ['content/Game/A.uasset'])
    (project / 'Content/Left.uasset').write_bytes(b'x')
    with pytest.raises(JobRefused, match='/Game is not empty') as refusal:
        loop.execute(request, set(), [])
    assert refusal.value.kind == 'dependency'
    (Path(request['job_dir']) / 'output/stale').write_bytes(b'x')
    with pytest.raises(JobRefused, match='output/ is not empty'):
        loop.execute(request, set(), [])


def test_the_worker_plugin_source_is_outside_every_folder_a_game_or_v1_enumerates():
    """No game discovers the editor-only plugin, and v1's checkpoint enumeration never sees it."""
    from atelier import paths, unreal_modules
    plugin = paths.PLATFORM / 'build-v2/unreal/AtelierBuildWorker'
    assert (plugin / 'AtelierBuildWorker.uplugin').is_file()
    # checkpoint_store.roots and checkpoint_actions walk these for every game.
    assert not plugin.resolve().is_relative_to(paths.ENGINE_PLUGINS.resolve())
    assert all(path.stem != 'AtelierBuildWorker' for path in paths.ENGINE_PLUGINS.rglob('*.uplugin'))
    projects = sorted((paths.REPO / 'games').glob('*/unreal/*.uproject'))
    assert projects
    for project in projects:
        assert 'AtelierBuildWorker' not in unreal_modules.plugins(project), project
        assert not plugin.resolve().is_relative_to(project.parent.resolve()), project
        enabled = {p['Name'] for p in json.loads(project.read_text()).get('Plugins', [])}
        assert 'AtelierBuildWorker' not in enabled, project
    # Its compiled binaries are build products of a scratch or micro compile, never committed.
    ignored = (plugin.parent / '.gitignore').read_text().split()
    assert '*/Binaries/' in ignored and '*/Intermediate/' in ignored


def test_the_cache_graph_may_hold_only_the_v2_folder_the_engine_pak_and_memory():
    policy = {'dir': '/store/unreal-ddc/5.8', 'engine_pak': '/engine/Engine/DerivedDataCache/Compressed.ddp'}
    v2 = {'kind': 'File System', 'path': '/store/unreal-ddc/5.8'}
    pak = {'kind': 'Pak File', 'path': '/engine/Engine/DerivedDataCache/Compressed.ddp'}
    assert unreal_worker.ddc_problem(policy, [pak, v2]) is None
    assert unreal_worker.ddc_problem(policy, [v2, {'kind': 'Memory', 'path': ''}]) is None
    assert 'no cache node' in unreal_worker.ddc_problem(policy, [pak])
    for bad in ({'kind': 'Zen', 'path': ''}, {'kind': 'File System', 'path': '/shared/DerivedDataCache'},
                {'kind': 'File System', 'path': '/store/unreal-ddc/5.8-other'},
                {'kind': 'File System', 'path': 'relative/unreal-ddc/5.8'},
                {'kind': 'Pak File', 'path': '/project/DerivedDataCache/DDC.ddp'},
                {'kind': 'Http', 'path': 'https://cache'}, {'kind': '', 'path': '/store/unreal-ddc/5.8'}):
        assert 'outside the v2 DDC folder' in unreal_worker.ddc_problem(policy, [v2, bad]), bad


def test_a_plugin_identity_covers_its_descriptor_and_binaries_by_relative_path(tmp_path):
    import hashlib
    plugin = tmp_path / 'Interchange'
    (plugin / 'Binaries/Mac').mkdir(parents=True)
    (plugin / 'Interchange.uplugin').write_bytes(b'{}')
    (plugin / 'Binaries/Mac/libUnrealEditor-Interchange.dylib').write_bytes(b'bytes')
    (plugin / 'Source').mkdir()
    (plugin / 'Source/Ignored.cpp').write_bytes(b'// never covered')
    digest = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
    manifest = (f'Interchange.uplugin\0{digest(b"{}")}\n'
                f'Binaries/Mac/libUnrealEditor-Interchange.dylib\0{digest(b"bytes")}\n')
    assert unreal_worker.plugin_identity(plugin, 'Interchange') == digest(manifest.encode())
    (plugin / 'Binaries/Mac/libUnrealEditor-Interchange.dylib').write_bytes(b'replaced')
    assert unreal_worker.plugin_identity(plugin, 'Interchange') != digest(manifest.encode())
    assert unreal_worker.plugin_identity(tmp_path / 'Missing', 'Missing').startswith('unreadable')


def test_a_declared_setting_matches_the_editor_value_as_text_or_an_exact_number():
    same = unreal_worker.same_value
    # Console variables: exact text, or the same finite decimal value printed another way.
    assert same('0', '0', numeric=True)
    assert same('0.5', '0.500000', numeric=True)
    assert same('1', '1.0', numeric=True)
    assert not same('1', '0', numeric=True)
    assert not same('Log', 'Verbose', numeric=True)
    # Never rounded through a binary float: neighbouring integers and overflowing texts stay distinct.
    assert not same('9007199254740993', '9007199254740992', numeric=True)
    assert not same('1e999', '2e999', numeric=True)
    assert not same('1e999', 'inf', numeric=True)
    assert not same('nan', 'nan ', numeric=True)
    # A setting the editor does not hold is never a match, whatever the declared text.
    assert not same('None', None, numeric=True)
    assert not same('None', None, numeric=False)
    # Ini values: exact text only.
    assert same('Verbose', 'Verbose', numeric=False)
    assert not same('01', '1', numeric=False)
    assert not same('0.5', '0.500000', numeric=False)


def test_scoped_python_guard_refuses_unknown_reads_and_restores_afterwards(tmp_path):
    root = tmp_path / 'job'
    root.mkdir()
    (root / 'output').mkdir()
    known = root / 'known'
    known.write_bytes(b'keyed')
    outside = tmp_path / 'outside'
    outside.write_bytes(b'not keyed')
    with pytest.raises(JobRefused, match='undeclared Python'):
        with unreal_worker.declared_python(root, [], [known], [Path(sys.base_prefix)]):
            assert known.read_bytes() == b'keyed'
            try:
                outside.read_bytes()
            except JobRefused:
                pass  # A caught refusal must not make the job successful.
    assert outside.read_bytes() == b'not keyed'
    # The first job's permanent audit dispatcher is inactive for the next job.
    with unreal_worker.declared_python(root, [], [known], [Path(sys.base_prefix)]):
        assert known.read_bytes() == b'keyed'


def test_long_native_sidecar_suffix_has_one_package_owner():
    for suffix in ('.m.ubulk', '.upayload'):
        assert unreal_worker.package_owning('content/Game/A' + suffix, 'content/Game/') == '/Game/A'
