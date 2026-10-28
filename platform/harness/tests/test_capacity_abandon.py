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


@pytest.fixture
def completed_case(case):
    record, evidence, rows = case
    record['request'].update(phase='job', performance=False)
    record.update(first_ready=1., limit_bytes=1024)
    terminal = dict(owner=10, owner_started=100, controller=[11,90], state='child_exited',
                    cleanup_complete=True, processes=[], footprint_bytes=0, peak_bytes=512,
                    limit_bytes=1024, time=2.)
    Path(record['guards']['tree_guard']['report']).write_text(json.dumps(terminal))
    evidence['guards'] = copy.deepcopy(record['guards'])
    evidence['report_sha256'] = {k:hashlib.sha256(Path(g['report']).read_bytes()).hexdigest()
                               for k,g in record['guards'].items()}
    return case


def test_completed_job_is_explicit_and_keeps_missing_history(completed_case):
    with pytest.raises(wire.CapacityError):recover(completed_case)
    witness = recover(completed_case, completed=True)
    assert witness['kind'] == 'administrative-completed-job'
    assert witness['output_certified'] is False and witness['missing_historical_exits'] == 1
    assert completed_case[0]['exited'] == [[10,100]] and completed_case[0]['ancestry_unknown']


@pytest.mark.parametrize('key,value', [('owner',11),('owner_started',101),('controller',[11,91]),
    ('state','memory_limit'),('cleanup_complete',False),('processes',[{}]),('footprint_bytes',1),
    ('limit_bytes',2048),('peak_bytes',1025),('time',float('nan')),('time',0),('termination_reason','stop')])
def test_completed_job_rejects_invalid_terminal(completed_case,key,value):
    record,evidence,_ = completed_case
    p=Path(record['guards']['tree_guard']['report']);receipt=json.loads(p.read_text());receipt[key]=value
    p.write_text(json.dumps(receipt));evidence['report_sha256']['tree_guard']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(wire.CapacityError):recover(completed_case,completed=True)


@pytest.mark.parametrize('change', ['monitor','hash','root-exit','exclusive','game','owner'])
def test_completed_job_fences_and_scope(completed_case,change):
    record,evidence,_=completed_case
    if change=='monitor':evidence['guards']['tree_guard']['start']+=1
    if change=='hash':evidence['report_sha256']['tree_guard']='0'*64
    if change=='root-exit':record['exited']=[]
    if change=='exclusive':record['request']['performance']=True
    if change=='game':record['request']['phase']='game'
    if change=='owner':evidence['administrator']='worker'
    with pytest.raises(wire.CapacityError):recover(completed_case,completed=True)


def test_completed_job_retains_pre_root_exclusions(completed_case):
    completed_case[2][45]=dict(pid=45,started=20,parent=1,executable='',uid=501,
                              executable_unavailable_before_root=True)
    witness=recover(completed_case,completed=True)
    assert len(witness['pre_root_path_exemptions'])==2
    completed_case[2][45]['started']=120
    with pytest.raises(wire.CapacityError):recover(completed_case,completed=True)


@pytest.mark.parametrize('change', [None, 'parent', 'uid', 'birth', 'not-older'])
def test_kernel_pre_root_path_exemption_requires_stable_full_binding(monkeypatch,change):
    import ctypes
    import struct
    from types import SimpleNamespace
    from atelier.harness.safety import memory_guard
    calls={'info':0,'usage':0}
    class Call:
        def __init__(self,fn):self.fn=fn
        def __call__(self,*args):return self.fn(*args)
    def listing(kind,uid,buffer,size):buffer[0]=7;return ctypes.sizeof(ctypes.c_int)
    def info(pid,kind,arg,buffer,size):
        calls['info']+=1
        parent=2 if change=='parent' and calls['info']>1 else 1
        uid=502 if change=='uid' and calls['info']>1 else 501
        raw=struct.pack('6I',0,0,0,7,parent,uid)
        ctypes.memmove(buffer,raw,len(raw));return 136
    def sample(pid):
        calls['usage']+=1
        started=100 if change=='not-older' else 51 if change=='birth' and calls['usage']>2 else 50
        return SimpleNamespace(started=started,exited=False)
    lib=SimpleNamespace(proc_listpids=Call(listing),proc_pidinfo=Call(info),proc_pidpath=Call(lambda *args:0))
    monkeypatch.setattr(abandon.sys,'platform','darwin')
    monkeypatch.setattr(abandon.ctypes,'CDLL',lambda *args,**kwargs:lib)
    monkeypatch.setattr(abandon.os,'getuid',lambda:501)
    monkeypatch.setattr(abandon.os,'getpid',lambda:7)
    monkeypatch.setattr(memory_guard,'usage',sample)
    with pytest.raises(wire.CapacityError):abandon.census()  # old policy stays strict
    calls.update(info=0,usage=0)
    if change is None:
        rows=abandon.census(before_root=100)
        assert rows[7]['executable_unavailable_before_root'] and rows[7]['uid']==501
    else:
        with pytest.raises(wire.CapacityError):abandon.census(before_root=100)


