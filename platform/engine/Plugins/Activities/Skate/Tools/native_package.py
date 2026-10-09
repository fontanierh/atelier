#!/usr/bin/env python3
"""Assemble, verify and stage the plugin's native skating package without conversion or compilation.

    native_package.py --assemble PACKAGE [--stage RUNTIME_FOLDER] [--output REPORT]
    native_package.py --bundle PACKAGE

The package is the runtime payloads (Data/runtime) plus the rig, clips and metadata banks built from the motion
text (Data/motion). Every payload must match the manifest's SHA-256 recorded in Data/bundle.json. `--stage` then
replaces a game's runtime folder (Content/Data/SkateNative) with the verified runtime payloads, the only files a
game ships. Only project-native data is read. The migration assembler and frozen Rust reference are development
proof tools, not dependencies of this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import sys

TOOLS = Path(__file__).resolve().parent
DATA = TOOLS.parent / 'Data'
RUNTIME = DATA / 'runtime'
MOTION = DATA / 'motion'
DESCRIPTOR = DATA / 'bundle.json'
MANIFEST = 'package-manifest.json'
FORMATS = ('ATATTR01', 'ATGEST01', 'ATGRPH01', 'ATPHYS01',
           'ATSKEL01', 'ATCLIP01', 'ATMETA01', 'ATCAM001')
REQUIRED = {
    'settings.skate': b'ATATTR01',
    'gestures.skate': b'ATGEST01',
    'physics-skeletons.skate': b'ATPHYS01',
    'action.graph': b'ATGRPH01',
    'motion.graph': b'ATGRPH01',
    'camera.graph': b'ATGRPH01',
    'animation/rig.skate': b'ATSKEL01',
    'metadata/bank-0.skate': b'ATMETA01',
    'metadata/bank-1.skate': b'ATMETA01',
    'camera.skate': b'ATCAM001',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def load_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'Invalid native skating manifest JSON: {error}') from error


def safe_relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\0' in name):
        raise ValueError(f'Invalid native skating asset path: {name!r}')
    relative = PurePosixPath(name)
    if (relative.is_absolute() or '..' in relative.parts
            or relative.as_posix() != name or name == '.'):
        raise ValueError(f'Invalid native skating asset path: {name!r}')
    return relative


def count(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(f'Invalid native skating count: {label}')
    return value


def sha(value, label):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError(f'Invalid native skating SHA-256: {label}')
    return value


class Reader:
    """Bounds-checked native layout inspection; sample words stay untouched."""
    def __init__(self, raw, name):
        self.raw, self.name, self.at = raw, name, 8

    def take(self, length):
        if length > len(self.raw) - self.at:
            raise ValueError(f'Truncated native skating data: {self.name}')
        start = self.at
        self.at += length
        return self.raw[start:self.at]

    def word(self):
        return struct.unpack('<I', self.take(4))[0]

    def text(self):
        try:
            return self.take(self.word()).decode('utf-8')
        except UnicodeError as error:
            raise ValueError(f'Invalid native skating text: {self.name}') from error

    def end(self):
        if self.at != len(self.raw):
            raise ValueError(f'Trailing native skating data: {self.name}')


def inspect_clip(raw, name, rig_bones):
    r = Reader(raw, name)
    clip_name, bank = r.text(), r.word()
    r.take(8 + 4 + 7 * 4)  # Source record, FPS and loop transform words.
    channel, weights = r.word(), r.word()
    if (name != f'animation/clips/{bank}/{clip_name}.skate'
            or bank not in (0, 1) or channel > 1 or weights != rig_bones):
        raise ValueError(f'Invalid native skating clip identity or bones: {name}')
    r.take(weights * 4)
    frames, bones = r.word(), r.word()
    count(frames, name + ' frames')
    if bones != weights:
        raise ValueError(f'Invalid native skating clip bones: {name}')
    for _ in range(weights * 10):
        samples = r.word()
        if samples not in (1, frames):
            raise ValueError(f'Invalid native skating sample track: {name}')
        r.take(samples * 4)
    r.end()
    return frames


def inspect_gestures(raw):
    r = Reader(raw, 'gestures.skate')
    sets, patterns = count(r.word(), 'gesture sets'), 0
    names = set()
    for _ in range(sets):
        name = r.text()
        stick, size = r.word(), r.word()
        if not name or name in names or stick > 1:
            raise ValueError('Invalid native skating gesture set')
        names.add(name)
        patterns += size
        for _ in range(size):
            if not r.text():
                raise ValueError('Invalid native skating gesture pattern')
            r.take(4)
            points = r.word()
            if not 2 <= points <= 15:
                raise ValueError('Invalid native skating gesture point count')
            r.take(points * 8)
    r.end()
    return patterns


def assemble(bundle, runtime=RUNTIME, motion=MOTION):
    """Replace bundle with the runtime payloads plus the motion payloads built from text; verify_bundle checks it."""
    bundle, runtime = Path(bundle), Path(runtime)
    files = {path.relative_to(runtime).as_posix(): path for path in sorted(runtime.rglob('*')) if path.is_file()}
    # Everything in the runtime folder is packaged with the game, which reads its motion from typed assets instead.
    shipped = sorted(name for name in files if name.startswith(('animation/', 'metadata/')))
    if shipped:
        raise ValueError(f'Native skating motion payloads belong in the motion source, not the runtime folder: {shipped[:3]}')
    if bundle.is_symlink() or bundle.is_file():
        raise ValueError(f'Native skating package path is not a directory: {bundle}')
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import motion_text
    built = motion_text.build(Path(motion))
    built.update((name, path.read_bytes()) for name, path in files.items())
    if bundle.exists():
        shutil.rmtree(bundle)
    for name, raw in built.items():
        path = bundle.joinpath(*safe_relative(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return bundle


def stage(folder, runtime=RUNTIME):
    """Replace a game's runtime folder with exactly the runtime payloads and their manifest."""
    folder, runtime = Path(folder), Path(runtime)
    if folder.is_symlink() or folder.is_file():
        raise ValueError(f'Native skating runtime folder is not a directory: {folder}')
    if folder.exists():
        shutil.rmtree(folder)
    for path in sorted(runtime.rglob('*')):
        if path.is_file():
            target = folder.joinpath(*safe_relative(path.relative_to(runtime).as_posix()).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return folder


def verify_bundle(bundle, descriptor=DESCRIPTOR):
    bundle, descriptor = Path(bundle), Path(descriptor)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError('Missing native skating package directory')
    contract = load_json(descriptor.read_bytes())
    if (not isinstance(contract, dict) or contract.get('version') != 3
            or contract.get('backend') != 'in-process-cpp'):
        raise ValueError('Invalid native skating package descriptor')
    manifest_path = bundle / MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Missing native skating package manifest')
    manifest_raw = manifest_path.read_bytes()
    manifest_sha = sha(contract.get('manifest_sha256'), 'package manifest')
    if digest(manifest_raw) != manifest_sha:
        raise ValueError('Native skating package manifest checksum mismatch')
    manifest = load_json(manifest_raw)
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise ValueError('Invalid native skating package manifest version')
    if (manifest.get('formats') != list(FORMATS)
            or contract.get('formats') != list(FORMATS)):
        raise ValueError('Native skating package required formats differ')
    source_identity = sha(manifest.get('source_identity'), 'source identity')
    if contract.get('source_identity') != source_identity:
        raise ValueError('Native skating package source identity differs')
    expected, entries = contract.get('expected'), manifest.get('files')
    if not isinstance(expected, dict) or not isinstance(entries, dict):
        raise ValueError('Invalid native skating package file table')
    for key in ('clips', 'animation_frames', 'patterns', 'metadata_banks', 'bytes'):
        if count(manifest.get(key), key) != count(expected.get(key), key):
            raise ValueError(f'Native skating package count differs: {key}')
    if len(entries) != count(expected.get('payloads'), 'payloads'):
        raise ValueError('Native skating package payload count differs')
    paths = {name: safe_relative(name) for name in entries}
    if not REQUIRED.keys() <= entries.keys():
        raise ValueError('Native skating package required files are missing')
    actual = set()
    for path in bundle.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Native skating package symlink: {path.relative_to(bundle)}')
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
        elif not path.is_dir():
            raise ValueError('Native skating package contains a non-regular file')
    if actual != set(entries) | {MANIFEST}:
        missing, extra = sorted(set(entries) - actual), sorted(actual - set(entries) - {MANIFEST})
        raise ValueError(f'Native skating package file set differs: missing={missing}, extra={extra}')
    payloads, total = {}, 0
    for name, relative in paths.items():
        entry = entries[name]
        if not isinstance(entry, dict):
            raise ValueError(f'Invalid native skating file record: {name}')
        size = count(entry.get('bytes'), name)
        checksum = sha(entry.get('sha256'), name)
        path = bundle.joinpath(*relative.parts)
        if path.stat().st_size != size:
            raise ValueError(f'Native skating asset size mismatch: {name}')
        raw = path.read_bytes()
        if digest(raw) != checksum:
            raise ValueError(f'Native skating asset checksum mismatch: {name}')
        magic = REQUIRED.get(name)
        if name.startswith('animation/clips/') and name.endswith('.skate'):
            magic = b'ATCLIP01'
        elif name == 'custom/climbing.skate':
            magic = b'SKCLIP1\0'
        elif name == 'custom/crouch-treflip.json':
            if not isinstance(load_json(raw), dict):
                raise ValueError('Invalid project-authored skating override')
        elif magic is None:
            raise ValueError(f'Unsupported native skating payload: {name}')
        if magic is not None and raw[:8] != magic:
            raise ValueError(f'Native skating format mismatch: {name}')
        payloads[name] = raw
        total += size
    if total != manifest['bytes']:
        raise ValueError('Native skating package byte count differs')
    rig = Reader(payloads['animation/rig.skate'], 'animation/rig.skate')
    bones = count(rig.word(), 'rig bones')
    if bones > 255 or rig.word() > 1:
        raise ValueError('Invalid native skating rig header')
    clips = {name: raw for name, raw in payloads.items() if name.startswith('animation/clips/')}
    frames = sum(inspect_clip(raw, name, bones) for name, raw in clips.items())
    patterns = inspect_gestures(payloads['gestures.skate'])
    banks = [name for name in payloads if name.startswith('metadata/')]
    if (len(clips) != manifest['clips'] or frames != manifest['animation_frames']
            or patterns != manifest['patterns'] or len(banks) != manifest['metadata_banks']):
        raise ValueError('Native skating payload counts differ from manifest')
    physics = Reader(payloads['physics-skeletons.skate'], 'physics-skeletons.skate')
    if physics.text() != source_identity:
        raise ValueError('Native skating physical source identity differs')
    metadata = Reader(payloads['metadata/bank-0.skate'], 'metadata/bank-0.skate')
    metadata.text()  # Original source label is retained provenance, not parsed source data.
    if metadata.text() != source_identity:
        raise ValueError('Native skating animation source identity differs')
    return dict(version=1, backend='in-process-cpp', manifest_sha256=manifest_sha,
                payloads=len(entries), clips=len(clips), animation_frames=frames,
                patterns=patterns, metadata_banks=len(banks), bytes=total,
                formats=list(FORMATS), source_identity=source_identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--assemble', type=Path, metavar='BUNDLE', help='Assemble the package here, then verify it')
    mode.add_argument('--bundle', type=Path, help='Verify an existing package')
    parser.add_argument('--descriptor', type=Path, default=DESCRIPTOR)
    parser.add_argument('--stage', type=Path, metavar='FOLDER',
                        help="After verifying, replace this game runtime folder with the runtime payloads")
    parser.add_argument('--output', type=Path, help='Build verification report; no source files are written')
    args = parser.parse_args()
    try:
        result = verify_bundle(assemble(args.assemble) if args.assemble else args.bundle, args.descriptor)
        if args.stage:
            stage(args.stage)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Native skating verification failed: {error}\n')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Verified {result["payloads"]} native skating payloads, '
          f'{result["clips"]} clips and {result["animation_frames"]} frames.')


if __name__ == '__main__':
    main()
