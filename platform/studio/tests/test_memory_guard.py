"""macOS integration tests: real child allocations, identity and fail-closed behavior."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from atelier.safety.memory_guard import guard,usage

class MemoryGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.child=subprocess.Popen([sys.executable,'-c','import time; x=bytearray(80*1024*1024); print("ready",flush=True); time.sleep(30)'],stdout=subprocess.PIPE,text=True)
        self.child.stdout.readline()
        self.report=Path(self.tmp.name)/'health.json'
    def tearDown(self):
        if self.child.poll() is None:self.child.kill()
        self.child.wait();self.child.stdout.close();self.tmp.cleanup()
    def test_footprint_limit(self):
        guard(self.child.pid,40*1024**2,self.report)
        self.assertEqual(self.child.wait(timeout=2),-9)
        self.assertEqual(json.loads(self.report.read_text())['state'],'memory_limit')
    def test_wrong_identity_never_signalled(self):
        guard(self.child.pid,1,self.report,expected_start=usage(self.child.pid).started+1)
        self.assertIsNone(self.child.poll())
    def test_report_failure_stops_game(self):
        self.report.mkdir()
        with self.assertRaises(OSError):guard(self.child.pid,1024**3,self.report)
        self.assertEqual(self.child.wait(timeout=2),-9)
    def test_bounded_test_duration(self):
        guard(self.child.pid,1024**3,self.report,duration=0)
        self.assertEqual(self.child.wait(timeout=2),-9)
        self.assertEqual(json.loads(self.report.read_text())['state'],'test_duration')

if __name__=='__main__':unittest.main()
