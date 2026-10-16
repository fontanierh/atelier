"""CPU telemetry must preserve identity, counter units and missing coverage without affecting jobs."""
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from atelier import capacity_cpu as cpu


@pytest.fixture
def live(tmp_path):
    class Live:
        now = 100.
        frame = 0
        hook = None

        def __init__(self):
            self.report = tmp_path / 'memory-health-tree.json'
            self.output = tmp_path / 'evidence'
            self.pins = [(11, 1100), (22, 2200)]
            self.calls = []
            self.write()

        def write(self, **extra):
            self.report.write_text(json.dumps(dict(owner=11, owner_started=1100, state='running',
                observed_monotonic=self.now, processes=[dict(pid=p, started=s) for p,s in self.pins], **extra)))

        def usage(self, pid):
            self.calls.append((self.frame, pid))
            return SimpleNamespace(started=pid*100, exited=0,
                user=1_000_000_000+(12_000_000 if pid==11 else 24_000_000)*self.frame, system=0)

        def sleep(self, duration):
            assert duration > 0
            self.now += duration
            self.frame += 1
            self.write()
            if self.hook:
                self.hook()

        def run(self, **options):
            return cpu.observe(self.report, self.output, usage=self.usage, numer=125, denom=3,
                seconds=2, interval=1, clock=lambda:self.now, wall=lambda:self.now+1000,
                sleep=self.sleep, echo=lambda text:None, **options)

        def rows(self):
            return [json.loads(line) for line in (self.output/'samples.jsonl').read_text().splitlines()]

    return Live()


def test_counts_helper_cpu_with_darwin_units_and_retains_first_sample_gap(live):
    result = live.run()
    assert result['samples'] == 3
    assert live.rows()[0]['observed_cpu_units'] is None
    assert result['max_observed_cpu_units'] == pytest.approx(1.5)
    assert result['mean_observed_cpu_units'] == pytest.approx(1.5)
    assert result['observed_cpu_seconds'] == pytest.approx(3)
    assert result['gaps']['new_identities'] == 2
    assert result['coverage_complete'] is False
    assert result['ending'] == 'duration'


def test_reused_pid_never_contributes_foreign_cpu(live):
    usage = live.usage
    def reused(pid):
        value = usage(pid)
        if pid == 22 and live.frame:
            value.started, value.user = 999, 10**15
        return value
    live.usage = reused
    result = live.run()
    assert result['max_observed_cpu_units'] == pytest.approx(.5)
    assert result['gaps']['unavailable'] == 2
    assert result['gaps']['departed_with_unobserved_tail'] == 1
    assert live.rows()[1]['unavailable'][0]['reason'] == 'identity changed'


def test_new_helper_lifetime_cpu_is_not_misattributed_to_the_current_interval(live):
    live.pins = [(11, 1100)];live.write()
    def birth():
        live.pins = [(11, 1100), (22, 2200)];live.write()
    live.hook = birth
    result = live.run()
    assert live.rows()[1]['observed_cpu_units'] == pytest.approx(.5)
    assert live.rows()[2]['observed_cpu_units'] == pytest.approx(1.5)
    assert result['gaps']['new_identities'] == 2


def test_unavailable_interval_is_not_zero_or_a_bridge_across_missing_data(live):
    usage = live.usage
    def missing(pid):
        if live.frame == 1:
            raise ProcessLookupError(pid)
        return usage(pid)
    live.usage = missing
    result = live.run()
    assert all(row['observed_cpu_units'] is None for row in live.rows())
    assert result['mean_observed_cpu_units'] is None
    assert result['max_observed_cpu_units'] is None
    assert result['observed_cpu_seconds'] is None
    assert result['gaps']['unavailable'] == 2


def test_counter_reset_remains_explicit_and_does_not_subtract_cpu(live):
    usage = live.usage
    def reset(pid):
        value = usage(pid)
        if pid == 22 and live.frame:
            value.user -= 900_000_000
        return value
    live.usage = reset
    result = live.run()
    assert live.rows()[1]['observed_cpu_units'] == pytest.approx(.5)
    assert result['gaps']['counter_resets'] == 1
    assert live.rows()[2]['observed_cpu_units'] == pytest.approx(1.5)


@pytest.mark.parametrize('change', ['invocation', 'stale', 'future', 'missing'])
def test_observation_failure_keeps_partial_evidence_and_stops_sampling(live, change):
    def changed():
        value = json.loads(live.report.read_text())
        if change == 'invocation':value['owner_started'] = 999
        if change == 'stale':value['observed_monotonic'] -= 4
        if change == 'future':value['observed_monotonic'] += 4
        if change == 'missing':live.report.unlink();return
        live.report.write_text(json.dumps(value))
    live.hook = changed
    with pytest.raises((ValueError, FileNotFoundError)):
        live.run()
    result = json.loads((live.output/'summary.json').read_text())
    assert result['ending'] == 'observation_error'
    assert result['samples'] == 1
    assert result['mean_observed_cpu_units'] is None
    assert all(frame == 0 for frame, pid in live.calls)