@pytest.mark.parametrize('bad', [None,'parent','path','owner','writable','sip','signature','timeout'])
def test_completed_xpc_exclusion_is_exact_and_verified(monkeypatch,bad):
    from types import SimpleNamespace
    row=dict(parent=1,executable=abandon.COMPLETED_XPC)
    if bad=='parent':row['parent']=2
    if bad=='path':row['executable']='/usr/bin/true'
    info=SimpleNamespace(st_uid=501 if bad=='owner' else 0,
                         st_mode=0o777 if bad=='writable' else 0o755,
                         st_flags=0 if bad=='sip' else 0x80000)
    monkeypatch.setattr(abandon,'Path',lambda path:SimpleNamespace(stat=lambda:info))
    def verify(command,**kwargs):
        assert command==['/usr/bin/codesign','--verify','-R=anchor apple',abandon.COMPLETED_XPC]
        if bad=='timeout':raise abandon.subprocess.TimeoutExpired(command,.5)
        return SimpleNamespace(returncode=1 if bad=='signature' else 0)
    monkeypatch.setattr(abandon.subprocess,'run',verify)
    assert abandon.completed_system_service(row) is (bad is None)


def test_xpc_exclusion_does_not_change_interrupted_compile_policy(completed_case,monkeypatch):
    record,evidence,rows=completed_case
    rows[45]=dict(pid=45,started=120,parent=1,executable=abandon.COMPLETED_XPC)
    monkeypatch.setattr(abandon,'completed_system_service',lambda row:row['pid']==45)
    with pytest.raises(wire.CapacityError):abandon.validate_snapshot(rows,record,set())
    witness=recover(completed_case,completed=True)
    assert len(witness['system_service_exemptions'])==2


@pytest.fixture
def unwitnessed_case(case):
    record, evidence, _ = case
    record['exited'] = []
    evidence.update(guards=copy.deepcopy(record['guards']), acknowledge_missing_root_exit=True,
        report_sha256={k:hashlib.sha256(Path(g['report']).read_bytes()).hexdigest()
                       for k,g in record['guards'].items()})
    return case


def test_missing_root_exit_requires_separate_acknowledged_recovery(unwitnessed_case):
    before = copy.deepcopy(unwitnessed_case[0])
    with pytest.raises(wire.CapacityError):recover(unwitnessed_case)
    witness = recover(unwitnessed_case, unwitnessed=True)
    assert witness['kind'] == 'administrative-unwitnessed-compile'
    assert witness['root_exit_observed'] is False
    assert witness['output_certified'] is False and witness['missing_historical_exits'] == 2
    assert unwitnessed_case[0] == before
    assert witness['original_report_sha256'] == unwitnessed_case[1]['report_sha256']


@pytest.mark.parametrize('change', ['ack', 'root-exit', 'monitor', 'hash', 'job', 'nonexclusive',
                                   'owner', 'controller', 'combined', 'epoch', 'boot', 'nonce'])
def test_unwitnessed_recovery_keeps_scope_and_fences(unwitnessed_case, change):
    record, evidence, _ = unwitnessed_case
    options = dict(unwitnessed=True)
    if change == 'ack':evidence['acknowledge_missing_root_exit'] = False
    if change == 'root-exit':record['exited'] = [record['child']]
    if change == 'monitor':evidence['guards']['tree_guard']['start'] += 1
    if change == 'hash':evidence['report_sha256']['tree_guard'] = '0'*64
    if change == 'job':record['request']['phase'] = 'job'
    if change == 'nonexclusive':record['request']['performance'] = False
    if change == 'owner':evidence['administrator'] = 'worker'
    if change == 'controller':record['principal'] = [31,300]
    if change == 'combined':options['completed'] = True
    if change == 'epoch':evidence['epoch'] += 1
    if change == 'boot':evidence['boot_id'] = 'new'
    if change == 'nonce':evidence['nonce'] = 'new'
    with pytest.raises(wire.CapacityError):recover(unwitnessed_case, **options)


@pytest.mark.parametrize('pin', [(10,100),(12,110),(11,90),(20,200),(21,201)])
def test_unwitnessed_live_identity_refuses_even_root_omitted_from_roster(unwitnessed_case,pin):
    record,evidence,rows = unwitnessed_case
    record['roster'] = [[12,110]]
    with pytest.raises(wire.CapacityError,match='live controller'):
        abandon.recover(record,evidence,principal=(31,300),boot='boot',epoch=18,
            scan=lambda:rows,missing=lambda observed:observed!=pin,unwitnessed=True)


