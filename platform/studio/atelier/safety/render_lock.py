"""One big render job at a time across every worktree on this machine, and optionally one small job beside it.

Each harness used to run its own preflight scan, which cannot stop two of them starting together:
both scan, both see nothing, both launch. `render_lock()` takes an exclusive advisory lock on a
single file outside any checkout, so the second caller is refused rather than admitted, and then
scans for render processes that no lock-aware harness owns (the phone stream's game, a hand-started
editor, a Blender render). The lock file carries the holder's pid, start time, checkout, purpose and
kind so a refusal can name who is running; a holder that has exited, or whose pid has been recycled,
does not block anything. The record is emptied when the slot is released.

    with render_lock('benchmark spawn'):
        ...launch exactly one Unreal child...

Slots. `render.lock` is the big slot, for any job. It is the only one unless `render-slots.json` next to it says
`{"slots": 2}`; `ATELIER_RENDER_SLOTS` overrides the file, a missing file or any other value means one slot, and
both are read at every attempt, so the switch works while jobs run. With two slots, `render.small.lock` is a second
slot for a job that says it may use it (`small_gib=`, its expected peak in GiB). It is admitted when:

* its expected peak is at most 3 GiB and it is neither a game nor a compile (`kind=`);
* the small lock is free;
* the big slot's holder is not a compile and does not run in this checkout (two Unreals on one project);
* at least 10 GiB of memory is available.

Otherwise it waits for the big slot, exactly as with one slot. `guarded.run` lowers a small job's memory ceiling from
10 to 4 GiB, so an overrun kills that job and not the machine. A big job does not wait for a small one: they overlap.
A compile takes the big slot and then the small one, waiting up to ten minutes for a small job to finish, so nothing
runs beside it; it records itself in the big lock first, so a small job never starts once it has begun.

Available memory is vm_stat's free, speculative, inactive and purgeable pages times the page size: what the system can
hand to a new process without swapping out pages in active use. It reads lower than the kernel's own figure (on a 36 GB
M3 Pro, 15 GiB where `memory_pressure` said 60% free, 22 GiB), so it errs towards refusing. When vm_stat cannot be
read the small slot is refused.

The foreign-process scan leaves out the other slot's live holder and all its descendants (found through their parent
pids), so the two slots do not refuse each other, and still refuses any render process nobody holds. A session on older
code knows only the big lock: it sees a small job's Unreal as foreign and refuses, which is safe.

`ATELIER_RENDER_LOCK` moves the lock files and the switch, and `ATELIER_RENDER_LOCK_SCAN=0` skips the foreign
process scan. Both exist for the CPU tests; a real measurement uses the defaults.
"""
import fcntl, json, os, re, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path

from ..paths import REPO
from .memory_guard import usage

DEFAULT_LOCK = Path.home()/'.cache/atelier/render.lock'
RENDER_NAMES = ('UnrealEditor', 'UnrealEditor-Cmd', 'ShaderCompileWorker', 'blender', 'Blender')
GiB = 1024**3
SMALL_PEAK_GIB = 3.     # a job expected to peak above this never uses the small slot
SMALL_LIMIT_GIB = 4.    # the memory guard's ceiling for a job in the small slot
SMALL_FREE_GIB = 10.    # memory that must be available when a small job starts
COMPILE_WAIT = 600.     # seconds a compile, holding the big slot, waits for a small job to finish
KINDS = ('job', 'game', 'compile')


def lock_path():
    return Path(os.environ.get('ATELIER_RENDER_LOCK') or DEFAULT_LOCK)


def small_lock_path(big=None):
    """The small slot's lock file, next to the big one: render.small.lock."""
    big = big or lock_path()
    return big.with_name(f'{big.stem}.small{big.suffix}')


def slots_path():
    """The switch: {"slots": 2} turns the small slot on."""
    return lock_path().with_name('render-slots.json')


def slot_count():
    """2 when ATELIER_RENDER_SLOTS, or else render-slots.json, says 2; otherwise 1 (today's single slot)."""
    value = os.environ.get('ATELIER_RENDER_SLOTS', '').strip()
    if not value:
        try:
            value = json.loads(slots_path().read_text()).get('slots')
        except (OSError, ValueError, AttributeError):
            return 1
    try:
        return 2 if float(value) == 2 else 1
    except (TypeError, ValueError):
        return 1


