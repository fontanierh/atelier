"""Bound the Mac stream's physical footprint, including compressed/GPU memory.

Runs outside Unreal so a stalled render/game thread cannot defeat the limit.
Never signals a reused PID: each sample must match its original process start.
"""
import argparse,ctypes,json,os,signal,time
from pathlib import Path

class Usage(ctypes.Structure):
    _fields_=[('uuid',ctypes.c_ubyte*16)]+[(n,ctypes.c_uint64) for n in (
        'user','system','idle_wakeups','interrupt_wakeups','pageins','wired','resident','footprint',
        'started','exited','child_user','child_system','child_idle','child_interrupt','child_pageins',
        'child_elapsed','read_bytes','written_bytes')]

LIB=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
LIB.proc_pid_rusage.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
LIB.proc_pid_rusage.restype=ctypes.c_int

def usage(pid):
    value=Usage()
    if LIB.proc_pid_rusage(pid,2,ctypes.byref(value)):
        raise ProcessLookupError(ctypes.get_errno(), 'Cannot sample process',pid)
    return value

def _guard(pid,limit_bytes,report,interval=1.,duration=None,expected_start=None):
    try:first=usage(pid)
    except ProcessLookupError:return
    if expected_start is not None and first.started!=expected_start:return
    start=time.monotonic();peak=0
    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True)
    def save(data):
        temp=report.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(report)
    while True:
        try:current=usage(pid)
        except ProcessLookupError:return
        if current.started!=first.started or current.exited:return
        elapsed=time.monotonic()-start;peak=max(peak,current.footprint)
        data=dict(pid=pid,process_start=first.started,time=time.time(),elapsed_seconds=elapsed,
                  footprint_bytes=current.footprint,resident_bytes=current.resident,peak_bytes=peak,
                  cpu_ticks=current.user+current.system,limit_bytes=limit_bytes,state='running')
        if current.footprint>limit_bytes:
            # A stalled GPU allocator may ignore SIGTERM. Stop this identified
            # game immediately instead of allowing it to exhaust the shared Mac.
            if usage(pid).started==first.started:os.kill(pid,signal.SIGKILL)
            data['state']='memory_limit';save(data);return
        if duration is not None and elapsed>=duration:
            if usage(pid).started==first.started:os.kill(pid,signal.SIGKILL)
            data['state']='test_duration';save(data);return
        save(data)
        history=report.with_suffix('.jsonl')
        if history.exists() and history.stat().st_size>8*1024*1024:
            history.replace(report.with_suffix('.previous.jsonl'))
        with history.open('a') as f:f.write(json.dumps(data)+'\n')
        time.sleep(interval)

def guard(pid,limit_bytes,report,interval=1.,duration=None,expected_start=None):
    try:identity=usage(pid).started
    except ProcessLookupError:return
    if expected_start is not None and identity!=expected_start:return
    try:
        _guard(pid,limit_bytes,report,interval,duration,identity)
    except Exception:
        # Losing telemetry must not leave an unprotected game running.
        try:
            if usage(pid).started==identity:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True)
    p.add_argument('--limit-gib',type=float,default=10);p.add_argument('--report',required=True)
    p.add_argument('--duration',type=float);p.add_argument('--expected-start',type=int)
    a=p.parse_args();guard(a.pid,int(a.limit_gib*1024**3),a.report,duration=a.duration,expected_start=a.expected_start)
