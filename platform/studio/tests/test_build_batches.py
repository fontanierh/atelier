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
                           run=lambda **kwargs: build.build('standin', echo=messages.append, **kwargs))


def test_heavy_budget_counts_a_whole_warm_process_once(project):
    p = project
    p.steps[2].batch = build.Batch('second process')
    assert p.run(max_heavy_commands=1) == 75
    assert len(p.launches) == 1
    assert {path.stem for path in p.ctx.stamps.glob('action*.json')} == {'action1', 'action2'}
    assert not (p.ctx.out / '3.txt').exists()
    assert p.run(max_heavy_commands=2) == 0
    assert len(p.launches) == 3  # action3, then the final three actions share one process


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


def test_batch_binds_each_leaf_owner(project, monkeypatch):
    p = project
    p.steps[:] = p.steps[:2]
    for step in p.steps:
        step.commands[0].script.write_text("from pathlib import Path\nimport os, sys\n"
                                         "Path(sys.argv[-1]).write_text(os.environ['ATELIER_BUILD_TASK'] + ':' + os.environ['ATELIER_BUILD_GAME'])\n")
    assert p.run() == 0
    assert (p.ctx.out / '1.txt').read_text() == 'action1:standin'
    assert (p.ctx.out / '2.txt').read_text() == 'action2:standin'


def test_requested_touched_repair_is_not_skipped_for_a_later_stale_batch(project, monkeypatch):
    p = project
    p.steps[:] = p.steps[:3]
    assert p.run() == 0
    first = p.ctx.stamps / 'action1.json'
    record = json.loads(first.read_text()); record['touched'] = True
    first.write_text(json.dumps(record))
    (p.ctx.stamps / 'action2.json').unlink()
    untouched = (p.ctx.stamps / 'action3.json').read_bytes()
    batch_launch = build.run_command
    standalone = []
    def launch(ctx, step, command, log, request=None, slots=None, **kwargs):
        if command.script == build_batches.WORKER:
            return batch_launch(ctx, step, command, log, request, slots)
        standalone.append(step.name)
        subprocess.run([sys.executable, str(command.script), *command.args], check=True)
    monkeypatch.setattr(build, 'run_command', launch)
    assert p.run(wanted=[s.name for s in p.steps], rebuild_touched=True) == 0
    assert standalone == ['action1']
    assert not json.loads(first.read_text()).get('touched')
    assert json.loads((p.ctx.stamps / 'action2.json').read_text())['batch']
    assert (p.ctx.stamps / 'action3.json').read_bytes() == untouched


def test_batch_phase_ids_are_per_action_and_previous_inventory_survives_invalidation(project):
    p = project
    p.steps[:] = p.steps[:2]
    for seconds, step in enumerate(p.steps, 1):
        script = step.commands[0].script
        begin = 'ATELIER_PHASE ' + json.dumps({'event': 'begin', 'id': 'work', 'name': 'work', 'at': 0.})
        end = 'ATELIER_PHASE ' + json.dumps({'event': 'end', 'id': 'work', 'at': float(seconds), 'ok': True})
        script.write_text(f'print({begin!r}, flush=True)\n' + script.read_text() + f'print({end!r}, flush=True)\n')
    assert p.run() == 0
    original = [(p.ctx.stamps / (step.name + '.json')).read_bytes() for step in p.steps]
    for seconds, data in enumerate(original, 1):
        record = json.loads(data)
        assert record['commands'][0]['scope'] == 'batch action'
        trace = record['commands'][0]['phases']
        assert trace['status'] == 'complete' and trace['phases'][0]['seconds'] == seconds
        assert record['output_changes']['baseline'] == 'unknown'
    script = p.steps[0].commands[0].script
    script.write_text(script.read_text().replace("'made'", "'changed'"))
    assert p.run() == 0
    record = json.loads((p.ctx.stamps / 'action1.json').read_text())
    assert record['output_changes']['baseline'] == 'known'
    assert record['output_changes']['products'][0]['changed'] == ['<build>/1.txt']
    assert (p.ctx.stamps / 'action2.json').read_bytes() == original[1]


