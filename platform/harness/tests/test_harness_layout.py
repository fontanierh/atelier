"""A relocation must preserve public imports, embedded interpreters and packaged entry points."""
import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from atelier import paths


@pytest.mark.parametrize('name', ['board', 'board_store', 'capacity', 'capacity_client',
                                  'safety', 'safety.guarded', 'safety.memory_guard'])
def test_legacy_import_is_the_canonical_module(name):
    old = importlib.import_module('atelier.' + name)
    current = importlib.import_module('atelier.harness.' + name)
    assert old is current
    assert current.__spec__.name == 'atelier.harness.' + name
    assert Path(current.__file__).is_relative_to(paths.PLATFORM / 'harness')


def test_legacy_types_keep_their_identity():
    from atelier.capacity import Resources as old
    from atelier.harness.capacity import Resources as current
    assert old is current


def test_embedded_python_needs_only_the_existing_studio_path():
    code = ('import atelier.capacity_client as old; '
            'import atelier.harness.capacity_client as new; '
            'assert old is new; assert old.AdmissionSession is new.AdmissionSession')
    subprocess.run([sys.executable, '-S', '-c', code], check=True, timeout=10,
                   env={**os.environ, 'PYTHONPATH': str(paths.STUDIO)}, capture_output=True)


@pytest.mark.parametrize('name', ['atelier.safety.guarded', 'atelier.harness.safety.guarded'])
def test_module_entry_point(name):
    result = subprocess.run([sys.executable, '-m', name, '--help'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert '--report' in result.stdout and '--kind' in result.stdout


def test_server_sources_and_assets_are_in_harness():
    from atelier.harness import board_web, slack_board
    assert Path(slack_board.__file__).is_file()
    assert (board_web.ASSETS / 'app.js').is_file()
    assert (board_web.ASSETS / 'index.html').is_file()


def test_static_recipe_scan_reaches_harness_and_shared_studio_code(tmp_path):
    from atelier.build_inputs import ImportScanner
    script = tmp_path / 'recipe.py'
    script.write_text('from atelier.harness import board_web\n')
    found = ImportScanner().local_imports(script)
    assert paths.HARNESS / 'harness' / 'board_web.py' in found
    assert paths.STUDIO / 'atelier' / 'paths.py' in found
    assert paths.STUDIO / 'atelier' / '__init__.py' in found
    assert paths.HARNESS / 'harness' / '__init__.py' in found
    assert paths.HARNESS / 'harness' / 'compat.py' in found
    script.write_text('from atelier import board_web\n')
    assert paths.HARNESS / 'harness' / 'board_web.py' in ImportScanner().local_imports(script)


def test_ordinary_authoring_import_does_not_load_harness():
    code = ('import sys; from atelier import paths; '
            'assert not any(n.startswith("atelier.harness") for n in sys.modules)')
    subprocess.run([sys.executable, '-S', '-c', code], check=True, timeout=10,
                   env={**os.environ, 'PYTHONPATH': str(paths.STUDIO)}, capture_output=True)


def test_ordinary_authoring_scan_does_not_depend_on_harness(tmp_path):
    from atelier.build_inputs import ImportScanner
    script = tmp_path / 'generator.py'
    script.write_text('from atelier import paths\n')
    assert not any(p.is_relative_to(paths.HARNESS) for p in ImportScanner().local_imports(script))


def test_source_tool_support_resolves_the_moved_guard_files():
    from atelier import build_cache, artifact_publisher
    support = build_cache.tool_support()
    for name in ('process.py', 'exec_gate.py'):
        source = paths.HARNESS / 'harness' / 'safety' / name
        assert support['safety/' + name] == source
        assert source.is_file() and source in artifact_publisher.TOOL_SUPPORT


def test_ordinary_import_performs_no_path_metadata_probes():
    # Audited generators can import the shared initializer while their reads are
    # restricted. Mounting the namespace must not inspect unrelated directories.
    code = '''
from pathlib import Path
def refuse(*args, **kwargs):
    raise AssertionError('ordinary package import probed filesystem metadata')
Path.resolve = Path.stat = refuse
import atelier
'''
    subprocess.run([sys.executable, '-S', '-c', code], check=True, timeout=10,
                   env={**os.environ, 'PYTHONPATH': str(paths.STUDIO)}, capture_output=True)
