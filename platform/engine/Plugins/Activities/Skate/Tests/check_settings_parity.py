#!/usr/bin/env python3
"""Verify every converted settings field and lookup against the original JSON values.

The expected values are read directly from the original dataset, not decoded from
the converted file. Name hashing has a separate independent Rust differential test.
Run under atelier.safety because this command compiles the C++ settings probe.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter, PLUGIN


def word(target,value):
    target.extend(struct.pack('<I',value))


def string(target,value):
    raw=value.encode('utf-8');word(target,len(raw));target.extend(raw)


def field(target,name,value):
    string(target,name);string(target,value['type'])
    data=value['data'] if value['type']=='EA::Reflection::Text' else bytes.fromhex(value['data']).hex().upper()
    string(target,data)


def typed_values(target,name,value):
    word(target,value is not None)
    if value is None:
        return
    field(target,name,value)
    kind=value['type'];flags=floats=integers=booleans=0
    if kind!='EA::Reflection::Text':
        raw=bytes.fromhex(value['data'])
        if kind=='EA::Reflection::Float' and len(raw)==4 and math.isfinite(struct.unpack('>f',raw)[0]):
            flags|=1;floats=int.from_bytes(raw,'big')
        if kind in ('EA::Reflection::UInt32','EA::Reflection::Int32') and len(raw)==4:
            flags|=2;integers=int.from_bytes(raw,'big')
        if kind=='EA::Reflection::Bool' and raw and raw[0] in (0,1):
            flags|=4;booleans=raw[0]
    for value in (flags,floats,integers,booleans):word(target,value)


def expected_dump(records):
    result=bytearray();word(result,len(records))
    for record in records:
        for key in ('class','key','parent'):string(result,record[key])
        word(result,len(record['fields']))
        for name,value in sorted(record['fields'].items()):field(result,name,value)
    return bytes(result)


def queries(records):
    identity=lru_cache(None)(converter.name_id)
    index={(identity(r['class']),identity(r['key'])):r for r in records}
    requests=[];expected=bytearray();inherited=0
    def resolve(category,key,name):
        for _ in range(len(records)+1):
            record=index.get((identity(category),identity(key)))
            if record is None:return None,None
            if name in record['fields']:return name,record['fields'][name]
            found=next(((k,v) for k,v in sorted(record['fields'].items()) if identity(k)==identity(name)),None)
            if found:return found
            if not record['parent']:return None,None
            key=record['parent']
        return None,None
    def query(category,key,name):
        requests.append((category,key,name))
        found_name,value=resolve(category,key,name)
        typed_values(expected,found_name,value)
    for record in records:
        available=set(record['fields'])
        parent=record['parent'];seen=set()
        while parent and identity(parent) not in seen:
            seen.add(identity(parent))
            ancestor=index.get((identity(record['class']),identity(parent)))
            if ancestor is None:break
            available.update(ancestor['fields']);parent=ancestor['parent']
        for name in sorted(available):
            query(record['class'],record['key'],name)
            query(f'0x{identity(record["class"]):016x}',f'Hash_{identity(record["key"]):016X}',f'0x{identity(name):016x}')
            if name not in record['fields']:inherited+=1
        query(record['class'],record['key'],'absent-port-test-field')
    query('absent-port-test-category','default','value')
    encoded=bytearray();word(encoded,len(requests))
    for request in requests:
        for value in request:string(encoded,value)
    return bytes(encoded),bytes(expected),dict(queries=len(requests),inherited_fields=inherited)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    source=args.assets/'private/stock/skater-collections.json'
    records=json.loads(source.read_text())['collections']
    simulation=output/'settings.skate';simulation.write_bytes(converter.encode_settings(source))
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation';binary=output/'settings-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-I',str(code),
                    str(code/'Settings.cpp'),str(code/'NameId.cpp'),str(PLUGIN/'Tests/Simulation/settings_probe.cpp'),
                    '-o',str(binary)],check=True)
    actual=subprocess.check_output([str(binary),str(simulation),'dump'])
    expected=expected_dump(records)
    if actual!=expected:
        (output/'expected-fields.bin').write_bytes(expected);(output/'actual-fields.bin').write_bytes(actual)
        raise AssertionError('C++ settings values differ from the original dataset')
    commands,expected,counts=queries(records)
    (output/'queries.bin').write_bytes(commands)
    actual=subprocess.check_output([str(binary),str(simulation),'query'],input=commands)
    if actual!=expected:
        (output/'expected-queries.bin').write_bytes(expected);(output/'actual-queries.bin').write_bytes(actual)
        first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)))
        raise AssertionError(f'C++ settings lookup differs at byte {first}')
    for i,raw in enumerate((b'',simulation.read_bytes()[:-1],simulation.read_bytes()+b'\0')):
        bad=output/f'invalid-{i}.skate';bad.write_bytes(raw)
        result=subprocess.run([str(binary),str(bad),'dump'],capture_output=True)
        if result.returncode!=2:raise AssertionError('Malformed settings data was accepted')
    report=dict(passed=True,records=len(records),fields=sum(len(r['fields']) for r in records),**counts,
                comparison='exact source fields, inherited/alias lookups and typed numeric bits',
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                simulation_sha256=hashlib.sha256(simulation.read_bytes()).hexdigest(),
                query_output_sha256=hashlib.sha256(expected).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
