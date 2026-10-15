"""CPU-only checks that an owned Unreal child is never left behind, and that only one may run.

    uv run pytest platform/studio/tests/test_guarded.py

Every case uses a fake child (a sleeping interpreter) and, where the point is the failure path, a
fake monitor. Reproducing an out-of-memory kill is not the point: the point is that whatever goes
wrong after the child exists, the child is reaped and the next run is not blocked by a stale lock.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier.safety import guarded as guarded_run
from atelier.safety import render_lock as exclusive
from atelier.safety.render_lock import RenderBusy, render_lock

SLEEPER = [sys.executable, '-c', 'import time; time.sleep(60)']
QUICK = [sys.executable, '-c', 'print("done")']


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def gone(pid, timeout=10.):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(.05)
    return not alive(pid)


class FakeMonitor:
    """Stands in for the guard process: `dead` makes it look like it exited early."""
    def __init__(self, dead=False, raises=None):
        self.dead, self.raises = dead, raises

    def poll(self):
        if self.raises:
            raise self.raises
        return 1 if self.dead else None


class ReapingChild:
    """waitpid lags the monitor, or never observes exit until owned cleanup terminates it."""
    pid = 999999

    def __init__(self, status=0, live=False, completed=False):
        self.status, self.live = status, live
        self.returncode = status if completed else None
        self.waits, self.terminated = [], False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.live and self.returncode is None:
            raise subprocess.TimeoutExpired('fake child', timeout)
        if self.returncode is None:
            self.returncode = self.status
        return self.returncode

    def terminate(self):
        self.terminated, self.returncode = True, -signal.SIGTERM


class MonitorExitTests(unittest.TestCase):
    """Deterministic lifecycle interleavings; no render processes or machine admission."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def run_child(self, child, monitor_status=0, record='running', callback=None):
        @contextmanager
        def attach(pid, report, **kwargs):
            if record is not None:
                value = dict(pid=pid, state=record) if isinstance(record, str) else record
                Path(report).write_text(json.dumps(value))
            yield SimpleNamespace(poll=lambda: monitor_status)
        with patch.object(guarded_run, 'spawn', return_value=child), \
                patch.object(guarded_run, 'attach_memory_guard', attach):
            return guarded_run.run(QUICK, self.folder, lock=False, on_poll=callback)

    def test_clean_monitor_exit_reconciles_delayed_child_reaping(self):
        child, acknowledged = ReapingChild(), []
        self.assertEqual(self.run_child(child, callback=acknowledged.append), 0)
        self.assertEqual(child.waits[0], 2.)
        self.assertEqual(acknowledged, [child.pid])
        self.assertFalse(child.terminated)

    def test_clean_monitor_exit_preserves_failed_child_status(self):
        child, acknowledged = ReapingChild(status=3), []
        self.assertEqual(self.run_child(child, callback=acknowledged.append), 3)
        self.assertEqual(acknowledged, [])

    def test_clean_monitor_exit_with_surviving_child_fails_and_reaps_it(self):
        child, acknowledged = ReapingChild(live=True), []
        with self.assertRaisesRegex(SystemExit, 'exited before the child'):
            self.run_child(child, callback=acknowledged.append)
        self.assertEqual(child.waits[0], 2.)
        self.assertTrue(child.terminated)
        self.assertEqual(acknowledged, [])

    def test_failed_terminal_monitor_fails_without_a_callback(self):
        with self.assertRaisesRegex(SystemExit, 'memory guard failed'):
            self.run_child(ReapingChild(completed=True), monitor_status=1)

    def test_stop_receipts_never_acknowledge_a_successful_child(self):
        for state in ('memory_limit', 'test_duration'):
            for monitor_status in (None, 0):
                with self.subTest(state=state, monitor_status=monitor_status):
                    acknowledged = []
                    with self.assertRaisesRegex(SystemExit, state):
                        self.run_child(ReapingChild(completed=True), monitor_status=monitor_status,
                                       record=state, callback=acknowledged.append)
                    self.assertEqual(acknowledged, [])

    def test_stop_receipt_fails_without_a_callback(self):
        with self.assertRaisesRegex(SystemExit, 'memory_limit'):
            self.run_child(ReapingChild(completed=True), record='memory_limit')

    def test_short_child_can_exit_before_first_sample(self):
        self.assertEqual(self.run_child(ReapingChild(), record=None), 0)

    def test_reused_report_from_an_old_child_is_not_a_current_stop(self):
        self.assertEqual(self.run_child(ReapingChild(), record=dict(pid=999998, state='memory_limit')), 0)

    def test_invalid_report_fails_closed(self):
        with self.assertRaisesRegex(SystemExit, 'report is invalid'):
            self.run_child(ReapingChild(), record=[])


class GuardedRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'report'
        os.environ['ATELIER_RENDER_LOCK'] = str(Path(self.temp.name)/'render.lock')
        os.environ['ATELIER_RENDER_LOCK_SCAN'] = '0'
        self.addCleanup(os.environ.pop, 'ATELIER_RENDER_LOCK', None)
        self.addCleanup(os.environ.pop, 'ATELIER_RENDER_LOCK_SCAN', None)
        self.seen = []

    def fake_attach(self, monitor=None, raises=None):
        """Replace the memory guard, recording the child pid it was asked to watch."""
        @contextmanager
        def attach(pid, report, duration, limit_gib=10., expected_start=None):
            self.seen.append(pid)
            Path(report).parent.mkdir(parents=True, exist_ok=True)
            Path(report).write_text('{"state": "fake"}')
            if raises:
                raise raises
            yield monitor if monitor is not None else FakeMonitor()
        original = guarded_run.attach_memory_guard
        guarded_run.attach_memory_guard = attach
        self.addCleanup(setattr, guarded_run, 'attach_memory_guard', original)

    def test_a_child_that_exits_on_its_own_returns_its_status(self):
        self.fake_attach()
        self.assertEqual(guarded_run.run(QUICK, self.folder), 0)
        self.assertIn('done', (self.folder/'stdout.log').read_text())
        self.assertEqual(len(self.seen), 1)

    def test_a_failing_child_returns_its_status(self):
        self.fake_attach()
        self.assertEqual(guarded_run.run([sys.executable, '-c', 'raise SystemExit(3)'], self.folder), 3)

    def test_a_monitor_that_never_starts_still_leaves_no_child(self):
        # The regression: ownership used to begin only once the monitor context was entered.
        self.fake_attach(raises=RuntimeError('monitor failed to start'))
        with self.assertRaises(RuntimeError):
            guarded_run.run(SLEEPER, self.folder)
        self.assertEqual(len(self.seen), 1)
        self.assertTrue(gone(self.seen[0]), 'the child outlived a monitor that never started')

    def test_a_monitor_that_dies_first_kills_the_child(self):
        self.fake_attach(monitor=FakeMonitor(dead=True))
        with self.assertRaises(SystemExit):
            guarded_run.run(SLEEPER, self.folder)
        self.assertTrue(gone(self.seen[0]))

    def test_failed_guard_prevents_poll_acknowledgement(self):
        self.fake_attach(monitor=FakeMonitor(dead=True))
        acknowledged = []
        with self.assertRaises(SystemExit):
            guarded_run.run(SLEEPER, self.folder, on_poll=acknowledged.append)
        self.assertEqual(acknowledged, [])
        self.assertTrue(gone(self.seen[0]))

    def test_failed_terminal_guard_prevents_final_acknowledgement(self):
        self.fake_attach(monitor=FakeMonitor(dead=True))
        acknowledged = []
        # Force the final-exit branch without scheduler timing or a real process. The cleanup
        # sees an already completed child and never signals this stand-in PID.
        child = SimpleNamespace(pid=999999, returncode=0, poll=lambda: 0)
        with patch.object(guarded_run, 'spawn', return_value=child):
            with self.assertRaisesRegex(SystemExit, 'final callback'):
                guarded_run.run(QUICK, self.folder, on_poll=acknowledged.append)
        self.assertEqual(acknowledged, [])

    def test_an_interruption_kills_the_child(self):
        self.fake_attach(monitor=FakeMonitor(raises=KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            guarded_run.run(SLEEPER, self.folder)
        self.assertTrue(gone(self.seen[0]))

    def test_the_deadline_kills_the_child(self):
        self.fake_attach()
        started = time.monotonic()
        with self.assertRaises(SystemExit):
            guarded_run.run(SLEEPER, self.folder, timeout=1.5)
        self.assertLess(time.monotonic()-started, 30)
        self.assertTrue(gone(self.seen[0]))

    def test_watched_descendants_are_guarded_and_unwound_on_the_deadline(self):
        self.fake_attach()
        launcher = [sys.executable, '-c', 'import subprocess, time; subprocess.Popen(["/bin/sleep", "60"]); time.sleep(60)']
        with self.assertRaises(SystemExit):
            guarded_run.run(launcher, self.folder, timeout=3, watch=('sleep',))
        self.assertEqual(len(self.seen), 2, 'the launcher and its heavy descendant each get a guard')
        self.assertTrue(gone(self.seen[0]) and gone(self.seen[1]))
        self.assertTrue((self.folder/f'memory-health-sleep-{self.seen[1]}.json').exists())

    def test_leftover_descendants_are_reaped_but_unrelated_processes_are_not(self):
        self.fake_attach()
        bystander = subprocess.Popen(['/bin/sleep', '60'])
        self.addCleanup(bystander.kill)
        launcher = [sys.executable, '-c', 'import subprocess, time; subprocess.Popen(["/bin/sleep", "60"]); time.sleep(2)']
        self.assertEqual(guarded_run.run(launcher, self.folder, timeout=30, watch=('sleep',), progress=.5), 0)
        self.assertTrue(gone(self.seen[1]), 'a descendant left running after success is reaped')
        self.assertTrue(alive(bystander.pid), 'a process outside the recorded tree is never signalled')

    def test_no_deadline_is_honoured_by_the_guard_too(self):
        # `--timeout 0` must not smuggle a 24-hour kill into the monitor.
        captured = {}

        @contextmanager
        def attach(pid, report, duration, limit_gib=10., expected_start=None):
            captured['duration'] = duration
            Path(report).write_text('{}')
            yield FakeMonitor()
        original = guarded_run.attach_memory_guard
        guarded_run.attach_memory_guard = attach
        self.addCleanup(setattr, guarded_run, 'attach_memory_guard', original)
        self.folder.mkdir(parents=True, exist_ok=True)
        guarded_run.run(QUICK, self.folder, timeout=0)
        self.assertIsNone(captured['duration'])

    def test_a_second_run_is_refused_while_the_slot_is_held(self):
        self.fake_attach()
        with render_lock('test holder'):
            with self.assertRaises(RenderBusy):
                guarded_run.run(QUICK, self.folder)
        self.assertEqual(self.seen, [], 'no child should have been started')

    def test_the_slot_is_released_after_a_failure(self):
        self.fake_attach(monitor=FakeMonitor(dead=True))
        with self.assertRaises(SystemExit):
            guarded_run.run(SLEEPER, self.folder)
        with render_lock('after failure'):
            pass


class ForeignProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        os.environ['ATELIER_RENDER_LOCK'] = str(Path(self.temp.name)/'render.lock')
        os.environ.pop('ATELIER_RENDER_LOCK_SCAN', None)
        self.addCleanup(os.environ.pop, 'ATELIER_RENDER_LOCK', None)

    def test_an_unowned_render_process_refuses_the_slot(self):
        original = exclusive.render_processes
        exclusive.render_processes = lambda ignore=(), table=None: [{'pid': 4242, 'command': '/x/UnrealEditor'}]
        self.addCleanup(setattr, exclusive, 'render_processes', original)
        with self.assertRaises(RenderBusy) as caught:
            with render_lock('scan'):
                pass
        self.assertIn('4242', str(caught.exception))

    def test_a_stale_holder_record_does_not_block(self):
        import json
        path = Path(os.environ['ATELIER_RENDER_LOCK'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(pid=999999, started=1, purpose='ghost')))
        original = exclusive.render_processes
        exclusive.render_processes = lambda ignore=(), table=None: []
        self.addCleanup(setattr, exclusive, 'render_processes', original)
        with render_lock('after a ghost'):
            pass


if __name__ == '__main__':
    unittest.main()