def parse_vm_stat(text):
    """Available bytes from `vm_stat` output: free, speculative, inactive and purgeable pages times the page size."""
    size = re.search(r'page size of (\d+) bytes', text)
    counts = {}
    for line in text.splitlines():
        name, _, value = line.partition(':')
        value = value.strip().rstrip('.')
        if value.isdigit():
            counts[name.strip().strip('"')] = int(value)
    wanted = ('Pages free', 'Pages speculative', 'Pages inactive', 'Pages purgeable')
    if not size or any(key not in counts for key in wanted):
        return None
    return int(size.group(1))*sum(counts[key] for key in wanted)


def available_bytes():
    """Memory available to a new job, or None when it cannot be measured."""
    try:
        text = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_vm_stat(text)


def process_table():
    """(pid, parent pid, command) for every process."""
    listing = subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout
    table = []
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table.append((int(fields[0]), int(fields[1]), fields[2].strip()))
    return table


def family(pid, table=None):
    """`pid` and all its descendants."""
    children = {}
    for child, parent, _ in (process_table() if table is None else table):
        children.setdefault(parent, []).append(child)
    found, todo = set(), [pid]
    while todo:
        current = todo.pop()
        if current not in found:
            found.add(current)
            todo.extend(children.get(current, ()))
    return found


def render_processes(ignore=(), table=None):
    """Live render processes by name, excluding pids in `ignore` and this process."""
    skip = set(ignore) | {os.getpid()}
    return [{'pid': pid, 'command': command} for pid, _, command in (process_table() if table is None else table)
            if pid not in skip and Path(command).name in RENDER_NAMES]


def holder(handle):
    """Whoever last wrote the lock file, if that process is still the one it claims to be."""
    try:
        handle.seek(0)
        record = json.loads(handle.read() or '{}')
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    pid, started = record.get('pid'), record.get('started')
    if not isinstance(pid, int) or pid <= 1:
        return None
    try:
        if started is not None and usage(pid).started != started:
            return None
    except ProcessLookupError:
        return None
    return record


def read_holder(path):
    """The live holder recorded in a lock file, without touching its lock."""
    try:
        with open(path) as handle:
            return holder(handle)
    except OSError:
        return None


def is_compile(record):
    """A holder that compiles; older code records only a purpose."""
    kind = record.get('kind')
    return kind == 'compile' if kind else 'compile' in str(record.get('purpose', '')).lower()


def checkout_root(path):
    """The checkout a directory belongs to: the nearest folder holding `.git` (a worktree's is a file)."""
    path = Path(path)
    for folder in (path, *path.parents):
        if (folder/'.git').exists():
            return folder
    return path


def same_checkout(record):
    """Whether a holder runs in this checkout; older code records only its working directory."""
    if record.get('repo'):
        return Path(record['repo']) == REPO
    return bool(record.get('checkout')) and checkout_root(record['checkout']) == REPO


def describe(record):
    return f" (pid {record['pid']}, {record.get('purpose')})" if record else ''


class RenderBusy(RuntimeError):
    """Another render job owns the machine; this one must not start."""


def _take(handle):
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release(handle):
    try:
        handle.seek(0)
        handle.truncate()
    except OSError:
        pass
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _write(handle, record):
    handle.seek(0)
    handle.truncate()
    json.dump(record, handle)
    handle.flush()


def _admit_small(small, big, gib):
    """(locked handle on the small slot, why) when this job may run there, else (None, why not)."""
    if slot_count() != 2:
        return None, 'one render slot configured'
    handle = small.open('a+')
    if not _take(handle):
        other = holder(handle)
        handle.close()
        return None, f'the small slot is busy{describe(other)}'
    # The small lock is held before the big holder is read, and a compile records itself before taking the small
    # lock, so either this job sees the compile or the compile finds the small lock held and waits.
    other = read_holder(big)
    free = None
    if other and is_compile(other):
        why = f'a compile holds the big slot{describe(other)}'
    elif other and same_checkout(other):
        why = f'the big slot runs a job in this checkout{describe(other)}'
    else:
        free = available_bytes()
        if free is None:
            why = 'available memory could not be measured'
        elif free < SMALL_FREE_GIB*GiB:
            why = f'{free/GiB:.1f} GiB available, the small slot needs {SMALL_FREE_GIB:g}'
        else:
            return handle, f'expected {gib:.1f} GiB, {free/GiB:.1f} GiB available'
    _release(handle)
    handle.close()
    return None, why


