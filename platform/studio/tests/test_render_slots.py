"""CPU-only checks of the optional small render slot beside the big one.

    uv run pytest platform/studio/tests/test_render_slots.py

Nothing heavy runs: the other slot's holder is this test process (or a thread) holding a lock file with a record,
`ps` and `vm_stat` are replaced by fixed tables, and the memory guard by a fake that writes a report.
"""
import contextlib
import fcntl
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier import build as builder
from atelier import paths
from atelier.safety import guarded as guarded_run
from atelier.safety import render_lock as slots
from atelier.safety.memory_guard import usage
from atelier.safety.render_lock import GiB, RenderBusy, render_lock

QUICK = [sys.executable, '-c', 'print("done")']
ELSEWHERE = '/tmp/another-checkout'
VM_STAT = '''Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                   100000.
Pages active:                                 400000.
Pages inactive:                               200000.
Pages speculative:                             50000.
Pages throttled:                                   0.
Pages wired down:                             270000.
Pages purgeable:                               10000.
"Translation faults":                    11107475603.
File-backed pages:                            549744.
'''


@contextmanager
def hold(path, **fields):
    """Hold a lock file as another job would, with its record (None drops a field, as older code has no kind)."""
    record = dict(pid=os.getpid(), started=usage(os.getpid()).started, purpose='other job', kind='job',
                  checkout=ELSEWHERE, repo=ELSEWHERE, time=time.time())
    record.update(fields)
    record = {key: value for key, value in record.items() if value is not None}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        json.dump(record, handle)
        handle.flush()
        try:
            yield record
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def is_locked(path):
    with open(path, 'a+') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False


