"""Timing diagnostics preserve build/cache semantics and need no native commands."""
import io
import json
import os
from types import SimpleNamespace
import uuid

import pytest

from atelier import build, build_timings, cli
from atelier.build import Call, Python, Step, UnrealScript
from test_build_audit import action  # noqa: F401 - reuse the isolated real Python/cache fixture
from test_build_cache import project  # noqa: F401 - independent output/cache fixture


def line(event, identity, at, **values):
    return build_timings.PREFIX + json.dumps({'event': event, 'id': identity, 'at': at, **values}) + '\n'


def interval(identity='work', start=1., end=4.):
    return line('begin', identity, start, name=identity) + line('end', identity, end, ok=True)


def launch_record(**values):
    return {'schema': 1, 'invocation_id': uuid.uuid4().hex, 'admission_seconds': 2.,
            'child_lifetime_seconds': 5., 'execution_seconds': None, **values}


@pytest.mark.parametrize('source', ['local', 'https', None, 'https://secret.invalid/private'])
def test_restore_source_is_historical_and_never_inferred(tmp_path, monkeypatch, source):
    ctx = SimpleNamespace(game='fixture', stamps=tmp_path)
    record = {'seconds': .5, 'commands': [], 'restored_from': 'key'}
    if source is not None:
        record['restore_source'] = source
    (tmp_path / 'mesh.json').write_text(json.dumps(record))
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [Step('mesh', [])]))
    item = build_timings.inspect(ctx, [Step('mesh', [])])['steps'][0]
    assert item.get('restore_source') == (source if source in ('local', 'https') else None)
    messages = []
    assert build_timings.show('fixture', echo=messages.append) == 0
    expected = {'local': 'local store', 'https': 'HTTPS fetched during this build'}.get(source, 'not recorded')
    assert f'  restore source: {expected}' in messages
    assert all('secret.invalid' not in message for message in messages)


@pytest.mark.parametrize('update', [
    {'schema': True}, {'invocation_id': 'old'}, {'admission_seconds': -1}, {'admission_seconds': True},
    {'child_lifetime_seconds': float('nan')}, {'execution_seconds': float('inf')},
    {'execution_seconds': 6.}, {'child_lifetime_seconds': None, 'execution_seconds': 1.}, {'extra': 1},
])
def test_invalid_launcher_diagnostics_stay_unknown(tmp_path, update):
    (tmp_path / build_timings.LAUNCH_REPORT).write_text(json.dumps(launch_record(**update)))
    assert build_timings.launch_receipt(tmp_path) is None


def test_launcher_reader_is_bounded_and_does_not_follow_links_or_wait_on_fifo(tmp_path):
    path = tmp_path / build_timings.LAUNCH_REPORT
    target = tmp_path / 'target'
    target.write_text(json.dumps(launch_record()))
    path.symlink_to(target)
    assert build_timings.launch_receipt(tmp_path) is None
    path.unlink()
    os.mkfifo(path)
    assert build_timings.launch_receipt(tmp_path) is None
    path.unlink()
    path.write_text('x' * 8193)
    assert build_timings.launch_receipt(tmp_path) is None
    path.write_text('[' * 4000 + ']' * 4000)
    assert build_timings.launch_receipt(tmp_path) is None


def test_build_uses_only_new_launcher_receipts_without_changing_products(project, monkeypatch):
    p = project
    p.step.heavy = True
    monkeypatch.setattr(build, 'slot_request', lambda *args: ('job', None))
    run = build.run_command
    receipt = launch_record()
    report = p.ctx.logs / 'mesh.guard' / build_timings.LAUNCH_REPORT
    def timed(*args, **kwargs):
        result = run(*args, **kwargs)
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps(receipt))
        return result
    monkeypatch.setattr(build, 'run_command', timed)
    assert p.run() == 0
    record = json.loads((p.ctx.stamps / 'mesh.json').read_text())
    key = record['fingerprint']
    assert record['commands'][0]['launcher'] == receipt
    entry = p.store.action(key).read_bytes()
    monkeypatch.setattr(build, 'run_command', run)  # Simulates a launcher without new diagnostics.
    assert p.run(force=True) == 0
    record = json.loads((p.ctx.stamps / 'mesh.json').read_text())
    assert 'launcher' not in record['commands'][0] and not report.exists()
    assert record['fingerprint'] == key and p.store.action(key).read_bytes() == entry
    p.step.products[1].paths[0].unlink()
    assert p.run() == 0
    assert json.loads((p.ctx.stamps / 'mesh.json').read_text())['restore_source'] == 'local'


