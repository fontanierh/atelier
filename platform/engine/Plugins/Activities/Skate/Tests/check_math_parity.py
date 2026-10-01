#!/usr/bin/env python3
"""Exact differential math/geometry/curve checks against frozen Rust modules.

Run through atelier.safety. All generated sources, binaries and evidence stay in
the supplied game build directory. No Rust numerical implementation is edited.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tarfile

from session_parity import PLUGIN, REFERENCE_REVISION, digest

OUTPUT_WORDS = (13, 17, 11, 70, 16, 1, 1, 6, 11, 16)
OPERATIONS = ('scalar', 'vector', 'quaternion', 'matrix', 'sqt', 'point_graph',
              'shake_bezier', 'closest_triangle', 'thin_triangle', 'axis_rotation')


def fword(value):
    try:
        return struct.unpack('<I', struct.pack('<f', value))[0]
    except OverflowError:
        return 0xff800000 if value < 0 else 0x7f800000


def fvalue(word):
    return struct.unpack('<f', struct.pack('<I', word))[0]


def corpus():
    rng = random.Random(0x4d415448)
    records = []
    cases = []
    output_word = 0

    def add(operation, words, label):
        nonlocal output_word
        records.append(struct.pack('<I', operation) + struct.pack('<' + 'I' * len(words), *words))
        cases.append(dict(case=len(cases), operation=OPERATIONS[operation], label=label,
                          first_output_word=output_word, output_words=OUTPUT_WORDS[operation] + 2))
        output_word += OUTPUT_WORDS[operation] + 2

    def floats(operation, values, label):
        add(operation, [fword(value) for value in values], label)

    edges = [0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x00800000, 0x00200000,
             0x34000000, 0x37800000, 0x39800000, 0x3c23d70a, 0x3d0efa35,
             0x3e8930a3, 0x3f000000, 0x3f800000, 0xbf800000, 0x3f800001,
             0x40490fdb, 0x40c90fdb, 0x4affffff, 0x4b000000, 0x7e800000,
             0x7f7fffff, 0x7f800000, 0xff800000, 0x7fc00000, 0xffc00000,
             0x7fc12345, 0xffc12345, 0x7f812345, 0xff812345]
    scalar_words = set(edges)
    for base in edges:
        if base & 0x7f800000 != 0x7f800000:
            for delta in (-2, -1, 1, 2):
                scalar_words.add((base + delta) & 0xffffffff)
    # Range-reduction halfway cases and neighbors test ties-even independently
    # of libm. Include small/large negative multiples and separate power trees.
    tau = fvalue(0x40c90fdb)
    for turn in range(-256, 257):
        for offset in (0., .25, .5, .75):
            base = fword((turn + offset) * tau)
            scalar_words.update(((base - 1) & 0xffffffff, base, (base + 1) & 0xffffffff))
    for word in sorted(scalar_words):
        add(0, [word], 'boundary')
    for _ in range(4096):
        add(0, [rng.getrandbits(32)], 'random_bits')
    for _ in range(2048):
        floats(0, [rng.uniform(-1., 1.)], 'inverse_trig_domain')

    bases = ([0., 0., 0., 0.], [-0., -0., -0., -0.], [1., 0., 0., 1.],
             [3., 4., 0., 100.], [1.e-20, 1.e-20, 0., 1.], [1.e20, 0., 1.e20, 1.])
    for a in bases:
        for b in bases:
            for limit in (0., -0., -1., 1., 5.):
                floats(1, list(a) + list(b) + [limit], 'vector_boundary')
    for a in edges:
        for b in edges:
            add(1, [a, fword(1.), fword(2.), 0, b, 0, 0, 0, fword(1.)], 'minmax_boundaries')
    for _ in range(2048):
        floats(1, [rng.uniform(-1000., 1000.) for _ in range(8)] + [rng.uniform(-10., 1000.)], 'random_vectors')

    weights = (-1., -0., 0., 1.e-8, .25, .5, 1., 1.5, float('nan'))
    quaternions = ([0., 0., 0., 1.], [0., 0., 0., -1.], [1., 0., 0., 0.],
                   [-1., 0., 0., 0.], [0., 0., 0., 0.], [.5, .5, .5, .5])
    for a in quaternions:
        for b in quaternions:
            for weight in weights:
                floats(2, list(a) + list(b) + [weight], 'hemisphere_boundary')
    for _ in range(2048):
        a = [rng.uniform(-1., 1.) for _ in range(4)]
        b = [rng.uniform(-1., 1.) for _ in range(4)]
        if rng.randrange(2):
            a = [v / sum(x * x for x in a) ** .5 for v in a]
            b = [v / sum(x * x for x in b) ** .5 for v in b]
        floats(2, a + b + [rng.uniform(-1., 2.)], 'random_quaternions')

    identity = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 0.]
    matrices = [identity, [0.] * 16,
                [-1., 0., 0., 0., 0., -1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 0.],
                [-1., 0., 0., 0., 0., 1., 0., 0., 0., 0., -1., 0., 0., 0., 0., 0.],
                [1., 0., 0., 0., 0., -1., 0., 0., 0., 0., -1., 0., 0., 0., 0., 0.],
                [0., 1., 0., 1., -1., 0., 0., -1., 0., 0., 1., 0., 3., 2., 1., 99.]]
    for a in matrices:
        for b in matrices:
            for weight in weights:
                floats(3, a + b + [weight], 'matrix_boundary')
    for _ in range(1024):
        floats(3, [rng.uniform(-3., 3.) for _ in range(32)] + [rng.uniform(-1., 2.)], 'random_matrices')
    for _ in range(1024):
        floats(4, [rng.uniform(-4., 4.) for _ in range(12)], 'random_sqt')
    for rotation in quaternions:
        floats(4, [1., 2., 3., 99.] + list(rotation) + [4., 5., 6., 77.], 'sqt_boundary')

    graphs = [list(range(8)), [0.] * 8, list(reversed(range(8))), [0., 1., 1., 2., 3., 3., 4., 5.],
              [0., float('nan'), 2., 3., 4., 5., 6., 7.], [0., 1., 2., 3., 4., 5., 6., float('nan')]]
    for x in graphs:
        for word in edges:
            add(5, [fword(v) for v in x + [1., 2., 3., 5., 8., 13., 21., 34.]] + [word], 'graph_boundary')
        for knot in x:
            base = fword(knot)
            for delta in (-1, 0, 1):
                add(5, [fword(v) for v in x + [1., 2., 3., 5., 8., 13., 21., 34.]] + [(base + delta) & 0xffffffff], 'graph_knots')
    for _ in range(2048):
        x = sorted(rng.uniform(-4., 4.) for _ in range(8))
        if rng.randrange(5) == 0:
            rng.shuffle(x)
        floats(5, x + [rng.uniform(-100., 100.) for _ in range(8)] + [rng.uniform(-6., 6.)], 'random_graph')
    for _ in range(1024):
        x = [0., rng.random(), rng.random(), 1.]
        y = [rng.uniform(-5., 5.) for _ in range(4)]
        points = sum(([x[i], y[i], rng.random(), rng.random()] for i in range(4)), [])
        floats(6, points + [rng.uniform(-1., 2.)], 'random_bezier')
    for word in edges:
        add(6, [fword(v) for v in [0., 0., 0., 0., .25, 1., 0., 0., .75, -1., 0., 0., 1., 0., 0., 0.]] + [word], 'bezier_boundary')

    triangles = ([0., 0., 0., 1., 0., 0., 0., 1., 0.], [0.] * 9,
                 [0., 0., 0., 1., 0., 0., 2., 0., 0.], [0., 0., 0., 0., 1., 0., 1., 0., 0.])
    # All seven closest-feature regions, degeneracy/ties, and both windings.
    points = ([0., 0., 1.], [1., 0., 1.], [0., 1., 1.], [.5, 0., 1.],
              [0., .5, 1.], [.5, .5, 1.], [.25, .25, 1.], [-1., -1., 0.], [2., 2., 0.])
    for triangle in triangles:
        for point in points:
            floats(7, list(point) + list(triangle), 'triangle_features')
            for direction in ([0., 0., -2.], [0., 0., 2.], [0., 0., 0.], [1., 0., -1.]):
                floats(8, list(point) + list(direction) + list(triangle), 'segment_boundary')
    for _ in range(4096):
        triangle = [rng.uniform(-10., 10.) for _ in range(9)]
        point = [rng.uniform(-10., 10.) for _ in range(3)]
        floats(7, point + triangle, 'random_triangle')
        direction = [rng.uniform(-20., 20.) for _ in range(3)]
        floats(8, point + direction + triangle, 'random_segment')
    # Guaranteed front-face hits and tolerated positions beyond endpoints.
    for _ in range(1024):
        x = rng.uniform(0., .5); y = rng.uniform(0., .5)
        height = rng.choice((1., 0., -1.e-6, 1.000001))
        floats(8, [x, y, height, 0., 0., -1.] + list(triangles[0]), 'front_face_segment')
    for axis in ([1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 99.]):
        for word in edges:
            add(9, [fword(v) for v in axis] + [word], 'axis_boundary')
    for _ in range(1024):
        floats(9, [rng.uniform(-1., 1.) for _ in range(4)] + [rng.uniform(-10., 10.)], 'random_axis')
    return struct.pack('<I', len(records)) + b''.join(records), cases


WRAPPERS = {
    'physics': '''
pub fn probe_closest(point:crate::math::Vector3,vertices:[crate::math::Vector3;3])
    ->(crate::math::Vector3,u32,f32,f32) {
    let result=triangle_closest::closest(point,vertices);
    (result.point,result.region,result.u,result.v)
}
''',
    'animation': '''
pub fn probe_quaternion_multiply(a:[f32;4],b:[f32;4])->[f32;4] {pose_trajectory::multiply(a,b)}
pub fn probe_quaternion_rotate(q:[f32;4],v:[f32;3])->[f32;3] {pose_trajectory::rotate(q,v)}
''',
    'animation/foot_ik': '''
pub fn probe_reciprocal(value:f32,count:usize)->f32 {math::reciprocal(value,count)}
pub fn probe_cross(a:[f32;4],b:[f32;4])->[f32;4] {math::cross(a,b)}
pub fn probe_normalize(value:[f32;4])->[f32;4] {math::normalize(value)}
pub fn probe_length(value:[f32;4])->f32 {math::length(value)}
pub fn probe_limit_length(value:[f32;4],limit:f32)->[f32;4] {math::limit_length(value,limit)}
pub fn probe_rotation_axis_angle(value:&[[f32;4];4])->([f32;4],f32) {math::rotation_axis_angle(value)}
pub fn probe_axis_rotation(axis:[f32;4],angle:f32)->[[f32;4];4] {math::axis_rotation(axis,angle)}
''',
    'camera': '''
pub fn probe_shake_curve(points:[[f32;4];4],input:f32)->f32 {shake_curve::sample(points,input)}
''',
}


def build_probes(output):
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN / 'ThirdParty/skate-runtime/crates/skate-core/src').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output / 'reference-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {path.relative_to(source).as_posix(): digest(path) for path in sorted(source.rglob('*.rs'))}
    shells = output / 'oracle-shells'
    # Preserve the complete original module layout. A #[path] redirect for a
    # foo.rs module changes where Rust resolves its foo/ children. Numerical
    # files below are therefore byte-identical copies at their original paths.
    if shells.exists():
        shutil.rmtree(shells)
    shutil.copytree(source, shells)
    shell_paths = {name: shells / name / 'mod.rs' for name in WRAPPERS}
    for name, wrapper in WRAPPERS.items():
        # These four files contain only module declarations and re-exports.
        # Added sibling functions forward into the unchanged private modules.
        shell_paths[name].write_text((source / name / 'mod.rs').read_text() + wrapper)
    for name, expected in originals.items():
        if name not in {key + '/mod.rs' for key in WRAPPERS} and digest(shells / name) != expected:
            raise AssertionError(f'A staged numerical reference module changed: {name}')
    main = shells / 'math-oracle.rs'
    # lib.rs contributes only its unchanged root declarations and attributes.
    probe = (PLUGIN / 'Tests/Reference/math_probe.rs').read_text().replace('//!', '//')
    main.write_text((source / 'lib.rs').read_text() + probe)
    reference = output / 'math-reference'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', '-A', 'dead_code', str(main), '-o', str(reference)], check=True)
    if any(digest(source / name) != expected for name, expected in originals.items()):
        raise AssertionError('A frozen reference module changed during the build')
    code = PLUGIN / 'Source/AtelierSkate/Private/Native'
    snapshot = output / 'native-source'
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ('NativeMath.h', 'NativeMath.cpp', 'Geometry.h', 'Geometry.cpp'):
        shutil.copy2(code / name, snapshot / name)
    shutil.copy2(PLUGIN / 'Tests/Native/math_probe.cpp', snapshot / 'math_probe.cpp')
    cpp = output / 'math-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
                    '-Wall', '-Wextra', '-Werror', '-I', str(snapshot),
                    str(snapshot / 'NativeMath.cpp'), str(snapshot / 'Geometry.cpp'),
                    str(snapshot / 'math_probe.cpp'), '-o', str(cpp)], check=True)
    provenance = dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(),
                      original_source_sha256=originals, probe_sha256=digest(PLUGIN / 'Tests/Reference/math_probe.rs'),
                      shell_sha256={name: digest(path) for name, path in shell_paths.items()},
                      reference_binary_sha256=digest(reference), cpp_binary_sha256=digest(cpp),
                      native_source_sha256={path.name: digest(path) for path in sorted(snapshot.iterdir())},
                      rust_compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip(),
                      cpp_compiler=subprocess.check_output(['clang++', '--version'], text=True).strip())
    (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return cpp, reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json', 'provenance.json'):
        (output / name).unlink(missing_ok=True)
    inputs, cases = corpus()
    (output / 'input.bin').write_bytes(inputs)
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    cpp, reference = build_probes(output)
    expected = subprocess.check_output([str(reference)], input=inputs)
    actual = subprocess.check_output([str(cpp)], input=inputs)
    (output / 'reference.bin').write_bytes(expected); (output / 'cpp.bin').write_bytes(actual)
    required = sum(case['output_words'] for case in cases) * 4
    if len(expected) != required:
        raise AssertionError(f'Incomplete reference output: {len(expected)} != {required}')
    if actual != expected:
        first = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
        case = next((case for case in cases if case['first_output_word'] * 4 <= first <
                     (case['first_output_word'] + case['output_words']) * 4), None)
        aligned = first // 4 * 4
        report = dict(passed=False, first_byte=first, first_word=first // 4, case=case,
                      reference_length=len(expected), cpp_length=len(actual),
                      reference_hex=expected[max(0, aligned - 16):aligned + 32].hex(),
                      cpp_hex=actual[max(0, aligned - 16):aligned + 32].hex())
        (output / 'first-divergence.json').write_text(json.dumps(report, indent=2) + '\n')
        raise AssertionError(report)
    coverage = {operation: sum(case['operation'] == operation for case in cases) for operation in OPERATIONS}
    region_counts = [0] * 7
    segment_hits = 0
    for case in cases:
        offset = (case['first_output_word'] + 2) * 4
        if case['operation'] == 'closest_triangle':
            region_counts[struct.unpack_from('<I', expected, offset + 12)[0]] += 1
        if case['operation'] == 'thin_triangle':
            segment_hits += struct.unpack_from('<I', expected, offset)[0]
    if any(count == 0 for count in region_counts) or segment_hits == 0:
        raise AssertionError('A triangle feature or segment hit was unexercised')
    report = dict(passed=True, cases=len(cases), operations=coverage, closest_triangle_regions=region_counts,
                  thin_triangle_hits=segment_hits, output_words=required // 4,
                  comparison='all binary32 and integer output bits; no tolerance or NaN canonicalization',
                  inputs_sha256=hashlib.sha256(inputs).hexdigest(), outputs_sha256=hashlib.sha256(expected).hexdigest())
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
