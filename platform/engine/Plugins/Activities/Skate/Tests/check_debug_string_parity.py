#!/usr/bin/env python3
"""Rust 1.97.1 actual std string Debug versus the isolated simulation helper.

Root alone compiles/runs under atelier.safety. --preflight only stages sources,
audits the exact official table transport, and generates the bounded corpus.
Invalid UTF-8 has no Rust str equivalent; its rejection/retention policy is
checked separately from valid-string formatter parity.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
import urllib.request

PLUGIN = Path(__file__).resolve().parents[1]
ROOT = PLUGIN.parents[4]
CODE = PLUGIN / 'Source/AtelierSkate/Private/Simulation'
ARCHIVE_URL = 'https://static.rust-lang.org/dist/2026-07-16/rust-src-1.97.1.tar.xz'
ARCHIVE_SHA = 'e9a1e616d04c6845895c827a178b9227f7c7199f3f4a80af81ab3aff7b80156b'
SOURCE_HASHES = {
    'library/core/src/unicode/printable.rs': '491bb78890521eab319bd4c45c6c33ab4c3eedd6aff4b5de2b8ddfda8abe7d78',
    'library/core/src/unicode/unicode_data.rs': '4438831f7c584a35457022c4016ab8a295f242ff809b81a5c81b9bb14dc5e166',
    'library/core/src/char/methods.rs': '6794677490411e762ee66df96438a112fb6ca5bdc0a1ae11a9933e93eee77909',
    'library/core/src/fmt/mod.rs': '0b01f8c3ef1a7c1a75eaf468456a2fc10a608d9f9191b56e1793f8b9bfb29b23',
    'library/alloc/src/string.rs': '68d7464cc83b0064bac9b600b72b4feb7c90eb5efc92def549b7eb586c6537ed',
}
LICENSE_SHA = 'b71bd43a069ca0641a9ecfe585ca7b3c53b5cc1608f8b68321168698e28b5ea1'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def word(value):
    return struct.pack('<I', value)

def text(value):
    return word(len(value)) + value

def original_sources(path):
    path.mkdir(parents=True, exist_ok=True)
    if any(not (path / name).exists() for name in SOURCE_HASHES):
        raw = urllib.request.urlopen(ARCHIVE_URL).read()
        assert hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:xz') as archive:
            for entry in archive.getmembers():
                for name in SOURCE_HASHES:
                    if entry.isfile() and entry.name.endswith('/' + name):
                        target = path / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.extractfile(entry).read())
    for name, expected in SOURCE_HASHES.items():
        assert digest(path / name) == expected, name
    license = path / 'LICENSE-MIT'
    if not license.exists() or digest(license) != LICENSE_SHA:
        license.write_bytes(urllib.request.urlopen(
            'https://raw.githubusercontent.com/rust-lang/rust/1.97.1/LICENSE-MIT').read())
    assert digest(license) == LICENSE_SHA
    return path

def audit_tables(original, candidate):
    printable = (original / 'library/core/src/unicode/printable.rs').read_text()
    unicode = (original / 'library/core/src/unicode/unicode_data.rs').read_text()
    simulation = candidate.read_text()
    report = {}
    numbers = lambda value: [int(v, 0) for v in re.findall(r'0x[0-9a-f]+|\d+', value)]
    for name in ('SINGLETONS0U', 'SINGLETONS0L', 'SINGLETONS1U', 'SINGLETONS1L', 'NORMAL0', 'NORMAL1'):
        rust = re.search(r'const ' + name + r':[^=]+= &\[(.*?)\];', printable, re.S).group(1)
        cpp = re.search(r'constexpr [^;]+ ' + name + r'\[\] = \{(.*?)\};', simulation, re.S).group(1)
        assert numbers(rust) == numbers(cpp), name
        report[name] = dict(ordered_words=len(numbers(rust)),
            ordered_word_sha256=hashlib.sha256(b''.join(word(n) for n in numbers(rust))).hexdigest())
    grapheme = re.search(r'pub mod grapheme_extend \{(.*?)\n\}', unicode, re.S).group(1)
    headers = re.findall(r'ShortOffsetRunHeader::new\((\d+), (\d+)\)', grapheme)
    expected = [int(v) for row in headers for v in row]
    cpp = re.search(r'constexpr OffsetRun GRAPHEME_RUNS\[\] = \{(.*?)\};', simulation, re.S).group(1)
    assert expected == numbers(cpp) and len(headers) == 33
    rust = re.search(r'static OFFSETS:.*?= \[(.*?)\];', grapheme, re.S).group(1)
    cpp = re.search(r'constexpr std::uint8_t GRAPHEME_OFFSETS\[\] = \{(.*?)\};', simulation, re.S).group(1)
    assert numbers(rust) == numbers(cpp) and len(numbers(rust)) == 767
    report['GRAPHEME_RUNS'] = dict(ordered_pairs=33,
        ordered_word_sha256=hashlib.sha256(b''.join(word(n) for n in expected)).hexdigest())
    report['GRAPHEME_OFFSETS'] = dict(ordered_words=767,
        ordered_byte_sha256=hashlib.sha256(bytes(numbers(rust))).hexdigest())
    bounds = re.findall(r'if (0x[0-9a-f]+) <= x && x < (0x[0-9a-f]+)', printable)
    cpp_bounds = re.findall(r'if \(value >= (0x[0-9a-f]+) && value < (0x[0-9a-f]+)\)', simulation)
    assert bounds == cpp_bounds and len(bounds) == 9
    assert '(17, 0, 0)' in unicode
    assert (original / 'LICENSE-MIT').read_text().strip() in simulation
    return report

def corpus():
    rows = [dict(op=0, label='Every valid Unicode scalar, actual std Debug', hex='')]
    def add(op, raw, label):
        rows.append(dict(op=op, label=label, hex=raw.hex()))
    def valid(value, label):
        add(1, value.encode('utf-8'), label)
    for value in ('', 'easy', 'NORMAL', '\0', '\t\r\n', "'\"\\", '\x85',
                  'a\u0301', '\u0301a', '\ufe0f', '\U000e0100',
                  '\U0001f469\u200d\U0001f680', '\u200c\u200d\u2060\ufeff',
                  '日本語', 'مرحبا', '\U00033479\U0003347a', '\U0010ffff'):
        valid(value, 'Authored ASCII/C1/marks/scripts/emoji/source17 boundary')
    # All 256 byte values have genuine scalar encodings; multiscalar contexts
    # ensure quote/backslash and mark escapes stay independent of position.
    for scalar in range(256):
        for prefix, suffix in (('', ''), ('a', 'z'), ('\"', "'\\")):
            valid(prefix + chr(scalar) + suffix, 'ASCII and C1 contextual scalar ' + hex(scalar))
    edges = [0x2ff, 0x300, 0x36f, 0x370, 0x7ff, 0x800, 0xd7ff, 0xe000,
             0xfe0f, 0xffff, 0x10000, 0x1ffff, 0x20000, 0x2a6df, 0x2a6e0,
             0x33479, 0x3347a, 0xe00ff, 0xe0100, 0xe01ef, 0xe01f0, 0x10ffff]
    for scalar in edges:
        valid('a' + chr(scalar) + chr(0x300) + chr(scalar) + "'", 'UTF8/table boundary context')
    rng = random.Random(0x8bab26f4)
    favorite = [0, 9, 10, 13, 34, 39, 92, 0x85, 0xa0, 0x300, 0x301, 0x200c,
                0x200d, 0xfe0f, 0xe0100, 0x1f3fb, 0x1f469, 0x1f680]
    for _ in range(4096):
        values = []
        for _ in range(rng.randrange(41)):
            scalar = rng.choice(favorite) if rng.randrange(2) else rng.randrange(0x110000)
            if 0xd800 <= scalar <= 0xdfff:
                scalar = 0x41
            values.append(chr(scalar))
        valid(''.join(values), 'Generated genuine multiscalar string')
    invalid = [bytes([n]) for n in range(0x80, 0x100)]
    invalid += [bytes.fromhex(value) for value in
        ('c080', 'c1bf', 'e08080', 'eda080', 'edbfbf', 'f0808080', 'f4908080',
         'f5808080', 'e282', 'f09f92', 'c220', 'e241a0', 'f0908041', 'ff')]
    for raw in invalid:
        for prefix in (b'', b'good', '\U0001f469'.encode()):
            valid('prior\0\u0301' + str(len(rows)), 'Successful output before invalid-byte policy')
            add(2, prefix + raw + b'after', 'No Rust str equivalent: rejection/output retention')
    return rows

def encode(rows):
    return word(len(rows)) + b''.join(word(row['op']) +
        (text(bytes.fromhex(row['hex'])) if row['op'] else b'') for row in rows)

class Reader:
    def __init__(self, raw):
        self.raw, self.at = raw, 0
    def word(self):
        value = struct.unpack_from('<I', self.raw, self.at)[0]
        self.at += 4
        return value
    def text(self):
        size = self.word()
        value = self.raw[self.at:self.at + size].decode('utf-8')
        self.at += size
        return value

def coverage(raw, rows):
    reader = Reader(raw)
    assert reader.word() == len(rows)
    counts = Counter()
    widths = Counter()
    witnesses = {}
    retained = 'retained\0output'
    failed_retention = 0
    distinct_contexts = set()
    scalars = 0
    for row in rows:
        op = reader.word()
        assert op == row['op']
        counts[op] += 1
        if op == 0:
            assert reader.word() == 0x110000 - 0x800
            for scalar in range(0x110000):
                if 0xd800 <= scalar <= 0xdfff:
                    continue
                assert reader.word() == scalar
                value = reader.text()
                assert value.startswith('"') and value.endswith('"')
                scalars += 1
                widths[len(chr(scalar).encode())] += 1
                if scalar in (0, 9, 10, 13, 34, 39, 92, 0x85, 0x300, 0x200d, 0xfe0f, 0xe0100):
                    witnesses[hex(scalar)] = value
        else:
            okay, error, value = reader.word(), reader.text(), reader.text()
            if op == 1:
                assert okay and not error
                retained = value
                distinct_contexts.add(value)
            else:
                assert not okay and error.startswith('Invalid UTF-8 at byte ')
                assert value == retained
                failed_retention += 1
    assert reader.at == len(raw)
    assert scalars == 1112064 and set(widths) == {1, 2, 3, 4}
    assert witnesses['0x85'] == '"\\u{85}"'
    assert witnesses['0x300'] == '"\\u{300}"'
    assert witnesses['0xfe0f'] == '"\\u{fe0f}"'
    assert witnesses['0xe0100'] == '"\\u{e0100}"'
    assert witnesses['0x27'] == '"\'"'
    assert len(distinct_contexts) > 4500 and failed_retention == 426
    return dict(all_valid_scalars=scalars, scalar_utf8_widths=dict(widths),
        multiscalar_commands=counts[1], distinct_formatted_contexts=len(distinct_contexts),
        source_escape_witnesses=witnesses,
        separate_simulation_invalid_utf8_retention_checks=failed_retention)

def prepare(output, source, rows):
    source = original_sources(source)
    snapshot = output / 'simulation-source'
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ('DebugString.h', 'DebugString.cpp'):
        shutil.copy2(CODE / name, snapshot / name)
    shutil.copy2(PLUGIN / 'Tests/Simulation/debug_string_probe.cpp', snapshot / 'debug_string_probe.cpp')
    reference = output / 'debug_string_probe.rs'
    shutil.copy2(PLUGIN / 'Tests/Reference/debug_string_probe.rs', reference)
    tables = audit_tables(source, snapshot / 'DebugString.cpp')
    raw = encode(rows)
    (output / 'input.bin').write_bytes(raw)
    (output / 'cases.json').write_text(json.dumps(rows, indent=2) + '\n')
    report = dict(rust_version='1.97.1', rust_commit='8bab26f4f', unicode_version='17.0.0',
        official_source_archive=ARCHIVE_URL, archive_sha256=ARCHIVE_SHA,
        complete_original_std_sources=SOURCE_HASHES, rust_license_sha256=LICENSE_SHA,
        exact_source_table_transport=tables,
        immutable_simulation_sources={p.name: digest(p) for p in sorted(snapshot.iterdir())},
        reference_probe_sha256=digest(reference), checker_sha256=digest(Path(__file__)),
        commands=len(rows), valid_scalars=1112064, input_bytes=len(raw),
        input_sha256=hashlib.sha256(raw).hexdigest(),
        boundary='Actual pinned std format!("{text:?}") is the independent oracle. No standard-library implementation is copied into its executable. Simulation invalid-UTF8 rejection/retention has no original str domain equivalent and is reported separately.')
    (output / 'provenance.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'owner-freeze.json').write_text(json.dumps(report, indent=2) + '\n')
    return snapshot, reference, report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rust-source', type=Path,
        default=ROOT / 'build/skate-cpp/debug-string-source')
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'first-divergence.json'):
        (output / name).unlink(missing_ok=True)
    rows = corpus()
    snapshot, source, report = prepare(output, args.rust_source.resolve(), rows)
    if args.preflight:
        print(json.dumps(dict(preflight='PASS', commands=len(rows), valid_scalars=1112064,
            input_bytes=report['input_bytes'], input_sha256=report['input_sha256'],
            exact_tables=len(report['exact_source_table_transport']))))
        return
    version = subprocess.check_output(['rustc', '+1.97.1', '--version', '--verbose'], text=True)
    assert 'release: 1.97.1' in version and 'commit-hash: 8bab26f4f' in version
    (output / 'reference-toolchain.txt').write_text(version)
    reference, candidate = output / 'debug-string-reference', output / 'debug-string-simulation'
    subprocess.run(['rustc', '+1.97.1', '--edition=2024', '-O', str(source), '-o', str(reference)], check=True)
    subprocess.run(['clang++', '-std=c++17', '-O2', '-fno-exceptions', '-fno-rtti',
        '-Wall', '-Wextra', '-Werror', '-I', str(snapshot), str(snapshot / 'DebugString.cpp'),
        str(snapshot / 'debug_string_probe.cpp'), '-o', str(candidate)], check=True)
    for name, expected in report['immutable_simulation_sources'].items():
        assert digest(snapshot / name) == expected
    assert digest(source) == report['reference_probe_sha256']
    results = []
    for binary, label in ((reference, 'reference'), (candidate, 'simulation')):
        run = subprocess.run([str(binary)], input=(output / 'input.bin').read_bytes(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        (output / (label + '.bin')).write_bytes(run.stdout)
        (output / (label + '.stderr')).write_bytes(run.stderr)
        results.append(run.stdout)
    if results[0] != results[1]:
        offset = next((n for n, (a, b) in enumerate(zip(*results)) if a != b), min(map(len, results)))
        (output / 'first-divergence.json').write_text(json.dumps(dict(byte_offset=offset,
            reference_bytes=len(results[0]), simulation_bytes=len(results[1])), indent=2) + '\n')
        raise AssertionError('DebugString first mismatch at byte ' + str(offset))
    proof = coverage(results[0], rows)
    result = dict(result='PASS', valid_scalar_formatter_records=1112064,
        commands=len(rows), exact_bytes=len(results[0]), sha256=hashlib.sha256(results[0]).hexdigest(), coverage=proof)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
