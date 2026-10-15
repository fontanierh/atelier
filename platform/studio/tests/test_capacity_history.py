"""Small retained-file fixtures; no native guard imports, processes or shared state."""
import json
import os
import sys

import pytest

from atelier import capacity_history as history


def sample(**changes):
    return {'pid': 41, 'process_start': 100, 'time': 1000, 'elapsed_seconds': 1.,
            'footprint_bytes': 100, 'resident_bytes': 80, 'peak_bytes': 120,
            'cpu_ticks': 10, 'limit_bytes': 1000, 'state': 'running', **changes}


def write(directory, source, records, stem='memory-health'):
    path = directory / f'{stem}.{source}'
    text = json.dumps(records, indent=2) if source == 'json' else ''.join(json.dumps(record) + '\n' for record in records)
    path.write_text(text)
    return path


def owned(report):
    return report['families'][0]


def test_rotation_final_dedup_and_distinct_retained_peak_measurements(tmp_path):
    first = sample()
    second = sample(elapsed_seconds=2., footprint_bytes=150, peak_bytes=900, cpu_ticks=30)
    third = sample(elapsed_seconds=4., footprint_bytes=140, peak_bytes=900, cpu_ticks=60, limit_bytes=1100)
    write(tmp_path, 'previous.jsonl', [first])
    write(tmp_path, 'jsonl', [second, third])
    write(tmp_path, 'json', third)
    report = history.inspect(tmp_path)
    assert report['read_status'] == 'complete' and report['historical']
    family = owned(report)
    assert family['deduplicated_final_records'] == 1
    session, = family['sessions']
    assert session['sample_count'] == 3 and session['sampled_span_seconds'] == 3.
    assert session['max_footprint_bytes'] == 150 and session['max_guard_peak_bytes'] == 900
    assert session['cpu_tick_delta'] == 50
    assert session['first_observed_limit_bytes'] == 1000
    assert session['limit_changes'] == [{'sample': 3, 'from_bytes': 1000, 'to_bytes': 1100}]
    assert session['last_recorded_state'] == 'running'
    assert not any(key in session for key in ('duration', 'alive', 'success', 'job_peak_bytes'))


def test_pid_reuse_and_elapsed_resets_split_sessions(tmp_path):
    records = [sample(), sample(elapsed_seconds=3., cpu_ticks=30),
               sample(process_start=200, elapsed_seconds=.1, cpu_ticks=3),
               sample(process_start=200, elapsed_seconds=4., cpu_ticks=7),
               sample(process_start=200, elapsed_seconds=.2, cpu_ticks=8)]
    write(tmp_path, 'jsonl', records)
    sessions = owned(history.inspect(tmp_path))['sessions']
    assert [(s['pid'], s['process_start'], s['sample_count']) for s in sessions] == [
        (41, 100, 2), (41, 200, 2), (41, 200, 1)]
    assert [s['cpu_tick_delta'] for s in sessions] == [20, 4, None]


def test_final_only_limit_event_is_a_distinct_observation(tmp_path):
    write(tmp_path, 'jsonl', [sample()])
    final = sample(elapsed_seconds=2., footprint_bytes=1200, peak_bytes=1200, cpu_ticks=20, state='memory_limit')
    write(tmp_path, 'json', final)
    report = history.inspect(tmp_path)
    session, = owned(report)['sessions']
    assert report['read_status'] == 'partial'  # No retained previous rotation.
    assert session['sample_count'] == 2 and session['last_recorded_state'] == 'memory_limit'
    assert session['max_footprint_bytes'] == 1200


def test_final_only_snapshot_has_no_cpu_delta_or_sampled_span(tmp_path):
    write(tmp_path, 'json', sample(state='test_duration'))
    session, = owned(history.inspect(tmp_path))['sessions']
    assert session['sample_count'] == 1 and session['cpu_tick_delta'] is None
    assert session['sampled_span_seconds'] is None and session['last_recorded_state'] == 'test_duration'


def test_inconsistent_guard_peak_remains_a_reported_value_with_diagnostic(tmp_path):
    write(tmp_path, 'json', sample(footprint_bytes=150, peak_bytes=120))
    session, = owned(history.inspect(tmp_path))['sessions']
    assert session['max_footprint_bytes'] == 150 and session['max_guard_peak_bytes'] == 120
    assert session['diagnostics'] == ['guard peak below retained footprint']


