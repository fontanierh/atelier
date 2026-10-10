#!/usr/bin/env python3
"""Former Unreal %.17g -> actual locked serde_json default f32 boundary.

Preflight only stages sources/corpus and verifies provenance. Compilation and
execution belong to the root's render-locked, memory-guarded job. The oracle uses
the original Cargo manifest/lock and actual serde_json, not copied arithmetic.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tarfile
import tomllib
from session_parity import PLUGIN,REFERENCE_REVISION,digest

ROOT=PLUGIN.parents[4]
CODE=PLUGIN/'Source/AtelierSkate/Private/Simulation'
TESTS=PLUGIN/'Tests'
OWNED=(CODE/'HostScalar.h',CODE/'HostScalar.cpp',TESTS/'Simulation/host_scalar_probe.cpp',
       TESTS/'Reference/host_scalar_probe.rs',Path(__file__))
SERDE_VERSION='1.0.151'
SERDE_CHECKSUM='c841b55ecdae098c80dcae9cf767f6f8a0c2cdb3416bbef72181df4d0fe73f14'
SENTINEL=struct.unpack('<I',struct.pack('<f',-151.375))[0]


def f32(word):return struct.unpack('<f',struct.pack('<I',word))[0]
def f64(word):return struct.unpack('<d',struct.pack('<Q',word))[0]
def dword(value):return struct.unpack('<Q',struct.pack('<d',value))[0]


def corpus():
    rows=[];rng=random.Random(0x17f32015)
    def token(text,tag):rows.append(dict(operation=0,token=text,tag=tag))
    def number(value,tag,operation=1,**extra):rows.append(dict(operation=operation,double_bits=dword(value),tag=tag,**extra))
    # Source-ordered syntax/range errors, exponent saturation and underflow.
    for text in ('',' ','\n\t','-','--1','+1','01','-01','00.1','1.','1.x','1e','1e+',
                 '1e-','1eX','1e+X','1e--2','1 2','1\n2','0x1','nan','-nan','inf','-inf',
                 'NaN','Infinity','null','true','false','n','nu','nul','nulX','truX','falsX',
                 '[]','{}','1e309','-1e309','1e99999999999999999999999',
                 '-1e2147483648','1e21474836470','1e+2147483648 ',
                 '9'*400,'-'+'9'*400):token(text,'syntax_or_range')
    for text in ('0','-0','0.0','-0.0','0e0','-0e0','0e2147483648','-0e2147483648',
                 '0e99999999999999999999','-0e-99999999999999999999','1e-2147483648',
                 '-1e-2147483648','1e-99999999999999999999','1e-309','1e-324',
                 '4.9406564584124654e-324','1.7976931348623157e308',
                 '1.7976931348623158e308','18446744073709551615',
                 '18446744073709551616','-9223372036854775808','-9223372036854775809',
                 '123456789012345678901234567890.123456789','0.'+'9'*400,
                 '\n\t -0.0 \r\n'):token(text,'numeric_boundary')
    # Direct integer visitors must not be rounded first into f64.
    for exponent in range(24,64):
        midpoint=(1<<exponent)+(1<<(exponent-24))
        for delta in (-4,-2,-1,0,1,2,4):
            for sign in ('','-'):token(sign+str(midpoint+delta),'integer_midpoint')
    for word in (0,0x8000000000000000,1,0x8000000000000001,0x000fffffffffffff,
                 0x0010000000000000,0x7fefffffffffffff,0xffefffffffffffff,
                 0x7ff0000000000000,0xfff0000000000000,0x7ff8123456789abc,
                 0xfff8123456789abc,0x7ff0000000000001,0xfff0000000000001):
        number(f64(word),'double_boundary')
    # Every binary64 exponent plus adjacent scientific-decimal boundaries.
    for exponent in range(0,2047):
        for sign in (0,1):
            word=(sign<<63)|(exponent<<52)|rng.getrandbits(52)
            number(f64(word),'binary64_exponent')
    for exponent in range(-324,309):
        for significant in ('1','9.9999999999999999','1.0000000000000001'):
            for sign in ('','-'):token(f'{sign}{significant}e{exponent}','decimal_exponent')
    # Exact f32 values must survive the old formatter/parser without a new loss.
    float_words=[0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x3f800000,
                 0xbf800000,0x7f7fffff,0xff7fffff]
    float_words += [rng.randrange(0x7f800000)|(rng.randrange(2)<<31)for _ in range(2048)]
    for word in float_words:number(float(f32(word)),'already_f32',expected_bits=word)
    # Genuine adjacent-f32 ties, both double neighbours, and the original UE
    # ToSimulation(double cm)*.01 operation before its command serialization.
    mids=[0x3f800000+i for i in range(1024)]
    mids += [rng.randrange(0x7f7fffff)for _ in range(1024)]
    for word in mids:
        middle=(float(f32(word))+float(f32(word+1)))/2
        for sign in (1,-1):
            for value in (math.nextafter(middle,-math.inf),middle,math.nextafter(middle,math.inf)):
                number(sign*value,'f32_midpoint')
            number(sign*(middle/.01),'ue_centimetre_midpoint',operation=2)
    # A deterministic representative fuzz set includes finite/subnormal,
    # negative-zero, overflow-to-f32 and source printf's non-finite spellings.
    for _ in range(8192):number(f64(rng.getrandbits(64)),'binary64_fuzz')
    witness=100.00002980232239
    number(witness,'known_rounding_witness',operation=2,expected_bits=0x3f800003,direct_bits=0x3f800002)
    encoded=bytearray(struct.pack('<I',len(rows)))
    for index,row in enumerate(rows):
        row['index']=index;encoded.extend(struct.pack('<I',row['operation']))
        if row['operation']==0:
            raw=row['token'].encode();encoded.extend(struct.pack('<I',len(raw)));encoded.extend(raw)
        else:encoded.extend(struct.pack('<Q',row['double_bits']))
    return bytes(encoded),rows


def validate_input(data,rows):
    at=0
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0];at+=4;return value
    assert word()==len(rows)
    for row in rows:
        assert word()==row['operation']
        if row['operation']==0:
            size=word();assert data[at:at+size]==row['token'].encode();at+=size
        else:
            assert struct.unpack_from('<Q',data,at)[0]==row['double_bits'];at+=8
    assert at==len(data)


def method(source,anchor,start):
    assert source[start:].startswith(anchor)
    at=source.index('{',start);depth=1;end=at+1
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    body=source[start:end];assert body.startswith(anchor)and body[-1]=='}'
    return dict(start_byte=len(source[:start].encode()),end_byte=len(source[:end].encode()),sha256=hashlib.sha256(body.encode()).hexdigest())


def dependency_provenance(lock):
    packages=tomllib.loads(lock.read_text())['package'];package=next(p for p in packages if p['name']=='serde_json')
    assert package['version']==SERDE_VERSION and package['checksum']==SERDE_CHECKSUM
    cargo_home=Path(os.environ.get('CARGO_HOME',Path.home()/'.cargo'))
    matches=sorted((cargo_home/'registry/src').glob(f'*/serde_json-{SERDE_VERSION}'))
    assert len(matches)==1,'Expected one exact locked serde_json source in the offline registry'
    dependency=matches[0];source=(dependency/'src/de.rs').read_text()
    anchors=('fn parse_integer(', 'fn parse_number(', 'fn parse_decimal(', 'fn parse_exponent(',
             'fn f64_from_parts(\n', 'fn parse_long_integer(&mut self, positive: bool, significand: u64)',
             'fn parse_decimal_overflow(\n', 'fn parse_exponent_overflow(')
    methods={}
    for anchor in anchors:
        # Both optional implementations are hashed when an overload exists.
        begins=[m.start()for m in re.finditer(re.escape(anchor),source)]
        methods[anchor]=[method(source,anchor,i)for i in begins]
    start=source.index('static POW10: [f64; 309] = [');end=source.index('];',start)+2
    body=source[source.index('[\n',start)+2:end-2]
    simulation=(CODE/'HostScalar.cpp').read_text();a=simulation.index('static const double Pow10[309] = {\n')
    a=simulation.index('\n',a)+1;b=simulation.index('};',a)
    assert simulation[a:b]==body,'Original POW10 literal table changed'
    serde=next(p for p in packages if p['name']=='serde');serde_source=next((cargo_home/'registry/src').glob(f"*/serde-{serde['version']}/src/core/de/impls.rs"))
    return dict(package=package,serde_version=serde['version'],files={p.relative_to(dependency).as_posix():digest(p)for p in(dependency/'src/de.rs',dependency/'src/read.rs',dependency/'src/error.rs',dependency/'Cargo.toml')},numeric_method_boundaries=methods,pow10=dict(start_byte=start,end_byte=end,body_sha256=hashlib.sha256(body.encode()).hexdigest(),literal_count=309),f32_visitor_source_sha256=digest(serde_source),expected_features=['default','std'],scope='Source-ordered numeric token parser and printf spellings only; no object/string/asset/command JSON reader. Actual oracle owns all parsing, range rejection, integer visitors and error messages.')


def feature_audit(target):
    fingerprints=sorted((target/'release/.fingerprint').glob('serde_json-*/lib-serde_json.json'))
    assert fingerprints,'Actual built serde_json feature fingerprint is required'
    observed=[]
    for path in fingerprints:
        data=json.loads(path.read_text());features=json.loads(data['features'])
        assert features==['default','std'],features
        observed.append(dict(file=path.name,parent=path.parent.name,sha256=digest(path),features=features))
    return observed


def stage_reference(out,target):
    relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(ROOT).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=ROOT)
    source=out/'reference-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive))as stream:stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p)for p in sorted(source.rglob('*.rs'))}
    crate=source/'atelier-host';cargo=crate/'Cargo.toml';original_cargo=cargo.read_bytes()
    cargo.write_bytes(original_cargo+b'\n[[bin]]\nname="host-scalar-reference"\npath="src/migration_probe.rs"\n')
    shutil.copy2(TESTS/'Reference/host_scalar_probe.rs',crate/'src/migration_probe.rs')
    dependency=dependency_provenance(crate/'Cargo.lock')
    assert all(digest(source/rel)==sha for rel,sha in originals.items())
    report=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),original_source_sha256=originals,cargo_original_sha256=hashlib.sha256(original_cargo).hexdigest(),cargo_staged_sha256=digest(cargo),cargo_lock_sha256=digest(crate/'Cargo.lock'),dependency=dependency,actual_feature_fingerprints=feature_audit(target),probe_sha256=digest(TESTS/'Reference/host_scalar_probe.rs'),scope=__doc__)
    (out/'reference-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return crate,originals


def stage_simulation(out):
    source=out/'simulation-source'
    if source.exists():shutil.rmtree(source)
    source.mkdir()
    for path in OWNED[:3]:shutil.copy2(path,source/path.name)
    report={p.name:digest(p)for p in sorted(source.iterdir())}
    (out/'simulation-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return source


def coverage(data,rows):
    at=0
    def word():
        nonlocal at
        value=struct.unpack_from('<I',data,at)[0];at+=4;return value
    def text():
        nonlocal at
        size=word();value=data[at:at+size].decode();at+=size;return value
    assert word()==len(rows);counts=Counter();errors=Counter();direct=Counter();zero=Counter();witness=None
    for row in rows:
        assert word()==row['index']and word()==row['operation']
        token=text();okay=word();value=word();error=text();cast=word()
        counts[(row['tag'],okay)]+=1
        if okay:
            assert error==''
            if value in(0,0x80000000):zero[value]+=1
            if row['operation']!=0 and value!=cast:direct[row['tag']]+=1
            if 'expected_bits'in row:assert value==row['expected_bits'],(row,value)
        else:
            assert value==SENTINEL and error;errors[error.split(' at line ')[0]]+=1
        if row['operation']==0:assert token==row['token']
        if row['tag']=='known_rounding_witness':
            assert okay and cast==row['direct_bits']and token=='1.0000002980232239';witness=dict(token=token,parsed_bits=value,direct_bits=cast)
    assert at==len(data)
    assert sum(n for(tag,okay),n in counts.items()if okay)>10000
    assert sum(n for(tag,okay),n in counts.items()if not okay)>=35
    assert direct['ue_centimetre_midpoint']>100 and direct['f32_midpoint']>100,direct
    assert zero[0]>100 and zero[0x80000000]>100,zero
    for kind in('invalid number','number out of range','EOF while parsing a value','trailing characters','expected ident','expected value'):assert errors[kind]>0,errors
    assert counts[('already_f32',1)]==2058 and counts[('already_f32',0)]==0
    return dict(records=len(rows),successful=sum(n for(tag,okay),n in counts.items()if okay),rejected=sum(n for(tag,okay),n in counts.items()if not okay),tag_status={tag:{str(okay):counts[(tag,okay)]for okay in(0,1)}for tag in sorted({t for t,_ in counts})},error_classes=dict(errors),different_from_direct_cast=dict(direct),signed_zero_counts={f'{word:08x}':count for word,count in zero.items()},known_midpoint=witness,retained_failure_output=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--target-dir',type=Path,required=True)
    parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);target=args.target_dir.resolve()
    data,rows=corpus();validate_input(data,rows);(out/'input.bin').write_bytes(data)
    (out/'cases.json').write_text(json.dumps(rows,indent=2)+'\n')
    crate,originals=stage_reference(out,target);snapshot=stage_simulation(out)
    freeze=dict(owned={p.relative_to(ROOT).as_posix():digest(p)for p in OWNED},corpus_rows=len(rows),corpus_sha256=hashlib.sha256(data).hexdigest(),simulation_units=['HostScalar'],reference_provenance_sha256=digest(out/'reference-provenance.json'),simulation_provenance_sha256=digest(out/'simulation-provenance.json'))
    (out/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
    if args.preflight:print(json.dumps(dict(preflight=True,**freeze),indent=2));return
    reference=out/'host-scalar-reference';simulation=out/'host-scalar-simulation'
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--locked','--jobs','2','--manifest-path',str(crate/'Cargo.toml'),'--target-dir',str(target),'--bin','host-scalar-reference'],check=True)
    shutil.copy2(target/'release/host-scalar-reference',reference)
    feature_audit(target)
    assert all(digest(out/'reference-source'/rel)==sha for rel,sha in originals.items())
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),str(snapshot/'HostScalar.cpp'),str(snapshot/'host_scalar_probe.cpp'),'-o',str(simulation)],check=True)
    expected=subprocess.check_output([str(reference)],input=data);actual=subprocess.check_output([str(simulation)],input=data)
    (out/'reference.bin').write_bytes(expected);(out/'simulation.bin').write_bytes(actual)
    if expected!=actual:
        first=next((i for i,(a,b)in enumerate(zip(expected,actual))if a!=b),min(len(expected),len(actual)))
        (out/'first-divergence.json').write_text(json.dumps(dict(byte=first,reference_bytes=len(expected),simulation_bytes=len(actual)),indent=2)+'\n')
        raise AssertionError(f'Host scalar differs at byte {first}')
    proof=coverage(expected,rows)
    result=dict(passed=True,coverage=proof,output_bytes=len(actual),output_sha256=hashlib.sha256(actual).hexdigest(),freeze_sha256=digest(out/'freeze.json'),reference_binary_sha256=digest(reference),simulation_binary_sha256=digest(simulation),comparison='Exact actual pinned serde_json::from_str::<f32> bits and errors, libc %.17g text, direct integer visitors, signed zero, u64/exponent overflow, and unchanged destination on failure.',limitations='Focused numeric command conversion only. General strings/objects/assets are outside this helper. Unreal FString formatting is source-audited to the same libc conversion, not executed in this standalone proof. Candidate command integration and complete live Unreal output remain separately verified.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
