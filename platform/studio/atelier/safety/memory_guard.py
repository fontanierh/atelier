"""Bound one owned process's physical footprint (a game, a build, a stream), including compressed/GPU memory.

Runs outside Unreal so a stalled render/game thread cannot defeat the limit.
Never signals a reused PID: each sample must match its original process start.
While an owned Unreal runs it also records the game's descendants, pinned to their start, in
`<report>.helpers.json`, so the SDK helpers it leaves behind can be reaped once it exits (`guard.reap_helpers`).
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

PROC_PPID_ONLY=6
LIB.proc_listpids.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_int]
LIB.proc_name.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32]

def children(pid):
    """The live children of pid; one born during the call is caught on the next tick."""
    size=ctypes.sizeof(ctypes.c_int);count=LIB.proc_listpids(PROC_PPID_ONLY,pid,None,0)
    if count<=0:return []
    buf=(ctypes.c_int*(count//size+64))();count=LIB.proc_listpids(PROC_PPID_ONLY,pid,buf,ctypes.sizeof(buf))
    return [p for p in buf[:max(count,0)//size] if p>0]

def name(pid):
    """The executable's name ('UnrealEditor', 'dotnet'), or '' once it is gone."""
    buf=ctypes.create_string_buffer(256)
    return buf.value.decode(errors='replace') if LIB.proc_name(pid,buf,256)>0 else ''

def helpers_path(report):return Path(report).with_suffix('.helpers.json')

def _started(pid):
    try:return usage(pid).started
    except ProcessLookupError:return None

def owned_children(parent,parent_start):
    """(pid, start) of each child of this exact parent. A parent is the same process before and after its listing,
    and a child has the same start on both sides of a second listing, so a reused pid (the parent's or a child's)
    never brings in another process's children."""
    if _started(parent)!=parent_start:return []
    first=children(parent);starts={c:_started(c) for c in first}
    again=set(children(parent))
    if _started(parent)!=parent_start:return []
    return [(c,s) for c,s in starts.items() if s is not None and c in again and _started(c)==s]

def record_helpers(pid,started,path,seen):
    """Every descendant of the owned Unreal, with its start, parent and depth. Once the game exits its helpers are
    reparented to launchd, so this record is the only proof they were ours."""
    if not name(pid).startswith('UnrealEditor'):return
    queue=[(pid,started,0)];new=False
    while queue:
        parent,parent_start,depth=queue.pop()
        for child,child_start in owned_children(parent,parent_start):
            key=f'{child}:{child_start}'
            if key not in seen:
                seen[key]=dict(pid=child,started=child_start,name=name(child),parent=parent,parent_started=parent_start,
                               depth=depth+1);new=True
            queue.append((child,child_start,depth+1))
    if new:
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(dict(game=pid,game_started=started,
            helpers=list(seen.values())),indent=2)+'\n');temp.replace(path)

def usage(pid):
    value=Usage()
    if LIB.proc_pid_rusage(pid,2,ctypes.byref(value)):
        raise ProcessLookupError(ctypes.get_errno(), 'Cannot sample process',pid)
    return value

def _guard(pid,limit_bytes,report,interval=1.,duration=None,expected_start=None):
    try:first=usage(pid)
    except ProcessLookupError:return
    if expected_start is not None and first.started!=expected_start:return
    start=time.monotonic();peak=0;seen={};helper_error=None
    report=Path(report);report.parent.mkdir(parents=True,exist_ok=True);helpers=helpers_path(report)
    def save(data):
        temp=report.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(report)
    while True:
        try:current=usage(pid)
        except ProcessLookupError:return
        if current.started!=first.started or current.exited:return
        # A failed helper record must never cost the game its guard (any exception here kills it).
        try:record_helpers(pid,first.started,helpers,seen)
        except Exception as e:helper_error=repr(e)
        elapsed=time.monotonic()-start;peak=max(peak,current.footprint)
        data=dict(pid=pid,process_start=first.started,time=time.time(),elapsed_seconds=elapsed,
                  footprint_bytes=current.footprint,resident_bytes=current.resident,peak_bytes=peak,
                  cpu_ticks=current.user+current.system,limit_bytes=limit_bytes,state='running')
        if helper_error:data['helper_error']=helper_error
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
