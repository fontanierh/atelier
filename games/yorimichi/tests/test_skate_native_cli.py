"""Explicit QA checks over the sole native Session's CLI command transport.

Run only under the render lock/memory guard with an already built native CLI:
  python3 games/yorimichi/tests/test_skate_native_cli.py --binary BINARY --output OUTPUT

Ordinary unit discovery skips this simulation check. No executable is built, no
Rust worker is located, and no alternate runtime is selected by this module.
Numerical latest-main parity/retained Tune writes remain in the full Session proof.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

GAME = Path(__file__).resolve().parents[1]
OPTIONS = None


def step(**changed):
    command = dict(op='step', dt=1/30, buttons=0, left=[0, 0], right=[0, 0], triggers=[0, 0])
    command.update(changed)
    return command


class NativeCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if OPTIONS is None:
            raise unittest.SkipTest('Native simulation QA requires an explicit --binary and root-owned guard')
        cls.binary, cls.package, cls.output = OPTIONS.binary, OPTIONS.native_package, OPTIONS.output
        spec = importlib.util.spec_from_file_location('verify_skate_native', GAME/'tools/verify_skate_native.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        descriptor = GAME/'assets/skate/runtime.json'
        cls.package = cls.package or verifier.PACKAGE
        verifier.verify_bundle(cls.package, descriptor)
        if not cls.binary.is_file():
            raise FileNotFoundError('Explicit native CLI is missing; build it separately under the render guard')
        cls.output.mkdir(parents=True, exist_ok=True)
        cls.world = cls.output/'world.json'
        cls.world.write_text(json.dumps(dict(triangles=[
            [[-100,0,-100],[-100,0,100],[100,0,100]],
            [[-100,0,-100],[100,0,100],[100,0,-100]]],
            rails=[], spawn=[0,0,0], heading=0)))
        cls.serial = 0

    def run_cli(self, commands):
        type(self).serial += 1
        case = self.output/f'{self._testMethodName}-{self.serial}'
        text = ''.join((json.dumps(command, allow_nan=False) if isinstance(command, dict) else command)+'\n'
                       for command in commands)
        # subprocess execution occurs only when root invokes this explicit QA test.
        completed = subprocess.run([str(self.binary), str(self.package), str(self.world)],
            input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        case.with_suffix('.commands.jsonl').write_text(text)
        case.with_suffix('.stdout.jsonl').write_text(completed.stdout)
        case.with_suffix('.stderr.log').write_text(completed.stderr)
        rows = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertTrue(rows)
        self.assertEqual(rows[0]['type'], 'ready')
        self.assertEqual(len(rows[0]['names']), len(rows[0]['reference']))
        return completed.returncode, rows

    def assert_default_equivalent(self, op, goofy):
        command = dict(op=op, goofy=goofy, difficulty='normal', trucks=.5)
        if op == 'activate':
            command.update(spawn=[0,0,0], heading=0, generation=17, velocity=[0,0,5])
        suffix = [step(buttons=0x1000 if i<12 else 0) for i in range(24)] + [dict(op='quit')]
        missing_status, missing = self.run_cli([command, *suffix])
        explicit_status, explicit = self.run_cli([dict(command, vert_assist=0), *suffix])
        self.assertEqual(missing_status, 0)
        self.assertEqual(explicit_status, 0)
        self.assertEqual(missing, explicit)  # All public pose/score/camera fields at every command.
        self.assertGreater(missing[-1]['tick'], missing[0]['tick'])
        self.assertNotEqual(missing[-1]['bones'], missing[0]['bones'])

    def test_configure_and_activate_default_assist(self):
        for op in ('configure', 'activate'):
            for goofy in (False, True):
                with self.subTest(op=op, goofy=goofy):
                    self.assert_default_equivalent(op, goofy)

    def test_all_valid_assist_endpoints_are_accepted(self):
        for value in (0, .5, 1):
            with self.subTest(vert_assist=value):
                status, rows = self.run_cli([
                    dict(op='configure', goofy=False, difficulty='normal', trucks=.5, vert_assist=value),
                    dict(op='activate', goofy=True, difficulty='normal', trucks=.5,
                         spawn=[0,0,0], heading=0, generation=23, vert_assist=value),
                    step(), dict(op='quit')])
                self.assertEqual(status, 0)
                self.assertEqual([r['type'] for r in rows], ['ready', 'pose', 'pose'])
                self.assertEqual(rows[-1]['generation'], 23)

    def test_rejects_malformed_command_domains(self):
        invalid = [
            step(left=[40000,0]), step(left=[-32769,0]), step(right=[32768,0]),
            step(buttons=65536), step(buttons=-1), step(triggers=[256,0]),
            step(left=[0]), step(left=[0.5,0]),
            dict(op='quit', unexpected=True),
            dict(op='configure', goofy=False, difficulty='normal', trucks=.5, vert_assist='1'),
            dict(op='configure', goofy=False, difficulty='normal', trucks=.5, vert_assist=-1.401298464324817e-45),
            dict(op='configure', goofy=False, difficulty='normal', trucks=.5, vert_assist=1.0000001192092896),
            '{"op":"configure","goofy":false,"difficulty":"normal","trucks":0.5,"vert_assist":NaN}',
            '{"op":"configure","goofy":false,"difficulty":"normal","trucks":0.5,"vert_assist":0,"vert_assist":1}',
        ]
        for command in invalid:
            with self.subTest(command=command):
                status, rows = self.run_cli([command, step(), dict(op='quit')])
                self.assertNotEqual(status, 0)
                self.assertEqual([r['type'] for r in rows], ['ready', 'error'])
                self.assertTrue(rows[-1]['message'])
                # The invalid command must never reach a subsequent published simulation step.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--native-package', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    OPTIONS, unittest_args = parser.parse_known_args()
    unittest.main(argv=[__file__, *unittest_args])