@pytest.mark.parametrize('change', [{'cpu_ticks': None}, {'cpu_ticks': 5}])
def test_missing_or_decreasing_cpu_ticks_do_not_produce_delta(tmp_path, change):
    write(tmp_path, 'jsonl', [sample(), sample(elapsed_seconds=2., **change),
                             sample(elapsed_seconds=3., cpu_ticks=30)])
    assert owned(history.inspect(tmp_path))['sessions'][0]['cpu_tick_delta'] is None


def test_missing_invalid_and_private_values_stay_unknown(tmp_path):
    bad = sample(pid=True, process_start=None, footprint_bytes=-1, peak_bytes='private-secret',
                 cpu_ticks=float('nan'), limit_bytes=True, elapsed_seconds=float('inf'),
                 state='private-secret', helper_error='/private/secret', unknown={'private': 'secret'})
    write(tmp_path, 'jsonl', [bad, {}])
    report = history.inspect(tmp_path)
    first, second = owned(report)['sessions']
    assert first['pid'] is None and first['process_start'] is None
    assert set(first['unknown_fields']) == set(history.FIELDS)
    assert first['max_footprint_bytes'] is None and first['max_guard_peak_bytes'] is None
    assert first['last_recorded_state'] is None and first['sampled_span_seconds'] is None
    assert second['sample_count'] == 1
    encoded = json.dumps(report, allow_nan=False)
    assert 'private' not in encoded and 'secret' not in encoded


def test_watched_descendants_are_separate_families_without_peak_sums(tmp_path):
    write(tmp_path, 'json', sample(footprint_bytes=2, peak_bytes=3))
    write(tmp_path, 'json', sample(pid=42, process_start=200, footprint_bytes=1000, peak_bytes=1200),
          stem='memory-health-UnrealEditor-Cmd-42')
    write(tmp_path, 'json', sample(pid=43, footprint_bytes=5000), stem='memory-health-private-label-43')
    families = history.inspect(tmp_path)['families']
    assert len(families) == 3 and families[0]['kind'] == 'owned'
    assert {f['label'] for f in families[1:]} == {'UnrealEditor-Cmd', 'other'}
    assert [f['sessions'][0]['max_footprint_bytes'] for f in families] == [2, 1000, 5000]
    assert 'private-label' not in json.dumps(families)


def test_malformed_nonobject_duplicate_keys_and_cut_records_are_not_samples(tmp_path):
    path = write(tmp_path, 'jsonl', [sample()])
    with path.open('a') as stream:
        stream.write('private-secret\n[]\n{"pid":1,"pid":2}\n')
        stream.write(json.dumps(sample(elapsed_seconds=2.)))  # Guard JSONL records end in a newline.
    report = owned(history.inspect(tmp_path))
    file = report['files'][1]
    assert file['status'] == 'partial' and file['malformed_records'] == 4
    assert report['sessions'][0]['sample_count'] == 1
    assert 'private-secret' not in json.dumps(report)


def test_absent_and_linked_directories_do_not_create_anything(tmp_path):
    missing = tmp_path / 'absent'
    assert history.inspect(missing)['read_status'] == 'unread' and not missing.exists()
    link = tmp_path / 'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    assert history.inspect(link)['read_status'] == 'unread'
    empty = owned(history.inspect(tmp_path))
    assert empty['sessions'] == [] and all(f['status'] == 'missing' for f in empty['files'])


def test_empty_files_explicitly_have_no_record_coverage(tmp_path):
    for source in history.SUFFIXES:
        (tmp_path / f'memory-health.{source}').write_text('')
    report = history.inspect(tmp_path)
    assert report['read_status'] == 'partial'
    family = owned(report)
    assert family['sessions'] == [] and all(file['reason'] == 'no retained records parsed' for file in family['files'])
    assert family['files'][2]['malformed_records'] == 1


def test_linked_special_and_directory_files_are_never_read_or_blocking(tmp_path):
    final = tmp_path / 'memory-health.json'
    final.symlink_to(tmp_path / 'absent')
    os.mkfifo(tmp_path / 'memory-health.jsonl')
    (tmp_path / 'memory-health.previous.jsonl').mkdir()
    family = owned(history.inspect(tmp_path))
    assert all(f['status'] == 'unread' for f in family['files'])
    assert family['sessions'] == []


