import pytest

from atelier.capacity import Request, Resources, conflicts, plan, replace


TOTAL = Resources(memory_mib=24000, cpu_millis=8000, temp_mib=120000, io_slots=2, gpu_mib=8000)
RESERVE = Resources(memory_mib=4000, cpu_millis=1000, temp_mib=10000)


def test_each_dimension_can_independently_refuse_admission():
    for name, value in vars(TOTAL).items():
        amounts = {name: value + 1}
        if name == 'gpu_mib': amounts['memory_mib'] = value + 1
        request = Request('job', Resources(**amounts))
        assert f'capacity:{name}' in conflicts(request, [], TOTAL, RESERVE)


def test_named_lock_conflict_is_independent_of_free_capacity():
    holder = Request('editor', Resources(memory_mib=1000), locks=('checkout:a',))
    next_job = Request('import', Resources(memory_mib=1000), locks=('checkout:a',))
    assert conflicts(next_job, [holder], TOTAL, RESERVE) == ['lock:checkout:a']


def test_queue_cannot_hold_any_grant_while_waiting():
    request = Request('job', Resources(memory_mib=1000))
    with pytest.raises(ValueError, match='queued'):
        plan(TOTAL, RESERVE, [request], [request], now=1)


def test_batch_accounts_for_earlier_recommendations_without_mutating_holders():
    holders = []
    jobs = [Request(str(i), Resources(memory_mib=12000)) for i in range(2)]
    result = plan(TOTAL, RESERVE, holders, jobs, now=1)
    assert [d['recommendation'] for d in result['decisions']] == ['would-admit', 'wait']
    assert result['admission'] is False and holders == []


def test_performance_window_waits_for_encode_and_compile_to_drain():
    for name in ('encode', 'compile'):
        holder = Request(name, Resources(cpu_millis=1000))
        benchmark = Request('judged-playtest', Resources(memory_mib=14000), performance=True)
        assert conflicts(benchmark, [holder], TOTAL, RESERVE)
        assert conflicts(holder, [benchmark], TOTAL, RESERVE)


def test_atomic_phase_change_checks_new_locks_and_keeps_old_grant_on_failure():
    old = Request('build', Resources(memory_mib=2000), locks=('checkout:a',))
    other = Request('other', Resources(memory_mib=2000), locks=('ubt',))
    replacement = Request('build', Resources(memory_mib=12000), locks=('checkout:a', 'ubt'))
    holders = [old, other]
    assert replace('build', replacement, holders, TOTAL, RESERVE) == ['lock:ubt']
    assert holders == [old, other]
    assert replace('build', replacement, [old], TOTAL, RESERVE) == []


def test_protected_long_waiter_drains_capacity_and_keeps_original_age():
    holder = Request('active', Resources(memory_mib=10000))
    long = Request('long', Resources(memory_mib=15000), ready_at=10, seconds=900, bypasses=2)
    short = Request('short', Resources(memory_mib=1000), ready_at=20, seconds=30)
    result = plan(TOTAL, RESERVE, [holder], [long, short], now=30)
    assert [d['recommendation'] for d in result['decisions']] == ['wait', 'wait']
    assert result['decisions'][0]['ready_at'] == 10
    assert 'protected waiter' in result['decisions'][1]['reasons'][-1]


@pytest.mark.parametrize('value', [-1, float('nan'), 1.5, True])
def test_invalid_resource_requests_fail_closed(value):
    with pytest.raises(ValueError): Resources(memory_mib=value)


def test_unified_gpu_memory_cannot_escape_the_system_memory_budget():
    with pytest.raises(ValueError, match='also be included'):
        Resources(memory_mib=1000, gpu_mib=2000)
    assert 'capacity:memory_mib' in conflicts(
        Request('gpu', Resources(memory_mib=21000, gpu_mib=1000)), [], TOTAL, RESERVE)


