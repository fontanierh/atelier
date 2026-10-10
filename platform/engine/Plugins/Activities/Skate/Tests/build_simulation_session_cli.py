#!/usr/bin/env python3
"""Stage or explicitly build the offline QA transport over GameplaySession.

The default is a lightweight immutable-source preflight. Only the root
coordinator may use --compile, inside the repository render lock and memory
guard. This executable is a test artifact. Its source
closure is the complete simulation source directory compiled by Unreal; no Rust
toolchain, historical Git objects, original asset reader, probe friend or
substitute producer is required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[5]
CODE = TESTS.parent / 'Source/AtelierSkate/Private/Simulation'
SOURCE = TESTS / 'Simulation/gameplay_session_cli.cpp'
DEFAULT_OUT = ROOT / 'build/skate-simulation-session-cli'
FLAGS = ('-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
         '-fno-exceptions', '-fno-rtti', '-Wall', '-Wextra', '-Werror', '-pthread')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def copy_source(source, destination):
    data = source.read_bytes()
    destination.write_bytes(data)
    if source.read_bytes() != data:
        raise RuntimeError(f'Source changed during preflight: {source.name}')
    return sha(data)


def stage(out):
    out = out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        raise ValueError('Generated QA sources must remain inside repository build/')
    snapshot = out / 'simulation-source'
    snapshot.mkdir(parents=True, exist_ok=True)
    # No observed/friend headers from the differential harness are used here.
    sources = {}
    for path in sorted(CODE.glob('*.h')):
        sources[str(path.relative_to(ROOT))] = copy_source(path, snapshot / path.name)
    units = tuple(sorted(path.stem for path in CODE.glob('*.cpp')))
    if not units or 'GameplaySession' not in units:
        raise ValueError('Missing simulation gameplay session sources')
    if len(units) != len(set(units)):
        raise ValueError('Duplicate simulation session translation unit')
    for name in units:
        path = CODE / (name + '.cpp')
        sources[str(path.relative_to(ROOT))] = copy_source(path, snapshot / path.name)
    sources[str(SOURCE.relative_to(ROOT))] = copy_source(SOURCE, snapshot / SOURCE.name)

    # Reuse the accepted project's existing JSON transport and f32 decimal
    # conversion. Extraction ends before its authored-document field schema.
    parser = CODE / 'AnimationPoseJson.cpp'
    raw = parser.read_bytes()
    start_marker, end_marker = b'struct Json\n{', b'std::string Type(const Json& j)'
    if raw.count(start_marker) != 1 or raw.count(end_marker) != 1:
        raise ValueError('JSON extraction boundaries changed')
    start = raw.index(start_marker)
    end = raw.index(end_marker, start)
    helper = raw[start:end]
    if not helper.startswith(start_marker) or not helper.endswith(b'\n'):
        raise ValueError('Invalid JSON extraction boundary')
    (snapshot / 'gameplay_cli_json.inc').write_bytes(helper)
    if b'class Reader\n{' not in helper or b'float Number(std::string_view s)' not in helper:
        raise ValueError('Expected original JSON transport declarations')
    executable = out / ('gameplay-session-cli.exe' if sys.platform == 'win32' else 'gameplay-session-cli')
    command = ['clang++', *FLAGS, '-I', str(snapshot),
               *(str(snapshot / (name + '.cpp')) for name in units),
               str(snapshot / SOURCE.name), '-o', str(executable)]
    syntax = ['clang++', *FLAGS, '-I', str(snapshot), '-fsyntax-only', str(snapshot / SOURCE.name)]
    report = {
        'purpose': 'offline QA transport over the in-process simulation GameplaySession',
        'units': list(units), 'unit_count': len(units),
        'closure_source': str(CODE.relative_to(ROOT)),
        'builder_sha256': sha(Path(__file__).read_bytes()),
        'sources': sources,
        'json_transport': {
            'source': str(parser.relative_to(ROOT)), 'source_sha256': sha(raw),
            'start': start, 'end': end,
            'start_marker': start_marker.decode(), 'end_marker': end_marker.decode(),
            'extracted_sha256': sha(helper), 'extracted_bytes': len(helper),
        },
        'compile_command': command, 'syntax_command': syntax,
        'output': str(executable.relative_to(ROOT)),
        'scope': 'Source-authored JSON worlds and raw controller packets; all simulation, input, graph, solver, pose, camera, score and elapsed state belongs to the actual simulation session. OS I/O and asynchronous thread completion timing are transport boundaries.',
        'compiled': False,
    }
    (out / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return executable, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--preflight', action='store_true', help='Stage immutable sources without compiling (default)')
    modes.add_argument('--compile', action='store_true', help='Explicit guarded root-only build')
    args = parser.parse_args()
    executable, report = stage(args.out)
    if args.compile:
        subprocess.run(report['compile_command'], check=True)
        report.update(compiled=True, executable_sha256=sha(executable.read_bytes()),
                      executable_bytes=executable.stat().st_size)
        (args.out.resolve() / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'compiled': report['compiled'], 'units': report['unit_count'],
                      'binary': str(executable), 'manifest': str(args.out.resolve() / 'build-manifest.json'),
                      'json_transport_sha256': report['json_transport']['extracted_sha256']}))


if __name__ == '__main__':
    main()
