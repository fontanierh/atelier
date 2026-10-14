"""Exercise the real worker/receipt protocol with tiny Python children, never native tool names."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from atelier import build, build_batches, build_plan


@pytest.fixture
def project(tmp_path, monkeypatch):
    out = tmp_path / 'out'
    ctx = SimpleNamespace(game='standin', out=out, stamps=out / 'stamps', logs=out / 'logs')
    steps, launches = [], []
    for i in range(1, 7):
        script = tmp_path / f'action{i}.py'
        script.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[-1]).write_text('made')\n")
        step = build.Step(f'action{i}', [build.Blender(script, (str(out / f'{i}.txt'),))],
                          products=[build.Product(f'product{i}', (out / f'{i}.txt',))], heavy=True,
                          batch=build.Batch('fixture'))
        steps.append(step)
    monkeypatch.setattr(build, 'Context', lambda game, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))

    def launch(ctx, first, command, log, request, slots):
        assert request == ('job', None)
        launches.append(command)
        guard = ctx.logs / (first.name + '.guard')
        guard.mkdir(parents=True, exist_ok=True)
        with (guard / 'stdout.log').open('w') as stdout:
            child = subprocess.Popen([sys.executable, str(command.script)], stdout=stdout, stderr=stdout,
                                     env=dict(os.environ, **dict(command.env)))
            deadline = time.monotonic() + 10
            try:
                while child.poll() is None:
                    assert time.monotonic() < deadline, 'worker protocol stalled'
                    build_batches.atomic_json(guard / 'memory-health.json',
                                              {'pid': child.pid, 'time': time.time(),
                                               'peak_bytes': 2 * build_batches.GiB,
                                               'footprint_bytes': build_batches.GiB})
                    command.on_poll(child.pid)
                    time.sleep(.01)
                command.on_poll(child.pid)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait()
        text = (guard / 'stdout.log').read_text()
        log.write(text)
        if child.returncode or command.marker not in text:
            raise RuntimeError(f'worker exited {child.returncode}: {text[-1000:]}')

    monkeypatch.setattr(build, 'run_command', launch)
    messages = []
    return SimpleNamespace(ctx=ctx, steps=steps, launches=launches, messages=messages,
                           run=lambda: build.build('standin', echo=messages.append))


def test_one_warm_process_keeps_individual_results_and_skips_current_actions(project):
    p = project
    assert p.run() == 0
    assert len(p.launches) == 1
    assert len(list(p.ctx.stamps.glob('action*.json'))) == 6
    before = {s.name: (p.ctx.stamps / (s.name + '.json')).read_bytes() for s in p.steps}
    assert p.run() == 0 and len(p.launches) == 1
    p.steps[2].commands[0].script.write_text("from pathlib import Path\nimport sys\nPath(sys.argv[-1]).write_text('new')\n")
    assert p.run() == 0 and len(p.launches) == 2
    assert (p.ctx.out / '3.txt').read_text() == 'new'
    for step in p.steps:
        assert ((p.ctx.stamps / (step.name + '.json')).read_bytes() == before[step.name]) == (step.name != 'action3')


def test_interrupted_fourth_action_preserves_first_three_and_resume_runs_only_remaining(project):
    p = project
    script = p.steps[3].commands[0].script
    good = script.read_text()
    script.write_text('import os\nos._exit(7)\n')
    assert p.run() == 1
    before = {path.name: path.read_bytes() for path in p.ctx.stamps.glob('action*.json')}
    assert set(before) == {'action1.json', 'action2.json', 'action3.json'}
    assert not (p.ctx.out / '5.txt').exists() and not (p.ctx.out / '6.txt').exists()
    script.write_text(good)
    assert p.run() == 0
    assert len(p.launches) == 2
    assert all((p.ctx.stamps / name).read_bytes() == value for name, value in before.items())
    assert (p.ctx.out / '6.txt').read_text() == 'made'


@pytest.mark.parametrize('change', ['neighbour_output', 'earlier_input', 'missing_marker'])
def test_later_actions_cannot_leave_false_certificates(project, change):
    p = project
    script = p.steps[1].commands[0].script
    if change == 'neighbour_output':
        script.write_text(script.read_text() + f"Path({str(p.ctx.out / '1.txt')!r}).write_text('changed neighbour')\n")
    elif change == 'earlier_input':
        script.write_text(script.read_text() + f"Path({str(p.steps[0].commands[0].script)!r}).write_text('# changed source')\n")
    else:
        # Unreal may exit zero after a script exception; a missing completion marker must still fail.
        p.steps[1].commands[0] = build.UnrealScript(script, 'NEVER PRINTED')
        p.steps[1].batch = build.Batch('editor')
        script.write_text('raise RuntimeError("failed before marker")\n')
    assert p.run() == 1
    if change == 'missing_marker':
        assert (p.ctx.stamps / 'action1.json').exists()
        assert not (p.ctx.stamps / 'action2.json').exists()
    else:
        assert not (p.ctx.stamps / 'action1.json').exists()
        assert (p.ctx.stamps / 'action6.json').exists()


def test_boundaries_use_memory_growth_and_wall_time_without_lifting_the_guard(project, monkeypatch):
    p = project
    policy, gib = build.Batch('test'), build_batches.GiB
    assert build_batches.yield_reason(policy, 1, 2 * gib, 2 * gib, .1 * gib) is None
    assert 'memory' in build_batches.yield_reason(policy, 1, 8 * gib, 2 * gib, 0)
    assert 'memory' in build_batches.yield_reason(policy, 1, 2 * gib, 2 * gib, 4 * gib)
    assert 'wall-time' in build_batches.yield_reason(policy, 241, 2 * gib, 2 * gib, 0)
    assert 'telemetry' in build_batches.yield_reason(policy, 1, None, 2 * gib, 0)
    monkeypatch.setattr(build_batches, 'yield_reason', lambda *args: 'fairness boundary')
    assert p.run() == 75
    assert (p.ctx.stamps / 'action1.json').exists()
    assert not (p.ctx.out / '2.txt').exists()
    assert p.messages[-1] == ('BATCH YIELDED: 1 of 6 actions done; recheck Waiting, '
                              'then resume with atelier build standin')
    decisions = build_plan.inspect(p.ctx, p.steps)['steps']
    assert [d['status'] for d in decisions] == ['current', *(['run'] * 5)]


def test_batch_cannot_silently_change_an_already_current_owner(project):
    p = project
    assert p.run() == 0
    script = p.steps[1].commands[0].script
    script.write_text(script.read_text() + f"Path({str(p.ctx.out / '1.txt')!r}).write_text('changed neighbour')\n")
    assert p.run() == 1
    assert not (p.ctx.stamps / 'action1.json').exists()
    assert p.messages[-1] == 'FAILED: products changed after their owner completed: action1'


def test_batch_growth_never_overwrites_standalone_peaks(project):
    p = project
    folder = p.ctx.logs / 'action2.guard'
    standalone = {'peak_bytes': 2 * build_batches.GiB}
    build_batches.atomic_json(folder / 'step-peak.json', standalone)
    assert build_batches.expected_growth(p.ctx, p.steps[1]) == standalone['peak_bytes']
    assert p.run() == 0
    assert json.loads((folder / 'step-peak.json').read_text()) == standalone
    assert not (folder / 'memory-health.json').exists()
    assert build.expected_peak_gib(folder) == 2
    assert build_batches.expected_growth(p.ctx, p.steps[1]) == 0  # constant fixture footprint
    assert build_batches.yield_reason(build.Batch('test'), 1, 7 * build_batches.GiB, 0, 0) is None


def test_environment_reset_preserves_untouched_native_keys(monkeypatch):
    from atelier.build_batch_worker import set_environment
    values = {'PATH': '/tools', 'ASSET_ID': 'oak', 'TEMP_SETTING': 'old'}
    writes = []

    class Environment(dict):
        def __setitem__(self, key, value):
            writes.append((key, value))
            super().__setitem__(key, value)

        def clear(self):
            pytest.fail('must not clear the native environment')

    monkeypatch.setattr(os, 'environ', Environment(values))
    set_environment({'PATH': '/tools', 'ASSET_ID': 'pine'})
    assert os.environ == {'PATH': '/tools', 'ASSET_ID': 'pine'}
    assert writes == [('ASSET_ID', 'pine')]


def test_batch_cannot_cross_a_read_edge_or_tool_settings(project):
    p = project
    p.steps[1].reads.append('product1')
    p.steps[3].commands[0] = replace(p.steps[3].commands[0], threads=2)
    assert p.run() == 0
    assert len(p.launches) == 4  # action1; actions2-3; action4; actions5-6


def test_batch_rejects_unowned_outputs_and_startup_environment(project):
    p = project
    p.steps[0].products = []
    with pytest.raises(SystemExit, match='named products'):
        p.run()
    p.steps[0].products = [build.Product('product1', (p.ctx.out / '1.txt',))]
    p.steps[0].batch = build.Batch('bad', runtime_env=('PYTHONHASHSEED',))
    with pytest.raises(SystemExit, match='process-start'):
        p.run()