def test_bad_batch_phase_trace_does_not_certify_a_later_failed_action(project):
    p = project
    p.steps[:] = p.steps[:2]
    script = p.steps[0].commands[0].script
    script.write_text(script.read_text() + "print('ATELIER_PHASE {invalid', flush=True)\n")
    p.steps[1].commands[0].script.write_text("raise RuntimeError('later action failed')\n")
    assert p.run() == 1
    record = json.loads((p.ctx.stamps / 'action1.json').read_text())
    assert record['commands'][0]['phases']['status'] == 'incomplete'
    assert not (p.ctx.stamps / 'action2.json').exists()


def test_batch_optional_source_is_not_required_and_still_invalidates(project):
    p = project
    p.steps[:] = p.steps[:2]
    optional = p.steps[0].commands[0].script.with_name('optional.json')
    p.steps[0].optional_inputs = [optional]
    required = build.required_inputs(p.steps[0])
    assert optional not in required and optional in build.declared_inputs(p.steps[0])
    assert {path.name for path in required} >= {'build_batches.py', 'build_batch_worker.py'}
    assert p.run() == 0
    first = json.loads((p.ctx.stamps / 'action1.json').read_text())
    second = (p.ctx.stamps / 'action2.json').read_bytes()
    optional.write_text('present')
    assert p.run() == 0
    assert json.loads((p.ctx.stamps / 'action1.json').read_text())['fingerprint'] != first['fingerprint']
    assert (p.ctx.stamps / 'action2.json').read_bytes() == second


def test_interrupted_fourth_action_preserves_first_three_and_resume_runs_only_remaining(project):
    p = project
    script = p.steps[3].commands[0].script
    good = script.read_text()
    script.write_text('import os\nos._exit(7)\n')
    launches = len(p.launches)
    assert p.run() == 1
    before = {path.name: path.read_bytes() for path in p.ctx.stamps.glob('action*.json')}
    # Keep-going: the independent actions after the failed one still finish in a new batch.
    assert set(before) == {'action1.json', 'action2.json', 'action3.json', 'action5.json', 'action6.json'}
    assert not (p.ctx.out / '4.txt').exists() and (p.ctx.out / '6.txt').read_text() == 'made'
    assert 'FAILED steps: action4' in p.messages
    script.write_text(good)
    launches = len(p.launches)
    assert p.run() == 0
    assert len(p.launches) == launches + 1  # Only the failed action reruns.
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
    assert p.messages[-2] == ('BATCH YIELDED: 1 of 6 actions done; recheck Waiting, '
                              'then resume with atelier build standin')
    assert p.messages[-1].startswith('6 steps, 1 ran, 0 restored, 0 up to date, 5 not reached, ')
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


@pytest.mark.parametrize('host_value', [None, 'host'])
def test_runtime_override_presence_starts_a_new_process_without_leaking_values(project, monkeypatch, host_value):
    p = project
    p.steps[:] = p.steps[:4]
    if host_value is None:
        monkeypatch.delenv('ASSET_ID', raising=False)
    else:
        monkeypatch.setenv('ASSET_ID', host_value)
    for step, value in zip(p.steps, ('oak', None, 'pine', 'cedar')):
        step.batch = build.Batch('runtime environment', runtime_env=('ASSET_ID',))
        step.commands[0].env = () if value is None else (('ASSET_ID', value),)
        step.commands[0].script.write_text(
            "import os, sys\nfrom pathlib import Path\n"
            "Path(sys.argv[-1]).write_text(repr(os.environ.get('ASSET_ID')))\n"
            # A script mutation also must not leak to the next action in its warm process.
            "os.environ['ASSET_ID'] = 'script mutation'\n")
    assert p.run() == 0
    assert len(p.launches) == 3  # explicit oak; inherited host; explicit pine and cedar together
    assert [(p.ctx.out / f'{i}.txt').read_text() for i in range(1, 5)] == [
        repr('oak'), repr(host_value), repr('pine'), repr('cedar')]
    stamps = {path.name: path.read_bytes() for path in p.ctx.stamps.glob('action*.json')}
    assert len(stamps) == 4
    assert p.run() == 0 and len(p.launches) == 3
    assert {path.name: path.read_bytes() for path in p.ctx.stamps.glob('action*.json')} == stamps


