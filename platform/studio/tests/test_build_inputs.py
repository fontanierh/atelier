"""Cache keys must cover helpers, without depending on Python's own bytecode writes."""
import os
import subprocess
import sys

import pytest

from atelier import build, build_inputs, build_products, paths


def test_importing_a_declared_source_directory_does_not_invalidate_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    source = tmp_path / 'sources'; source.mkdir()
    helper = source / 'helper.py'; helper.write_text('VALUE = 1\n')
    script = source / 'run.py'; script.write_text('import helper\nprint(helper.VALUE)\n')
    step = build.Step('source', [build.Python(script)], inputs=[source],
                      products=[build.Product('result', (tmp_path / 'out',))])
    before = build.fingerprint(step, {})
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONDONTWRITEBYTECODE'}
    subprocess.run([sys.executable, str(script)], check=True, capture_output=True, env=env)
    assert list(source.rglob('*.pyc'))
    assert build.fingerprint(step, {}) == before
    (source / 'notes.md').write_text('documentation')
    (source / '.DS_Store').write_bytes(b'cache')
    assert build.fingerprint(step, {}) == before
    helper.write_text('VALUE = 2\n')
    assert build.fingerprint(step, {}) != before


def test_static_local_import_gate_includes_relative_helpers_and_initializers(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    pkg = tmp_path / 'pkg'; pkg.mkdir()
    (pkg / '__init__.py').write_text('from . import helper\n')
    (pkg / 'helper.py').write_text('from .nested import value\n')
    nested = pkg / 'nested'; nested.mkdir()
    (nested / '__init__.py').write_text('value = 1\n')
    script = tmp_path / 'run.py'; script.write_text('def later():\n    from pkg.helper import value\n')
    step = build.Step('source', [build.Python(script)], inputs=[pkg / 'helper.py'], cache=True,
                      products=[build.Product('result', (tmp_path / 'out',))])
    with pytest.raises(ValueError, match='undeclared local imports'):
        build_inputs.validate_imports(step, build.declared_inputs(step))
    step.inputs = [pkg]
    build_inputs.validate_imports(step, build.declared_inputs(step))
    assert set(build_inputs.local_imports(script)) == {script, pkg / '__init__.py', pkg / 'helper.py', nested / '__init__.py'}


def test_named_source_links_are_refused_but_explicit_docs_are_read(tmp_path):
    actual = tmp_path / 'actual.md'; actual.write_text('one')
    first = build_inputs.inventory(actual, hasher=build_products.file_digest)
    actual.write_text('two')
    assert build_inputs.inventory(actual, hasher=build_products.file_digest) != first
    link = tmp_path / 'linked.py'; link.symlink_to(actual)
    with pytest.raises(ValueError, match='linked'):
        build_inputs.inventory(link, hasher=build_products.file_digest)


def test_an_excluded_directory_cannot_claim_import_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    ignored = tmp_path / 'Saved'; ignored.mkdir()
    helper = ignored / 'helper.py'; helper.write_text('VALUE = 1')
    script = tmp_path / 'run.py'; script.write_text('from Saved import helper')
    step = build.Step('source', [build.Python(script)], inputs=[tmp_path], cache=True,
                      products=[build.Product('result', (tmp_path.parent / 'out',))])
    with pytest.raises(ValueError, match='undeclared local imports'):
        build_inputs.validate_imports(step, build.declared_inputs(step))
    step.inputs.append(helper)
    build_inputs.validate_imports(step, build.declared_inputs(step))


def test_statement_suites_cover_nested_imports_and_fresh_scans_find_new_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    script = tmp_path / 'run.py'
    script.write_text('''def later(value):
    try:
        import missing
    except Exception:
        from caught import value
    else:
        import success
    finally:
        match value:
            case 1:
                import matched
''')
    for name in ('caught', 'success', 'matched'):
        (tmp_path / (name + '.py')).write_text('value = 1')
    before = set(build_inputs.local_imports(script))
    assert before == {script, *(tmp_path / (name + '.py') for name in ('caught', 'success', 'matched'))}
    added = tmp_path / 'missing.py'
    added.write_text('value = 2')
    assert set(build_inputs.local_imports(script)) == before | {added}
    added.unlink()
    assert set(build_inputs.local_imports(script)) == before


def test_a_retargeted_link_is_rediscovered_between_scans(tmp_path, monkeypatch):
    """A cached closure must revalidate where each import path points, not just the bytes it
    already resolved: retargeting a link leaves every recorded file untouched."""
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    one = tmp_path / 'one.py'; one.write_text('VALUE = 1\n')
    two = tmp_path / 'two.py'; two.write_text('VALUE = 2\n')
    link = tmp_path / 'helper.py'; link.symlink_to(one)
    script = tmp_path / 'run.py'; script.write_text('import helper\n')
    assert set(build_inputs.local_imports(script)) == {script, one}
    link.unlink(); link.symlink_to(two)
    assert set(build_inputs.local_imports(script)) == {script, two}
