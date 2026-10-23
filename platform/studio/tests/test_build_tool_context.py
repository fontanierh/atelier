"""Complete installed-tool identities with tiny fake bundles; no native tool runs."""
import hashlib
import os

import pytest

from atelier import build, build_cache, build_products, engine


@pytest.fixture
def app(tmp_path, monkeypatch):
    bundle = tmp_path / 'Fixture App.app/Contents'
    binary = bundle / 'MacOS/Blender'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'fake executable')
    for name in ('Resources/one/shared.py', 'Resources/two/shared.py',
                 'Resources/space name/日本語.txt', 'Resources/literal\\name.txt',
                 'Resources/__pycache__/ignored.pyc'):
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))
    step = build.Step('fixture', [build.Blender(tmp_path / 'action.py', factory_startup=True)])
    return bundle, step


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legacy_resources(bundle):
    return {path.relative_to(bundle).as_posix(): digest(path)
            for path in sorted(bundle.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts}


@pytest.mark.parametrize('links', [False, True])
def test_complete_resource_keys_and_hasher_order_match_legacy(app, tmp_path, links):
    bundle, step = app
    if links:
        external = tmp_path / 'external.txt'
        external.write_text('external resource')
        try:
            (bundle / 'Resources/linked-file').symlink_to(external)
            (bundle / 'Resources/linked-directory').symlink_to(external.parent, target_is_directory=True)
            (bundle / 'Resources/broken-link').symlink_to(tmp_path / 'missing')
        except OSError:
            pytest.skip('Host does not permit fixture symlinks')
    expected = legacy_resources(bundle)
    seen = []

    def observed(path):
        seen.append(path)
        return digest(path)

    actual = build_cache.tool_context(step, observed)['blender']
    assert list(actual.items()) == list(expected.items())
    assert build_products.identity(actual) == build_products.identity(expected)
    files = [path for path in sorted(bundle.rglob('*'))
             if path.is_file() and '__pycache__' not in path.parts]
    # The executable is hashed once per stat signature: it identifies the invocation cache, and its
    # resource entry reuses that digest.
    assert [path for path in seen if path.is_relative_to(bundle)] == [bundle / 'MacOS/Blender',
                                                                       *(p for p in files if p != bundle / 'MacOS/Blender')]
    assert 'Resources/one/shared.py' in actual and 'Resources/two/shared.py' in actual
    assert not any('__pycache__' in name for name in actual)


def test_fresh_invocations_discover_resource_add_delete_and_edit(app):
    bundle, step = app
    root_times = bundle.stat()

    def current():
        # A directory timestamp is not a substitute for rediscovering the complete app tree.
        os.utime(bundle, ns=(root_times.st_atime_ns, root_times.st_mtime_ns))
        resources = build_cache.tool_context(step, digest)['blender']
        assert resources == legacy_resources(bundle)
        return resources

    first = current()
    added = bundle / 'Resources/one/new.txt'
    added.write_text('added')
    second = current()
    assert set(second) == set(first) | {'Resources/one/new.txt'}
    added.write_text('edited')
    third = current()
    assert third['Resources/one/new.txt'] != second['Resources/one/new.txt']
    assert {key for key in third if third[key] != second[key]} == {'Resources/one/new.txt'}
    added.unlink()
    assert current() == first