def test_batch_cannot_cross_a_read_edge_or_tool_settings(project):
    p = project
    p.steps[1].reads.append('product1')
    p.steps[3].commands[0] = replace(p.steps[3].commands[0], threads=2)
    assert p.run() == 0
    assert len(p.launches) == 4  # action1; actions2-3; action4; actions5-6


@pytest.mark.parametrize('mutates_own_read', [False, True])
def test_changed_consumed_product_cannot_keep_a_completed_consumer_stamp(project, mutates_own_read):
    p = project
    p.steps[:] = p.steps[:3]
    source = p.ctx.out / '1.txt'
    p.steps[1].reads = ['product1']
    read = f"from pathlib import Path\nPath({str(p.ctx.out / '2.txt')!r}).write_text(Path({str(source)!r}).read_text())\n"
    mutate = f"from pathlib import Path\nPath({str(source)!r}).write_text('changed input')\n"
    if mutates_own_read:
        p.steps[1].commands[0].script.write_text(mutate + read)
    else:
        p.steps[1].commands[0].script.write_text(read)
        p.steps[2].commands[0].script.write_text(mutate + "raise RuntimeError('failed after changing an earlier read')\n")
    assert p.run() == 1
    assert (p.ctx.out / '2.txt').read_text() == ('changed input' if mutates_own_read else 'made')
    assert not (p.ctx.stamps / 'action2.json').exists()
    assert not (p.ctx.stamps / 'action1.json').exists()


def test_batch_rejects_unowned_outputs_and_startup_environment(project):
    p = project
    p.steps[0].products = []
    with pytest.raises(SystemExit, match='named products'):
        p.run()
    p.steps[0].products = [build.Product('product1', (p.ctx.out / '1.txt',))]
    p.steps[0].batch = build.Batch('bad', runtime_env=('PYTHONHASHSEED',))
    with pytest.raises(SystemExit, match='process-start'):
        p.run()


@pytest.mark.parametrize('expire_after_first', [False, True])
def test_queue_wait_does_not_consume_the_batch_budget_but_running_time_still_does(project, monkeypatch, expire_after_first):
    p = project
    clock = SimpleNamespace(now=0.)
    monkeypatch.setattr(build_batches, 'time', SimpleNamespace(monotonic=lambda: clock.now, time=time.time))
    launch_worker = build.run_command

    def after_queue(ctx, first, command, log, request, slots):
        # A long admission wait happens after Session construction, before the owned worker.
        clock.now = 900.
        if expire_after_first:
            original_poll = command.on_poll
            def poll(pid):
                original_poll(pid)
                if original_poll.__self__.completed:
                    # The second action must yield; repeated polls must not reset the clock.
                    clock.now = 1141.
            command.on_poll = poll
        return launch_worker(ctx, first, command, log, request, slots)

    monkeypatch.setattr(build, 'run_command', after_queue)
    assert p.run() == (75 if expire_after_first else 0)
    assert len(p.launches) == 1
    assert {path.stem for path in p.ctx.stamps.glob('action*.json')} == (
        {'action1', 'action2'} if expire_after_first else {f'action{i}' for i in range(1, 7)})
    if expire_after_first:
        assert any('wall-time budget' in message for message in p.messages)
        assert not (p.ctx.out / '3.txt').exists()
