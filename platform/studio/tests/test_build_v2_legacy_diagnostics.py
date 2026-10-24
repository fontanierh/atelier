"""Bounded observational phases, never runtime/task/cleanup authority."""
import importlib
import io
import sys
from types import ModuleType

import pytest

from atelier.build_v2 import legacy_qualification as phases


@pytest.fixture
def records(monkeypatch, capsys):
    output = io.StringIO()
    clock = iter(range(1000, 10000))
    monkeypatch.setattr(phases, '_diagnostic_records', 0)
    monkeypatch.setattr(phases, '_diagnostic_now', lambda: next(clock))
    class CapturedRecords:
        def getvalue(self):
            output.write(capsys.readouterr().err)
            return output.getvalue()
    return CapturedRecords()


def test_closed_phase_records_are_numeric_ascii_and_count_bounded(records):
    with phases.diagnostic_phase('not-a-phase/private-secret'):
        pass
    phases._diagnostic_event('entry.capture', 'private-secret', 1000)
    assert not records.getvalue()
    for _ in range(80):
        with phases.diagnostic_phase('entry.capture'):
            pass
    lines = records.getvalue().splitlines(keepends=True)
    assert len(lines) == phases._diagnostic_records == 128
    assert all(len(line.encode('ascii')) <= 384 for line in lines)
    assert all('private-secret' not in line for line in lines)
    for line in lines:
        fields = dict(item.split('=', 1) for item in line.split()[2:])
        assert fields['phase'] == 'entry.capture'
        assert fields['event'] in ('begin', 'returned')
        assert all(int(fields[name]) >= 0 for name in ('pid', 'at_ns', 'elapsed_ns'))
        assert fields['clock'] == 'posix-clock-monotonic-v1'


def test_diagnostic_write_or_clock_failure_preserves_original_result_and_exception(monkeypatch):
    class Broken:
        def write(self, value):
            raise OSError('diagnostic write unavailable')
    monkeypatch.setattr(sys, 'stderr', Broken())
    monkeypatch.setattr(phases, '_diagnostic_records', 0)
    with phases.diagnostic_phase('entry.capture'):
        value = object()
    assert value is not None
    original = ValueError('private-original-sentinel')
    with pytest.raises(ValueError) as caught:
        with phases.diagnostic_phase('entry.preflight'):
            raise original
    assert caught.value is original
    monkeypatch.setattr(phases, '_diagnostic_now', lambda: None)
    with phases.diagnostic_phase('entry.preflight'):
        pass


def test_actual_captured_exception_has_separate_finally_restoration_and_stable_counter(tmp_path, records, monkeypatch):
    path = tmp_path / 'platform/studio/phase_provider.py'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'VALUE = 1\n')
    old = ModuleType('phase_provider')
    old.VALUE = 999
    monkeypatch.setitem(sys.modules, 'phase_provider', old)
    original = RuntimeError('original-execution')
    with pytest.raises(RuntimeError) as caught:
        with phases.captured_recipe_imports(
                [phases.CapturedCode(str(path), path.read_bytes())], checkout=tmp_path):
            assert importlib.import_module('phase_provider').VALUE == 1
            raise original
    assert caught.value is original and sys.modules['phase_provider'] is old
    lines = records.getvalue().splitlines()
    def index(phase, event):
        return next(i for i, line in enumerate(lines) if f'phase={phase} event={event}' in line)
    assert index('imports.execute', 'raised') < index('bindings.restore', 'begin')
    assert index('bindings.restore', 'returned') < index('imports.restore', 'returned')
    before = phases._diagnostic_records
    with phases._private_declarations((phases.__name__,)):
        assert sys.modules[phases.__name__] is phases
        with phases.diagnostic_phase('discovery.graph'):
            pass
    assert sys.modules[phases.__name__] is phases and phases._diagnostic_records > before


def test_first_managed_marker_precedes_classifier_and_preserves_refusal(tmp_path, records, monkeypatch):
    from atelier.build_v2 import legacy_entry
    original = ValueError('classifier-original')
    def classifier(game, checkout):
        assert 'phase=managed event=begin' in records.getvalue()
        raise original
    monkeypatch.setattr(legacy_entry, '_checkout', lambda: tmp_path)
    monkeypatch.setattr(legacy_entry, 'controller_names', classifier)
    with pytest.raises(ValueError) as caught:
        legacy_entry.managed('example', ())
    assert caught.value is original
    assert 'phase=managed event=raised' in records.getvalue()
    assert 'classifier-original' not in records.getvalue()
