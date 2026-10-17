"""No native workloads: exercise the administrative interruption policy and its refusal paths."""
import copy
import errno
import hashlib
import json
from pathlib import Path

import pytest

from atelier.harness import capacity_abandon as abandon
from atelier.harness import capacity_protocol as wire


@pytest.fixture
def case(tmp_path):
    reports = {}
    for name in ('process_guard', 'tree_guard'):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps({'state': 'running', 'original': True}))
        reports[name] = dict(pid=20 + len(reports), start=200 + len(reports), report=str(path))
    record = dict(request=dict(id='compile', owner='worker', phase='compile', performance=True),
                  nonce='lease', state='uncertain', child=[10, 100], principal=[11, 90],
                  guards=reports, roster=[[10, 100], [12, 110]], exited=[[10, 100]], ancestry_unknown=True)
    evidence = dict(id='compile', nonce='lease', epoch=18, boot_id='boot',
                    administrator='maintenance', operator_reference='operator board instruction 123', services=[])
    rows = {1: dict(pid=1, started=1, parent=0, executable='/sbin/launchd'),
            30: dict(pid=30, started=20, parent=1, executable='/apps/agent'),
            31: dict(pid=31, started=300, parent=30, executable='/usr/bin/python')}
    return record, evidence, rows


def recover(case, **changes):
    record, evidence, rows = case
    return abandon.recover(record, evidence, principal=(31, 300), boot='boot', epoch=18,
                           scan=lambda: copy.deepcopy(rows), missing=lambda pin: True, **changes)


def test_interruption_is_a_distinct_failed_release_and_preserves_original_reports(case):
    record, _, _ = case
    before = copy.deepcopy(record)
    witness = recover(case)
    assert witness['kind'] == 'administrative-interruption'
    assert witness['output_certified'] is False
    assert witness['missing_historical_exits'] == 1 and witness['ancestry_unknown']
    assert witness['nonce'] == 'lease' and witness['epoch'] == 18
    assert witness['coverage'] == 'current-observed-quiescence'
    assert record == before
    for kind, report in record['guards'].items():
        raw = Path(report['report']).read_bytes()
        assert json.loads(raw)['state'] == 'running'
        assert witness['original_report_sha256'][kind] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('key,value', [('id','another'),('nonce','new'),('epoch',19),('boot_id','new')])
def test_binding_change_refuses(case, key, value):
    case[1][key] = value
    with pytest.raises(wire.CapacityError, match='fenced'):
        recover(case)


@pytest.mark.parametrize('change', ['released', 'running', 'game', 'not-exclusive', 'no-root-exit', 'owner'])
def test_ordinary_jobs_live_runs_and_replay_cannot_use_policy(case, change):
    record, evidence, _ = case
    if change in ('released','running'): record['state'] = change
    if change == 'game': record['request']['phase'] = 'game'
    if change == 'not-exclusive': record['request']['performance'] = False
    if change == 'no-root-exit': record['exited'] = []
    if change == 'owner': evidence['administrator'] = 'worker'
    with pytest.raises(wire.CapacityError):recover(case)


@pytest.mark.parametrize('pin', [(10,100),(12,110),(11,90),(20,200),(21,201)])
def test_any_live_retained_controller_or_guard_refuses(case,pin):
    record,evidence,rows=case
    with pytest.raises(wire.CapacityError,match='live controller'):
        abandon.recover(record,evidence,principal=(31,300),boot='boot',epoch=18,
                        scan=lambda:rows,missing=lambda observed:observed!=pin)


@pytest.mark.parametrize('name', ['clang','clang++','dotnet','xcodebuild','UnrealEditor-Cmd','Blender','ShaderCompileWorker'])
def test_foreign_native_workload_refuses_even_if_older(case,name):
    case[2][45]=dict(pid=45,started=2,parent=1,executable='/tools/'+name)
    with pytest.raises(wire.CapacityError,match='compiler/build/render'):recover(case)


def test_reparented_unknown_python_refuses(case):
    case[2][45]=dict(pid=45,started=120,parent=1,executable='/usr/bin/python')
    with pytest.raises(wire.CapacityError,match='Unclassified'):recover(case)


def test_indexer_is_narrow_and_cannot_exempt_retained_identity(case):
    case[2][45]=dict(pid=45,started=120,parent=1,executable=abandon.INDEXER)
    assert recover(case)['kind']=='administrative-interruption'
    case[0]['roster'].append([45,120])
    with pytest.raises(wire.CapacityError):recover(case)


def test_independently_verified_service_exemption_is_exact(case):
    record,evidence,rows=case
    rows[45]=dict(pid=45,started=120,parent=1,executable='/usr/bin/python')
    evidence['services']=[dict(pid=45,started=120,label='viewer',plist_sha256='reviewed')]
    assert recover(case,service=lambda item:(45,120))['service_exemptions']==evidence['services']
    with pytest.raises(wire.CapacityError):recover(case,service=lambda item:(45,121))


def test_new_unknown_in_second_census_refuses(case):
    record,evidence,rows=case
    count=0
    def scan():
        nonlocal count
        count+=1
        if count==2:rows[45]=dict(pid=45,started=120,parent=1,executable='/usr/bin/python')
        return copy.deepcopy(rows)
    with pytest.raises(wire.CapacityError,match='Unclassified'):
        abandon.recover(record,evidence,principal=(31,300),boot='boot',epoch=18,scan=scan,missing=lambda pin:True)


def test_report_changed_during_scan_refuses(case):
    record,evidence,rows=case
    def scan():
        Path(record['guards']['tree_guard']['report']).write_text('{"state":"new"}')
        return rows
    with pytest.raises(wire.CapacityError,match='reports changed'):
        abandon.recover(record,evidence,principal=(31,300),boot='boot',epoch=18,scan=scan,missing=lambda pin:True)


@pytest.mark.parametrize('number,expected',[(errno.ESRCH,True),(errno.ENOENT,True),(errno.EPERM,None),(errno.EIO,None)])
def test_kernel_errors_never_become_silent_absence(monkeypatch,number,expected):
    def probe(pid):raise OSError(number,'query failed')
    monkeypatch.setattr(wire,'process_start',probe)
    if expected is None:
        with pytest.raises(wire.CapacityError):abandon.absent((10,100))
    else:assert abandon.absent((10,100)) is expected


def test_pid_reuse_is_not_the_old_identity(monkeypatch):
    monkeypatch.setattr(wire,'process_start',lambda pid:101)
    assert abandon.absent((10,100))
