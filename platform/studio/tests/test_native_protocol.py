"""Embedded imports never depend on build/release controllers."""
from pathlib import Path
import subprocess
import sys

import pytest

from atelier import native_protocol, paths, source_imports


def test_declared_native_protocol_is_complete_and_excludes_controller():
    actual = source_imports.local_imports(Path(native_protocol.__file__).with_name('unreal_mesh_reuse.py'))
    assert set(actual) == set(native_protocol.runtime_files())
    assert all(file.parent == Path(native_protocol.__file__).parent for file in actual)
    forbidden = {'build.py', 'build_cache.py', 'checkpoint_store.py', 'checkpoint_actions.py',
                 'release.py', 'playtest.py', 'artifact_pool.py'}
    assert not forbidden.intersection(file.name for file in actual)
    # Also exercise import execution with only the standard interpreter available.
    program = ('import sys; from atelier import unreal_mesh_reuse; '
               'assert not any(name in sys.modules for name in '
               + repr(tuple('atelier.' + name.removesuffix('.py') for name in forbidden)) + ')')
    subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0,' + repr(str(paths.STUDIO)) + '); ' + program], check=True)


def test_native_context_reads_existing_paths_without_creating_state(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'GAMES', tmp_path / 'games')
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(tmp_path / 'generated'))
    folder = paths.GAMES / 'sample/unreal'; folder.mkdir(parents=True)
    project = folder / 'Sample.uproject'; project.write_text('{}')
    ctx = native_protocol.native_context('sample')
    assert vars(ctx).keys() == {'game', 'out', 'uproject', 'unreal_root'}
    assert ctx.uproject == project and ctx.out == tmp_path / 'generated/sample'
    assert not ctx.out.exists()


@pytest.mark.parametrize('name', ['../sample', '/sample', 'a/b', '', 'a..b'])
def test_native_context_refuses_noncanonical_game_owner(name):
    with pytest.raises(ValueError):
        native_protocol.native_context(name)
