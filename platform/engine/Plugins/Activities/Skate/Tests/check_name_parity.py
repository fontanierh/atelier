#!/usr/bin/env python3
"""Check C++ and converter name identities against Rust for every database name plus boundary/fuzz inputs.

Compiles both probes: run under atelier.safety, with generated output under build/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import string
import subprocess
from check_gesture_parity import converter, PLUGIN


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries = json.loads((args.assets/'private/stock/skater-collections.json').read_text())['collections']
    names = {'', 'Hash_', '0x', 'Hash_+ff', 'Hash_-1', 'Hash_ 1', 'Hash_0x10', '0x00000000000000000000001',
             '0xffffffffffffffff', '0x10000000000000000', '0x+FF', 'Hash_0', 'Hash_+','Hash_++f'}
    for entry in entries:
        names.update([entry['class'],entry['key'],entry['parent'],*entry['fields']])
        names.update(value['type'] for value in entry['fields'].values())
    # All offsets across 24-byte chunk boundaries, including UTF-8 bytes.
    for width in range(300):
        names.update(['a'*width, 'あ'*width, 'é'*width])
    rng = random.Random(0x48415348)
    alphabet = string.ascii_letters+string.digits+'_ :+-あé'
    for _ in range(10000):
        names.add(''.join(rng.choice(alphabet) for _ in range(rng.randrange(1,240))))
    names = sorted(names)
    corpus = ('\n'.join(names)+'\n').encode()
    (output/'input.txt').write_bytes(corpus)
    code = PLUGIN/'Source/AtelierSkate/Private/Native'
    cpp, rust = output/'name-cpp', output/'name-reference'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(code),str(code/'NameId.cpp'),
                    str(PLUGIN/'Tests/Native/name_probe.cpp'),'-o',str(cpp)],check=True)
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O',str(PLUGIN/'Tests/Reference/name_probe.rs'),'-o',str(rust)],check=True)
    expected = subprocess.check_output([str(rust)],input=corpus)
    actual = subprocess.check_output([str(cpp)],input=corpus)
    converted = ''.join(f'{converter.name_hash(name):016x} {converter.name_id(name):016x}\n' for name in names).encode()
    for label, result in [('C++',actual),('converter',converted)]:
        if result != expected:
            for name, a, b in zip(names,result.splitlines(),expected.splitlines()):
                if a != b:
                    raise AssertionError(dict(implementation=label,name=name,actual=a.decode(),reference=b.decode()))
            raise AssertionError(f'{label} output count differs')
    (output/'reference.txt').write_bytes(expected)
    report = dict(passed=True,names=len(names),comparison='exact u64 identities',
                  output_sha256=hashlib.sha256(expected).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    main()
