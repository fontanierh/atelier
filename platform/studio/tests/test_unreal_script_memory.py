"""Explicit editor ceilings preserve ordinary identities and reserve the actual guarded limit."""
from dataclasses import fields, replace
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build


def test_default_script_identity_is_unchanged_and_opt_in_is_distinct():
    command = build.UnrealScript(Path('import.py'), 'DONE')
    old = [f for f in fields(command) if f.name != 'memory_gib' and (f.name != 'modules' or command.modules)]
    assert repr(command) == f'UnrealScript({", ".join(f"{f.name}={getattr(command, f.name)!r}" for f in old)})'
    assert repr(replace(command, memory_gib=10)) == repr(command)
    assert repr(replace(command, memory_gib=24)) != repr(command)


@pytest.mark.parametrize('value', [None, True, '24', 9, 25, float('nan'), float('inf')])
def test_bad_script_ceiling_is_rejected(value):
    with pytest.raises(ValueError, match='10 to 24'):
        build.UnrealScript(Path('import.py'), 'DONE', memory_gib=value)


def test_selected_ceiling_reaches_one_aggregate_guard_and_cannot_use_small_slot(tmp_path, monkeypatch):
    command = build.UnrealScript(Path('import.py'), 'DONE', memory_gib=24)
    ctx = SimpleNamespace(logs=tmp_path / 'logs', out=tmp_path / 'out', game='fixture', env=lambda extra: dict(extra))
    step = build.Step('import', [command], heavy=True)
    calls = []
    def guard(argv, folder, **kwargs):
        calls.append(kwargs)
        folder.mkdir(parents=True)
        (folder / 'stdout.log').write_text('DONE\n')
        return 0
    monkeypatch.setattr(build.guarded, 'run', guard)
    build.run_argv(ctx, step, command, ['editor'], (), io.StringIO(), ('job', 1.), None)
    assert len(calls) == 1
    assert calls[0]['limit_gib'] == calls[0]['script_memory_gib'] == 24
    assert calls[0]['kind'] == 'job' and calls[0]['small_gib'] is None
    assert calls[0]['aggregate_tree'] is True


def test_unguarded_batched_and_mutated_commands_refuse_before_preparation():
    command = build.UnrealScript(Path('import.py'), 'DONE', memory_gib=24)
    step = build.Step('import', [command])
    with pytest.raises(ValueError, match='separate guarded'):
        build.run_argv(SimpleNamespace(), step, command, ['editor'], (), io.StringIO(), None, None)
    step = replace(step, heavy=True, products=[build.Product('mesh', (Path('mesh'),))], batch=build.Batch('native'))
    with pytest.raises(ValueError, match='without batching'):
        build.check_modules([step])
    with pytest.raises(ValueError, match='without batching'):
        build.run_command(SimpleNamespace(), step, command, io.StringIO())
    command.memory_gib = 30
    with pytest.raises(ValueError, match='10 to 24'):
        build.run_argv(SimpleNamespace(), step, command, ['editor'], (), io.StringIO(), None, None)


def test_later_nondefault_batch_member_is_rejected_before_selection_or_execution():
    first = build.Step('first', [build.UnrealScript(Path('first.py'), 'DONE')], heavy=True, batch=build.Batch('native'))
    later = replace(first, name='later', commands=[replace(first.commands[0], memory_gib=24)])
    with pytest.raises(ValueError, match='without batching'):
        build.check_modules([first, later])
