"""Captured callable observations do not bless arbitrary functions or shadow a game's paths."""
import importlib.util
import sys
from pathlib import Path

import pytest

from atelier.build_v2.legacy_qualification import (
    CapturedCode, IdentityBinding, NamedCapturedImports, UnsupportedOrigin, captured_spec, verify_callable,
)


def loaded(source, path):
    namespace = {}
    exec(compile(source, str(path), 'exec', dont_inherit=True), namespace)
    return namespace


def test_callable_checks_captured_body_defaults_helpers_and_logical_filename(tmp_path):
    path = tmp_path / 'profile.py'
    source = b'HELPER = None\ndef run(value=2, *, flag=True):\n    return HELPER(value) if flag else value\n'
    ns = loaded(source, path)
    helper = lambda value: value
    ns['HELPER'] = helper
    captured = CapturedCode(str(path), source)
    def check():
        return verify_callable(ns['run'], captured, qualname='run', namespace=ns,
                               defaults=(2,), keyword_defaults={'flag': True},
                               globals_={'HELPER': IdentityBinding(helper)})
    observation = check()
    assert observation.filename == str(path)
    assert observation.source_digest == captured.digest
    assert not hasattr(observation, 'content')
    ns['HELPER'] = lambda value: value + 1
    with pytest.raises(UnsupportedOrigin, match='global'):
        check()
    ns['HELPER'] = helper
    ns['run'].__defaults__ = (3,)
    with pytest.raises(UnsupportedOrigin, match='defaults'):
        check()
    ns['run'].__defaults__ = (2,)
    for changed in (ns['run'].__code__.replace(co_filename=str(tmp_path / 'other.py')),
                    ns['run'].__code__.replace(co_qualname='other')):
        original = ns['run'].__code__
        ns['run'].__code__ = changed
        with pytest.raises(UnsupportedOrigin, match='code'):
            check()
        ns['run'].__code__ = original
    wrong = CapturedCode(str(path), source.replace(b'else value', b'else 0'))
    with pytest.raises(UnsupportedOrigin, match='code'):
        verify_callable(ns['run'], wrong, qualname='run', namespace=ns)


def test_nested_discovery_profile_binds_captured_roster_instead_of_function_repr(tmp_path):
    path = tmp_path / 'factory.py'
    source = b'def factory(roster):\n    def discover():\n        return tuple(roster)\n    return discover\n'
    ns = loaded(source, path)
    roster = ['first']
    fn = ns['factory'](roster)
    captured = CapturedCode(str(path), source)
    def check():
        return verify_callable(fn, captured, qualname='factory.<locals>.discover', namespace=ns,
                               closures={'roster': ['first']}, builtins_={'tuple': IdentityBinding(tuple)})
    check()
    roster.append('unreviewed-child')
    with pytest.raises(UnsupportedOrigin, match='closure'):
        check()
    with pytest.raises(UnsupportedOrigin, match='closure names'):
        verify_callable(fn, captured, qualname='factory.<locals>.discover', namespace=ns)


def test_named_loader_executes_captured_bytes_without_reading_live_or_relocating_game(tmp_path):
    path = tmp_path / 'game' / 'profile.py'
    source = b'from pathlib import Path\nGAME = Path(__file__).parent\ndef run():\n    return GAME\n'
    captured = CapturedCode(str(path), source)
    # Logical source is deliberately absent: loader must not read or create it/pycache.
    spec = captured_spec('known_game_profile', captured)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.run() == path.parent
    assert module.__file__ == str(path) and module.__spec__.origin == str(path)
    assert not path.parent.exists()
    verify_callable(module.run, captured, qualname='run', namespace=module.__dict__,
                    globals_={'GAME': path.parent})


