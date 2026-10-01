"""Normal builds validate only committed project-native skating data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_skate_native', GAME / 'tools/verify_skate_native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def words(*values):
    return struct.pack('<' + 'I' * len(values), *values)


def text(value):
    raw = value.encode()
    return words(len(raw)) + raw


def write_manifest(bundle, descriptor, *, change=None):
    files = {p.relative_to(bundle).as_posix(): {'bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in bundle.rglob('*') if p.is_file() and p.name != native.MANIFEST}
    manifest = dict(version=1, formats=list(native.FORMATS), source_identity='a' * 64,
                    files=files, clips=1, animation_frames=2, patterns=1,
                    metadata_banks=2, bytes=sum(row['bytes'] for row in files.values()))
    if change:
        change(manifest)
    raw = (json.dumps(manifest, indent=2) + '\n').encode()
    (bundle / native.MANIFEST).write_bytes(raw)
    descriptor.write_text(json.dumps(dict(version=3, backend='in-process-cpp',
        manifest_sha256=hashlib.sha256(raw).hexdigest(), source_identity='a' * 64,
        formats=list(native.FORMATS), expected={'payloads': len(files),
        **{key: manifest[key] for key in ('clips', 'animation_frames', 'patterns', 'metadata_banks', 'bytes')}})))


def fixture(folder):
    """Small native-only layout fixture; no original data reader or converter."""
    bundle, descriptor = folder / 'native', folder / 'runtime.json'
    for name, magic in native.REQUIRED.items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(magic + words(1, 1))
    (bundle / 'physics-skeletons.skate').write_bytes(b'ATPHYS01' + text('a' * 64) + words(1))
    for bank in (0, 1):
        (bundle / f'metadata/bank-{bank}.skate').write_bytes(
            b'ATMETA01' + text('fixture') + text('a' * 64) + words(48, 0))
    (bundle / 'animation/rig.skate').write_bytes(
        b'ATSKEL01' + words(1, 0) + text('ROOT') + words(0xffffffff, 0xffffffff, 0))
    (bundle / 'gestures.skate').write_bytes(b'ATGEST01' + words(1) + text('main')
        + words(1, 1) + text('Ollie') + words(0, 2, 0, 0, 0, 0))
    clip = bundle / 'animation/clips/0/TEST.skate'
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b'ATCLIP01' + text('TEST') + words(0, 0, 0, 0x41f00000)
        + words(*([0] * 7)) + words(0, 1, 0x3f800000, 2, 1)
        + words(*([1, 0] * 10)))
    write_manifest(bundle, descriptor)
    return bundle, descriptor


class NativeDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.bundle, self.descriptor = fixture(Path(self.temporary.name))

    def verify(self):
        return native.verify_bundle(self.bundle, self.descriptor)

    def test_committed_bundle_matches_native_manifest(self):
        result = native.verify_bundle()
        self.assertEqual((result['payloads'], result['clips'], result['animation_frames'],
                          result['patterns'], result['metadata_banks'], result['bytes']),
                         (3334, 3324, 131642, 285, 2, 70695340))

    def test_small_native_bundle_counts(self):
        result = self.verify()
        self.assertEqual((result['payloads'], result['clips'], result['animation_frames'], result['patterns']),
                         (11, 1, 2, 1))

    def test_missing_file_is_rejected_without_repair(self):
        target = self.bundle / 'settings.skate'
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'file set differs'):
            self.verify()
        self.assertFalse(target.exists())

    def test_size_and_checksum_fail_without_mutating_source(self):
        target = self.bundle / 'settings.skate'
        original = target.read_bytes()
        for raw, message in ((original[:-1], 'size mismatch'),
                             (original[:-1] + b'x', 'checksum mismatch')):
            target.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, message):
                self.verify()
            self.assertEqual(target.read_bytes(), raw)

    def test_extra_file_and_symlink_are_rejected(self):
        extra = self.bundle / 'unlisted.skate'
        extra.write_bytes(b'ATATTR01')
        with self.assertRaisesRegex(ValueError, 'file set differs'):
            self.verify()
        extra.unlink()
        extra.symlink_to(self.descriptor)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.verify()

    def test_unsafe_manifest_paths(self):
        for name in ('../outside', '/outside', 'C:/outside', 'a\\b', './settings.skate',
                     'a//b', '.', 'a/../b', ''):
            with self.subTest(name=name):
                write_manifest(self.bundle, self.descriptor,
                    change=lambda m: m['files'].__setitem__(name, m['files'].pop('settings.skate')))
                with self.assertRaisesRegex(ValueError, 'Invalid native skating asset path'):
                    self.verify()

    def test_manifest_pin_and_duplicate_json_keys(self):
        manifest = self.bundle / native.MANIFEST
        manifest.write_bytes(manifest.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'manifest checksum mismatch'):
            self.verify()
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            native.load_json(b'{"version":1,"version":1}')

    def test_required_header_even_with_matching_hash(self):
        target = self.bundle / 'settings.skate'
        target.write_bytes(b'ORIGINAL' + target.read_bytes()[8:])
        write_manifest(self.bundle, self.descriptor)
        with self.assertRaisesRegex(ValueError, 'format mismatch'):
            self.verify()

    def test_native_layout_counts_and_truncation(self):
        write_manifest(self.bundle, self.descriptor, change=lambda m: m.update(animation_frames=3))
        with self.assertRaisesRegex(ValueError, 'payload counts differ'):
            self.verify()
        target = self.bundle / 'animation/clips/0/TEST.skate'
        target.write_bytes(target.read_bytes()[:-4])
        write_manifest(self.bundle, self.descriptor)
        with self.assertRaisesRegex(ValueError, 'Truncated native skating data'):
            self.verify()

    def test_source_identity_and_required_formats(self):
        target = self.bundle / 'physics-skeletons.skate'
        target.write_bytes(b'ATPHYS01' + text('b' * 64) + words(1))
        write_manifest(self.bundle, self.descriptor)
        with self.assertRaisesRegex(ValueError, 'physical source identity differs'):
            self.verify()
        write_manifest(self.bundle, self.descriptor, change=lambda m: m['formats'].pop())
        with self.assertRaisesRegex(ValueError, 'required formats differ'):
            self.verify()

    def test_build_step_only_verifies_native_data(self):
        repository = GAME.parents[1]
        with patch.object(sys, 'path', [str(repository / 'platform/studio'), *sys.path]):
            from atelier import build
            recipe = build.load_recipe(GAME.name)
        output = Path(self.temporary.name) / 'output'
        data = Path(self.temporary.name) / 'Data'
        context = SimpleNamespace(game=GAME.name, out=output,
                                  uproject=GAME / 'unreal/Yorimichi.uproject')
        # Recipe construction only: no build command, editor, compiler or cache write.
        with patch.object(recipe.paths, 'content_data', return_value=data), \
             patch.object(recipe.paths, 'cache_dir', return_value=output / 'cache'):
            declared = recipe.steps(context)
        steps = {step.name: step for step in declared}
        runtime, compile_step = steps['skate.runtime'], steps['unreal.compile']
        descriptor = json.loads((GAME / 'assets/skate/runtime.json').read_text())
        self.assertEqual(descriptor['backend'], 'in-process-cpp')
        bundle = GAME / descriptor['data_directory']
        self.assertEqual(bundle, GAME / 'unreal/Content/Data/SkateNative')
        report = output / 'skate-native/verification.json'
        self.assertEqual(len(runtime.commands), 1)
        self.assertIsInstance(runtime.commands[0], build.Python)
        self.assertEqual(runtime.commands[0].script, GAME / 'tools/verify_skate_native.py')
        self.assertEqual(tuple(runtime.commands[0].args), ('--output', report))
        self.assertEqual(set(runtime.inputs), {GAME / 'tools/verify_skate_native.py',
                         GAME / 'assets/skate/runtime.json', data / bundle.name})
        self.assertEqual(runtime.outputs, [report])
        self.assertEqual(runtime.needs, [])
        self.assertFalse(runtime.heavy)
        self.assertIn(runtime.name, compile_step.needs)
        plan = build.order(declared, [compile_step.name])
        self.assertLess(plan.index(runtime), plan.index(compile_step))

    def test_verification_needs_no_external_process(self):
        with patch('subprocess.Popen', side_effect=AssertionError('external process')), \
             patch('subprocess.run', side_effect=AssertionError('external process')), \
             patch('os.system', side_effect=AssertionError('external process')):
            self.assertEqual(self.verify()['payloads'], 11)


if __name__ == '__main__':
    unittest.main()
