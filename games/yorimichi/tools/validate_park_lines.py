#!/usr/bin/env python3
"""Run authored park lines through the existing gameplay Session CLI; never compiles a runtime."""
import argparse
from contextlib import ExitStack
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import selectors
import subprocess
import sys
import time
import numpy as np
import check_skate_feel as feel
from park_line_geometry import LineWorld, RouteProgress
from park_line_metrics import analyze, is_ground, DEFAULTS
from park_line_controller import LineFollower
from park_line_gaps import validate_gap_specs
from park_line_vert import VertReturns


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def guarded_big_holder():
    """Require a pinned live ancestor and a currently held BIG kernel lock.

    The guard launcher remains responsible for the validator Python process.
    This check never reserves a second slot and never writes the lock record.
    """
    from atelier.safety.memory_guard import usage
    from atelier.safety.render_lock import family, holder, lock_path
    message = 'native collision requires an owned live BIG-slot guarded job'
    try:
        path = lock_path()
        with path.open() as handle:
            record = holder(handle)
            if not record or record.get('slot') != 'big' or record.get('started') is None:
                raise ValueError(message)
            current = usage(record['pid'])
            if (current.exited or current.started != record['started'] or record['pid'] == os.getpid()
                    or os.getpid() not in family(record['pid'])):
                raise ValueError(message)
            before = os.fstat(handle.fileno())
            named = path.stat()
            if (before.st_dev, before.st_ino) != (named.st_dev, named.st_ino):
                raise ValueError(message)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                raise ValueError(message)
            # Reject a release/replacement or changed identity during the check.
            after = path.stat()
            if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                    or holder(handle) != record or usage(record['pid']).started != record['started']):
                raise ValueError(message)
            return record
    except (OSError, ProcessLookupError) as error:
        raise ValueError(message) from error


def collision_capacity(full_scene=False):
    """@cc [owner:fontanierh,label:safety] full-scene-native-admission
    The default capacity MUST remain 100000 triangles. The 250000-triangle
    full-scene tier MUST require a pinned live BIG-holder ancestor and a held
    kernel lock. Neither tier MAY change gameplay verdict thresholds or acquire
    a second slot. The caller MUST guard the Python process; ObservedSession
    MUST separately guard and reap its actual native child before readiness.
    """
    if full_scene:
        guarded_big_holder()
        return 250000
    return 100000


class ObservedSession(feel.Session):
    def __init__(self, *args, duration=150):
        self._owned = ExitStack()
        self._monitors = ExitStack()
        self._owned.callback(self._monitors.close)
        self.guard_duration = duration
        self.guard_report = None
        self._started = False
        self._stopped = False
        try:
            super().__init__(*args)
        except BaseException:
            self._owned.close()
            if hasattr(self, 'log'):
                self.log.close()
            raise

    def start(self):
        if self._started:
            raise RuntimeError('ObservedSession is one-shot; create a fresh Session per trial')
        self._started = True
        from atelier.safety.guard import attach, reap
        from atelier.safety.process import spawn
        guarded_big_holder()
        self.proc = spawn(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=self.log, text=True, bufsize=1)
        # Register cleanup immediately, including monitor attachment failures.
        self._owned.callback(reap, self.proc)
        self.guard_report = Path(self.log.name).with_suffix('.memory-health.json')
        self.monitor = self._monitors.enter_context(attach(
            self.proc.pid, self.guard_report, duration=self.guard_duration, limit_gib=10.))
        self.check_guard()
        self.selector = selectors.DefaultSelector()
        self._owned.callback(self.selector.close)
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.ready = self.read()
        if self.ready.get('type') != 'ready':
            raise RuntimeError('Session did not report ready')
        self.deck = self.ready['names'].index('SKATEBOARD_ROOT')
        self.generation = 0

    def check_guard(self):
        if self.monitor is None or self.monitor.poll() is not None:
            raise RuntimeError('Native Session memory monitor unavailable or exited')

    def read(self):
        deadline = time.monotonic()+20
        heartbeat = time.monotonic()+10
        while True:
            self.check_guard()
            if self.selector.select(1):
                break
            if time.monotonic() > deadline:
                raise TimeoutError('No Session response for 20 seconds')
            if time.monotonic() > heartbeat:
                print('Waiting for Session response; no new simulation frame yet', flush=True)
                heartbeat = time.monotonic()+10
        self.check_guard()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError('Session exited; inspect its stderr log')
        row = json.loads(line)
        if row['type'] == 'error':
            raise RuntimeError(row['message'])
        return row

    def send(self, op, **values):
        self.check_guard()
        super().send(op, **values)

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        try:
            self.check_guard()
            if self.proc.poll() is not None:
                raise RuntimeError('Native Session exited before intentional shutdown')
            self.send('quit')
            status = self.proc.wait(timeout=10)
            if status != 0:
                raise RuntimeError(f'Native Session shutdown exited with status {status}')
        finally:
            self._owned.close()


