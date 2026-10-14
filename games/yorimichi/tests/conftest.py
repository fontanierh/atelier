"""Shared, immutable inputs for the game tests; mutation tests use private fixtures."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope='session')
def skating_package(tmp_path_factory):
    """@cc [owner:fontanierh,label:correctness] fresh-shared-skating-fixture
    The package MUST be assembled from committed sources in this test session. Its files and
    directories MUST be read-only while shared; tests that mutate payloads MUST use private copies.
    """
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        'simulation_package_fixture',
        repo / 'platform/engine/Plugins/Activities/Skate/Tools/simulation_package.py')
    simulation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(simulation)
    package = simulation.assemble(tmp_path_factory.mktemp('skating') / 'package')
    members = [package, *package.rglob('*')]
    try:
        for path in members:
            path.chmod(0o555 if path.is_dir() else 0o444)
        yield package
    finally:
        # Restore write permission for pytest's temporary-directory cleanup, even on test failure.
        for path in members:
            path.chmod(0o755 if path.is_dir() else 0o644)
