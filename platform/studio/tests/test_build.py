import tempfile, unittest
from pathlib import Path

from atelier.build import Step, fingerprint, order


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


if __name__ == '__main__':
    unittest.main()