def controls(spec, frame):
    buttons, left, right = 0, [0, 0], [0, 0]
    for entry in spec.get('controls', []):
        if entry['start_frame'] <= frame < entry['end_frame']:
            buttons = int(entry.get('buttons', 0))
            left, right = entry.get('left', [0, 0]), entry.get('right', [0, 0])
    return buttons, left, right


def validate_speeds(speeds):
    if not speeds or len(speeds) > 30 or any(not math.isfinite(s) or s < 0 for s in speeds):
        raise ValueError('Use 1..30 finite nonnegative entry speeds')
    return speeds


def simulate(world, entry_speed, binary, package, output, run_id, timeout):
    """@cc [owner:fontanierh,label:correctness] actual-session-observations
    Frames MUST come from check_skate_feel.Session's configured CLI transport, never a ballistic substitute.
    Each speed trial MUST use a fresh session and preserve its controls and compact observations.
    """
    validate_gap_specs(world)
    VertReturns(world)
    spawn, heading, direction = world.spawn()
    collision = dict(triangles=world.triangles.tolist(), rails=world.spec.get('rails', []),
                     spawn=spawn.tolist(), heading=heading)
    follower = LineFollower(world.path, world.spec['follower'],start_m=world.spawn_m) if 'follower' in world.spec else None
    progress = RouteProgress(world.path,world.spawn_m)
    if follower and any(c.get('left', [0, 0])[0] != 0 for c in world.spec.get('controls', [])):
        raise ValueError('Choose scripted steering or follower; do not combine left.x writers')
    frames = int(world.spec.get('frames', 1200))
    recovery_frames = math.ceil(60*world.spec.get('acceptance', {}).get('landing_recovery_s', DEFAULTS['landing_recovery_s']))
    if not 1 <= frames <= 7200:
        raise ValueError('frames must be 1..7200')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Trial timeout must be finite and positive')
    feel.OUTPUT = output
    session = ObservedSession(binary, package, collision, run_id, duration=timeout+30)
    rows = []; began = time.monotonic(); last_report = began
    last_air_frame = -100000
    try:
        extra = {'feel': world.spec['feel']} if 'feel' in world.spec else {}
        session.send('activate', spawn=spawn.tolist(), heading=heading, goofy=False,
                     difficulty=world.spec.get('difficulty', 'normal'), trucks=.5, generation=1,
                     velocity=[float(direction[0]*entry_speed), 0., float(direction[1]*entry_speed)],
                     vert_assist=float(world.spec.get('vert_assist', 0)), **extra)
        session.read()
        with (output/(run_id+'.frames.jsonl')).open('w') as trace:
            for frame in range(frames):
                if time.monotonic()-began > timeout:
                    raise TimeoutError('Trial wall-clock deadline exceeded; partial trace retained')
                buttons, left, right = controls(world.spec, frame)
                if follower:
                    left = [follower.steering(rows[-1] if rows else None), left[1]]
                session.send('step', dt=1/60, buttons=buttons, left=left, right=right, triggers=[0, 0])
                row = session.read()
                compact = dict(frame=frame, time_s=(frame+1)/60, tick=row['tick'],
                               position=row['root'][12:15], velocity=row['velocity'], state=row['state'],
                               surface=row.get('surface'), trick=row.get('trick'), buttons=buttons,
                               left=left, right=right)
                rows.append(compact)
                trace.write(json.dumps(compact, allow_nan=False)+'\n')
                if 'Air' in row['state']:
                    last_air_frame = frame
                path_s,_ = progress.update(compact['position'],float(np.linalg.norm(compact['velocity'])))
                if (world.spec.get('stop_at_finish', True) and path_s >= world.finish_m
                        and is_ground(row['state']) and frame-last_air_frame > recovery_frames):
                    print(f'{run_id}: finish reached at frame {frame+1}; landing recovery observed', flush=True)
                    break
                if time.monotonic()-last_report >= 15:
                    trace.flush()
                    print(f'{run_id}: {frame+1}/{frames} frames; state={row["state"]}; elapsed={time.monotonic()-began:.1f}s', flush=True)
                    last_report = time.monotonic()
    finally:
        session.close()
    result = analyze(rows, world)
    result.update(entry_speed_mps=entry_speed, wall_seconds=time.monotonic()-began,
                  trace=run_id+'.frames.jsonl', collision=run_id+'.json', log=run_id+'.log',
                  collision_sha256=sha(output/(run_id+'.json')),
                  memory_guard_report=session.guard_report.name,
                  controls_mode='path_follower' if follower else 'scripted' if world.spec.get('controls') else 'coast')
    if follower:
        result['controller'] = follower.report()
        result['controller']['stayed_in_corridor'] = result['max_corridor_excess_m'] == 0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout', type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--line', action='append', help='Only these line IDs; may repeat')
    parser.add_argument('--speeds', nargs='+', type=float)
    parser.add_argument('--frames', type=int)
    parser.add_argument('--timeout-per-run', type=float, default=120.)
    parser.add_argument('--full-scene', action='store_true', help='250k collision tier; requires owned live BIG slot')
    args = parser.parse_args()
    guarded_big_holder()
    triangle_limit = collision_capacity(args.full_scene)
    raw = args.layout.read_bytes(); layout = json.loads(raw)
    args.out.mkdir(parents=True, exist_ok=True)
    binary = args.binary.resolve(); package = args.package.resolve()
    manifest_path = binary.parent/'build-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('compiled') or manifest.get('executable_sha256') != sha(binary):
        raise ValueError('Binary does not match its compiled build manifest')
    package_manifest = package/'package-manifest.json'
    if not package_manifest.is_file():
        raise ValueError('Missing assembled simulation package manifest')
    report = dict(complete=False, layout_sha256=hashlib.sha256(raw).hexdigest(),
                  binary_sha256=sha(binary), build_manifest_sha256=sha(manifest_path),
                  package_manifest_sha256=sha(package_manifest),
                  scope='Actual offline game Session, 60 Hz; scripted/coasting controls, not a human playtest.',
                  collision_triangle_limit=triangle_limit, lines=[])
    (args.out/'layout.json').write_bytes(raw)
    selected = [s for s in layout['lines'] if not args.line or s['id'] in args.line]
    if not selected or (args.line and set(args.line)-{s['id'] for s in selected}):
        raise ValueError('Requested line IDs not found')
    save(args.out/'report.json', report)
    for line_number, original in enumerate(selected):
        spec = {**original}
        if args.frames:
            spec['frames'] = args.frames
        world = LineWorld(spec, args.layout.resolve().parent, triangle_limit=triangle_limit)
        speeds = validate_speeds(args.speeds or spec.get('entry_speeds_mps', [4, 8, 12, 16]))
        line = dict(id=spec['id'], triangles=len(world.triangles), runs=[])
        report['lines'].append(line)
        for speed_number, speed in enumerate(speeds):
            run_id = f'line-{line_number:02d}-speed-{speed_number:02d}'
            print(f'{spec["id"]}: entry {speed:g} m/s, {len(world.triangles)} collision triangles', flush=True)
            try:
                result = simulate(world, float(speed), binary, package, args.out, run_id, args.timeout_per_run)
            except (RuntimeError, TimeoutError, ValueError, AssertionError) as error:
                result = dict(entry_speed_mps=float(speed), passed=False, error=str(error),
                              trace=run_id+'.frames.jsonl', failures=['trial did not complete'])
            line['runs'].append(result)
            print(f'{spec["id"]} {speed:g} m/s: {"PASS" if result["passed"] else "FAIL"}; '+
                  '; '.join(result.get('failures', [])), flush=True)
            save(args.out/'report.json', report)
        line['passing_tested_speeds_mps'] = [r['entry_speed_mps'] for r in line['runs'] if r['passed']]
        line['passed_all_tested_speeds'] = all(r['passed'] for r in line['runs'])
    report['complete'] = True
    report['passed'] = all(line['passed_all_tested_speeds'] for line in report['lines'])
    report['child_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*(1 if sys.platform == 'darwin' else 1024)
    save(args.out/'report.json', report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
