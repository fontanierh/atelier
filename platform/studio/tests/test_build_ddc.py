"""Retained-log diagnostics require no Unreal process, cache access or artifact changes."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_ddc as ddc, cli


def summary(values=None, *, closed=True, prefix=''):
    values = values if values is not None else {'TotalGetHits': 9, 'TotalGetMisses': 1, 'TotalGets': 10, 'TotalGetHitPct': .9}
    lines = ['DDC Summary Stats', '================='] + [f'{key} = {value}' for key, value in values.items()]
    if closed:
        lines.append('')
    return ''.join(f'{prefix}LogCookStats: Display: {line}\n' for line in lines)


def parse(text):
    return ddc.parse(io.StringIO(text))


def step(name='unreal.import', *, needs=()):
    return build.Step(name, [build.UnrealScript(Path('import.py'), 'SUCCESS')], needs=list(needs))


def test_observed_configuration_discards_private_paths_endpoints_and_namespaces():
    messages = [
        'ZenLocal: Using ZenServer HTTP service at http://user:secret@private.invalid:8558 with namespace private_namespace. Status: OK!.',
        'Local: Using data cache path /private/cache-location: Writable',
        "ZenShared: Disabled because Host is set to 'None'",
        "Cloud: Disabled because Host is set to 'None'",
        'Shared: Disabled because no path is configured.',
        '/private/cache-location/pak.ddp: Opened pak cache for reading. (2978 MiB)',
        'ProjectPak: Pak cache file /private/project.ddp not found, will not use a pak cache.',
        'InstalledProjectPak: Pak cache file /private/installed.ddp not found, will not use a pak cache.',
    ]
    text = ''.join(f'[2026.01.01-12.00.00:000][  0]LogDerivedDataCache: Display: {message}\n' for message in messages)
    report = parse(text)
    assert {n['backend']: n['state'] for n in report['configuration']} == {
        'ZenLocal': 'available', 'Local': 'writable', 'ZenShared': 'disabled', 'Cloud': 'disabled',
        'Shared': 'disabled', 'Pak (unspecified)': 'readable', 'ProjectPak': 'unavailable', 'InstalledProjectPak': 'unavailable'}
    assert report['summaries'] == []
    encoded = json.dumps(report)
    for private in ('secret', 'private', 'namespace', '8558', 'http://'):
        assert private not in encoded


def test_conflicting_configuration_is_mixed_and_repeated_lines_do_not_invent_hits():
    available = 'LogDerivedDataCache: Local: Using data cache path /cache: Writable\n'
    disabled = 'LogDerivedDataCache: Shared: Disabled because no path is configured.\n'
    text = available * 5 + disabled + available.replace('Local:', 'Shared:')
    report = parse(text)
    assert report['configuration'][0]['observations'] == [{'state': 'writable', 'line': 1}]
    assert report['configuration'][1]['state'] == 'mixed'
    assert report['summaries'] == []


def test_explicit_cook_counts_are_separate_from_overlapping_backend_counters():
    text = summary({'HasLocalCache': 'true', 'HasSharedCache': 'false', 'HasZenCache': 'true',
                    'TotalGetHits': 16971, 'TotalGetMisses': 203, 'TotalGets': 17174, 'TotalGetHitPct': .988180,
                    'LocalGetHits': 16955, 'LocalGetMisses': 203, 'LocalGetTotal': 17158,
                    'ZenLocalGetHits': 16955, 'ZenLocalGetTotal': 17158})
    first, second = parse(text + text)['summaries']
    assert first['status'] == 'complete' and first['diagnostics'] == []
    assert first['metrics'] == second['metrics'] and first['line'] < second['line']
    assert first['metrics']['TotalGetHits'] == 16971  # Local and ZenLocal overlap; never sum them.
    assert first['metrics']['HasLocalCache'] is True and first['metrics']['HasSharedCache'] is False
    assert first['metrics']['CloudGetHits'] is None


def test_absent_totals_and_explicit_zero_are_distinct():
    assert parse('LogZenStore: Cook storage ready\nMissing cached shadermap\n')['summaries'] == []
    zero = parse(summary(dict.fromkeys(ddc.GET_TOTALS, 0)))['summaries'][0]
    assert zero['status'] == 'complete' and all(zero['metrics'][key] == 0 for key in ddc.GET_TOTALS)
    assert zero['metrics']['TotalGetHitPct'] is None  # Do not compute a missing ratio.
    partial = parse(summary({'HasZenCache': 'true'}))['summaries'][0]
    assert partial['status'] == 'incomplete' and partial['metrics']['TotalGets'] is None


@pytest.mark.parametrize('key,value', [
    ('TotalGetHits', '-1'), ('TotalGetHits', '1.5'), ('TotalGetHits', str(2**63)),
    ('TotalGetHitPct', 'nan'), ('TotalGetHitPct', 'inf'), ('TotalGetHitPct', '1.1'), ('HasLocalCache', 'yes'),
])
def test_malformed_known_fields_stay_unknown_without_raw_text(key, value):
    report = parse(summary({key: value}))['summaries'][0]
    assert report['status'] == 'incomplete' and report['metrics'][key] is None and report['diagnostics']


def test_conflicting_field_is_sticky_but_identical_duplicates_are_allowed():
    text = summary(closed=False) + 'LogCookStats: Display: TotalGets = 10\n'
    assert parse(text + 'LogCookStats: Display:\n')['summaries'][0]['status'] == 'complete'
    text += 'LogCookStats: Display: TotalGets = 11\nLogCookStats: Display: TotalGets = 10\nLogCookStats: Display:\n'
    report = parse(text)['summaries'][0]
    assert report['status'] == 'incomplete' and report['metrics']['TotalGets'] is None


def test_inconsistent_counts_and_reported_fraction_are_not_usable_aggregates():
    report = parse(summary({'TotalGetHits': 9, 'TotalGetMisses': 2, 'TotalGets': 10, 'TotalGetHitPct': .9}))['summaries'][0]
    assert all(report['metrics'][key] is None for key in (*ddc.GET_TOTALS, 'TotalGetHitPct'))
    report = parse(summary({'TotalGetHits': 9, 'TotalGetMisses': 1, 'TotalGets': 10, 'TotalGetHitPct': .8}))['summaries'][0]
    assert report['metrics']['TotalGetHitPct'] is None and report['metrics']['TotalGets'] == 10


@pytest.mark.parametrize('hits,misses,total', [
    ddc.GET_TOTALS, ('TotalPutHits', 'TotalPutMisses', 'TotalPuts'), ('LocalGetHits', 'LocalGetMisses', 'LocalGetTotal'),
])
def test_excessive_misses_invalidate_aggregate_even_when_hits_are_unknown(hits, misses, total):
    report = parse(summary({hits: 'invalid', misses: 11, total: 10}))['summaries'][0]
    assert all(report['metrics'][key] is None for key in (hits, misses, total))
    assert f'inconsistent {total}' in report['diagnostics']


@pytest.mark.parametrize('hits,misses,total,fraction', [
    (*ddc.GET_TOTALS, 'GetMissPct'), ('TotalPutHits', 'TotalPutMisses', 'TotalPuts', 'PutMissPct'),
])
def test_reported_miss_fraction_is_checked_even_when_hits_are_unknown(hits, misses, total, fraction):
    report = parse(summary({hits: 'invalid', misses: 2, total: 10, fraction: .8}))['summaries'][0]
    assert report['metrics'][fraction] is None and report['metrics'][misses] == 2


@pytest.mark.parametrize('counts,fractions,known', [
    ({'TotalGets': 10}, (.8, .8), False),
    ({}, (.8, .8), False),
    ({'TotalGets': 10}, (0., 0.), False),
    ({'TotalGetHits': 2}, (0., 0.), False),
    ({}, (0., 0.), True),
    ({}, (.8, .2), True),
    ({'TotalGets': 0}, (0., 0.), True),
    ({'TotalGets': 0}, (.5, .5), False),
])
def test_complementary_fractions_respect_known_totals_and_zero_request_convention(counts, fractions, known):
    report = parse(summary({**counts, 'TotalGetHitPct': fractions[0], 'GetMissPct': fractions[1]}))['summaries'][0]
    assert [report['metrics'][key] for key in ('TotalGetHitPct', 'GetMissPct')] == (list(fractions) if known else [None, None])


@pytest.mark.parametrize('total,fraction', [('LocalGetTotal', 'LocalGetHitPct'), ('TotalPuts', 'PutMissPct')])
def test_explicit_zero_total_invalidates_nonzero_single_fraction(total, fraction):
    report = parse(summary({total: 0, fraction: .2}))['summaries'][0]
    assert report['metrics'][fraction] is None


def test_known_opposite_count_can_refute_reported_fraction_without_inventing_counts():
    report = parse(summary({'TotalGetHits': 9, 'TotalGets': 10, 'GetMissPct': .8}))['summaries'][0]
    assert report['metrics']['GetMissPct'] is None and report['metrics']['TotalGetMisses'] is None


@pytest.mark.parametrize('hits,misses,total,fractions', [
    (*ddc.GET_TOTALS, ('TotalGetHitPct', 'GetMissPct')),
    ('TotalPutHits', 'TotalPutMisses', 'TotalPuts', ('TotalPutHitPct', 'PutMissPct')),
    ('LocalGetHits', 'LocalGetMisses', 'LocalGetTotal', ('LocalGetHitPct',)),
])
@pytest.mark.parametrize('counts,reported,known', [
    ((9, 1), (.8, .2), False), ((9, 1), (.9, .1), True),
    ((0, 0), (.5, .5), False), ((0, 0), (0., 0.), True),
])
def test_missing_total_stays_unknown_while_counts_validate_fractions(hits, misses, total, fractions, counts, reported, known):
    values = {hits: counts[0], misses: counts[1], **dict(zip(fractions, reported))}
    result = parse(summary(values))['summaries'][0]
    assert result['metrics'][total] is None
    assert [result['metrics'][key] for key in (hits, misses)] == list(counts)
    assert [result['metrics'][key] for key in fractions] == (list(reported[:len(fractions)]) if known else [None] * len(fractions))
    assert bool(result['diagnostics']) is not known


@pytest.mark.parametrize('count,fraction', [
    ('TotalGetHits', 'TotalGetHitPct'), ('TotalGetMisses', 'GetMissPct'),
    ('TotalPutHits', 'TotalPutHitPct'), ('TotalPutMisses', 'PutMissPct'),
    *((f'{prefix}GetHits', f'{prefix}GetHitPct') for prefix in ('Local', 'Shared', 'ZenLocal', 'ZenRemote', 'Cloud')),
])
def test_zero_count_refutes_nonzero_fraction_without_other_counts(count, fraction):
    result = parse(summary({count: 0, fraction: .8}))['summaries'][0]
    assert result['metrics'][count] == 0 and result['metrics'][fraction] is None
    assert result['diagnostics']


@pytest.mark.parametrize('reported,expected', [((.8, .2), (None, None)), ((0, .2), (None, None)),
                                               ((0, 1), (0, 1)), ((0, 0), (0, 0))])
def test_zero_opposite_count_allows_only_zero_or_all_requests(reported, expected):
    result = parse(summary({'TotalGetHits': 0, 'TotalGetHitPct': reported[0], 'GetMissPct': reported[1]}))['summaries'][0]
    assert [result['metrics'][key] for key in ('TotalGetHitPct', 'GetMissPct')] == list(expected)
    assert result['metrics']['TotalGets'] is None and result['metrics']['TotalGetMisses'] is None


def test_blocks_end_at_boundaries_and_never_absorb_other_stats():
    prefix = '[2026.01.01-12.00.00:000][  0]'
    text = summary(prefix=prefix) + 'LogCookStats: Display: TotalGets = 999\n'
    assert parse(text)['summaries'][0]['metrics']['TotalGets'] == 10
    text = summary(closed=False) + 'LogCookStats: Display: Different Summary\nLogCookStats: Display: TotalGets = 999\n'
    report = parse(text)['summaries'][0]
    assert report['status'] == 'incomplete' and report['metrics']['TotalGets'] == 10
    assert parse(summary(closed=False))['summaries'][0]['status'] == 'incomplete'
    text = summary(closed=False) + 'LogCookStats: Display: DDC Resource Stats\n'
    assert parse(text)['summaries'][0]['status'] == 'complete'


def test_parsing_limits_leave_coverage_partial(monkeypatch):
    monkeypatch.setattr(ddc, 'MAX_SUMMARIES', 1)
    report = parse(summary() * 2)
    assert len(report['summaries']) == 1 and report['coverage'] == 'partial'
    monkeypatch.setattr(ddc, 'MAX_LINES', 2)
    assert parse(summary())['coverage'] == 'partial'
    assert parse('x' * (ddc.MAX_LINE + 1))['coverage'] == 'partial'


def test_read_limit_discards_cut_records_and_keeps_complete_prior_blocks(tmp_path, monkeypatch):
    path = tmp_path / 'stdout.log'
    first = summary()
    path.write_text(first + summary(closed=False))
    report, used = ddc.read_log(path, len(first))
    assert used == len(first) and report['coverage'] == 'partial' and report['summaries'][0]['status'] == 'complete'
    monkeypatch.setattr(ddc, 'MAX_LOG_BYTES', len(first) - len('LogCookStats: Display: \n') - 2)
    report, used = ddc.read_log(path, 10000)
    assert used == ddc.MAX_LOG_BYTES and report['summaries'][0]['metrics']['TotalGetHitPct'] is None


def test_links_and_special_files_are_not_followed_or_blocking(tmp_path):
    log = tmp_path / 'log'
    log.write_text(summary())
    link = tmp_path / 'link'
    link.symlink_to(log)
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    for path in (link, fifo, tmp_path, tmp_path / 'missing'):
        report, used = ddc.read_log(path, 1000)
        assert report['coverage'] == 'unread' and used == 0


def test_changed_log_is_partial_and_deletion_still_charges_read_budget(tmp_path, monkeypatch):
    path = tmp_path / 'stdout.log'
    path.write_text(summary())
    original = Path.stat
    def changed(self, **kwargs):
        if self == path:
            path.write_text('changed')
        return original(self, **kwargs)
    monkeypatch.setattr(Path, 'stat', changed)
    report, used = ddc.read_log(path, 10000)
    assert report['coverage'] == 'partial' and 'log changed while reading' in report['diagnostics'] and used > 0
    monkeypatch.setattr(Path, 'stat', lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    report, used = ddc.read_log(path, 10000)
    assert report['coverage'] == 'unread' and used == len('changed')


def test_selection_prefers_guard_log_and_obeys_total_budget(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', logs=tmp_path)
    guard = tmp_path / 'unreal.import.guard/stdout.log'
    guard.parent.mkdir()
    guard.write_text(summary())
    fallback = tmp_path / 'unreal.import.log'
    fallback.write_text(summary(dict.fromkeys(ddc.GET_TOTALS, 0)))
    (tmp_path / 'unreal.next.log').write_text(summary())
    steps = [step(), step('unreal.next', needs=['unreal.import'])]
    monkeypatch.setattr(ddc, 'MAX_TOTAL_BYTES', guard.stat().st_size)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (guard, fallback)}
    reports = ddc.inspect(ctx, steps, ['unreal.next'])['steps']
    assert len(reports) == 2 and reports[0]['summaries'][0]['metrics']['TotalGets'] == 10
    assert reports[0]['scope'] == 'last guarded command' and reports[1]['reason'] == 'invocation byte limit reached'
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
    assert len(ddc.inspect(ctx, steps, ['unreal.import'])['steps']) == 1


def test_fallback_requires_absent_guard_log_and_non_unreal_steps_are_ignored(tmp_path):
    ctx = SimpleNamespace(game='fixture', logs=tmp_path)
    (tmp_path / 'unreal.import.log').write_text(summary())
    steps = [build.Step('world', [build.Python(Path('generate.py'))]), step(needs=['world'])]
    reports = ddc.inspect(ctx, steps)['steps']
    assert len(reports) == 1 and reports[0]['scope'] == 'retained step log'
    assert reports[0]['summaries'][0]['metrics']['TotalGets'] == 10
    guard = tmp_path / 'unreal.import.guard/stdout.log'
    guard.parent.mkdir()
    guard.symlink_to(tmp_path / 'absent')
    report = ddc.inspect(ctx, steps)['steps'][0]
    assert report['scope'] == 'last guarded command' and report['coverage'] == 'unread'


@pytest.mark.parametrize('flag', ['--force', '--touch', '--list', '--plan', '--explain', '--verify', '--changes', '--timings'])
def test_cli_rejects_conflicting_flags(flag):
    with pytest.raises(SystemExit, match='--ddc combines only'):
        cli.main(['build', 'sandbox', '--ddc', flag])


def test_cli_is_read_only_and_missing_reused_logs_do_not_invent_receipts(tmp_path, monkeypatch, capsys):
    ctx = SimpleNamespace(game='fixture', logs=tmp_path / 'absent')
    creates = []
    def forbidden(*args, **kwargs):
        raise AssertionError('DDC inspection must not execute or certify a build')
    monkeypatch.setattr(build, 'Context', lambda game, *, create: creates.append(create) or ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [step()]))
    monkeypatch.setattr(build, 'fingerprint_state', forbidden)
    monkeypatch.setattr(build, 'outputs_present', forbidden)
    monkeypatch.setattr(build, 'run_command', forbidden)
    assert cli.main(['build', 'fixture', '--ddc', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['historical'] and 'unverified' in report['verification']
    assert report['steps'][0]['reason'] == 'log not found' and creates == [False] and not ctx.logs.exists()
    messages = []
    assert ddc.show('fixture', echo=messages.append) == 0
    assert any('unverified' in line for line in messages) and any('log not found' in line for line in messages)