def test_nested_intervals_are_inclusive_and_failed_phase_is_still_measured():
    text = line('begin', 'all', 1., name='whole action')
    text += line('begin', 'ao', 2., name='ambient occlusion', parent='all')
    text += line('end', 'ao', 5., ok=False) + line('end', 'all', 7., ok=True)
    receipt = build_timings.parse_phases(text)
    assert receipt['status'] == 'complete' and receipt['diagnostics'] == []
    assert [(p['id'], p['parent'], p['seconds'], p['ok']) for p in receipt['phases']] == [
        ('all', None, 6., True), ('ao', 'all', 3., False)]
    assert all('at' not in p for p in receipt['phases'])
    assert build_timings.parse_phases('ordinary command output\n') is None


@pytest.mark.parametrize('invalid', [
    'ATELIER_PHASE {broken\n',
    line('begin', 'bad', float('nan'), name='bad'),
    line('begin', 'bad', float('inf'), name='bad'),
    line('begin', 'bad', True, name='bad'),
    line('begin', 'bad', 5., name='bad', typo=True),
    line('begin', 'bad', 5., name='x' * 129),
    line('begin', 'bad', 5., name='bad', parent='absent'),
    line('end', 'absent', 5., ok=True),
    line('begin', 'work', 5., name='duplicate id'),
    line('begin', 'bad', 3., name='clock moved backwards'),
    'ATELIER_PHASE ' + ' ' * 8193 + '{}\n',
], ids=['json', 'nan', 'infinity', 'boolean', 'unknown-field', 'long-name', 'parent', 'end', 'id', 'clock', 'payload'])
def test_invalid_trace_keeps_only_previously_completed_measurements(invalid):
    receipt = build_timings.parse_phases(interval() + invalid + interval('later', 10., 15.))
    assert receipt['status'] == 'incomplete' and receipt['diagnostics']
    assert [p['id'] for p in receipt['phases']] == ['work']
    assert receipt['phases'][0]['seconds'] == 3.


def test_unclosed_or_crossed_intervals_are_not_given_guessed_durations():
    text = line('begin', 'all', 1., name='all') + line('begin', 'child', 2., name='child', parent='all')
    for suffix in ('', line('end', 'all', 10., ok=True)):
        receipt = build_timings.parse_phases(text + suffix)
        assert receipt['status'] == 'incomplete'
        assert all(p['seconds'] is None and p['ok'] is None for p in receipt['phases'])


def test_echoes_are_only_allowed_when_adjacent_and_opted_in():
    begin, end = interval().splitlines(keepends=True)
    echoed = begin + 'LogPython: ' + begin + end + 'LogPython: Display: ' + end
    assert build_timings.parse_phases(echoed, allow_echo=True)['status'] == 'complete'
    assert build_timings.parse_phases(echoed)['status'] == 'incomplete'
    assert build_timings.parse_phases(begin + 'other output\n' + begin, allow_echo=True)['status'] == 'incomplete'


def test_record_and_nesting_limits_bound_receipts(monkeypatch):
    monkeypatch.setattr(build_timings, 'MAX_RECORDS', 2)
    receipt = build_timings.parse_phases(interval() + interval('extra', 5., 6.))
    assert receipt['status'] == 'incomplete' and len(receipt['phases']) == 1
    monkeypatch.setattr(build_timings, 'MAX_DEPTH', 1)
    receipt = build_timings.parse_phases(line('begin', 'all', 1., name='all')
                                        + line('begin', 'child', 2., name='child', parent='all'))
    assert receipt['status'] == 'incomplete' and len(receipt['phases']) == 1