def test_terminal_stops_without_inventing_exit_tail_or_completion_authority(live):
    def ended():
        value = json.loads(live.report.read_text())
        value.update(state='child_exited', processes=[])
        live.report.write_text(json.dumps(value))
    live.hook = ended
    result = live.run()
    assert result['ending'] == 'guard_terminal' and result['terminal_state'] == 'child_exited'
    assert result['gaps']['departed_with_unobserved_tail'] == 2
    assert result['max_observed_cpu_units'] is None
    assert result['coverage_complete'] is False


def test_existing_evidence_is_never_overwritten(live):
    live.output.mkdir();(live.output/'summary.json').write_text('preserve')
    with pytest.raises(FileExistsError):live.run()
    assert (live.output/'summary.json').read_text() == 'preserve'


def test_guard_publish_during_read_is_not_a_future_timestamp_failure(live, monkeypatch):
    read = cpu.read_report
    def published(path):
        live.now += .001
        live.write()
        return read(path)
    monkeypatch.setattr(cpu, 'read_report', published)
    result = live.run()
    assert result['ending'] == 'duration'
    assert result['samples'] >= 2


def test_running_guard_without_root_refuses_before_output(live):
    live.pins = [(22, 2200)];live.write()
    with pytest.raises(ValueError, match='pinned root'):live.run()
    assert not live.output.exists()


@pytest.mark.parametrize('change', ['stale', 'terminal', 'reused_root'])
def test_initial_refusal_creates_no_evidence(live, change):
    value = json.loads(live.report.read_text())
    if change == 'stale':value['observed_monotonic'] -= 4
    if change == 'terminal':value['state'] = 'child_exited'
    if change == 'reused_root':value['owner_started'] = 999
    live.report.write_text(json.dumps(value))
    with pytest.raises(ValueError):live.run()
    assert not live.output.exists()


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'large', 'duplicate'])
def test_report_reads_are_bounded_and_refuse_nonregular_or_ambiguous_input(live, kind):
    if kind in ('symlink', 'fifo'):
        live.report.unlink()
        if kind == 'symlink':live.report.symlink_to('missing')
        else:os.mkfifo(live.report)
    elif kind == 'large':
        with live.report.open('wb') as stream:stream.truncate(cpu.MAX_REPORT_BYTES+1)
    else:
        value = json.loads(live.report.read_text());value['processes'] *= 2
        live.report.write_text(json.dumps(value))
    with pytest.raises((OSError, ValueError)):live.run()
    assert not live.output.exists()


@pytest.mark.parametrize('seconds,interval', [(float('nan'),1),(float('inf'),1),(901,1),(1,1),(60,0),(60,6)])
def test_invalid_deadlines_refuse_before_output(live, seconds, interval):
    with pytest.raises(ValueError):
        cpu.observe(live.report, live.output, usage=live.usage, numer=125, denom=3,
                    seconds=seconds, interval=interval)
    assert not live.output.exists()


def test_cli_routes_observation_and_refuses_its_flags_on_other_actions(monkeypatch):
    from atelier import cli
    calls = []
    monkeypatch.setattr(cpu, 'main', lambda *args,**kw:calls.append((args,kw)) or 0)
    assert cli.main(['capacity','observe-cpu','guard','--output','new','--seconds','30','--interval','.5','--json']) == 0
    assert calls == [(('guard','new'), dict(seconds=30., interval=.5, as_json=True))]
    with pytest.raises(SystemExit, match='only supported'):
        cli.main(['capacity','status','socket','--seconds','30'])
    with pytest.raises(SystemExit, match='requires --output'):
        cli.main(['capacity','observe-cpu','guard'])


@pytest.mark.skipif(sys.platform != 'darwin', reason='Darwin native CPU counter conversion')
def test_native_timebase_agrees_with_the_process_cpu_clock():
    from atelier.safety.memory_guard import usage
    numer, denom = cpu.timebase()
    before = usage(os.getpid());began = time.process_time()
    while time.process_time()-began < .15:
        sum(range(1000))
    elapsed = time.process_time()-began;after = usage(os.getpid())
    measured = (after.user+after.system-before.user-before.system)*numer/denom/1e9
    assert after.started == before.started
    assert .8 < measured/elapsed < 1.2
