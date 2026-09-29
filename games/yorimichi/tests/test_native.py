"""Pure C++ logic tested outside Unreal: compile each test with clang++ and run it."""
import shutil, subprocess, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class NativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('clang++'), 'clang++ not installed')
    def test_sprint_stamina(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'sprint_stamina'
            subprocess.run(['clang++', '-std=c++17', str(HERE / 'sprint_stamina.cpp'), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