def test_source_observation_refuses_native_wrappers_ambiguous_code_and_mutable_objects(tmp_path):
    path = tmp_path / 'profile.py'
    source = b'def run():\n    return 1\n'
    ns = loaded(source, path)
    captured = CapturedCode(str(path), source)
    with pytest.raises(UnsupportedOrigin):
        verify_callable(len, captured, qualname='run', namespace=ns)
    decorated = loaded(b'from functools import lru_cache\n@lru_cache()\ndef run():\n    return 1\n', path)
    with pytest.raises(UnsupportedOrigin):
        verify_callable(decorated['run'], captured, qualname='run', namespace=decorated)
    duplicate = b'def run():\n    return 1\ndef run():\n    return 1\n'
    duplicate_ns = loaded(duplicate, path)
    with pytest.raises(UnsupportedOrigin):
        verify_callable(duplicate_ns['run'], CapturedCode(str(path), duplicate),
                        qualname='run', namespace=duplicate_ns)
    ns['BAD'] = object()
    with pytest.raises(UnsupportedOrigin, match='binding coverage'):
        verify_callable(ns['run'], captured, qualname='run', namespace=ns, globals_={'BAD': ns['BAD']})


def test_origin_requires_all_loaded_global_and_builtin_bindings(tmp_path):
    path = tmp_path / 'profile.py'
    source = b'def run():\n    return tuple(ROSTER)\n'
    ns = loaded(source, path)
    ns['ROSTER'] = ['a']
    captured = CapturedCode(str(path), source)
    with pytest.raises(UnsupportedOrigin, match='coverage'):
        verify_callable(ns['run'], captured, qualname='run', namespace=ns)
    expected = dict(globals_={'ROSTER': ['a']}, builtins_={'tuple': IdentityBinding(tuple)})
    verify_callable(ns['run'], captured, qualname='run', namespace=ns, **expected)
    ns['tuple'] = lambda value: ()
    with pytest.raises(UnsupportedOrigin, match='builtin'):
        verify_callable(ns['run'], captured, qualname='run', namespace=ns, **expected)


def test_named_imports_use_captured_packages_and_refuse_unknown_project_code_before_exec(tmp_path, monkeypatch):
    package = tmp_path / 'named_legacy_fixture'
    package.mkdir()
    marker = tmp_path / 'unexpected-write'
    (package / '__init__.py').write_text('raise RuntimeError("mutable package ran")')
    (package / 'helper.py').write_text('raise RuntimeError("mutable helper ran")')
    (package / 'unreviewed.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")')
    finder = NamedCapturedImports({
        'named_legacy_fixture': CapturedCode(str(package / '__init__.py'), b'ROOT = __file__\n'),
        'named_legacy_fixture.helper': CapturedCode(str(package / 'helper.py'), b'VALUE = 7\n'),
    }, checkout=tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, 'meta_path', [finder, *sys.meta_path])
    try:
        import named_legacy_fixture.helper as helper
        assert helper.VALUE == 7 and helper.__file__ == str(package / 'helper.py')
        with pytest.raises(UnsupportedOrigin, match='outside the named capture'):
            importlib.import_module('named_legacy_fixture.unreviewed')
        assert not marker.exists()
    finally:
        for name in tuple(sys.modules):
            if name == 'named_legacy_fixture' or name.startswith('named_legacy_fixture.'):
                del sys.modules[name]


def test_recipe_direct_spec_loads_captured_bytes_at_original_path_and_refuses_unknown_prewrite(tmp_path):
    from atelier.build_v2.legacy_qualification import captured_recipe_imports
    known = tmp_path / 'games/example/helper.py'
    known.parent.mkdir(parents=True)
    known.write_text('raise RuntimeError("mutable source executed")')
    unknown = known.with_name('unreviewed.py')
    written = tmp_path / 'unreviewed-write'
    unknown.write_text(f'from pathlib import Path\nPath({str(written)!r}).touch()')
    # A platform source supplies the finite normal-import mapping; direct game helper
    # names are chosen by the existing recipe, and still require captured exact paths.
    platform = tmp_path / 'platform/studio/example_platform.py'
    platform.parent.mkdir(parents=True)
    platform.write_text('raise RuntimeError("mutable platform executed")')
    sources = [CapturedCode(str(known), b'VALUE = 17\nORIGIN = __file__\n'),
               CapturedCode(str(platform), b'VALUE = 23\n')]
    original = importlib.util.spec_from_file_location
    with captured_recipe_imports(sources, checkout=tmp_path):
        spec = importlib.util.spec_from_file_location('original_recipe_helper', known)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.VALUE == 17 and module.ORIGIN == str(known)
        with pytest.raises(UnsupportedOrigin, match='outside the named capture'):
            importlib.util.spec_from_file_location('unreviewed_helper', unknown)
        outside = tmp_path.parent / (tmp_path.name + '-outside-alias.py')
        outside.symlink_to(known)
        try:
            # A lexical path outside the checkout must not reload live checkout
            # bytes under an alias, even when its real target is already captured.
            with pytest.raises(UnsupportedOrigin, match='outside the named capture'):
                importlib.util.spec_from_file_location('outside_alias', outside)
        finally:
            outside.unlink()
        assert not written.exists()
    assert importlib.util.spec_from_file_location is original