@contextmanager
def render_lock(purpose, wait=0., ignore=(), scan=None, small_gib=None, kind='job', on_slot=None):
    """Own a render slot for the duration of the block; yields the lock file taken.

    Without `small_gib` this is the machine's single big slot, as it always was. `small_gib`, the job's expected peak,
    lets it use the small slot when two are configured and it is admitted. `kind` ('job', 'game' or 'compile') is
    recorded in the lock file; a compile also takes the small slot. `on_slot(slot, why)` hears which slot was taken
    ('big' or 'small') and why, once the scan has passed."""
    kind = kind or 'job'
    if kind not in KINDS:
        raise ValueError(f'kind must be one of {KINDS}, not {kind!r}')
    big = lock_path()
    small = small_lock_path(big)
    big.parent.mkdir(parents=True, exist_ok=True)
    why = ''
    if small_gib is not None:
        if kind != 'job':
            why = f'a {kind} always uses the big slot'
        elif not 0 <= small_gib <= SMALL_PEAK_GIB:
            why = f'expected {small_gib:.1f} GiB, over the small slot\'s {SMALL_PEAK_GIB:g}'
    eligible = small_gib is not None and not why
    opened, owned = [], []
    handle = big.open('a+')
    opened.append(handle)
    deadline = time.monotonic()+max(wait, 0.)
    try:
        while True:
            if eligible:
                taken, why = _admit_small(small, big, small_gib)
                if taken:
                    opened.append(taken)
                    owned.append(taken)
                    slot = 'small'
                    break
            if _take(handle):
                owned.append(handle)
                slot = 'big'
                break
            if time.monotonic() >= deadline:
                other = holder(handle)
                detail = f" held by pid {other['pid']} ({other.get('purpose')})" if other else ''
                aside = f' (not the small slot: {why})' if eligible else ''
                raise RenderBusy(f'another render job is running{detail}; '
                                 f'stop it (or the phone stream) before starting this one{aside}')
            time.sleep(.25)
        record = dict(pid=os.getpid(), started=usage(os.getpid()).started, purpose=str(purpose), kind=kind,
                      slot=slot, checkout=str(Path.cwd()), repo=str(REPO), time=time.time())
        if slot == 'small':
            record['expected_gib'] = round(float(small_gib), 2)
        _write(owned[0], record)
        if kind == 'compile':
            # Nothing runs beside a compile. Holding the big slot, recorded as a compile, stops new small jobs;
            # one already running is waited for.
            why = 'a compile, which also holds the small slot'
            extra = small.open('a+')
            opened.append(extra)
            limit = max(deadline, time.monotonic()+COMPILE_WAIT)
            told = False
            while not _take(extra):
                other = holder(extra)
                if time.monotonic() >= limit:
                    raise RenderBusy(f'a small render job is still running{describe(other)}; '
                                     f'a compile does not start beside it')
                if not told:
                    print(f'waiting for the small render job{describe(other)} to finish before compiling',
                          file=sys.stderr, flush=True)
                    told = True
                time.sleep(.25)
            owned.append(extra)
            _write(extra, record)
        if scan is None:
            scan = os.environ.get('ATELIER_RENDER_LOCK_SCAN', '1') != '0'
        if scan:
            # One listing for both, so a shader worker the other slot's Unreal starts meanwhile is not taken for foreign.
            table = process_table()
            skip = set(ignore)
            if kind != 'compile':
                other = read_holder(big if slot == 'small' else small)
                if other:
                    skip |= family(other['pid'], table)
            foreign = render_processes(ignore=skip, table=table)
            if foreign:
                names = ', '.join(f"{p['pid']} {Path(p['command']).name}" for p in foreign)
                raise RenderBusy(f'render processes are already running and no harness owns them: {names}. '
                                 f'Stop them (the phone stream: `atelier stream stop`) first')
        if on_slot is not None:
            on_slot(slot, why)
        yield small if slot == 'small' else big
    finally:
        for taken in reversed(owned):
            _release(taken)
        for opened_handle in opened:
            opened_handle.close()