def test_real_execution_noop_and_repeated_restore_preserve_distinct_receipts(action):
    a = action
    a.code(f"print({interval()!r})\noutput.write_text(source.read_text())")
    assert a.run() == 0, a.messages
    original = build_timings.producer_receipt(a.stamp())
    assert original['commands'][0]['phases']['phases'][0]['seconds'] == 3.
    stamp_path = a.ctx.stamps / 'generate.json'
    stamp_bytes = stamp_path.read_bytes()
    assert a.run() == 0 and stamp_path.read_bytes() == stamp_bytes
    key = a.stamp()['fingerprint']
    entry_bytes = a.store.action(key).read_bytes()
    for _ in range(2):
        a.output.unlink()
        assert a.run() == 0, a.messages
        restored = a.stamp()
        assert restored['commands'] == [] and restored['producer_receipt'] == original
        item = build_timings.inspect(a.ctx, a.steps)['steps'][0]
        assert item['last_action'] == 'cache restore' and item['producer'] == original
    assert a.store.action(key).read_bytes() == entry_bytes  # timings never enter the CAS action entry
    stamp_path.unlink()
    a.output.unlink()
    assert a.run() == 0
    assert build_timings.inspect(a.ctx, a.steps)['steps'][0]['producer'] is None
    a.source.write_text('different')
    assert a.run() == 0
    a.source.write_text('input')
    assert a.run() == 0
    assert 'producer_receipt' not in a.stamp()  # another fingerprint's execution is not this producer


def test_bad_phase_output_does_not_certify_or_fail_an_action_by_itself(action):
    a = action
    a.code("print('ATELIER_PHASE {invalid')\noutput.write_text(source.read_text())")
    assert a.run() == 0, a.messages
    assert a.stamp()['commands'][0]['phases']['status'] == 'incomplete'
    a.output.unlink()
    assert a.run() == 0  # restore replaces the local command log, but preserves diagnostic receipts
    messages = []
    assert build_timings.show('fixture', echo=messages.append) == 0
    assert any('line 1:' in message for message in messages)
    a.code("print('ATELIER_PHASE {invalid')\nraise RuntimeError('actual failure')")
    assert a.run() == 1
    assert not (a.ctx.stamps / 'generate.json').exists()


def test_unreal_command_echoes_parse_after_normal_success_checks(tmp_path, monkeypatch):
    begin, end = interval().splitlines(keepends=True)
    stdout = 'SUCCESS\n' + begin + 'LogPython: ' + begin + end + 'LogPython: ' + end
    monkeypatch.setattr(build, 'run_light', lambda *args, **kwargs: (0, stdout))
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'build', env=lambda _: {})
    command = UnrealScript(tmp_path / 'import.py', 'SUCCESS')
    receipt = build.run_argv(ctx, Step('import', [command]), command, ['fake-command'], (), io.StringIO(), None, None)
    assert receipt['status'] == 'complete'
    command.marker = 'MISSING'
    with pytest.raises(RuntimeError, match='missing from the log'):
        build.run_argv(ctx, Step('import', [command]), command, ['fake-command'], (), io.StringIO(), None, None)


def test_inspection_reads_only_stamps_and_honors_selection(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'build', stamps=tmp_path / 'build/stamps')
    def forbidden(*args, **kwargs):
        raise AssertionError('read-only timing inspection executed work')
    steps = [Step('selected', [Call('no execution', forbidden)], verify=forbidden),
             Step('unselected', [Python(tmp_path / 'missing.py')])]
    monkeypatch.setattr(build, 'fingerprint_state', forbidden)
    monkeypatch.setattr(build, 'outputs_present', forbidden)
    assert build_timings.inspect(ctx, steps, ['selected'])['steps'] == [
        {'step': 'selected', 'last_action': 'not recorded', 'time': None, 'seconds': None, 'producer': None}]
    assert not ctx.out.exists()
    ctx.stamps.mkdir(parents=True)
    stamp = ctx.stamps / 'selected.json'
    stamp.write_text(json.dumps({'fingerprint': 'old', 'seconds': 99, 'commands': []}))
    before = stamp.read_bytes(), stamp.stat().st_mtime_ns
    assert build_timings.inspect(ctx, steps, ['selected'])['steps'][0]['seconds'] == 99
    assert (stamp.read_bytes(), stamp.stat().st_mtime_ns) == before
    (ctx.stamps / 'selected.restore.json').write_text('{}')
    item = build_timings.inspect(ctx, steps, ['selected'])['steps'][0]
    assert item['last_action'] == 'interrupted restoration' and item['producer'] is None


