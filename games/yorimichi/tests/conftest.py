"""Shared, immutable inputs for the game tests; mutation tests use private fixtures."""
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def unmanaged_builder_checkout(tmp_path, monkeypatch):
    """Bind isolated v1 Context/recipe simulations to their actual unmanaged checkout.

    These tests do not exercise the real mixed game caller. Do not override management
    decisions: use a checkout with no controller declarations or saved B3 ownership.
    The real normal-CLI integration fixture does not request this substitution.
    """
    from atelier.build_v2 import legacy_entry
    monkeypatch.setattr(legacy_entry, '_checkout', lambda: tmp_path)
    assert legacy_entry.controller_names('yorimichi', tmp_path) == ()
    metadata = tmp_path / 'build/build-v2/install'
    assert not metadata.exists() and not metadata.is_symlink()
    assert not legacy_entry.managed('yorimichi', ())
    return tmp_path


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


@pytest.fixture(autouse=True)
def craterpark_generator_by_choice(monkeypatch):
    """The build ships the editor park by default (craterpark.v2.v4_config.SHIPPED); a test sees the older generator
    unless it selects a park itself, as these tests were written against."""
    if 'ATELIER_CRATERPARK_EDITOR_PARK' not in os.environ:
        monkeypatch.setenv('ATELIER_CRATERPARK_EDITOR_PARK', 'off')