class SlotTestCase(unittest.TestCase):
    """A private lock folder, the scan off, two slots and plenty of memory unless a test says otherwise."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.big = Path(self.temp.name)/'render.lock'
        self.small = Path(self.temp.name)/'render.small.lock'
        self.env(ATELIER_RENDER_LOCK=str(self.big), ATELIER_RENDER_LOCK_SCAN='0', ATELIER_RENDER_SLOTS='2')
        self.patch(slots, 'available_bytes', lambda: 20*GiB)
        self.seen = []

    def env(self, **values):
        """Set (or, with None, remove) environment variables until the test ends."""
        for name, value in values.items():
            if name in os.environ:
                self.addCleanup(os.environ.__setitem__, name, os.environ[name])
            else:
                self.addCleanup(os.environ.pop, name, None)
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def patch(self, owner, name, value):
        self.addCleanup(setattr, owner, name, getattr(owner, name))
        setattr(owner, name, value)

    def note(self, slot, why):
        self.seen.append((slot, why))

    def take(self, **options):
        """The slot a job gets, and the lock file it yields."""
        with render_lock('test job', on_slot=self.note, **options) as path:
            return self.seen[-1][0], path


class SwitchTests(SlotTestCase):
    def setUp(self):
        super().setUp()
        self.env(ATELIER_RENDER_SLOTS=None)
        self.switch = Path(self.temp.name)/'render-slots.json'

    def test_one_slot_without_the_switch_file(self):
        self.assertEqual(slots.slot_count(), 1)

    def test_the_switch_file_turns_on_two(self):
        self.switch.write_text('{"slots": 2}')
        self.assertEqual(slots.slots_path(), self.switch)
        self.assertEqual(slots.slot_count(), 2)
        self.switch.write_text('{"slots": 1}')
        self.assertEqual(slots.slot_count(), 1)

    def test_the_environment_overrides_the_file(self):
        self.switch.write_text('{"slots": 2}')
        self.env(ATELIER_RENDER_SLOTS='1')
        self.assertEqual(slots.slot_count(), 1)
        self.switch.unlink()
        self.env(ATELIER_RENDER_SLOTS='2')
        self.assertEqual(slots.slot_count(), 2)

    def test_anything_else_means_one_slot(self):
        for text in ('not json', '{"slots": 3}', '[2]', '{"slots": "many"}', '{}'):
            self.switch.write_text(text)
            self.assertEqual(slots.slot_count(), 1, text)

    def test_the_small_lock_sits_next_to_the_big_one(self):
        self.assertEqual(slots.small_lock_path(), self.small)

    def test_one_slot_keeps_a_small_job_in_the_big_slot(self):
        slot, path = self.take(small_gib=2)
        self.assertEqual((slot, path), ('big', self.big))
        self.assertIn('one render slot', self.seen[-1][1])
        self.assertFalse(self.small.exists(), 'with one slot the small lock is never touched')
        with hold(self.big):
            with self.assertRaises(RenderBusy):
                self.take(small_gib=2)

    def test_the_switch_is_read_at_every_attempt(self):
        def switch_on():
            time.sleep(.5)
            self.switch.write_text('{"slots": 2}')
        with hold(self.big):
            flip = threading.Thread(target=switch_on)
            flip.start()
            slot, _ = self.take(small_gib=2, wait=5)
            flip.join()
        self.assertEqual(slot, 'small')


class MemoryTests(unittest.TestCase):
    def test_available_memory_counts_free_speculative_inactive_and_purgeable_pages(self):
        self.assertEqual(slots.parse_vm_stat(VM_STAT), 16384*(100000+50000+200000+10000))

    def test_unreadable_output_is_unknown(self):
        self.assertIsNone(slots.parse_vm_stat(''))
        self.assertIsNone(slots.parse_vm_stat(VM_STAT.replace('Pages purgeable', 'Pages something')))


class SmallSlotTests(SlotTestCase):
    def test_a_small_job_runs_beside_a_big_one(self):
        with hold(self.big, purpose='a game', kind='game'):
            with render_lock('small import', small_gib=2.4, on_slot=self.note) as path:
                self.assertEqual(path, self.small)
                record = json.loads(self.small.read_text())
                self.assertEqual((record['slot'], record['kind'], record['expected_gib']), ('small', 'job', 2.4))
                self.assertEqual(record['pid'], os.getpid())
        self.assertEqual(self.seen[-1][0], 'small')
        self.assertIn('20.0 GiB available', self.seen[-1][1])
        self.assertEqual(self.small.read_text(), '', 'the record goes when the slot is released')

    def test_a_small_job_prefers_the_small_slot_when_both_are_free(self):
        self.assertEqual(self.take(small_gib=1), ('small', self.small))

    def test_a_big_job_does_not_wait_for_a_small_one(self):
        with hold(self.small, slot='small'):
            self.assertEqual(self.take(), ('big', self.big))

    def test_a_second_small_job_waits_for_the_big_slot(self):
        with hold(self.small, slot='small', purpose='first small job'):
            self.assertEqual(self.take(small_gib=2)[0], 'big')
            self.assertIn('small slot is busy', self.seen[-1][1])
            with hold(self.big):
                with self.assertRaises(RenderBusy) as caught:
                    self.take(small_gib=2)
        self.assertIn('first small job', str(caught.exception))

    def test_a_job_over_three_gib_uses_the_big_slot(self):
        self.assertEqual(self.take(small_gib=3.5)[0], 'big')
        self.assertIn('3.5 GiB', self.seen[-1][1])
        with hold(self.big):
            with self.assertRaises(RenderBusy):
                self.take(small_gib=3.5)

    def test_games_and_compiles_never_use_the_small_slot(self):
        self.assertEqual(self.take(small_gib=1, kind='game')[0], 'big')
        with hold(self.big):
            with self.assertRaises(RenderBusy):
                self.take(small_gib=1, kind='game')
        self.assertEqual(self.take(small_gib=1, kind='compile')[0], 'big')

    def test_no_small_job_beside_a_compile(self):
        with hold(self.big, purpose='build compile', kind='compile'):
            with self.assertRaises(RenderBusy) as caught:
                self.take(small_gib=1)
        self.assertIn('compile', str(caught.exception))

    def test_a_compile_from_older_code_is_known_by_its_purpose(self):
        with hold(self.big, purpose='atelier build game unreal.compile', kind=None, repo=None):
            with self.assertRaises(RenderBusy):
                self.take(small_gib=1)
        with hold(self.big, purpose='atelier build game unreal.import', kind=None, repo=None):
            self.assertEqual(self.take(small_gib=1)[0], 'small')

    def test_no_small_job_beside_a_job_in_the_same_checkout(self):
        with hold(self.big, repo=str(paths.REPO)):
            with self.assertRaises(RenderBusy) as caught:
                self.take(small_gib=1)
        self.assertIn('this checkout', str(caught.exception))
        with hold(self.big, repo=None, checkout=str(paths.REPO/'platform')):
            with self.assertRaises(RenderBusy):
                self.take(small_gib=1)

    def test_little_memory_keeps_the_small_slot_shut(self):
        self.patch(slots, 'available_bytes', lambda: 8*GiB)
        self.assertEqual(self.take(small_gib=1)[0], 'big')
        self.assertIn('8.0 GiB available', self.seen[-1][1])
        with hold(self.big):
            with self.assertRaises(RenderBusy) as caught:
                self.take(small_gib=1)
        self.assertIn('8.0 GiB available', str(caught.exception))
        self.patch(slots, 'available_bytes', lambda: None)
        self.assertEqual(self.take(small_gib=1)[0], 'big')

    def test_a_dead_holder_does_not_count_as_a_compile(self):
        with hold(self.big, kind='compile', pid=999999, started=1):
            self.assertEqual(self.take(small_gib=1)[0], 'small')

    def test_a_refusal_from_the_big_slot_still_names_an_older_holder(self):
        with hold(self.big, purpose='older harness', kind=None, repo=None):
            with self.assertRaises(RenderBusy) as caught:
                self.take()
        self.assertIn(f'held by pid {os.getpid()} (older harness)', str(caught.exception))


class CompileTests(SlotTestCase):
    def test_a_compile_holds_both_slots(self):
        with render_lock('compile', kind='compile') as path:
            self.assertEqual(path, self.big)
            self.assertTrue(is_locked(self.big) and is_locked(self.small))
            self.assertEqual(json.loads(self.big.read_text())['kind'], 'compile')
        self.assertFalse(is_locked(self.big) or is_locked(self.small))
        self.assertEqual(self.big.read_text(), '')

    def test_a_compile_waits_for_a_small_job(self):
        started = threading.Event()

        def small_job():
            with hold(self.small, slot='small', purpose='short import'):
                started.set()
                time.sleep(.6)
        job = threading.Thread(target=small_job)
        job.start()
        started.wait()
        told = io.StringIO()
        begun = time.monotonic()
        with contextlib.redirect_stderr(told):
            with render_lock('compile', kind='compile'):
                waited = time.monotonic()-begun
        job.join()
        self.assertGreater(waited, .4)
        self.assertIn('short import', told.getvalue())

    def test_a_compile_gives_up_when_the_small_job_runs_too_long(self):
        self.patch(slots, 'COMPILE_WAIT', .3)
        with hold(self.small, slot='small', purpose='long import'):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(RenderBusy) as caught:
                    with render_lock('compile', kind='compile'):
                        pass
        self.assertIn('long import', str(caught.exception))
        self.assertFalse(is_locked(self.big), 'the big slot is released after the refusal')
        self.assertEqual(self.big.read_text(), '')


class ScanTests(SlotTestCase):
    """The other slot's holder is this process; its "children" come from a fixed process table."""
    def setUp(self):
        super().setUp()
        self.env(ATELIER_RENDER_LOCK_SCAN=None)
        me = os.getpid()
        self.table = [(me, 1, sys.executable), (900001, me, '/Engine/Binaries/Mac/UnrealEditor-Cmd'),
                      (900002, 900001, '/Engine/Binaries/Mac/ShaderCompileWorker'), (900003, 1, '/usr/bin/login')]
        self.patch(slots, 'process_table', lambda: list(self.table))

    def test_the_family_holds_every_descendant(self):
        self.assertEqual(slots.family(os.getpid(), self.table), {os.getpid(), 900001, 900002})

    def test_a_small_job_leaves_the_big_holders_processes_alone(self):
        with hold(self.big):
            self.assertEqual(self.take(small_gib=1)[0], 'small')

    def test_a_big_job_leaves_the_small_holders_processes_alone(self):
        with hold(self.small, slot='small'):
            self.assertEqual(self.take()[0], 'big')

    def test_an_unowned_render_process_is_still_refused(self):
        self.table.append((900004, 1, '/Applications/Blender.app/Contents/MacOS/Blender'))
        with hold(self.big):
            with self.assertRaises(RenderBusy) as caught:
                self.take(small_gib=1)
        self.assertIn('900004 Blender', str(caught.exception))
        self.assertNotIn('900001', str(caught.exception))

    def test_one_listing_serves_the_whole_scan(self):
        # A shader worker started between two listings would look foreign; the scan reads the table once.
        def listing():
            listing.calls += 1
            extra = [(900005, 900001, '/Engine/Binaries/Mac/ShaderCompileWorker')] if listing.calls > 1 else []
            return list(self.table)+extra
        listing.calls = 0
        self.patch(slots, 'process_table', listing)
        with hold(self.big):
            self.assertEqual(self.take(small_gib=1)[0], 'small')
        self.assertEqual(listing.calls, 1)

    def test_the_processes_of_a_holder_that_is_gone_count_as_foreign(self):
        with hold(self.big, started=1):
            with self.assertRaises(RenderBusy) as caught:
                self.take(small_gib=1)
        self.assertIn('900001 UnrealEditor-Cmd', str(caught.exception))

    def test_without_a_holder_every_render_process_counts(self):
        with self.assertRaises(RenderBusy):
            self.take()


