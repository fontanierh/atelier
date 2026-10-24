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


def test_fixed_captured_runtime_enables_observation_without_mutating_original_audit_flag(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from atelier import build, build_audit, build_source, build_cache
    source = tmp_path / 'generate.py'; source.write_text('value = 1\n')
    step = build.Step('original', [build.Python(source)],
                      products=[build.Product('result', (tmp_path / 'result.json',))], cache=True)
    names = {'generate.py', *build_audit._CAPTURED_WORKER}
    for name in build_audit._CAPTURED_WORKER:
        file = tmp_path / name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('pass\n')
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: {'original': 'python'})
    original = build.fingerprint(step, {})
    assert step.audit is False and not build_audit.enabled(step)
    runtime = build_audit._bind_captured_runtime(step, checkout=tmp_path, issuer_files=sorted(names))
    assert step.audit is False and build_audit.enabled(step)
    changed = build.fingerprint(step, {})
    assert changed != original
    assert set(build_audit.SUPPORT) <= set(build.required_inputs(step))
    assert build.fingerprint_state(step, {})[1]['audit'] == 1
    calls = []
    @contextmanager
    def audited(ctx, actual, products, *, receipt):
        assert actual is step
        calls.append((products, receipt)); yield ['original-checked-worker'], (), ()
    monkeypatch.setattr(build_audit, 'prepared', audited)
    products, receipt = {'actual': 'products'}, {}
    with build_source.prepared(SimpleNamespace(), step, step.commands[0],
                               products=products, audit_receipt=receipt) as action:
        assert action[0] == ['original-checked-worker']
    assert calls == [(products, receipt)] and step.audit is False
    worker = tmp_path / 'platform/studio/atelier/build_v2/legacy_action.py'
    worker.write_text('changed = True\n')
    assert build.fingerprint(step, {}) != changed
    step._captured_audit_runtime = SimpleNamespace(files=runtime.files)
    with pytest.raises(ValueError, match='unqualified'):
        build_audit.enabled(step)