def test_private_declarations_ignore_poisoned_preloaded_graph_context_and_paths(monkeypatch):
    from atelier import build_products, paths
    from atelier.build_v2 import controller_entry
    from atelier.build_v2.controller_client import capture_named_sources
    from atelier.build_v2.legacy_entry import original_python_context
    from atelier.build_v2.legacy_qualification import captured_recipe_imports
    from atelier.source_imports import ImportScanner
    root = paths.REPO
    names = tuple(source.relative_to(root).as_posix() for source in
                  ImportScanner().local_imports(root / 'platform/studio/atelier/build.py'))
    source = capture_named_sources(root, names)
    codes = [CapturedCode(str(root / name), raw) for name, raw in source.files]
    context = original_python_context()
    called = []
    def poisoned(*args, **kwargs):
        called.append('preloaded-object-executed')
        raise AssertionError('preloaded declaration object executed')
    monkeypatch.setattr(build_products.Graph, 'select', poisoned)
    monkeypatch.setattr(controller_entry, 'declaration_context', poisoned)
    monkeypatch.setattr(paths, 'build_root', poisoned)
    monkeypatch.setattr(paths, 'build_dir', poisoned)
    before_path = list(sys.path)
    before_modules = {name: sys.modules.get(name) for name in (
        'atelier', 'atelier.build_products', 'atelier.paths', 'atelier.build_v2.controller_entry')}
    with captured_recipe_imports(codes, checkout=root, platform_roots=context['platform_roots']):
        from atelier import build as fresh_build, build_products as fresh_products, paths as fresh_paths
        from atelier.build_v2 import controller_entry as fresh_entry
        assert fresh_products is not build_products and fresh_paths is not paths
        step = fresh_build.Step('existing-declaration', [])
        assert fresh_products.Graph([step]).select(['existing-declaration']) == [step]
        assert fresh_entry.declaration_context('sandbox').game == 'sandbox'
        with fresh_paths.captured_declaration('sandbox'):
            assert fresh_paths.build_dir('sandbox') == root / 'build/sandbox'
    assert not called
    assert sys.path == before_path
    assert all(sys.modules.get(name) is module for name, module in before_modules.items())
    assert build_products.Graph.select is poisoned
    assert controller_entry.declaration_context is poisoned
    assert paths.build_root is poisoned and paths.build_dir is poisoned


def test_captured_package_loader_preserves_default_path_and_explicit_plain_module(tmp_path):
    from atelier.build_v2.legacy_qualification import captured_recipe_imports
    package = tmp_path / 'platform/studio/captured_declaration_package'
    package.mkdir(parents=True)
    content = b'ORIGIN = __file__\n'
    (package / '__init__.py').write_bytes(content)
    source = CapturedCode(str(package / '__init__.py'), content)
    with captured_recipe_imports([source], checkout=tmp_path):
        loaded_package = importlib.import_module('captured_declaration_package')
        assert loaded_package.__path__ == [str(package)]
        assert loaded_package.ORIGIN == str(package / '__init__.py')
        plain_spec = importlib.util.spec_from_file_location(
            'explicit_plain', package / '__init__.py', submodule_search_locations=None)
        plain = importlib.util.module_from_spec(plain_spec)
        plain_spec.loader.exec_module(plain)
        assert not hasattr(plain, '__path__')
        assert plain.ORIGIN == str(package / '__init__.py')
        explicit_paths = [str(package / 'explicit-search')]
        explicit_spec = importlib.util.spec_from_file_location(
            'explicit_package', package / '__init__.py', submodule_search_locations=explicit_paths)
        explicit = importlib.util.module_from_spec(explicit_spec)
        explicit_spec.loader.exec_module(explicit)
        assert explicit.__path__ == explicit_paths
        assert explicit.ORIGIN == str(package / '__init__.py')
    assert 'captured_declaration_package' not in sys.modules


