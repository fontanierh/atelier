"""Launch policy and actual owned-child lifecycle; no Unreal or Blender work."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier.safety import process


class PolicyTests(unittest.TestCase):
    def test_other_platforms_keep_the_argv(self):
        with patch.object(process.sys, 'platform', 'linux'):
            self.assertEqual(process.policy_command(['tool', 'a b']), ['tool', 'a b'])

    def test_jobs_restore_application_policies_without_a_qos_clamp(self):
        with patch.object(process.sys, 'platform', 'darwin'), patch.object(process.os, 'getpriority', return_value=0):
            self.assertEqual(process.policy_command(['tool', 'a b']),
                             ['/usr/sbin/taskpolicy', '-a', '/usr/bin/nice', '-n', '10', 'tool', 'a b'])

    def test_games_keep_application_qos_and_do_not_double_nice(self):
        with patch.object(process.sys, 'platform', 'darwin'), patch.object(process.os, 'getpriority', return_value=10):
            self.assertEqual(process.policy_command(['game'], kind='game'), ['/usr/sbin/taskpolicy', '-a', 'game'])

    def test_lower_caller_priority_is_preserved(self):
        with patch.object(process.sys, 'platform', 'darwin'), patch.object(process.os, 'getpriority', return_value=15):
            self.assertEqual(process.policy_command(['compile'], kind='compile'),
                             ['/usr/sbin/taskpolicy', '-a', 'compile'])

    def test_spawn_preserves_io_and_environment(self):
        env = {'SAMPLE': 'not a shell expansion'}
        with patch.object(process.sys, 'platform', 'linux'), patch.object(process.subprocess, 'Popen') as popen:
            process.spawn(['tool', '$SAMPLE'], stdout=subprocess.PIPE, env=env)
            popen.assert_called_once_with(['tool', '$SAMPLE'], stdout=subprocess.PIPE, env=env)

    def test_shell_and_empty_commands_are_refused(self):
        with self.assertRaises(ValueError): process.spawn(['tool'], shell=True)
        with self.assertRaises(TypeError): process.policy_command('tool')
        with self.assertRaises(ValueError): process.policy_command([])

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS launch policies')
    def test_native_child_and_descendant_leave_the_background_band(self):
        code = '''import os,subprocess,sys
print(subprocess.check_output(['ps','-o','pid=,ni=,pri=','-p',str(os.getpid())],text=True).strip(),flush=True)
subprocess.run([sys.executable,'-c',"import os,subprocess;print(subprocess.check_output(['ps','-o','pid=,ni=,pri=','-p',str(os.getpid())],text=True).strip(),flush=True)"],check=True)
'''
        for kind in ('job','game'):
            with self.subTest(kind=kind):
                child=process.spawn([sys.executable,'-c',code],kind=kind,stdout=subprocess.PIPE,text=True)
                output,_=child.communicate(timeout=10)
                self.assertEqual(child.returncode,0)
                rows=[list(map(int,line.split())) for line in output.splitlines()]
                self.assertEqual(len(rows),2)
                self.assertEqual(rows[0][0],child.pid, 'taskpolicy must exec, not hide the guarded PID')
                for pid,nice,priority in rows:
                    self.assertGreaterEqual(nice,10)
                    self.assertGreater(priority,4, 'inherited background clamp remains')


if __name__ == '__main__':
    unittest.main()
