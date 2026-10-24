"""The real one-shot action's source gate; no scheduler or cleanup authority fabricated."""
from pathlib import Path
import pytest
from atelier.build_v2.legacy_action import captured_execution_check
from atelier.build_v2.legacy_qualification import CapturedCode, UnsupportedOrigin


def test_captured_action_code_gate_is_exact_and_sticky_even_if_body_catches_refusal(tmp_path):
    source = CapturedCode(str(tmp_path / 'known.py'), b'value = 1\n')
    check = captured_execution_check([source], checkout=tmp_path, platform_roots=[])
    check('exec', (source.compiled(),))
    check.require_clean()
    with pytest.raises(UnsupportedOrigin):
        check('exec', (compile('value = 2', source.filename, 'exec'),))
    with pytest.raises(UnsupportedOrigin, match='sticky'):
        check.require_clean()


def test_unknown_action_checkout_code_refuses_before_exec_and_installed_context_is_separate(tmp_path):
    source = CapturedCode(str(tmp_path / 'known.py'), b'value = 1\n')
    installed = tmp_path / '.venv'
    check = captured_execution_check([source], checkout=tmp_path, platform_roots=[installed])
    check('exec', (compile('value = 2', str(installed / 'library.py'), 'exec'),))
    check.require_clean()
    with pytest.raises(UnsupportedOrigin):
        check('exec', (compile('value = 2', str(tmp_path / 'unknown.py'), 'exec'),))
    with pytest.raises(UnsupportedOrigin):
        check.require_clean()



def test_unmanaged_audit_support_does_not_hash_unused_captured_runtime():
    from atelier import build_audit
    assert build_audit.SUPPORT == (Path(build_audit.__file__), build_audit.WORKER, build_audit.NATIVE)
