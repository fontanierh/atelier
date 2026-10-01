"""Optional execution-only batching of independent frozen reference cases.

The caller already holds the root render lock. Each original executable reads
count=1 and one exact outer case, constructs all original owners, and has its
own identified-PID 2 GiB memory guard. No constructor or numeric data is reused.
The default checker path remains the original single invocation.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_case_ranges(input_bytes, exact_case_ranges):
    """Require ordered, contiguous, four-byte-aligned outer-count slices."""
    if len(input_bytes) < 4 or len(input_bytes) % 4:
        raise ValueError('Reference input must contain aligned count framing')
    count, = struct.unpack_from('<I', input_bytes)
    ranges = tuple(exact_case_ranges)
    if count != len(ranges):
        raise ValueError('Case range count differs from original outer count')
    previous = 4
    streams = []
    for start, end in ranges:
        if start != previous or start % 4 or end % 4 or not start < end <= len(input_bytes):
            raise ValueError('Case ranges must partition the complete original payload in order')
        streams.append(struct.pack('<I', 1) + input_bytes[start:end])
        previous = end
    if previous != len(input_bytes):
        raise ValueError('Case ranges leave trailing original input')
    joined = struct.pack('<I', count) + b''.join(raw[4:] for raw in streams)
    if joined != input_bytes:
        raise ValueError('Rejoined case slices differ from unchanged original input')
    return streams


def join_case_outputs(outputs):
    """Merge only outer framing after complete per-case protocol validation."""
    for raw in outputs:
        if len(raw) < 4 or len(raw) % 4 or struct.unpack_from('<I', raw)[0] != 1:
            raise ValueError('Each reference case must return one aligned output stream')
    return struct.pack('<I', len(outputs)) + b''.join(raw[4:] for raw in outputs)


def _memory_guard():
    # Derive the project guard location from this checkout, never a home path.
    relative = Path('platform/studio/atelier/safety/memory_guard.py')
    path = next((p / relative for p in Path(__file__).resolve().parents
                 if (p / relative).is_file()), None)
    if path is None:
        raise FileNotFoundError('Repository memory_guard.py was not found')
    spec = importlib.util.spec_from_file_location('_skate_reference_memory_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module.usage


@dataclass
class IdentifiedProcess:
    process: subprocess.Popen
    started: int


def _identify(process, usage):
    deadline = time.monotonic() + 1
    while True:
        try:
            return IdentifiedProcess(process, usage(process.pid).started)
        except ProcessLookupError:
            if process.poll() is not None or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def _stop(owned, usage):
    """Reap only our Popen child; verify start identity before every signal."""
    process = owned.process
    if process.poll() is not None:
        process.wait()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            current = usage(process.pid)
        except ProcessLookupError:
            process.wait(timeout=5)
            return
        if current.started != owned.started:
            raise RuntimeError('Owned process PID start identity changed; no signal sent')
        process.send_signal(sig)
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError('Identified reference process did not exit after SIGKILL')


def _report(path):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def run_reference_cases(binary, argv, input_bytes, exact_case_ranges, output_dir,
                        workers=1, limit_gib=2, *, validate_output):
    """Run exact independent case streams and return their source-ordered bytes.

    validate_output(index, bytes) must decode the *whole* original per-case
    protocol, including operation counts and trailing framing. Its exceptions
    abort the batch and reap all owned workers/guards. Root chooses 1..4 workers
    after measuring actual capacity; this function never changes memory prefs.
    """
    if workers not in (1, 2, 3, 4) or limit_gib != 2:
        raise ValueError('Reference workers require 1..4 processes with a 2 GiB cap each')
    if not callable(validate_output):
        raise TypeError('A complete original-output protocol validator is required')
    exact_case_ranges = tuple(exact_case_ranges)
    streams = validate_case_ranges(input_bytes, exact_case_ranges)
    binary = Path(binary).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    guard_path, usage = _memory_guard()
    summary = dict(strategy='unchanged independent original cases', workers=workers,
                   worker_limit_bytes=2 * 1024**3, maximum_worker_limit_bytes=workers * 2 * 1024**3,
                   input_sha256=sha256(input_bytes), binary_sha256=sha256(binary.read_bytes()),
                   exact_case_ranges=[list(r) for r in exact_case_ranges], cases=[])
    active = {}
    outputs = [None] * len(streams)
    pending = 0
    failure = None
    cleanup_errors = []

    def cleanup(label, operation):
        try:
            return operation()
        except BaseException as error:
            cleanup_errors.append(f'{label}: {type(error).__name__}: {error}')
            return None

    def close_handles(state):
        for handle in ('stdout', 'stderr', 'guard_log'):
            cleanup(f'case {state["row"]["index"]} {handle}.close', state[handle].close)
        if state['worker'] is not None and state['worker'].process.stdin is not None:
            cleanup(f'case {state["row"]["index"]} stdin.close', state['worker'].process.stdin.close)

    def save():
        path = output_dir / 'result.json'
        temp = output_dir / 'result.tmp'
        temp.write_text(json.dumps(summary, indent=2) + '\n')
        temp.replace(path)

    def start(index):
        folder = output_dir / f'case-{index:04d}'
        folder.mkdir(exist_ok=True)
        for name in ('memory-health.json', 'memory-health.jsonl', 'memory-health.previous.jsonl'):
            (folder / name).unlink(missing_ok=True)
        raw = streams[index]
        (folder / 'input.bin').write_bytes(raw)
        row = dict(index=index, input_bytes=len(raw), input_sha256=sha256(raw),
                   original_byte_range=list(exact_case_ranges[index]), status='starting',
                   evidence_directory=folder.name, memory_report=folder.name + '/memory-health.json')
        summary['cases'].append(row)
        # stdin remains open and empty until the independent guard confirms its
        # first sample. Original Rust read_to_end cannot construct owners yet.
        stdout = (folder / 'output.bin').open('wb')
        stderr = (folder / 'stderr.log').open('wb')
        guard_log = (folder / 'guard.log').open('wb')
        state = dict(row=row, folder=folder, stdout=stdout, stderr=stderr,
                     guard_log=guard_log, worker=None, guard=None)
        active[index] = state
        process = subprocess.Popen([str(binary), *map(str, argv)], stdin=subprocess.PIPE,
                                   stdout=stdout, stderr=stderr)
        try:
            state['worker'] = _identify(process, usage)
        except ProcessLookupError as error:
            # No input was released. EOF makes the unchanged count reader
            # reject this empty stream, without constructing case owners.
            cleanup(f'case {index} unidentified stdin.close', process.stdin.close)
            cleanup(f'case {index} unidentified worker wait', lambda: process.wait(timeout=5))
            raise RuntimeError('Reference exited before its PID could be identified') from error
        row.update(pid=process.pid, process_start=state['worker'].started)
        guard = subprocess.Popen([sys.executable, str(guard_path), '--pid', str(process.pid),
                                  '--expected-start', str(state['worker'].started),
                                  '--limit-gib', '2', '--report', str(folder / 'memory-health.json')],
                                 stdout=guard_log, stderr=guard_log)
        try:
            state['guard'] = _identify(guard, usage)
        except ProcessLookupError as error:
            # The worker is identified; stopping it lets its unidentifiable
            # guard finish naturally. Never signal a guard without identity.
            cleanup(f'case {index} worker after guard identification failure', lambda: _stop(state['worker'], usage))
            cleanup(f'case {index} unidentified guard wait', lambda: guard.wait(timeout=5))
            raise RuntimeError('Memory guard exited before its PID could be identified') from error
        row.update(guard_pid=guard.pid, guard_process_start=state['guard'].started)
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None or guard.poll() is not None:
                raise RuntimeError('Reference or memory guard exited before guarded input release')
            health = _report(folder / 'memory-health.json')
            if health is not None:
                if (health['pid'], health['process_start'], health['limit_bytes'], health['state']) != (
                        process.pid, state['worker'].started, 2 * 1024**3, 'running'):
                    raise RuntimeError('Memory guard initial identity/limit validation failed')
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Memory guard did not confirm initial telemetry')
            time.sleep(.05)
        process.stdin.write(raw)
        process.stdin.close()
        row['status'] = 'running'
        save()
        print(f'Reference case {index + 1}/{len(streams)} PID {process.pid}, independent 2 GiB guard', flush=True)

    try:
        while pending < len(streams) or active:
            while pending < len(streams) and len(active) < workers:
                start(pending)
                pending += 1
            finished = []
            for index, state in active.items():
                process, guard = state['worker'].process, state['guard'].process
                code = process.poll()
                if code is None:
                    if guard.poll() is not None:
                        raise RuntimeError(f'Case {index} memory guard exited while reference was live')
                    continue
                state['row']['returncode'] = process.wait()
                # Allow the guard to observe the identified process exit. A
                # monitor surviving that interval is a lifecycle error.
                guard_code = guard.wait(timeout=3)
                state['row']['guard_returncode'] = guard_code
                close_handles(state)
                health = _report(state['folder'] / 'memory-health.json')
                state['row']['memory_health'] = health
                raw = (state['folder'] / 'output.bin').read_bytes()
                state['row'].update(output_bytes=len(raw), output_sha256=sha256(raw))
                if code != 0 or guard_code != 0 or health is None or health['state'] != 'running':
                    raise RuntimeError(f'Case {index} failed reference/guard execution; inspect its retained evidence')
                if cleanup_errors:
                    raise RuntimeError('Reference evidence handle cleanup failed; inspect cleanup_errors')
                join_case_outputs([raw])
                validate_output(index, raw)
                outputs[index] = raw
                state['row'].update(status='passed', complete_output_protocol_validated=True)
                finished.append(index)
                print(f'Reference case {index + 1}/{len(streams)} passed complete protocol validation', flush=True)
            for index in finished:
                del active[index]
            save()
            if active:
                time.sleep(.1)
        merged = join_case_outputs(outputs)
        summary.update(passed=True, merged_output_bytes=len(merged), merged_output_sha256=sha256(merged))
        (output_dir / 'merged.bin').write_bytes(merged)
        return merged
    except BaseException as error:
        failure = error
        summary.update(passed=False, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        for state in active.values():
            for role in ('worker', 'guard'):
                owned = state[role]
                if owned is not None:
                    try:
                        _stop(owned, usage)
                        state['row'][role + '_cleanup_returncode'] = owned.process.returncode
                    except BaseException as error:
                        cleanup_errors.append(f'{role}: {type(error).__name__}: {error}')
            close_handles(state)
            raw = cleanup(f'case {state["row"]["index"]} output evidence', (state['folder'] / 'output.bin').read_bytes)
            if raw is not None:
                state['row'].update(output_bytes=len(raw), output_sha256=sha256(raw))
            state['row']['memory_health'] = cleanup(f'case {state["row"]["index"]} guard evidence',
                lambda: _report(state['folder'] / 'memory-health.json'))
            if state['row']['status'] != 'passed':
                state['row']['status'] = 'failed'
        if cleanup_errors:
            summary.update(passed=False, cleanup_errors=cleanup_errors)
        cleanup('final result save', save)
        if cleanup_errors and failure is not None and hasattr(failure, 'add_note'):
            failure.add_note('Reference cleanup evidence: ' + '; '.join(cleanup_errors))
        if cleanup_errors and failure is None:
            raise RuntimeError('; '.join(cleanup_errors))