@pytest.mark.parametrize('extra, kind, producer', [
    ({'reused_from': 'donor'}, 'copied stamp', True),
    ({'pooled_from': 'key'}, 'copied stamp', True),
    ({'touched': True}, 'touched', False),
    ({'restored_from': 'key'}, 'cache restore', False),
    ({'commands': None}, 'legacy stamp', False),
])
def test_copied_touched_and_old_stamps_do_not_invent_restore_or_execution_times(tmp_path, extra, kind, producer):
    ctx = SimpleNamespace(game='fixture', stamps=tmp_path)
    record = {'seconds': 10., 'commands': [{'kind': 'Python', 'seconds': 9.}], **extra}
    (tmp_path / 'step.json').write_text(json.dumps(record))
    item = build_timings.inspect(ctx, [Step('step', [])])['steps'][0]
    assert item['last_action'] == kind and (item['producer'] is not None) == producer
    assert item['seconds'] == (10. if kind == 'cache restore' else None)


@pytest.mark.parametrize('flag', ['--force', '--touch', '--list', '--plan', '--explain', '--verify'])
def test_cli_rejects_conflicting_timing_flags(flag):
    with pytest.raises(SystemExit, match='--timings combines only'):
        cli.main(['build', 'sandbox', '--timings', flag])


def test_json_timings_uses_noncreating_context_and_not_the_plan(tmp_path, monkeypatch, capsys):
    ctx = SimpleNamespace(game='fixture', stamps=tmp_path / 'missing')
    created = []
    monkeypatch.setattr(build, 'Context', lambda game, *, create: created.append(create) or ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [Step('world', [])]))
    assert cli.main(['build', 'fixture', 'world', '--timings', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert created == [False] and report['historical'] and report['steps'][0]['step'] == 'world'
    assert not ctx.stamps.exists()


@pytest.mark.parametrize('operation', ['copied', 'restored'])
def test_batch_action_scope_survives_copied_and_restored_producer_receipts(tmp_path, monkeypatch, operation):
    ctx = SimpleNamespace(game='fixture', stamps=tmp_path)
    command = {'kind': 'Blender', 'seconds': 2., 'scope': 'batch action'}
    producer = {'time': 1., 'seconds': 2., 'commands': [command]}
    record = {**producer, 'reused_from': 'donor'} if operation == 'copied' else {
        'time': 3., 'seconds': .01, 'commands': [], 'restored_from': 'key', 'producer_receipt': producer}
    (tmp_path / 'action.json').write_text(json.dumps(record))
    monkeypatch.setattr(build, 'Context', lambda game, *, create: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [Step('action', [])]))
    messages = []
    assert build_timings.show('fixture', echo=messages.append) == 0
    assert any('batch action; shared startup/shutdown and host verification excluded' in message for message in messages)
    item = build_timings.inspect(ctx, [Step('action', [])])['steps'][0]
    assert item['producer']['commands'][0] == command


def test_missing_historical_timing_scope_stays_unknown(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', stamps=tmp_path)
    record = {'seconds': 2., 'batch': 'legacy-session',
              'commands': [{'kind': 'Blender', 'seconds': 2.}], 'reused_from': 'donor'}
    (tmp_path / 'action.json').write_text(json.dumps(record))
    monkeypatch.setattr(build, 'Context', lambda game, *, create: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [Step('action', [])]))
    messages = []
    assert build_timings.show('fixture', echo=messages.append) == 0
    assert any('timing scope not recorded' in message for message in messages)
