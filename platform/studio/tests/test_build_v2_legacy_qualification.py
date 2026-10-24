"""Captured callable observations do not bless arbitrary functions or shadow a game's paths."""
import importlib.util
from pathlib import Path

import pytest

from atelier.build_v2.legacy_qualification import (
    CapturedCode, IdentityBinding, UnsupportedOrigin, captured_spec, verify_callable,
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
