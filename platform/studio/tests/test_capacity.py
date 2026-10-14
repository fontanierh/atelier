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