class GuardedSlotTests(SlotTestCase):
    def setUp(self):
        super().setUp()
        self.limits = []

        @contextmanager
        def attach(pid, report, duration, limit_gib=10.):
            self.limits.append(limit_gib)
            Path(report).write_text('{"state": "fake"}')
            yield None
        self.patch(guarded_run, 'attach_memory_guard', attach)
        self.folder = Path(self.temp.name)/'report'

    def test_a_small_job_gets_the_four_gib_ceiling(self):
        with hold(self.big):
            self.assertEqual(guarded_run.run(QUICK, self.folder, small_gib=2, on_slot=self.note), 0)
        self.assertEqual((self.seen[-1][0], self.limits[-1]), ('small', 4.))

    def test_a_job_in_the_big_slot_keeps_ten(self):
        guarded_run.run(QUICK, self.folder)
        self.patch(slots, 'available_bytes', lambda: 1*GiB)
        guarded_run.run(QUICK, self.folder, small_gib=2)
        self.assertEqual(self.limits, [10., 10.])

    def test_the_command_line_takes_the_expected_peak_and_kind(self):
        with hold(self.big):
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                guarded_run.main(['--report', str(self.folder), '--small', '2', '--', *QUICK])
        self.assertEqual(self.limits[-1], 4.)
        self.assertIn('small render slot', printed.getvalue())
        with hold(self.big):
            with self.assertRaises(RenderBusy):
                guarded_run.main(['--report', str(self.folder), '--small', '2', '--kind', 'game', '--', *QUICK])


