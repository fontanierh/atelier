"""Native capture callers delegate one lifecycle; tests never launch Unreal or Blender."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


GAME = Path(__file__).resolve().parents[1]


def load(relative):
    path = GAME / relative
    spec = importlib.util.spec_from_file_location('capacity_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark():
    return load('tools/benchmark.py')


def test_benchmark_uses_one_performance_admission_and_observes_actual_child(benchmark, tmp_path, monkeypatch):
    calls, observed = [], []
    command = ['native-game', '-game', '-unchanged']

    def run(argv, folder, **options):
        calls.append((argv, folder, options))
        options['on_poll'](123)
        return 0

    monkeypatch.setattr(benchmark.guarded, 'run', run)
    monkeypatch.setattr(benchmark, 'other_render_processes', lambda pid: observed.append(pid) or [])
    benchmark.run_benchmark(command, tmp_path, purpose='benchmark route', timeout=360, slot_deadline=0)
    assert len(calls) == 1 and calls[0][:2] == (command, tmp_path)
    assert calls[0][2] | {'on_poll': None} == dict(purpose='benchmark route', timeout=360, kind='game',
                                                 performance=True, on_poll=None)
    assert observed == [123]


def test_benchmark_overlap_cannot_publish_valid_performance(benchmark, tmp_path, monkeypatch):
    job = {'pid': 456, 'command': 'other-game'}
    monkeypatch.setattr(benchmark, 'other_render_processes', lambda pid: [job])

    def run(*args, **options):
        options['on_poll'](123)
        return 0

    monkeypatch.setattr(benchmark.guarded, 'run', run)
    with pytest.raises(RuntimeError, match='not a valid performance measurement'):
        benchmark.run_benchmark(['native-game'], tmp_path, purpose='benchmark', timeout=360, slot_deadline=0)
    assert json.loads((tmp_path / 'overlapping-jobs.json').read_text()) == [job]


def test_benchmark_wait_retries_only_unallocated_legacy_refusal(benchmark, tmp_path, monkeypatch):
    calls, sleeps = [], []

    def run(*args, **options):
        calls.append(options)
        if len(calls) == 1:
            raise benchmark.RenderBusy('occupied')
        return 0

    monkeypatch.setattr(benchmark.guarded, 'run', run)
    monkeypatch.setattr(benchmark.time, 'monotonic', lambda: 10.)
    monkeypatch.setattr(benchmark.time, 'sleep', sleeps.append)
    benchmark.run_benchmark(['native-game'], tmp_path, purpose='benchmark', timeout=360, slot_deadline=12)
    assert len(calls) == 2 and sleeps == [1.]


@pytest.mark.parametrize('failure', ['broker', 'exit', 'deadline'])
def test_benchmark_failure_never_becomes_a_retry_or_success(benchmark, tmp_path, monkeypatch, failure):
    from atelier.capacity_client import CapacityError
    calls = []

    def run(*args, **options):
        calls.append(options)
        if failure == 'broker':
            raise CapacityError('broker unavailable')
        if failure == 'deadline':
            raise benchmark.RenderBusy('occupied')
        return 7

    monkeypatch.setattr(benchmark.guarded, 'run', run)
    monkeypatch.setattr(benchmark.time, 'monotonic', lambda: 10.)
    expected = {'broker': CapacityError, 'exit': subprocess.CalledProcessError, 'deadline': benchmark.RenderBusy}[failure]
    with pytest.raises(expected):
        benchmark.run_benchmark(['native-game'], tmp_path, purpose='benchmark', timeout=360,
                                slot_deadline=10 if failure == 'deadline' else 20)
    assert len(calls) == 1


@pytest.fixture
def capture(tmp_path, monkeypatch):
    module = load('tools/capture.py')
    game, output = tmp_path / 'game', tmp_path / 'output'
    project = game / 'unreal'
    for path, data in [(project / 'Saved/settings.txt', b'saved settings'),
                       (project / 'Binaries/Mac/libUnrealEditor-Yorimichi.dylib', b'game binary')]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(module, 'ROOT', game)
    monkeypatch.setattr(module, 'PROJECT', project)
    monkeypatch.setattr(module.yori, 'OUT', output)
    monkeypatch.setattr(module, 'head', lambda: 'a' * 40)
    monkeypatch.setattr(module, 'other_render_processes', lambda: [])
    return module


def test_capture_common_guard_keeps_progress_and_output_certification(capture, monkeypatch, capsys):
    calls = []
    now = [0.]
    monkeypatch.setattr(capture.time, 'monotonic', lambda: now[0])

    def run(command, folder, **options):
        calls.append((command, folder, options))
        assert '-noshaderworker' in command and '-UseFixedTimeStep' in command
        assert options['kind'] == 'game' and options['timeout'] == 1800
        assert options['purpose'] == 'trailer test/shot'
        Image.new('RGB', (640, 360)).save(folder / 'frame_00000.png')
        (folder / 'game.log').write_text('TRAILER SHOT COMPLETE')
        with (folder / 'telemetry.csv').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=['frame', 'clip', 'speed', 'falling'])
            writer.writeheader()
            writer.writerow(dict(frame=0, clip='Ground', speed=0, falling=0))
        options['on_poll'](123)
        now[0] = 31.
        options['on_poll'](123)
        return 0

    monkeypatch.setattr(capture.guarded, 'run', run)
    capture.capture('test', 'shot', dict(seconds=1 / 60, width=640, height=360))
    assert len(calls) == 1
    report = json.loads((calls[0][1] / 'checks.json').read_text())
    assert report['passed'] and report['settings_unchanged'] and report['frames'] == 1
    assert 'CAPTURE PROGRESS shot: 31s elapsed, 1 frames saved' in capsys.readouterr().out


def test_capture_common_guard_failure_prevents_output_acceptance(capture, monkeypatch):
    calls = []
    monkeypatch.setattr(capture.guarded, 'run', lambda *args, **options: calls.append(options) or 9)
    with pytest.raises(subprocess.CalledProcessError) as error:
        capture.capture('failed', 'shot', dict(seconds=1 / 60))
    assert error.value.returncode == 9 and len(calls) == 1
    assert not (capture.yori.OUT / 'captures/failed/shot/checks.json').exists()


def test_sailboat_uses_one_common_guard_before_accepting_native_evidence(tmp_path, monkeypatch):
    sailboat = load('scenarios/sailboat.py')
    project, output = tmp_path / 'project', tmp_path / 'output'
    binary = project / 'Binaries/Mac/libUnrealEditor-Yorimichi.dylib'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'game binary')
    monkeypatch.setattr(sailboat, 'PROJECT', project)
    monkeypatch.setattr(sailboat.yori, 'OUT', output)
    monkeypatch.setattr(sailboat, 'head', lambda: 'a' * 40)
    monkeypatch.setattr(sailboat, 'status', lambda: '')
    monkeypatch.setattr(sailboat, 'other_render_processes', lambda: [])
    monkeypatch.setattr(sys, 'argv', ['sailboat.py', 'fixture'])
    calls = []

    def run(command, folder, **options):
        calls.append((command, folder, options))
        assert '-sailboatqa' in command and '-FPS=60' in command
        for name in ['01_rear', '02_rear', '03_side', '04_helm', '05_helm', '06_side', '13_rear']:
            Image.new('RGB', (1920, 1080)).save(folder / f'sailboat_{name}.png')
        (folder / 'game.log').write_text('SAILBOAT QA COMPLETE')
        (folder / 'results.json').write_text(json.dumps(dict(checks=45, passed=True, errors=[])))
        with (folder / 'telemetry.csv').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=['step'])
            writer.writeheader()
            writer.writerows({'step': index % 23} for index in range(1501))
        return 0

    monkeypatch.setattr(sailboat.guarded, 'run', run)
    sailboat.main()
    assert len(calls) == 1
    assert calls[0][2] == dict(timeout=900, purpose='sailboat QA fixture', kind='game')
    assert json.loads((output / 'sailboat/fixture/checks.json').read_text())['passed']