def test_byte_limit_discards_partial_record_and_charges_budget(tmp_path, monkeypatch):
    path = write(tmp_path, 'previous.jsonl', [sample(), sample(elapsed_seconds=2.)])
    first_size = len(path.read_bytes().splitlines(keepends=True)[0])
    write(tmp_path, 'jsonl', [sample(elapsed_seconds=3.)])
    monkeypatch.setattr(history, 'MAX_TOTAL_BYTES', first_size + 5)
    family = owned(history.inspect(tmp_path))
    assert family['sessions'][0]['sample_count'] == 1
    assert family['files'][0]['byte_limited'] and family['files'][0]['bytes_read'] == first_size + 5
    assert family['files'][1]['reason'] == 'invocation byte limit reached'


@pytest.mark.parametrize('limit,value', [('MAX_LINES', 1), ('MAX_RECORDS', 1), ('MAX_SESSIONS', 1)])
def test_record_line_and_session_limits_are_visible(tmp_path, monkeypatch, limit, value):
    write(tmp_path, 'jsonl', [sample(), sample(process_start=200)])
    monkeypatch.setattr(history, limit, value)
    family = owned(history.inspect(tmp_path))
    assert family['files'][1]['status'] == 'partial'
    assert family['files'][1]['record_limited']
    assert sum(s['sample_count'] for s in family['sessions']) == 1


def test_oversized_lines_and_final_records_are_partial(tmp_path, monkeypatch):
    write(tmp_path, 'jsonl', [sample(helper_error='x' * 500)])
    write(tmp_path, 'json', sample())
    monkeypatch.setattr(history, 'MAX_LINE_BYTES', 20)
    family = owned(history.inspect(tmp_path))
    assert family['sessions'] == [] and all(f['record_limited'] for f in family['files'][1:])


def test_directory_family_and_limit_change_caps_are_visible(tmp_path, monkeypatch):
    write(tmp_path, 'jsonl', [sample(limit_bytes=n, elapsed_seconds=n) for n in (1, 2, 3)])
    for pid in (42, 43):
        write(tmp_path, 'json', sample(pid=pid), stem=f'memory-health-dotnet-{pid}')
    monkeypatch.setattr(history, 'MAX_FAMILIES', 2)
    monkeypatch.setattr(history, 'MAX_LIMIT_CHANGES', 1)
    report = history.inspect(tmp_path)
    assert len(report['families']) == 2 and 'watched family limit reached' in report['diagnostics']
    session = owned(report)['sessions'][0]
    assert len(session['limit_changes']) == 1 and 'limit change detail capped' in session['diagnostics']
    monkeypatch.setattr(history, 'MAX_ENTRIES', 0)
    assert 'directory entry limit reached' in history.inspect(tmp_path)['diagnostics']


def test_read_only_rendering_and_no_native_guard_imports(tmp_path):
    write(tmp_path, 'jsonl', [sample(), sample(elapsed_seconds=2.)])
    write(tmp_path, 'json', tree_sample(), stem='memory-health-tree')
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    imported = {name for name in sys.modules if name.startswith('atelier.safety')}
    messages = []
    assert history.show(tmp_path, echo=messages.append) == 0
    assert any('Historical' in text for text in messages)
    messages.clear()
    assert history.show(tmp_path, as_json=True, echo=messages.append) == 0
    assert json.loads(messages[0])['historical']
    assert imported == {name for name in sys.modules if name.startswith('atelier.safety')}
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}


def tree_sample(**changes):
    return {'owner': 41, 'owner_started': 100, 'elapsed_seconds': 8.,
            'footprint_bytes': 0, 'peak_bytes': 950, 'limit_bytes': 1000,
            'state': 'child_exited', 'cleanup_complete': True,
            'processes': [], **changes}