class BuildSlotTests(SlotTestCase):
    """`atelier build` on a stand-in game whose heavy steps print a marker; the memory guard reports set peaks."""
    def setUp(self):
        super().setUp()
        root = Path(self.temp.name)
        (root/'games'/'standin').mkdir(parents=True)
        self.patch(paths, 'GAMES', root/'games')
        self.env(ATELIER_BUILD_ROOT=str(root/'build'))
        script = root/'step.py'
        script.write_text('print("STEP DONE")\n')
        self.peaks = []

        @contextmanager
        def attach(pid, report, duration, limit_gib=10.):
            Path(report).write_text(json.dumps({'peak_bytes': int(self.peaks.pop(0)*GiB), 'state': 'running'}))
            yield None
        self.patch(guarded_run, 'attach_memory_guard', attach)
        self.steps = [builder.Step('unreal.one', [builder.Python(script)], heavy=True),
                      builder.Step('unreal.two', [builder.Python(script), builder.Python(script, ('again',))], heavy=True),
                      builder.Step('unreal.compile', [builder.UnrealCompile('StandinEditor')], heavy=True)]
        self.patch(builder, 'load_recipe', lambda game: types.SimpleNamespace(steps=lambda ctx: self.steps))
        self.logs = root/'build'/'standin'/'logs'

    def run_build(self, *wanted):
        lines = []
        with contextlib.redirect_stdout(io.StringIO()):
            code = builder.build('standin', wanted, force=True, echo=lines.append)
        self.assertEqual(code, 0, lines)
        return lines

    def test_a_step_without_a_report_takes_the_big_slot_then_the_small_one(self):
        self.peaks = [2.]
        first = self.run_build('unreal.one')
        self.assertIn('done', first[0])
        self.assertTrue(first[0].endswith(', big slot'), first[0])
        self.assertIn('render slot: big (no guard report yet)', (self.logs/'unreal.one.log').read_text())
        self.peaks = [2.]
        second = self.run_build('unreal.one')
        self.assertTrue(second[0].endswith(', small slot'), second[0])
        self.assertIn('render slot: small', (self.logs/'unreal.one.log').read_text())

    def test_a_step_with_several_commands_keeps_its_highest_peak(self):
        self.peaks = [3.5, 1.]
        self.run_build('unreal.two')
        self.assertAlmostEqual(builder.expected_peak_gib(self.logs/'unreal.two.guard'), 3.5)
        self.peaks = [1., 1.]
        lines = self.run_build('unreal.two')
        self.assertTrue(lines[0].endswith(', big slot'), lines[0])

    def test_one_slot_leaves_the_summary_as_it_was(self):
        self.env(ATELIER_RENDER_SLOTS='1')
        self.peaks = [2., 2.]
        self.run_build('unreal.one')
        lines = self.run_build('unreal.one')
        self.assertRegex(lines[0], r'done in [0-9.]+ s$')

    def test_a_compile_asks_for_the_big_slot_as_a_compile(self):
        self.assertEqual(builder.slot_request(builder.Context('standin'), self.steps[2]), ('compile', None))
        self.assertEqual(builder.slot_request(builder.Context('standin'), self.steps[0]), ('job', None))


if __name__ == '__main__':
    unittest.main()
