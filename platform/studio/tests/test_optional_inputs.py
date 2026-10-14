"""Optional exact-file dependencies use real small audited Python actions, never native tools."""
from dataclasses import replace
import os
from pathlib import Path

import pytest

from atelier import build, build_inputs, build_plan, build_products
from test_build_audit import action  # noqa: F401


def optional(action):
    path = action.root / 'optional.txt'
    action.step.optional_inputs = [path]
    action.code(f"extra = Path({str(path)!r})\noutput.write_text(extra.read_text() if extra.exists() else source.read_text())")
    return path


def test_presence_content_and_removal_invalidate_with_noop_and_restore(action):
    a = action
    path = optional(a)
    assert a.run() == 0, a.messages
    absent = a.stamp()['fingerprint']
    before = (a.ctx.stamps / 'generate.json').read_bytes()
    (a.root / 'unrelated.txt').write_text('not an input')
    assert a.run() == 0 and (a.ctx.stamps / 'generate.json').read_bytes() == before
    path.write_text('first')
    plan = build_plan.inspect(a.ctx, a.steps)['steps'][0]
    assert any('optional input appeared:' in reason for reason in plan['reasons'])
    assert a.run() == 0 and a.output.read_text() == 'first'
    first = a.stamp()['fingerprint']
    path.write_text('second')
    assert a.run() == 0 and a.output.read_text() == 'second'
    assert len({absent, first, a.stamp()['fingerprint']}) == 3
    path.unlink()
    assert any('optional input removed:' in r for r in build_plan.inspect(a.ctx, a.steps)['steps'][0]['reasons'])
    assert a.run() == 0 and a.output.read_text() == 'input'
    assert a.stamp()['fingerprint'] == absent and a.stamp()['restored_from'] == absent
    a.output.unlink()
    assert a.run() == 0 and a.output.read_text() == 'input'


def test_absence_is_valid_in_read_only_plan_and_required_inputs_remain_required(action):
    a = action
    optional(a)
    decision = build_plan.inspect(a.ctx, a.steps)['steps'][0]
    assert decision['status'] == 'run' and not a.ctx.out.exists()
    assert not any('required input missing' in r for r in decision['reasons'])
    assert a.run() == 0
    a.source.unlink()
    assert a.run() == 1 and any('required inputs missing' in m for m in a.messages)
    a.source.write_text('input')
    a.script.unlink()
    assert a.run() == 1  # An optional source cannot make the command script optional.


def test_required_and_optional_declarations_are_distinct_keys(action):
    a = action
    path = optional(a)
    path.write_text('same bytes')
    required = replace(a.step, inputs=[*a.step.inputs, path], optional_inputs=[])
    assert build.fingerprint(a.step, {}) != build.fingerprint(required, {})
    previous = build.fingerprint_state(required, {})[1]
    current = build.fingerprint_state(a.step, {})[1]
    assert any('optional input declared' in r for r in build_plan.changed_inputs(previous, current))
    assert any('optional input declaration removed' in r for r in build_plan.changed_inputs(current, previous))


@pytest.mark.parametrize('kind', ['directory', 'link', 'dangling', 'fifo', 'not-directory', 'permission'])
def test_nonfiles_and_io_errors_cannot_be_cached_as_absence(action, monkeypatch, kind):
    a = action
    path = optional(a)
    assert a.run() == 0
    if kind == 'directory':
        path.mkdir()
    elif kind in ('link', 'dangling'):
        target = a.root / 'linked-source'
        if kind == 'link':
            target.write_text('linked bytes')
        path.symlink_to(target)
    elif kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'not-directory':
        a.step.optional_inputs = [a.source / 'child']
    else:
        original = Path.lstat
        def denied(self):
            if self == path:
                raise PermissionError('fixture access denied')
            return original(self)
        monkeypatch.setattr(Path, 'lstat', denied)
    assert a.run() == 1
    assert any('FAILED' in m for m in a.messages)
    assert any('invalid inputs:' in r for r in build_plan.inspect(a.ctx, a.steps)['steps'][0]['reasons'])


