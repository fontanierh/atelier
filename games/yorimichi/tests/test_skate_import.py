"""Data boundary checks: endian/layout, inheritance and authored PAT variants."""
import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).resolve().parents[1]/'tools/import_skate_native.py'
spec = importlib.util.spec_from_file_location('skate_import', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SkateImportTests(unittest.TestCase):
    def test_schema_graph_and_inherited_override(self):
        def scalar(value):
            return {'type': 'EA::Reflection::Float', 'data': struct.pack('>f', value).hex()}
        values = [0, 0, 8, 1] + list(range(8)) + [i/7 for i in range(8)]
        graph = {'type': 'Sk8::PointNegGraphData8', 'data': struct.pack('>20f', *values).hex()}
        data = {'collections': [
            {'class': 'physics_steering', 'key': 'default', 'parent': '', 'fields': {'Damping': scalar(.7), 'Curve': graph}},
            {'class': 'physics_steering', 'key': 'child', 'parent': 'default', 'fields': {'Damping': scalar(.5)}}]}
        result = module.parameters(data)
        self.assertEqual(result['physics_steering/child/Damping'], .5)
        self.assertEqual(result['physics_steering/child/Curve'][0], list(range(8)))
        self.assertEqual(result['physics_steering/default/Curve'][1][-1], 1)
        data['collections'][0]['parent'] = 'child'
        with self.assertRaises(ValueError):
            module.parameters(data)

    def test_pattern_variants_and_tolerance(self):
        data = module.patterns('''global_tolerance_dist .4
pattern Ollie
 tolerance_dist .55
 coord 0 1
 coord 0 -1
pattern Ollie
 coord .1 1
 coord .1 -1
''')
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['tolerance'], .55)
        self.assertEqual(data[1]['tolerance'], .4)
        self.assertEqual(data[0]['points'], [[0, 1], [0, -1]])
        with self.assertRaises(ValueError):
            module.patterns('pattern incomplete\ncoord 0 1')


if __name__ == '__main__':
    unittest.main()
