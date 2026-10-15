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

An optional `fitting_checkout` in that same configuration reserves `render.fitting.lock` for background Blender
model fitting in one absolute checkout, with the same 3 GiB estimate, 4 GiB guard and 10 GiB available-memory rules.
`fitting_gib` requests this lane only, with no fallback. `fitting_paused: true` refuses new fitting jobs. Before enabling
it, every active client must adopt protocol 2: compiles acquire all three mutexes, and fitting admission refuses live
holders from older guards. Keep `slots` at 2 so clients can be upgraded before the reserved lane is enabled.

`ATELIER_RENDER_LOCK` moves the lock files and the switch, and `ATELIER_RENDER_LOCK_SCAN=0` skips the foreign
process scan. Both exist for the CPU tests; a real measurement uses the defaults.
"""
import fcntl, json, math, os, re, selectors, subprocess, sys, time
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
PROTOCOL = 2           # includes the reserved fitting mutex in compile exclusion


def lock_path():
    return Path(os.environ.get('ATELIER_RENDER_LOCK') or DEFAULT_LOCK)


def small_lock_path(big=None):
    """The small slot's lock file, next to the big one: render.small.lock."""
    big = big or lock_path()
    return big.with_name(f'{big.stem}.small{big.suffix}')


def fitting_lock_path(big=None):
    """A reserved Blender fitting lane; never used by ordinary builds or games."""
    big = big or lock_path()
    return big.with_name(f'{big.stem}.fitting{big.suffix}')


def lock_paths():
    """All records, including disabled lanes whose current job must still finish."""
    return {'big': lock_path(), 'small': small_lock_path(), 'fitting': fitting_lock_path()}


