import tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from atelier.build import Step, Python, fingerprint, order


def steps():
    return [
        Step('compile', ['cc']),
        Step('art', ['blender']),
        Step('import', ['unreal'], needs=['art'], after=['compile']),
        Step('other', ['x']),
    ]


class BuildTests(unittest.TestCase):
    def test_order_pulls_in_needs_and_after(self):
        self.assertEqual([s.name for s in order(steps(), ['import'])], ['compile', 'art', 'import'])

    def test_order_prefix_selects_a_group(self):
        group = [Step('unreal.a', []), Step('unreal.b', []), Step('world.c', [])]
        self.assertEqual([s.name for s in order(group, ['unreal'])], ['unreal.a', 'unreal.b'])

    def test_after_does_not_feed_the_fingerprint(self):
        step = steps()[2]
        base = fingerprint(step, {'art': 'a1', 'compile': 'c1'})
        self.assertEqual(fingerprint(step, {'art': 'a1', 'compile': 'c2'}), base)
        self.assertNotEqual(fingerprint(step, {'art': 'a2', 'compile': 'c1'}), base)

    def test_docs_in_a_source_folder_do_not_change_the_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'build.py').write_text('print(1)')
            step = Step('region', ['blender'], inputs=[Path(folder)])
            base = fingerprint(step, {})
            (Path(folder) / 'README.md').write_text('notes')
            self.assertEqual(fingerprint(step, {}), base)
            (Path(folder) / 'build.py').write_text('print(2)')
            self.assertNotEqual(fingerprint(step, {}), base)

    def test_unreal_outputs_do_not_invalidate_source_but_code_does(self):
        with tempfile.TemporaryDirectory() as folder:
            plugin = Path(folder) / 'Plugin'
            source = plugin / 'Source' / 'Example.cpp'
            source.parent.mkdir(parents=True)
            source.write_text('int value = 1;')
            step = Step('compile', ['cc'], inputs=[plugin])
            before = fingerprint(step, {})
            for name in ('Binaries', 'Intermediate', 'Saved', 'DerivedDataCache'):
                generated = plugin / name / 'generated.bin'
                generated.parent.mkdir()
                generated.write_bytes(b'output')
                self.assertEqual(fingerprint(step, {}), before)
            source.write_text('int value = 2;')
            self.assertNotEqual(fingerprint(step, {}), before)

    def test_commands_are_portable_between_checkouts_and_build_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            fingerprints = []
            for name in ('first', 'second'):
                repo = Path(folder) / name
                repo.mkdir()
                script = repo / 'generate.py'
                script.write_text('print(1)')
                output = Path(folder) / (name + '-outputs')
                step = Step('art', [Python(script, args=(output / 'mesh.glb',))], inputs=[script])
                with patch('atelier.build.paths.REPO', repo), patch('atelier.build.paths.build_root', return_value=output):
                    fingerprints.append(fingerprint(step, {}))
            self.assertEqual(*fingerprints)


if __name__ == '__main__':
    unittest.main()
