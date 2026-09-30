"""The ordinary build supplies all skating data without a local disc import."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_skate_runtime', GAME / 'tools/build_skate_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeBundleTests(unittest.TestCase):
    def test_fresh_install_and_repair(self):
        manifest = json.loads((runtime.BUNDLE / 'runtime.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'assets'
            runtime.stage_assets(destination)
            for name, digest in manifest['sha256'].items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
            # A generated file can disappear or be damaged; staging must repair both.
            (destination / 'private/game.json').unlink()
            (destination / 'private/headless.glb').write_bytes(b'incomplete')
            runtime.stage_assets(destination)
            for name in ('private/game.json', 'private/headless.glb'):
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), manifest['sha256'][name])


if __name__ == '__main__':
    unittest.main()