@pytest.mark.parametrize('fault', ['new-orphan', 'compiler', 'query', 'root-reappears', 'report-change'])
def test_unwitnessed_second_observation_must_stay_quiescent(unwitnessed_case, fault):
    record,evidence,rows = unwitnessed_case
    calls = 0
    def scan():
        nonlocal calls
        calls += 1
        if calls == 2:
            if fault == 'new-orphan':rows[45]=dict(pid=45,started=120,parent=1,executable='/usr/bin/python')
            if fault == 'compiler':rows[45]=dict(pid=45,started=2,parent=1,executable='/tools/cargo')
            if fault == 'query':raise wire.CapacityError('kernel observation failed')
            if fault == 'report-change':Path(record['guards']['tree_guard']['report']).write_text('{}')
        return copy.deepcopy(rows)
    def missing(pin):
        return not (fault == 'root-reappears' and calls == 2 and pin == (10,100))
    with pytest.raises(wire.CapacityError):
        abandon.recover(record,evidence,principal=(31,300),boot='boot',epoch=18,
            scan=scan,missing=missing,unwitnessed=True)
    assert calls == 2


def test_unwitnessed_service_binding_is_rechecked_after_censuses(unwitnessed_case):
    record,evidence,rows = unwitnessed_case
    rows[45]=dict(pid=45,started=120,parent=1,executable='/usr/bin/python')
    evidence['services']=[dict(pid=45,started=120,label='viewer',plist_sha256='reviewed')]
    calls = 0
    def service(item):
        nonlocal calls
        calls += 1
        return (45,120 if calls == 1 else 121)
    with pytest.raises(wire.CapacityError,match='service identities changed'):
        recover(unwitnessed_case,unwitnessed=True,service=service)
    assert calls == 2


@pytest.mark.parametrize('bad', [None,'parent','path','owner','writable','sip','signature','timeout','stat-error'])
def test_unwitnessed_indexer_is_exact_and_cryptographically_verified(monkeypatch,bad):
    from types import SimpleNamespace
    row=dict(parent=1,executable=abandon.SYSTEM_INDEXER)
    if bad=='parent':row['parent']=2
    if bad=='path':row['executable']='/usr/bin/true'
    info=SimpleNamespace(st_uid=501 if bad=='owner' else 0,
                         st_mode=0o777 if bad=='writable' else 0o755,
                         st_flags=0 if bad=='sip' else 0x80000)
    def stat():
        if bad=='stat-error':raise OSError('unavailable')
        return info
    monkeypatch.setattr(abandon,'Path',lambda path:SimpleNamespace(stat=stat))
    def verify(command,**kwargs):
        assert command==['/usr/bin/codesign','--verify','-R=anchor apple',abandon.SYSTEM_INDEXER]
        if bad=='timeout':raise abandon.subprocess.TimeoutExpired(command,.5)
        return SimpleNamespace(returncode=1 if bad=='signature' else 0)
    monkeypatch.setattr(abandon.subprocess,'run',verify)
    assert abandon.unwitnessed_system_indexer(row) is (bad is None)


def test_indexer_exception_is_only_explicit_unwitnessed_recovery(unwitnessed_case,monkeypatch):
    record,evidence,rows=unwitnessed_case
    rows[45]=dict(pid=45,started=120,parent=1,executable=abandon.SYSTEM_INDEXER)
    monkeypatch.setattr(abandon,'unwitnessed_system_indexer',lambda row:row['pid']==45)
    with pytest.raises(wire.CapacityError):abandon.validate_snapshot(rows,record,set())
    with pytest.raises(wire.CapacityError):abandon.validate_snapshot(rows,record,set(),completed=True)
    witness=recover(unwitnessed_case,unwitnessed=True)
    assert len(witness['system_indexer_exemptions'])==2
    assert witness['root_exit_observed'] is False and witness['output_certified'] is False
    assert all(row['pid']==45 for row in witness['system_indexer_exemptions'])
    record['roster'].append([45,120])
    with pytest.raises(wire.CapacityError):recover(unwitnessed_case,unwitnessed=True)


def test_indexer_signature_failure_in_second_census_refuses(unwitnessed_case,monkeypatch):
    unwitnessed_case[2][45]=dict(pid=45,started=120,parent=1,executable=abandon.SYSTEM_INDEXER)
    calls=0
    def verified(row):
        nonlocal calls
        if row['pid']!=45:return False
        calls+=1
        return calls==1
    monkeypatch.setattr(abandon,'unwitnessed_system_indexer',verified)
    with pytest.raises(wire.CapacityError,match='Unclassified'):
        recover(unwitnessed_case,unwitnessed=True)
    assert calls==2
