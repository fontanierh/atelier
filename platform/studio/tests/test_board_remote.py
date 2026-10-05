"""Fault injection for recovery decisions, process protection, and session isolation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from atelier import board_remote as w


@pytest.fixture(autouse=True)
def owned_services(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'OWNED', {f'test.remote.{i}': (f'session {i}', tmp_path / str(i)) for i in range(3)})
    monkeypatch.setattr(w, 'HOME', tmp_path)
    monkeypatch.setattr(w, 'ROOT', tmp_path / 'supervisor')
    (tmp_path / 'supervisor').mkdir()



class RecoveryPolicy(unittest.TestCase):
    def test_multiple_samples_and_elapsed_time_are_both_required(self):
        state = {}
        self.assertEqual(w.decide(state, 0, "1:1", "disconnected"), "startup_grace")
        self.assertEqual(w.decide(state, 130, "1:1", "disconnected"), "confirming_disconnect")
        self.assertEqual(w.decide(state, 160, "1:1", "disconnected"), "terminate")
        state = {"identity": "1:1", "first_seen": 0}
        for now in (130, 131, 132):
            self.assertEqual(w.decide(state, now, "1:1", "disconnected"), "confirming_disconnect")
        self.assertEqual(w.decide(state, 190, "1:1", "disconnected"), "terminate")

    def test_connection_recovery_or_api_failure_discards_stale_evidence(self):
        for status in ("connected", None):
            state = {"identity": "1:1", "first_seen": 0}
            w.decide(state, 130, "1:1", "disconnected")
            w.decide(state, 160, "1:1", "disconnected")
            w.decide(state, 170, "1:1", status)
            self.assertEqual(w.decide(state, 200, "1:1", "disconnected"), "confirming_disconnect")
            self.assertEqual(state["bad_count"], 1)

    def test_restart_changes_identity_and_honors_cooldown(self):
        state = {"identity": "1:1", "first_seen": 0, "restarts": [190],
                 "pending": {"time": 190, "signal": "SIGTERM"}}
        self.assertEqual(w.decide(state, 220, "2:2", "disconnected"), "startup_grace")
        self.assertIsNone(state["pending"])
        w.decide(state, 310, "2:2", "disconnected")
        self.assertEqual(w.decide(state, 340, "2:2", "disconnected"), "restart_cooldown")
        self.assertEqual(w.decide(state, 490, "2:2", "disconnected"), "terminate")

    def test_graceful_shutdown_precedes_escalation(self):
        state = {"identity": "1:1", "first_seen": 0, "bad_count": 3, "first_bad": 100,
                 "restarts": [190], "pending": {"time": 190, "signal": "SIGTERM"}}
        self.assertEqual(w.decide(state, 250, "1:1", "disconnected"), "waiting_for_restart")
        self.assertEqual(w.decide(state, 280, "1:1", "disconnected"), "kill")
        self.assertEqual(w.decide(state, 290, "1:1", "connected"), "healthy")
        self.assertIsNone(state["pending"])

    def test_restart_storm_is_bounded_and_retry_eventually_returns(self):
        state = {"identity": "1:1", "first_seen": 0, "bad_count": 3, "first_bad": 100,
                 "restarts": [200, 600, 1000]}
        self.assertEqual(w.decide(state, 1500, "1:1", "disconnected"), "restart_budget_wait")
        self.assertEqual(w.decide(state, 3801, "1:1", "disconnected"), "terminate")


class ProcessProtection(unittest.TestCase):
    def setUp(self):
        stale = patch.object(w, "stale_read_only_query", return_value=False)
        stale.start()
        self.addCleanup(stale.stop)
        self.table = {10: (1, "S", "/opt/homebrew/bin/claude"),
                      11: (10, "S", "/opt/homebrew/bin/claude"),
                      12: (11, "Ss", "/bin/zsh"), 13: (12, "S", "/bin/sleep"),
                      20: (1, "S", "/foreign/UnrealEditor")}
        self.start = lambda pid: pid * 100

    def blocker(self, table=None, locks=()):
        return w.restart_blocker(10, 1000, self.table if table is None else table,
                                 locks, self.start)

    def test_idle_waiter_and_foreign_build_do_not_block_scoped_recovery(self):
        self.assertIsNone(self.blocker(locks=[{"pid": 20, "started": 2000}]))

    def test_every_actual_tool_is_protected(self):
        for executable in ("UnrealEditor", "clang++", "dotnet", "blender", "python3", "git"):
            table = dict(self.table, **{})
            table[14] = (12, "S", "/tools/" + executable)
            self.assertEqual(self.blocker(table), "active_tool_process")

    def test_live_lock_owner_is_protected_even_for_allowed_executable(self):
        self.assertEqual(self.blocker(locks=[{"pid": 12, "started": 1200}]), "active_render_holder")
        self.assertIsNone(self.blocker(locks=[{"pid": 12, "started": 1199}]))

    def test_pid_reuse_and_zombies(self):
        self.assertEqual(w.restart_blocker(10, 999, self.table, [], self.start), "process_changed")
        table = dict(self.table)
        table[14] = (11, "Z", "python3")
        self.assertIsNone(self.blocker(table))


class SessionIsolation(unittest.TestCase):
    def setUp(self):
        inbox = patch.object(w, "inbox_responsive", return_value=True)
        inbox.start()
        self.addCleanup(inbox.stop)
    def test_offline_worker_recovers_only_its_own_service(self):
        labels = list(w.OWNED)
        states = {label: {"identity": f"{100+i}:{100+i}", "first_seen": 0}
                  for i, label in enumerate(labels)}
        signals = []
        with patch.object(w, "launch_pid", side_effect=lambda label: 100 + labels.index(label)), \
             patch.object(w, "process_start", side_effect=lambda pid: pid), \
             patch.object(w, "validate_service", side_effect=lambda label: w.OWNED[label][1]), \
             patch.object(w, "current_session", return_value="cse_test"), \
             patch.object(w, "restart_blocker", return_value=None), \
             patch.object(w, "pin_resume"), \
             patch.object(w, "process_table", return_value={100: (1, 'S', 'claude')}), \
             patch.object(w, "finish_retiring"), \
             patch.object(w, "command", side_effect=lambda argv: signals.append(argv) or ""), \
             patch.object(w, "report", side_effect=lambda state, health, label: state.update(health=health)):
            for now in (130, 160, 190):
                with patch.object(w.time, "time", return_value=now):
                    for label in labels:
                        connected = "disconnected" if label == labels[0] else "connected"
                        with patch.object(w, "remote_status", return_value={"status": "active", "connection_status": connected}):
                            w.check_session(label, states[label], "fixture")
            self.assertEqual(signals, [["/bin/launchctl", "bootout", f"{w.DOMAIN}/{labels[0]}"],
                ["/bin/launchctl", "bootstrap", w.DOMAIN,
                 str(w.HOME / "Library/LaunchAgents" / f"{labels[0]}.plist")]])
            self.assertEqual([states[label]["health"] for label in labels[1:]], ["healthy", "healthy"])
            # A newly active build blocks escalation of the old, unresponsive supervisor.
            with patch.object(w.time, "time", return_value=300), \
                 patch.object(w, "remote_status", return_value={"status": "active", "connection_status": "disconnected"}), \
                 patch.object(w, "restart_blocker", return_value="active_render_holder"):
                w.check_session(labels[0], states[labels[0]], "fixture")
            self.assertEqual(len(signals), 2)
            self.assertEqual(states[labels[0]]["health"], "recovery_deferred_active_render_holder")

    def test_api_auth_outage_does_not_restart_any_service(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(w, "ROOT", Path(directory)), \
             patch.object(w, "keychain_token", side_effect=w.CheckError("keychain_auth_unavailable")), \
             patch.object(w, "command") as command, patch.object(w, "report"):
            w.main()
            self.assertFalse(command.called)
            state = json.loads((Path(directory) / "status.json").read_text())
            self.assertEqual(len(state["sessions"]), 3)

    def test_archived_session_is_never_reopened(self):
        label = next(iter(w.OWNED))
        state = {"identity": "100:100", "first_seen": 0, "bad_count": 10, "first_bad": 1}
        with patch.object(w.time, "time", return_value=400), \
             patch.object(w, "launch_pid", return_value=100), \
             patch.object(w, "process_start", return_value=100), \
             patch.object(w, "validate_service", return_value=w.OWNED[label][1]), \
             patch.object(w, "current_session", return_value="cse_test"), \
             patch.object(w, "remote_status", return_value={"status": "archived", "connection_status": "disconnected"}), \
             patch.object(w, "command") as command, patch.object(w, "report"):
            w.check_session(label, state, "fixture")
            self.assertFalse(command.called)
            self.assertEqual(state["bad_count"], 0)


class FailureModes(unittest.TestCase):
    def test_old_worker_exits_before_replacement_is_bootstrapped(self):
        label = next(iter(w.OWNED))
        table = {10: (1, 'S', 'claude'), 11: (10, 'S', 'claude.exe')}
        live = {10, 11}
        events = []

        def command(argv):
            events.append(argv[1])
            if argv[1] == 'bootout':
                live.discard(10)
                table[11] = (1, 'S', 'claude.exe')
            if argv[1] == 'bootstrap':
                self.assertFalse(live)
            return ''

        def signal(pid, _):
            events.append('stop-old-worker')
            live.discard(pid)

        with patch.object(w, 'launch_pid', return_value=10), \
             patch.object(w, 'process_table', return_value=table), \
             patch.object(w, 'process_start', side_effect=lambda pid: pid*100 if pid in live else None), \
             patch.object(w, 'restart_blocker', return_value=None), \
             patch.object(w, 'pin_resume'), patch.object(w, 'command', side_effect=command), \
             patch.object(w.os, 'kill', side_effect=signal), patch.object(w.time, 'sleep'):
            w.recover_service(label, 'cse_fixture', {})
        self.assertEqual(events, ['bootout', 'stop-old-worker', 'bootstrap'])

    def test_new_heavy_work_blocks_recovery_before_service_configuration_changes(self):
        with patch.object(w, 'launch_pid', return_value=10), \
             patch.object(w, 'process_table', return_value={10:(1,'S','claude')}), \
             patch.object(w, 'process_start', return_value=100), \
             patch.object(w, 'restart_blocker', return_value='active_render_holder'), \
             patch.object(w, 'pin_resume') as pin, patch.object(w, 'command') as command:
            with self.assertRaisesRegex(w.CheckError, 'active_render_holder'):
                w.recover_service(next(iter(w.OWNED)), 'cse_fixture', {})
            self.assertFalse(pin.called)
            self.assertFalse(command.called)

    def test_only_stale_non_mutating_queries_can_be_abandoned(self):
        for args, age, expected in [("bfs / -name file", "20:00", True),
                ("find / -delete", "20:00", False), ("find / -exec touch x ;", "20:00", False),
                ("head -20", "00:30", False), ("python3 render.py", "20:00", False)]:
            with patch.object(w, "command", side_effect=[age, args]):
                self.assertEqual(w.stale_read_only_query(10), expected)

    def test_connected_but_frozen_inbox_triggers_scoped_recovery(self):
        label = list(w.OWNED)[1]
        state = {"identity": "100:100", "first_seen": 0, "bad_count": 3, "first_bad": 100}
        with patch.object(w.time, "time", return_value=400), \
             patch.object(w, "launch_pid", return_value=100), \
             patch.object(w, "process_start", return_value=100), \
             patch.object(w, "validate_service", return_value=w.OWNED[label][1]), \
             patch.object(w, "current_session", return_value="cse_test"), \
             patch.object(w, "remote_status", return_value={"status": "active", "connection_status": "connected"}), \
             patch.object(w, "inbox_responsive", return_value=False), \
             patch.object(w, "restart_blocker", return_value=None), \
             patch.object(w, "recover_service") as recover, patch.object(w, "report"):
            w.check_session(label, state, "fixture")
            recover.assert_called_once_with(label, "cse_test", state)
            self.assertFalse(state['inbox_responsive'])


if __name__ == "__main__":
    unittest.main()
