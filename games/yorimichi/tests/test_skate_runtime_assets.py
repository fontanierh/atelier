"""The ordinary build supplies all skating data without a local disc import."""
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import unittest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_skate_runtime', GAME / 'tools/build_skate_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeDataTests(unittest.TestCase):
    def test_tracked_data_matches_manifest(self):
        runtime.verify_assets()

    def test_missing_or_corrupt_data_fails_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'assets'
            shutil.copytree(runtime.ASSETS, destination)
            source = destination / 'private/game.json'
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing tracked Skate runtime asset: private/game.json'):
                runtime.verify_assets(destination)
            self.assertFalse(source.exists())
            source.write_bytes(b'incomplete')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch: private/game.json'):
                runtime.verify_assets(destination)
            self.assertEqual(source.read_bytes(), b'incomplete')

    def test_no_unmanifested_runtime_files(self):
        manifest = json.loads((runtime.BUNDLE / 'runtime.json').read_text())
        files = {p.relative_to(runtime.ASSETS).as_posix() for p in runtime.ASSETS.rglob('*') if p.is_file()}
        self.assertEqual(files, set(manifest['sha256']))


if __name__ == '__main__':
    unittest.main()
