"""Yorimichi V2: the skate RuntimeData input set and the package it assembles (pure Python, no Unreal).

Donor-free: every input is a tracked file (the Skate plugin's Data under platform/engine, and the data/skate/runtime record
that pins the assembler code and the input list). tools/import/run.py calls prepare() before the editor import
(importer skate-runtime@1 in unreal/Scripts/import_asset.py), which takes the package and receipt written here.

    uv run python -I games/yorimichi_v2/tools/import/skate_runtime.py --check
    uv run python -I games/yorimichi_v2/tools/import/skate_runtime.py --assemble build/yorimichi_v2/skate-runtime

--check: the pinned input list (the record's copy, src/skate_runtime_inputs.sha256) must match its record pin, every
listed Skate/Data file must match its sha256, and the tracked Data tree must hold exactly the files the assembler reads.

--assemble BUILD: stages only the pinned inputs into BUILD/stage (a fresh folder; the pinned code from the record's src/
and the pinned Data files), runs the pinned assembler there with --assemble, checks the package manifest hash, and writes
BUILD/package (the folder the editor import reads), BUILD/verification.json (the assembler's own report) and
BUILD/receipt.json (what the editor import must read back).
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]                       # games/yorimichi_v2
REPO = GAME.parents[1]
RECORD = GAME / 'assets' / 'data' / 'skate' / 'runtime'   # the generated record; generator/skate/runtime pins the same files
INPUTS_NAME = 'skate_runtime_inputs.sha256'  # the tracked list; the record pins its copy in src/
DATA = REPO / 'platform' / 'engine' / 'Plugins' / 'Activities' / 'Skate' / 'Data'
BUILD = REPO / 'build' / 'yorimichi_v2' / 'skate-runtime'
CODE = ('simulation_package.py', 'motion_text.py', 'runtime_text.py')
RUNTIME_TEXT = ('settings.json', 'action-graph.json', 'motion-graph.json', 'camera-graph.json', 'camera.json',
                'gestures.json', 'physics-skeletons.json')
RUNTIME_FILES = ('settings.skate', 'action.graph', 'motion.graph', 'camera.graph', 'camera.skate', 'gestures.skate',
                 'physics-skeletons.skate')
# Skate/Data/bundle.json:6. The assembler checks the package against it; this module checks it again, never trusts it.
PACKAGE_MANIFEST_SHA256 = 'add4fc5692861f7f7134da3049030d2030335000b782b38419a79dcf27fe034d'
# Counts of the closed set (the rig, 2 metadata banks, 3,324 clips, 7 runtime text files, the manifest and bundle.json).
EXPECTED_READS, EXPECTED_CLIPS = 3336, 3324
LINE = re.compile(r'([0-9a-f]{64})  ([^\s\\:]+)')
CLIP = re.compile(r'motion/clips/[^/]+/[^/]+\.json')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def assembler_reads(names):
    """The Data-relative files simulation_package.py --assemble reads, out of `names` (the files present in Skate/Data).

    simulation_package.py:21-25 sets DATA = TOOLS.parent / 'Data' and the RUNTIME, MOTION, DESCRIPTOR and MANIFEST paths;
    assemble() reads runtime_text.build(RUNTIME) (runtime_text.py:482-488: exactly the seven names in RUNTIME_TEXT),
    motion_text.build(MOTION) (motion_text.py:438-452: rig.json, metadata/bank-0.json and bank-1.json, and the glob
    clips/*/*.json, which is the CLIP pattern here), and the manifest (simulation_package.py:170); verify reads the default
    descriptor bundle.json (simulation_package.py:24, :278). README.md and any other file are not read."""
    fixed = {'motion/rig.json', 'motion/metadata/bank-0.json', 'motion/metadata/bank-1.json',
             'package-manifest.json', 'bundle.json', *(f'runtime/{name}' for name in RUNTIME_TEXT)}
    return sorted(name for name in names if name in fixed or CLIP.fullmatch(name))


def scan(data):
    """Every regular file under data, Data-relative POSIX names; a symlink or other entry is refused."""
    data = Path(data)
    names = []
    for path in sorted(data.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Skate/Data holds a symlink: {path.relative_to(data).as_posix()}')
        if path.is_file():
            names.append(path.relative_to(data).as_posix())
        elif not path.is_dir():
            raise ValueError(f'Skate/Data holds a non-regular entry: {path.relative_to(data).as_posix()}')
    return names


def parse_inputs(raw):
    """The pinned list: `<sha256>  <path>` lines (sha256sum format), paths relative to Skate/Data, sorted, unique."""
    if not raw.endswith(b'\n'):
        raise ValueError('Input list must end with a newline')
    rows = []
    for line in raw.decode('utf-8').split('\n')[:-1]:
        match = LINE.fullmatch(line)
        if not match:
            raise ValueError(f'Invalid input line: {line!r}')
        digest, rel = match.groups()
        path = PurePosixPath(rel)
        if path.is_absolute() or '..' in path.parts or path.as_posix() != rel or rel == '.':
            raise ValueError(f'Invalid input path: {rel!r}')
        rows.append((digest, rel))
    names = [rel for _, rel in rows]
    if names != sorted(names) or len(set(names)) != len(names):
        raise ValueError('Input list must be sorted and hold each path once')
    return rows


def write_inputs(data, out):
    """Write the pinned list for the tracked Data tree: one line per file the assembler reads, with its sha256."""
    names = assembler_reads(scan(data))
    if len(names) != EXPECTED_READS or sum(CLIP.fullmatch(n) is not None for n in names) != EXPECTED_CLIPS:
        raise ValueError(f'Skate/Data reads {len(names)} files, expected {EXPECTED_READS}')
    lines = [f'{sha256((Path(data) / name).read_bytes())}  {name}\n' for name in names]
    Path(out).write_text(''.join(lines))
    return len(lines)


def verify_inputs(rows, data):
    """Every pinned file matches its sha256, and the tree holds exactly the files the assembler reads (closed set)."""
    if len(rows) != EXPECTED_READS:
        raise ValueError(f'Input list names {len(rows)} files, expected {EXPECTED_READS}')
    data, names = Path(data), [rel for _, rel in rows]
    tree = assembler_reads(scan(data))
    if tree != names:
        missing, extra = sorted(set(names) - set(tree)), sorted(set(tree) - set(names))
        raise ValueError(f'Skate/Data differs from the pinned input list: missing={missing[:5]} extra={extra[:5]}')
    for digest, rel in rows:
        if sha256((data / rel).read_bytes()) != digest:
            raise ValueError(f'Skate/Data input differs from its pin: {rel}')


def record_pins(record=RECORD):
    doc = tomllib.loads((Path(record) / 'asset.toml').read_text())
    return {source['path']: source['sha256'] for source in doc['sources']}


def verify_record(record=RECORD):
    """The record's pinned sources (the assembler code and the input list) match their src/ copies."""
    record = Path(record)
    pins = record_pins(record)
    for name in (*CODE, INPUTS_NAME):
        rel = f'src/{name}'
        if pins.get(rel) is None:
            raise ValueError(f'{rel} is not pinned by the record')
        if sha256((record / rel).read_bytes()) != pins[rel]:
            raise ValueError(f'{rel} differs from its pin; restore it from the donor, never edit it here')


def read_inputs(record=RECORD):
    """The pinned input list, from the record's own pinned copy (verified first)."""
    verify_record(record)
    return parse_inputs((Path(record) / 'src' / INPUTS_NAME).read_bytes())


def stage(rows, data, stage_root, record=RECORD):
    """A fresh folder with the pinned code under Tools/ and only the pinned files under Data/ (the assembler's layout)."""
    verify_record(record)
    verify_inputs(rows, data)
    stage_root = Path(stage_root)
    if stage_root.exists():
        shutil.rmtree(stage_root)
    for name in CODE:
        (stage_root / 'Tools').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(record) / 'src' / name, stage_root / 'Tools' / name)
    for _, rel in rows:
        target = stage_root / 'Data' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((Path(data) / rel).read_bytes())
    return stage_root / 'Tools' / 'simulation_package.py'


def _u32(raw, at):
    if at < 0 or at + 4 > len(raw):
        raise ValueError('Truncated skating payload')
    return struct.unpack_from('<I', raw, at)[0], at + 4


def _text(raw, at):
    size, at = _u32(raw, at)
    if at + size > len(raw):
        raise ValueError('Truncated skating text')
    return raw[at:at + size].decode('utf-8'), at + size


def _magic(raw, name, magic):
    if raw[:8] != magic:
        raise ValueError(f'Skating format mismatch: {name}')


def asset_counts(payloads):
    """The counts the editor asset must expose, read from the payload headers in the order the C++ decoders read them
    (SkateRuntimeData.cpp: DecodeSettings :102-105, DecodeGraph :160-162, DecodeCamera :226, DecodeGestures :293-296,
    DecodePhysics :330-332). Camera shakes are always two (EncodeCamera :277)."""
    settings = payloads['settings.skate']
    _magic(settings, 'settings.skate', b'ATATTR01')
    counts = {'settings_records': _u32(settings, 12)[0]}
    graphs = {'action': 'action.graph', 'motion': 'motion.graph', 'camera': 'camera.graph'}
    for key, name in graphs.items():
        _magic(payloads[name], name, b'ATGRPH01')
        counts[f'{key}_elements'] = _u32(payloads[name], 12)[0]
    gestures = payloads['gestures.skate']
    _magic(gestures, 'gestures.skate', b'ATGEST01')
    counts['gesture_sets'] = _u32(gestures, 8)[0]
    camera = payloads['camera.skate']
    _magic(camera, 'camera.skate', b'ATCAM001')
    counts['camera_shots'] = _u32(camera, _text(camera, 8)[1])[0]
    physics = payloads['physics-skeletons.skate']
    _magic(physics, 'physics-skeletons.skate', b'ATPHYS01')
    source, at = _text(physics, 8)
    counts['physical_skeletons'] = _u32(physics, at)[0]
    counts['physical_source'] = source
    counts['camera_shakes'] = 2
    return counts


def receipt(package, report, expected_manifest_sha=PACKAGE_MANIFEST_SHA256):
    """What the editor read-back must match: the package manifest hash, the seven runtime files' sizes and SHA-1 (the
    asset stores them as Digests, SkateRuntimeData.cpp:475-479), and the counts above."""
    package = Path(package)
    manifest_sha = sha256((package / 'package-manifest.json').read_bytes())
    if manifest_sha != expected_manifest_sha or report.get('manifest_sha256') != manifest_sha:
        raise ValueError(f'Package manifest hash differs: {manifest_sha}, report {report.get("manifest_sha256")}')
    payloads = {name: (package / name).read_bytes() for name in RUNTIME_FILES}
    counts = asset_counts(payloads)
    runtime = {name: {'bytes': len(raw), 'sha1': hashlib.sha1(raw).hexdigest()} for name, raw in payloads.items()}
    if counts['physical_source'] != report.get('source_identity'):
        raise ValueError('Physical source differs from the package source identity')
    return {'version': 1, 'manifest_sha256': manifest_sha, 'source_identity': report['source_identity'],
            'payloads': report['payloads'], 'clips': report['clips'], 'animation_frames': report['animation_frames'],
            'patterns': report['patterns'], 'metadata_banks': report['metadata_banks'], 'bytes': report['bytes'],
            'runtime': runtime, 'asset': counts}


def assemble(script, build):
    """Run the pinned assembler (--assemble) into BUILD/package; its report goes to BUILD/verification.json."""
    build = Path(build)
    package, report = build / 'package', build / 'verification.json'
    build.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([sys.executable, '-I', str(script), '--assemble', str(package), '--output', str(report)],
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f'simulation_package.py --assemble failed: {done.stderr.strip() or done.stdout.strip()}')
    return package, json.loads(report.read_text())


def prepare(record, build):
    """@cc [owner:fontanierh,label:correctness] skate-runtime-pinned-inputs
    The package the editor import reads, from pinned bytes only: the record's pinned code and input list, every listed
    Skate/Data file checked against its sha256 and the tree holding exactly those files, assembled in a fresh stage. The
    manifest hash must equal the record's `manifest_sha256`. Returns (package folder, receipt) and writes the receipt
    beside the package; the editor read-back is checked against it."""
    record, build = Path(record), Path(build)
    expected = tomllib.loads((record / 'asset.toml').read_text())['recipe']['settings']['manifest_sha256']
    rows = read_inputs(record)
    script = stage(rows, DATA, build / 'stage', record)
    package, report = assemble(script, build)
    result = receipt(package, report, expected)
    (build / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    return package, result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='verify the pinned inputs against the tracked tree')
    mode.add_argument('--assemble', type=Path, metavar='BUILD', help='stage, assemble and write the receipt under BUILD')
    args = parser.parse_args(argv)
    rows = read_inputs()
    if args.check:
        verify_inputs(rows, DATA)
        print(f'Pinned {len(rows)} Skate/Data inputs ({sum(CLIP.fullmatch(r) is not None for _, r in rows)} clips); '
              'the record pins the code and the list.')
        return 0
    _, result = prepare(RECORD, args.assemble)
    print(f'Assembled {result["payloads"]} payloads; manifest {result["manifest_sha256"][:16]}... verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
