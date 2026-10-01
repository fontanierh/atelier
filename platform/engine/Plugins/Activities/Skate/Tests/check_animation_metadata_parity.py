#!/usr/bin/env python3
"""Verify every native metadata word and original duplicate/merge lookup rule.

Run through the shared render lock and memory guard: this compiles both probes.
Original Rust source is extracted from frozen Git and remains byte-identical.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import subprocess
from check_gesture_parity import PLUGIN
from reference_build import build_probe

spec=importlib.util.spec_from_file_location('metadata_converter',PLUGIN/'Tools/convert_animation_metadata.py')
converter=importlib.util.module_from_spec(spec);spec.loader.exec_module(converter)


def fixture():
    value=dict(version=1,source_bank='Fixture.abin',source_sha256='a'*64,source_bytes=100000,
               clips=[],phase_blends=[],blend_spaces=[],selectors=[],selection_spaces=[],unsupported_trees=[])
    clip=dict(name='DUP',source_offset=48,fps_bits=0x41f00000,frames_bits=0x42400000,base_speed_bits=0x3f800000,flags_word=0,attributes=[])
    value['clips']=[clip,dict(clip,source_offset=96,flags_word=7),dict(clip,source_offset=96,flags_word=9)]
    value['phase_blends']=[dict(name='DUP',source_offset=96,parameter='VALUE',children=['DUP','DUP']),dict(name='DUPE_TREE',source_offset=128,parameter='VALUE',children=['DUP','DUP'])]
    value['selectors']=[dict(name='DUPE_TREE',source_offset=128,parameter='VALUE',default='DUP',children=['DUP','DUP'],values=['VALUE','VALUE'])]
    value['unsupported_trees']=[dict(name='DUP',source_offset=160,type_id=10),dict(name='UNSUPPORTED',source_offset=144,type_id=9)]
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assets',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--target-dir',required=True,type=Path)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    reference=build_probe(output,'animation-metadata-reference',PLUGIN/'Tests/Reference/animation_metadata_export.rs',args.target_dir)
    decoded=output/'decoded';native=output/'native';subprocess.run([str(reference),'export',str(args.assets.resolve()),str(decoded)],check=True)
    report=converter.convert_animation_metadata(decoded,native)
    code=PLUGIN/'Source/AtelierSkate/Private/Native';binary=output/'animation-metadata-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),str(code/'AnimationMetadata.cpp'),str(PLUGIN/'Tests/Native/animation_metadata_probe.cpp'),'-o',str(binary)],check=True)
    for bank in report['banks']:
        actual=subprocess.check_output([str(binary),'dump',str(native/bank['file'])]);expected=(decoded/Path(bank['file']).with_suffix('.raw')).read_bytes()
        if actual!=expected:raise AssertionError(f'Original metadata word/order differs: {bank["file"]}')
    actual=subprocess.check_output([str(binary),'merge',str(native/'bank-0.skate'),str(native/'bank-1.skate'),str(decoded/'queries.txt')])
    if actual!=(decoded/'queries.raw').read_bytes():raise AssertionError('Original bank identity or authored lookup differs')
    fixtures=[fixture()]
    rng=random.Random(0x46513a6)
    for index in range(32):
        value=fixture();value['source_bank']=f'Fixture{index}.abin'
        for c in value['clips']:c['source_offset']=rng.choice([48,96,128,160]);c['flags_word']=rng.getrandbits(32)
        for group in ('phase_blends','selectors','unsupported_trees'):
            for t in value[group]:t['source_offset']=rng.choice([48,96,128,160])
        fixtures.append(value)
    queries=output/'fixture-queries.txt';queries.write_text('dup\ndupe_tree\nunsupported\nmissing\nbad-name\n')
    for index,value in enumerate(fixtures):
        source=output/f'fixture-{index}.json';source.write_text(json.dumps(value));packed=output/f'fixture-{index}.skate';packed.write_bytes(converter.pack_metadata(value))
        expected=subprocess.check_output([str(reference),'query',str(source),str(queries)])
        actual=subprocess.check_output([str(binary),'query',str(packed),str(queries)])
        if actual!=expected:raise AssertionError(f'Duplicate/cross-type/tie lookup differs: {index}')
    first=fixtures[0];second=fixture();second['source_bank']='Second.abin';second['source_sha256']='B'*64
    for group in ('clips','phase_blends','selectors','unsupported_trees'):
        for t in second[group]:t['name']='OTHER_'+t['name']
    for index,(a,b) in enumerate(((first,second),(first,first))):
        paths=[]
        for label,value in (('a',a),('b',b)):
            source=output/f'merge-{index}-{label}.json';source.write_text(json.dumps(value));packed=source.with_suffix('.skate');packed.write_bytes(converter.pack_metadata(value));paths.append((source,packed))
        expected=subprocess.check_output([str(reference),'merge',str(paths[0][0]),str(paths[1][0]),str(queries)])
        actual=subprocess.check_output([str(binary),'merge',str(paths[0][1]),str(paths[1][1]),str(queries)])
        if actual!=expected:raise AssertionError('Merge namespace/source identity differs')
    # Native bounds checks, huge allocation counts, invalid dimensions and
    # header rejection are tested independently of reference JSON formatting.
    valid=(native/'bank-0.skate').read_bytes();malformed=[b'',valid[:8],valid[:40],valid[:-1],valid+b'\0',b'INVALID!'+valid[8:]]
    invalid=fixture();invalid['clips'][0]['fps_bits']=0x7fc01234;malformed.append(converter.pack_metadata(invalid))
    invalid=fixture();invalid['phase_blends'][0]['children']=[];malformed.append(converter.pack_metadata(invalid))
    invalid=fixture();invalid['selectors'][0]['values']=[];malformed.append(converter.pack_metadata(invalid))
    for index,data in enumerate(malformed):
        bad=output/f'invalid-{index}.skate';bad.write_bytes(data)
        if subprocess.run([str(binary),'dump',str(bad)],capture_output=True).returncode!=2:raise AssertionError('Malformed metadata was accepted')
    result=dict(passed=True,comparison='all original records, raw words, array ordering, bank identities and lookup results',
                banks=report['banks'],queries=len((decoded/'queries.txt').read_text().splitlines()),duplicate_fixtures=len(fixtures),merge_fixtures=2,malformed_fixtures=len(malformed))
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