def slot_config():
    try:
        value = json.loads(slots_path().read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


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


def _bounded_process_listing(timeout):
    """A failed, truncated or oversized observation is never an empty machine."""
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(['/bin/ps', '-axo', 'pid=,ppid=,comm='],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    listing = bytearray()
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not ready.select(remaining):
                    raise OSError('Native process observation timed out')
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                listing.extend(chunk)
                if len(listing) > 1024 * 1024:
                    raise OSError('Native process observation exceeded its bound')
        if process.wait(timeout=max(.001, deadline - time.monotonic())):
            raise OSError('Native process observation failed')
        return listing.decode('utf-8', errors='strict')
    except subprocess.SubprocessError:
        raise OSError('Native process observation failed to complete within its bound') from None
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()  # Only this observer's own bounded ps child.
            try:
                process.wait(timeout=1.)
            except subprocess.SubprocessError:
                raise OSError('Owned process observer did not exit within its reap bound') from None


def process_table(timeout=None):
    """(pid, parent pid, command) for every process."""
    listing = (_bounded_process_listing(timeout) if timeout is not None else
               subprocess.run(['ps', '-axo', 'pid=,ppid=,comm='], capture_output=True, text=True).stdout)
    if timeout is not None and not listing.endswith('\n'):
        raise OSError('Native process observation ended with an incomplete row')
    table = []
    seen = set()
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            pid, parent, command = int(fields[0]), int(fields[1]), fields[2].strip()
            if timeout is not None and (pid in seen or not command or any(ord(c) < 32 for c in command)):
                raise OSError('Native process observation has duplicate or incomplete rows')
            seen.add(pid)
            table.append((pid, parent, command))
        elif timeout is not None:
            raise OSError('Native process observation has malformed rows')
    if timeout is not None and (not table or os.getpid() not in seen):
        raise OSError('Native process observation is empty or incomplete')
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


def native_candidates():
    """Pin every observed native candidate; a failed identity lookup is not absence."""
    from .. import capacity_protocol as wire
    table = process_table(timeout=2.)
    values = []
    for item in render_processes(table=table):
        pin = (item['pid'], wire.process_start(item['pid']))
        if not wire.live(pin) or wire.process_start(pin[0]) != pin[1]:
            raise wire.CapacityError('Native process identity changed during the foreign scan')
        values.append(list(pin))
    if len(values) > wire.MAX_ROSTER:
        raise wire.CapacityError('Native ownership observation exceeds the complete bounded query')
    return values


@contextmanager
def _shared_capacity(admission, on_slot, *, ignore, scan):
    from contextlib import ExitStack
    from .. import capacity_compat
    if ignore or scan is False or os.environ.get('ATELIER_RENDER_LOCK_SCAN') == '0':
        raise ValueError('Full capacity requires exact broker ownership and the normal foreign scan')
    proof = capacity_compat.verify(admission.cutover)
    if proof['activation_id'] != admission.activation_id:
        raise RenderBusy('capacity session belongs to another compatibility activation')
    with ExitStack() as stack:
        handles = {}
        for name, path in lock_paths().items():
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            handle = stack.enter_context(os.fdopen(fd, 'rb'))
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise RenderBusy('a legacy exclusive lane still blocks full capacity') from None
            handles[name] = handle
        capacity_compat.verify(admission.cutover, handles=handles)
        candidates = native_candidates()
        owned = admission.owned(candidates)
        if any(tuple(pin) not in owned for pin in candidates):
            raise RenderBusy('unregistered native processes refuse full capacity')
        if on_slot is not None:
            on_slot('capacity', 'broker resources and named locks decide admission; legacy inodes stay sealed')
        yield lock_path()
        # Closing only our shared descriptors releases them. Never _write/_release these records.


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
    fitting = read_holder(fitting_lock_path(big))
    free = None
    if other and is_compile(other):
        why = f'a compile holds the big slot{describe(other)}'
    elif other and same_checkout(other):
        why = f'the big slot runs a job in this checkout{describe(other)}'
    elif fitting and same_checkout(fitting):
        why = f'the fitting slot runs a job in this checkout{describe(fitting)}'
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


def _admit_fitting(fitting, big, small, gib):
    """Only the configured checkout may use this lane, with no fallback to another slot."""
    config = slot_config()
    checkout = config.get('fitting_checkout')
    if slot_count() != 2 or not isinstance(checkout, str) or not Path(checkout).is_absolute():
        return None, 'the reserved fitting slot is not configured'
    if config.get('fitting_paused'):
        return None, 'the reserved fitting slot is paused'
    if Path(checkout).resolve() != REPO.resolve():
        return None, 'the fitting slot belongs to another checkout'
    handle = fitting.open('a+')
    if not _take(handle):
        other = holder(handle)
        handle.close()
        return None, f'the fitting slot is busy{describe(other)}'
    why = None
    for path in (big, small):
        other = read_holder(path)
        if not other:
            # An older guard does not use our admission mutex and may hold this slot before publishing
            # a valid record. Probe the mutex, without clearing or rewriting any other owner's metadata.
            with path.open('a+') as probe:
                if not _take(probe):
                    why = f'the {path.name} mutex is held without a valid holder record'
                    break
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
            continue
        if is_compile(other):
            why = f'a compile holds a render slot{describe(other)}'
        elif other.get('protocol') != PROTOCOL:
            why = f'a render holder uses an older guard{describe(other)}'
        elif same_checkout(other):
            why = f'another render slot runs in this checkout{describe(other)}'
        if why:
            break
    if why is None:
        free = available_bytes()
        if free is None:
            why = 'available memory could not be measured'
        elif free < SMALL_FREE_GIB*GiB:
            why = f'{free/GiB:.1f} GiB available, the fitting slot needs {SMALL_FREE_GIB:g}'
        else:
            return handle, f'expected {gib:.1f} GiB, {free/GiB:.1f} GiB available'
    _release(handle)
    handle.close()
    return None, why


@contextmanager
def render_lock(purpose, wait=0., ignore=(), scan=None, small_gib=None, kind='job', on_slot=None, fitting_gib=None,
                exclusive_bridge=False, capacity=None):
    """Own a render slot for the duration of the block; yields the lock file taken.

    Without `small_gib` this is the machine's single big slot, as it always was. `small_gib`, the job's expected peak,
    lets it use the small slot when two are configured and it is admitted. `kind` ('job', 'game' or 'compile') is
    recorded in the lock file; a compile also takes the small and fitting slots. `fitting_gib` requests only the
    configured reserved lane. `on_slot(slot, why)` hears 'big', 'small' or 'fitting' once the scan has passed.

    `exclusive_bridge` is the capacity client's migration boundary: acquire all existing lane mutexes
    together or none, without waiting while holding a subset. Old clients therefore cannot enter a
    second lane after the broker's capacity check. It adds an admission requirement, never concurrency.
    """
    kind = kind or 'job'
    if kind not in KINDS:
        raise ValueError(f'kind must be one of {KINDS}, not {kind!r}')
    if capacity is not None:
        if (getattr(capacity, 'mode', None) != 'capacity' or wait or exclusive_bridge
                or small_gib is not None or fitting_gib is not None):
            raise ValueError('Shared capacity needs one nonblocking, fully configured admission')
        with _shared_capacity(capacity, on_slot, ignore=ignore, scan=scan) as path:
            yield path
        return
    from .. import capacity_compat
    capacity_compat.refuse_unmanaged('Direct legacy render locking')
    if exclusive_bridge and (small_gib is not None or fitting_gib is not None or wait):
        raise ValueError('the capacity bridge requires one nonblocking attempt without a slot preference')
    if fitting_gib is not None and (kind != 'job' or small_gib is not None
                                   or not math.isfinite(fitting_gib) or not 0 < fitting_gib <= SMALL_PEAK_GIB):
        raise ValueError('fitting requires a job with an expected peak above zero and at most 3 GiB, without small_gib')
    big = lock_path()
    small = small_lock_path(big)
    fitting = fitting_lock_path(big)
    big.parent.mkdir(parents=True, exist_ok=True)
    why = ''
    if small_gib is not None:
        if kind != 'job':
            why = f'a {kind} always uses the big slot'
        elif not 0 <= small_gib <= SMALL_PEAK_GIB:
            why = f'expected {small_gib:.1f} GiB, over the small slot\'s {SMALL_PEAK_GIB:g}'
    eligible = small_gib is not None and not why
    opened, owned = [], []
    try:
        handle = big.open('a+')
        opened.append(handle)
        admission = big.with_name(f'{big.stem}.admission{big.suffix}').open('a+')
        opened.append(admission)
        bridge_handles = [handle]
        if exclusive_bridge:
            for path in (small, fitting):
                extra = path.open('a+')
                opened.append(extra)
                bridge_handles.append(extra)
        deadline = time.monotonic()+max(wait, 0.)
        while True:
            slot = None
            # Publish the chosen slot's record before another new guard checks admission. Otherwise two
            # launches in the same checkout can both see an empty record between flock and _write.
            if _take(admission):
                try:
                    if exclusive_bridge:
                        taken = []
                        for candidate in bridge_handles:
                            if not _take(candidate):
                                why = f'the capacity bridge needs every lane; {candidate.name} is busy'
                                break
                            taken.append(candidate)
                        if len(taken) == len(bridge_handles):
                            owned.extend(taken)
                            slot, why = 'big', 'capacity migration bridge holds every legacy lane'
                        else:
                            # Nothing was published. Do not truncate any previous owner's record.
                            for candidate in reversed(taken):
                                fcntl.flock(candidate.fileno(), fcntl.LOCK_UN)
                    elif fitting_gib is not None:
                        taken, why = _admit_fitting(fitting, big, small, fitting_gib)
                        if taken:
                            opened.append(taken)
                            owned.append(taken)
                            slot = 'fitting'
                    else:
                        if eligible:
                            taken, why = _admit_small(small, big, small_gib)
                            if taken:
                                opened.append(taken)
                                owned.append(taken)
                                slot = 'small'
                        if slot is None and _take(handle):
                            owned.append(handle)
                            slot = 'big'
                            other = read_holder(fitting)
                            if kind != 'compile' and other and same_checkout(other):
                                raise RenderBusy(f'the fitting slot runs a job in this checkout{describe(other)}')
                    if slot is not None:
                        record = dict(pid=os.getpid(), started=usage(os.getpid()).started, purpose=str(purpose),
                                      kind=kind, slot=slot, checkout=str(Path.cwd()), repo=str(REPO),
                                      time=time.time(), protocol=PROTOCOL)
                        if slot in ('small', 'fitting'):
                            record['expected_gib'] = round(float(fitting_gib if slot == 'fitting' else small_gib), 2)
                        if exclusive_bridge:
                            record['capacity_bridge'] = True
                        for target in owned if exclusive_bridge else owned[:1]:
                            _write(target, record)
                finally:
                    fcntl.flock(admission.fileno(), fcntl.LOCK_UN)
            else:
                why = 'another render job is checking admission'
            if slot is not None:
                break
            if time.monotonic() >= deadline:
                if fitting_gib is not None:
                    raise RenderBusy(why)
                other = holder(handle)
                detail = f" held by pid {other['pid']} ({other.get('purpose')})" if other else ''
                aside = f' (not the small slot: {why})' if eligible else ''
                raise RenderBusy(f'another render job is running{detail}; '
                                 f'stop it (or the phone stream) before starting this one{aside}')
            time.sleep(.25)
        if kind == 'compile' and not exclusive_bridge:
            # Nothing runs beside a compile. Holding the big slot, recorded as a compile, stops new small jobs;
            # one already running is waited for.
            why = 'a compile, which also holds the small and fitting slots'
            limit = max(deadline, time.monotonic()+COMPILE_WAIT)
            for label, path in (('small', small), ('fitting', fitting)):
                extra = path.open('a+')
                opened.append(extra)
                told = False
                while not _take(extra):
                    other = holder(extra)
                    if time.monotonic() >= limit:
                        raise RenderBusy(f'a {label} render job is still running{describe(other)}; '
                                         f'a compile does not start beside it')
                    if not told:
                        print(f'waiting for the {label} render job{describe(other)} to finish before compiling',
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
            if kind != 'compile' and not exclusive_bridge:
                for label, path in lock_paths().items():
                    if label != slot:
                        other = read_holder(path)
                        if other:
                            skip |= family(other['pid'], table)
            foreign = render_processes(ignore=skip, table=table)
            if foreign:
                names = ', '.join(f"{p['pid']} {Path(p['command']).name}" for p in foreign)
                raise RenderBusy(f'render processes are already running and no harness owns them: {names}. '
                                 f'Stop them (the phone stream: `atelier stream stop`) first')
        if on_slot is not None:
            on_slot(slot, why)
        yield {'big': big, 'small': small, 'fitting': fitting}[slot]
    finally:
        for taken in reversed(owned):
            _release(taken)
        for opened_handle in opened:
            opened_handle.close()