def test_owned_tree_retains_its_simultaneous_peak_separately_from_process_peaks(tmp_path):
    write(tmp_path, 'json', sample(peak_bytes=10, footprint_bytes=1))
    write(tmp_path, 'json', sample(pid=42, peak_bytes=2000), stem='memory-health-dotnet-42')
    write(tmp_path, 'json', tree_sample(processes=[{'name': 'private-name', 'footprint_bytes': 9999}],
                                      exception='private error'), stem='memory-health-tree')
    report = history.inspect(tmp_path)
    tree = report['owned_tree']
    assert tree['file']['status'] == 'read' and tree['diagnostics'] == []
    assert tree['observation'] == {'pid': 41, 'process_start': 100, 'elapsed_seconds': 8.,
                                   'footprint_bytes': 0, 'peak_bytes': 950, 'limit_bytes': 1000,
                                   'state': 'child_exited', 'cleanup_complete': True, 'unknown_fields': []}
    assert [f['sessions'][0]['max_guard_peak_bytes'] for f in report['families']] == [10, 2000]
    assert 'private' not in json.dumps(report)
    messages = []
    history.show(tmp_path, echo=messages.append)
    assert any('Owned-tree latest receipt: read' in line for line in messages)
    assert any('guard-reported peak 950 bytes' in line for line in messages)
    assert '  recorded limit 1000 bytes' in messages


def test_tree_invalid_or_absent_fields_stay_unknown_without_copying_raw_text(tmp_path):
    write(tmp_path, 'json', tree_sample(owner=True, owner_started='private', elapsed_seconds=float('nan'),
                                      footprint_bytes=-1, peak_bytes=True, limit_bytes=None,
                                      state='private', cleanup_complete='true'), stem='memory-health-tree')
    tree = history.inspect(tmp_path)['owned_tree']
    observation = tree['observation']
    keys = {'pid', 'process_start', 'elapsed_seconds', 'footprint_bytes', 'peak_bytes', 'limit_bytes',
            'state', 'cleanup_complete'}
    assert observation['unknown_fields'] == sorted(keys)
    assert all(observation[key] is None for key in keys)
    assert 'private' not in json.dumps(tree, allow_nan=False)


@pytest.mark.parametrize('pid,start', [(0, 0), (1, 0)])
def test_tree_impossible_process_identities_stay_unknown(tmp_path, pid, start):
    write(tmp_path, 'json', tree_sample(owner=pid, owner_started=start), stem='memory-health-tree')
    observed = history.inspect(tmp_path)['owned_tree']['observation']
    assert observed['pid'] is None and observed['process_start'] is None


@pytest.mark.parametrize('data', ['private', '[]', '{"owner":1,"owner":2}', '{"owner":'])
def test_tree_malformed_or_nonobject_receipts_are_explicitly_partial(tmp_path, data):
    (tmp_path / 'memory-health-tree.json').write_text(data)
    tree = history.inspect(tmp_path)['owned_tree']
    assert tree['file']['status'] == 'partial' and tree['observation'] is None
    assert 'private' not in json.dumps(tree)


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'directory'])
def test_tree_linked_or_special_receipts_are_not_read(tmp_path, kind):
    path = tmp_path / 'memory-health-tree.json'
    if kind == 'symlink':
        secret = tmp_path / 'secret'
        secret.write_text(json.dumps(tree_sample()))
        path.symlink_to(secret)
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.mkdir()
    tree = history.inspect(tmp_path)['owned_tree']
    assert tree['file']['status'] == 'unread' and tree['observation'] is None


def test_tree_read_is_bounded_and_counts_against_the_invocation_budget(tmp_path, monkeypatch):
    path = write(tmp_path, 'json', tree_sample(), stem='memory-health-tree')
    write(tmp_path, 'json', sample())
    monkeypatch.setattr(history, 'MAX_TOTAL_BYTES', path.stat().st_size)
    report = history.inspect(tmp_path)
    assert report['owned_tree']['observation']['peak_bytes'] == 950
    assert owned(report)['files'][2]['reason'] == 'invocation byte limit reached'
    monkeypatch.setattr(history, 'MAX_TREE_BYTES', 20)
    tree = history.inspect(tmp_path)['owned_tree']
    assert tree['file']['bytes_read'] == 20 and tree['file']['byte_limited']
    assert tree['file']['status'] == 'partial' and tree['observation'] is None


def test_tree_missing_is_explicit_and_inconsistent_peak_is_not_repaired(tmp_path):
    assert history.inspect(tmp_path)['owned_tree'] == {
        'file': {'status': 'missing'}, 'observation': None, 'diagnostics': []}
    write(tmp_path, 'json', tree_sample(footprint_bytes=100, peak_bytes=10), stem='memory-health-tree')
    tree = history.inspect(tmp_path)['owned_tree']
    assert tree['observation']['peak_bytes'] == 10 and tree['observation']['footprint_bytes'] == 100
    assert tree['diagnostics'] == ['aggregate guard peak below retained footprint']
