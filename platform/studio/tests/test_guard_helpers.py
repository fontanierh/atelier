"""CPU-only checks that the SDK helpers an owned Unreal leaves behind are ended, and nothing else.

    uv run pytest platform/studio/tests/test_guard_helpers.py

The fake game and helpers are this Python under other names (`UnrealEditor-Fake`, `dotnet`, `UnrealTraceServer`):
the guard reads a process's executable name, and a copied system binary would not run. Each helper is a real
descendant of the fake game, reparented to launchd when it exits, as Turnkey's VerifySdk was.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier.safety import guard
from atelier.safety.memory_guard import children, helpers_path, name, usage


def alive(pid, started):
    try:
        current = usage(pid)
    except ProcessLookupError:
        return False
    return current.started == started and not current.exited


@unittest.skipUnless(sys.platform == 'darwin', 'libproc')
class HelperReap(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir/'bin').mkdir()
        (self.dir/'lib').symlink_to(Path(sys.base_prefix)/'lib')   # the interpreter finds libpython at ../lib
        for executable in ('UnrealEditor-Fake', 'Blender', 'dotnet', 'UnrealTraceServer'):
            os.link(os.path.realpath(sys.executable), self.dir/'bin'/executable)
        self.env = dict(os.environ, PYTHONHOME=sys.base_prefix)
        self.leftovers = []
        self.addCleanup(self.end_leftovers)

    def end_leftovers(self):
        for pid, started in self.leftovers:
            if alive(pid, started):
                os.kill(pid, signal.SIGKILL)

    def run_python(self, executable, code, **kwargs):
        return subprocess.Popen([str(self.dir/'bin'/executable), '-c', code], env=self.env, **kwargs)

    def game(self, helpers, seconds, executable='UnrealEditor-Fake'):
        """A fake game that starts `helpers` (name, seconds) as its children and exits after `seconds`."""
        spawn = ''.join(f"subprocess.Popen([{str(self.dir/'bin'/n)!r}, '-c', 'import time; time.sleep({s})']);"
                        for n, s in helpers)
        game = self.run_python(executable, f'import subprocess, time; {spawn} time.sleep({seconds})')
        deadline = time.monotonic()+5
        while len(children(game.pid)) < len(helpers) and time.monotonic() < deadline:
            time.sleep(.05)
        kids = {name(pid): (pid, usage(pid).started) for pid in children(game.pid)}
        self.leftovers += kids.values()
        return game, kids

    def test_ends_the_orphaned_sdk_helper_and_keeps_shared_services(self):
        game, kids = self.game([('dotnet', 120), ('UnrealTraceServer', 120)], 2.5)
        report = self.dir/'memory-health.json'
        with guard.attach(game.pid, report, duration=60) as monitor:
            self.assertIsNotNone(monitor)
            game.wait(timeout=10)
        self.assertFalse(alive(*kids['dotnet']), 'the orphaned helper survived its game')
        self.assertTrue(alive(*kids['UnrealTraceServer']), 'a shared service was ended')
        record = json.loads(helpers_path(report).read_text())
        self.assertEqual([h['name'] for h in record['reaped']], ['dotnet'])

    def test_reap_waits_for_the_game_and_then_ends_its_helpers(self):
        game, kids = self.game([('dotnet', 120)], 60)
        report = self.dir/'memory-health.json'
        with guard.attach(game.pid, report, duration=60):
            time.sleep(1.5)
            self.assertEqual(guard.reap_helpers(game.pid), [], 'helpers were ended while the game ran')
            self.assertTrue(alive(*kids['dotnet']))
        # The harness's reap runs after `attach` while the game is still up (an exception, the deadline).
        self.assertTrue(alive(*kids['dotnet']))
        guard.reap(game, grace=2)
        self.assertFalse(alive(*kids['dotnet']))

    def test_a_game_that_is_not_unreal_records_nothing(self):
        game, kids = self.game([('dotnet', 120)], 2.5, executable='Blender')
        report = self.dir/'memory-health.json'
        with guard.attach(game.pid, report, duration=60):
            game.wait(timeout=10)
        self.assertTrue(alive(*kids['dotnet']))
        self.assertFalse(helpers_path(report).exists())

    def test_never_signals_a_reused_pid_or_a_process_that_is_not_the_games(self):
        game = self.run_python('UnrealEditor-Fake', 'pass')
        started = usage(game.pid).started
        game.wait(timeout=10)
        # Named like a helper and alive, but a child of this test: never the game's.
        stranger = self.run_python('dotnet', 'import time; time.sleep(120)')
        self.leftovers.append((stranger.pid, usage(stranger.pid).started))
        entry = dict(pid=stranger.pid, name='dotnet', parent=game.pid, parent_started=started, depth=1)
        record = self.dir/'memory-health.helpers.json'
        record.write_text(json.dumps(dict(game=game.pid, game_started=started, helpers=[
            dict(entry, started=usage(stranger.pid).started+1),   # the pid, reused by another process
            dict(entry, started=usage(stranger.pid).started),     # the process, now under a living parent
        ])))
        guard._owned[game.pid] = (record, started)
        self.assertEqual(guard.reap_helpers(game.pid, grace=.5), [])
        self.assertIsNone(stranger.poll())


if __name__ == '__main__':
    unittest.main()