@pytest.mark.parametrize('dimension', list(vars(TOTAL)))
def test_ready_request_that_cannot_fit_an_empty_snapshot_names_each_exceeded_dimension(dimension):
    amount = getattr(TOTAL, dimension) - getattr(RESERVE, dimension) + 1
    resources = {dimension: amount}
    if dimension == 'gpu_mib':
        resources['memory_mib'] = amount  # The GPU ceiling remains a valid unified-memory subset.
    request = Request('oversized', Resources(**resources), ready_at=10, bypasses=2)
    report = plan(TOTAL, RESERVE, [], [request], now=10)
    decision, = report['decisions']
    assert decision['recommendation'] == 'cannot-fit'
    assert decision['exceeded_dimensions'] == [dimension]
    assert f'capacity:{dimension}' in decision['reasons']
    assert 'this snapshot' in decision['reasons'][-1] and 'no holders' in decision['reasons'][-1]
    assert decision['ready_at'] == 10 and report['mode'] == 'shadow' and report['admission'] is False
    if getattr(RESERVE, dimension):
        assert amount <= getattr(TOTAL, dimension)  # Reserve alone makes these requests impossible.


def test_impossible_oldest_waiter_preserves_next_feasible_protection_and_age_after_release():
    holder = Request('active', Resources(memory_mib=10000))
    impossible = Request('impossible', Resources(memory_mib=21000), ready_at=5, seconds=900, bypasses=2)
    protected = Request('protected', Resources(memory_mib=15000), ready_at=10, seconds=900, bypasses=2)
    short = Request('short', Resources(memory_mib=1000), ready_at=20, seconds=30)
    waiting = [impossible, protected, short]
    busy = plan(TOTAL, RESERVE, [holder], waiting, now=30)['decisions']
    assert [d['recommendation'] for d in busy] == ['cannot-fit', 'wait', 'wait']
    assert busy[2]['reasons'][-1] == 'drain for oldest protected waiter: protected'
    released = plan(TOTAL, RESERVE, [], waiting, now=30)['decisions']
    assert [d['recommendation'] for d in released] == ['cannot-fit', 'would-admit', 'would-admit']
    assert [d['ready_at'] for d in released] == [5, 10, 20]
    assert waiting == [impossible, protected, short] and protected.bypasses == 2


@pytest.mark.parametrize('bypasses', [0, 1, 2])
def test_impossible_requests_never_reserve_virtual_capacity_or_locks(bypasses):
    impossible = Request('impossible', Resources(memory_mib=21000), locks=('checkout',),
                         ready_at=0, bypasses=bypasses, performance=True)
    jobs = [Request(f'job{i}', Resources(memory_mib=12000), locks=('checkout',), ready_at=1) for i in range(2)]
    report = plan(TOTAL, RESERVE, [], [impossible, *jobs], now=2)
    assert [d['recommendation'] for d in report['decisions']] == ['cannot-fit', 'would-admit', 'wait']
    assert report['decisions'][1]['reasons'] == []
    assert 'capacity:memory_mib' in report['decisions'][2]['reasons']
    assert not any('performance' in reason or 'protected waiter' in reason
                   for decision in report['decisions'][1:] for reason in decision['reasons'])


def test_exact_empty_holder_envelope_fit_is_feasible():
    request = Request('exact', Resources(**{key: value - getattr(RESERVE, key) for key, value in vars(TOTAL).items()}),
                      bypasses=2)
    decision, = plan(TOTAL, RESERVE, [], [request], now=0)['decisions']
    assert decision['recommendation'] == 'would-admit' and decision['reasons'] == []


@pytest.mark.parametrize('holder,locks,reason', [
    (Request('holder', Resources(), locks=('checkout',)), ('checkout',), 'lock:checkout'),
    (Request('holder', Resources(memory_mib=1000), performance=True), (), 'performance window must drain first'),
    (Request('holder', Resources(memory_mib=25000)), (), 'capacity:memory_mib'),
])
def test_feasible_requests_still_wait_for_locks_performance_and_existing_overcommit(holder, locks, reason):
    request = Request('fitting', Resources(memory_mib=1000), locks=locks)
    decision, = plan(TOTAL, RESERVE, [holder], [request], now=0)['decisions']
    assert decision['recommendation'] == 'wait' and reason in decision['reasons']
    assert 'exceeded_dimensions' not in decision


def test_future_impossible_request_keeps_not_ready_behavior():
    future = Request('future', Resources(memory_mib=21000), ready_at=10, bypasses=2)
    fitting = Request('fitting', Resources(memory_mib=1000))
    result = plan(TOTAL, RESERVE, [], [future, fitting], now=1)['decisions']
    assert result[0]['recommendation'] == 'wait' and result[0]['reasons'] == ['not ready']
    assert result[1]['recommendation'] == 'would-admit'