@pytest.mark.parametrize('operation', [
    'list(extra.parent.iterdir())', "extra.write_text('bad')", "(extra.parent / 'sibling.txt').read_text()",
])
def test_optional_file_grants_no_listing_sibling_or_write_access(action, operation):
    a = action
    path = optional(a)
    path.write_text('untouched')
    (path.parent / 'sibling.txt').write_text('undeclared')
    a.code(f'''extra = Path({str(path)!r})
try:
    {operation}
except PermissionError:
    pass
output.write_text('otherwise successful')''')
    assert a.run() == 1 and not a.report()['passed']
    assert path.read_text() == 'untouched' and not (a.ctx.stamps / 'generate.json').exists()


def test_directory_replacement_never_grants_descendant_or_listing_access(action, monkeypatch):
    a = action
    path = optional(a)
    path.write_text('before')
    a.code(f'''extra = Path({str(path)!r})
try:
    (extra / 'child').read_text()
except PermissionError:
    pass
output.write_text('otherwise successful')''')
    original = build.run_command
    def replace_before_worker(*args, **kwargs):
        path.unlink()
        path.mkdir()
        (path / 'child').write_text('undeclared')
        return original(*args, **kwargs)
    monkeypatch.setattr(build, 'run_command', replace_before_worker)
    assert a.run() == 1 and a.report()['violations']
    assert any(r['path'].endswith('child') for r in a.report()['violations'])


@pytest.mark.parametrize('before,after', [(None, 'appeared'), ('present', None), ('before', 'after')])
def test_optional_changes_during_execution_prevent_certification(action, monkeypatch, before, after):
    a = action
    path = optional(a)
    if before is not None:
        path.write_text(before)
    original = build.run_command
    def change_after_command(*args, **kwargs):
        result = original(*args, **kwargs)
        if after is None:
            path.unlink()
        else:
            path.write_text(after)
        return result
    monkeypatch.setattr(build, 'run_command', change_after_command)
    assert a.run() == 1 and not (a.ctx.stamps / 'generate.json').exists()
    assert not list((a.store.root / 'actions').glob('*.json'))
    assert any('inputs changed during build' in m for m in a.messages)


def test_optional_change_during_restoration_cannot_certify_previous_bytes(action, monkeypatch):
    a = action
    path = optional(a)
    assert a.run() == 0
    a.output.unlink()
    original = a.store.restore
    def restore(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_text('new input')
        return result
    monkeypatch.setattr(a.store, 'restore', restore)
    assert a.run() == 1 and not (a.ctx.stamps / 'generate.json').exists()
    assert a.run() == 0 and a.output.read_text() == 'new input'


@pytest.mark.parametrize('kind', ['legacy', 'duplicate', 'required', 'script', 'own-output', 'inside-output'])
def test_invalid_declarations_fail_before_any_execution(action, kind):
    a = action
    path = optional(a)
    if kind == 'legacy':
        a.step.products = []
    elif kind == 'duplicate':
        a.step.optional_inputs.append(path)
    elif kind == 'required':
        a.step.optional_inputs = [a.source]
    elif kind == 'script':
        a.step.optional_inputs = [a.script]
    else:
        a.step.optional_inputs = [a.output if kind == 'own-output' else a.output / 'child']
    with pytest.raises(ValueError):
        build_products.Graph(a.steps)
    assert not a.ctx.out.exists()


def test_optional_type_changes_during_inventory_are_refused(tmp_path, monkeypatch):
    path = tmp_path / 'file'
    path.write_text('before')
    original = build_inputs.inventory
    def replace_before_inventory(*args, **kwargs):
        path.unlink()
        path.mkdir()
        return original(*args, **kwargs)
    monkeypatch.setattr(build_inputs, 'inventory', replace_before_inventory)
    with pytest.raises(ValueError, match='changed type'):
        build_inputs.optional_file(path, hasher=build_products.file_digest)


def test_optional_parents_may_use_system_style_aliases(tmp_path):
    real = tmp_path / 'real'; real.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(real, target_is_directory=True)
    assert build_inputs.optional_file(alias / 'input', hasher=None)['kind'] == 'absent'
    (real / 'input').write_text('bytes')
    assert build_inputs.optional_file(alias / 'input', hasher=None) == build_inputs.optional_file(real / 'input', hasher=None)