def test_named_issuer_imports_accept_512_and_refuse_513_or_duplicate_paths(tmp_path):
    from atelier.build_v2.legacy_qualification import NamedCapturedImports, captured_recipe_imports
    sources = [CapturedCode(str(tmp_path / f'provider_{i}.py'), b'VALUE = 1\n')
               for i in range(513)]
    modules = {f'provider_{i}': source for i, source in enumerate(sources)}
    assert len(NamedCapturedImports(dict(list(modules.items())[:512]), checkout=tmp_path).modules) == 512
    with pytest.raises(UnsupportedOrigin, match='invalid'):
        NamedCapturedImports(modules, checkout=tmp_path)
    with captured_recipe_imports(sources[:512], checkout=tmp_path):
        pass  # Admission only: no captured module or recipe body is executed.
    with pytest.raises(UnsupportedOrigin, match='invalid'):
        with captured_recipe_imports(sources, checkout=tmp_path):
            pass
    with pytest.raises(UnsupportedOrigin, match='invalid'):
        with captured_recipe_imports([*sources[:511], sources[0]], checkout=tmp_path):
            pass


def test_captured_regions_alias_reloads_poisoned_bindings_and_restores_them(tmp_path, monkeypatch):
    from types import ModuleType
    from atelier.build_v2.legacy_qualification import captured_recipe_imports
    region = tmp_path / 'games/example/world/regions/belmonte'
    region.mkdir(parents=True)
    helper = region / 'query_surface.py'
    helper.write_bytes(b'VALUE = "captured"\nORIGIN = __file__\n')
    unknown = region / 'unknown.py'
    marker = tmp_path / 'unexpected-execution'
    unknown.write_text(f'open({str(marker)!r}, "w").write("ran")\n')
    old_package, old_helper = ModuleType('belmonte'), ModuleType('belmonte.query_surface')
    old_package.__path__ = [str(region)]
    old_helper.VALUE = 'poisoned'
    old_package.query_surface = old_helper
    monkeypatch.setitem(sys.modules, 'belmonte', old_package)
    monkeypatch.setitem(sys.modules, 'belmonte.query_surface', old_helper)
    with captured_recipe_imports([CapturedCode(str(helper), helper.read_bytes())], checkout=tmp_path):
        loaded_helper = importlib.import_module('belmonte.query_surface')
        assert loaded_helper.VALUE == 'captured' and loaded_helper is not old_helper
        assert loaded_helper.ORIGIN == str(helper)
        assert loaded_helper.__name__ == 'belmonte.query_surface'
        with pytest.raises(UnsupportedOrigin, match='outside the named capture'):
            importlib.import_module('belmonte.unknown')
        assert not marker.exists()
    assert sys.modules['belmonte'] is old_package
    assert sys.modules['belmonte.query_surface'] is old_helper
    assert old_package.query_surface is old_helper and old_helper.VALUE == 'poisoned'
    assert 'belmonte.unknown' not in sys.modules


def test_captured_world_regions_alias_ambiguity_refuses_before_exec(tmp_path):
    from atelier.build_v2.legacy_qualification import captured_recipe_imports
    paths = [tmp_path / 'games/example/world/same.py',
             tmp_path / 'games/example/world/regions/same.py']
    marker = tmp_path / 'unexpected-execution'
    content = f'open({str(marker)!r}, "w").write("ran")\n'.encode()
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with captured_recipe_imports([CapturedCode(str(path), content) for path in paths], checkout=tmp_path):
        with pytest.raises(UnsupportedOrigin, match='ambiguous WORLD/REGIONS'):
            importlib.import_module('same')
        assert not marker.exists()
