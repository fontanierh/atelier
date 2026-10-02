#!/usr/bin/env python3
"""Build the ride reference recorder: every native source plus Tests/Native/ride_oracle_recorder.cpp.

Objects are compiled once into OUT/obj and reused while their source is unchanged, so editing the recorder only
recompiles it and relinks. Same flags as build_native_session_cli.py. Run it under the render lock and memory guard:

    uv run python -m atelier.safety.guarded --report OUT/guard --kind compile --purpose "skate ride oracle" -- \
        python3 platform/engine/Plugins/Activities/Skate/Tests/build_ride_oracle.py --out OUT
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[5]
CODE = TESTS.parent / 'Source/AtelierSkate/Private/Native'
RECORDER = TESTS / 'Native/ride_oracle_recorder.cpp'
FLAGS = ('-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti',
         '-Wall', '-Wextra', '-Werror', '-pthread')


def digest(*parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else part.encode())
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='output folder under the repository build/')
    parser.add_argument('--jobs', type=int, default=10)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        raise SystemExit('the recorder builds under the repository build/ folder')
    objects = out / 'obj'
    objects.mkdir(parents=True, exist_ok=True)
    # Every header goes into the key, so a header edit rebuilds everything.
    headers = digest(*(p.name.encode() + p.read_bytes() for p in sorted(CODE.glob('*.h'))), ' '.join(FLAGS))
    units = sorted(CODE.glob('*.cpp')) + [RECORDER]

    def compile_unit(source):
        key = digest(headers, source.read_bytes())
        target = objects / f'{source.stem}.o'
        stamp = objects / f'{source.stem}.key'
        if target.exists() and stamp.exists() and stamp.read_text() == key:
            return source.stem, False
        command = ['clang++', *FLAGS, '-I', str(CODE), '-c', str(source), '-o', str(target)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'{source.name}:\n{result.stderr}')
        stamp.write_text(key)
        return source.stem, True

    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(compile_unit, units))
    built = [name for name, fresh in results if fresh]
    executable = out / 'ride-oracle-recorder'
    subprocess.run(['clang++', *FLAGS, *(str(objects / f'{u.stem}.o') for u in units), '-o', str(executable)],
                   check=True)
    report = dict(units=len(units), compiled=len(built), binary=str(executable.relative_to(ROOT)),
                  sha256=digest(executable.read_bytes()))
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    sys.exit(main())
