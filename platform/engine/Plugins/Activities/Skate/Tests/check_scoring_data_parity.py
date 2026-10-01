#!/usr/bin/env python3
"""Exact original scoring catalog, definitions, collector tuning and load order.

Only the root render guard compiles and runs. Every original implementation
byte remains unchanged; the generated module appends a read-only observer.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
from check_gesture_parity import PLUGIN, converter
from check_skeleton_input_runtime_parity import source
from reference_build import build_probe
from session_parity import REFERENCE_REVISION, digest

CODE=PLUGIN/'Source/AtelierSkate/Private/Native'
UNITS=('NativeMath','NameId','Settings','StockSettingsReader','AnimationName','ScoringCatalog','ScoringData')
SCORABLE='Hash_6918469984A8C596'
COLLECTOR='Hash_546C36B656038E04'
TUNING='Hash_349215E2E817703C'
ALIASES={'atelier-host/src/scoring_fields.rs':'crates/skate-data/src/scoring_fields.rs'}

def schema():
    catalog=source('crates/skate-core/src/scoring/catalog.rs')
    identifiers=re.findall(r'\("([^"]+)",\s*(\d+),\s*(\d+)\)',catalog)
    assert len(identifiers)==332
    fields=source('crates/skate-data/src/scoring_fields.rs')
    collector=[(int(offset,16),name,int(size))for offset,name,size in re.findall(r'\((0x[0-9a-f]+),\s*"([^"]+)",\s*(\d+)\)',fields)]
    assert len(collector)==62
    order=[(SCORABLE,identifiers[0][0],name,kind)for name,kind in(
        ('Hash_B2383F16252DFE8E','enum'),('Hash_843613E915014627','text'),
        ('Hash_937F62AE5C1ED284','integer'),('TrickType','word'),
        ('Hash_DC7F402E5680BA02','float'),('Hash_2E90BC04042A0B5A','word'),
        ('Hash_D34A84B044B60CE3','word'))]
    order.extend((COLLECTOR,'default',name,'float'if size==4 else'raw_curve')for _,name,size in collector)
    order.extend((TUNING,'default',name,'curve')for name in('Hash_59D91EAABF033A24','Hash_263B277F8CA17126'))
    order.extend((TUNING,'default',name,'float')for name in(
        'Hash_FE02A45231F7B06A','Hash_57478337ACCFFF18','Hash_88407506DC9780ED','Hash_28767A5F961C7129',
        'Hash_829887D8C24A5B8A','Hash_4752056364FF91FE','Hash_FB8408A15C17A9D4','Hash_F4993A13ED7B44C1',
        'Hash_30AAE071A7868771','Hash_DC0C3853F6C5FC2E','Hash_E36197BFC8EA1CAD','Hash_2577DF0FCE5251E4',
        'Hash_B0B56FF046508506','Hash_6DC5982591F80A4C'))
    assert len(order)==85
    return identifiers,collector,order

def row(data,category,key):
    return next(r for r in data['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))

def resolve(data,category,key,name):
    for _ in range(len(data['collections'])+1):
        record=row(data,category,key)
        actual=next((n for n in record['fields']if converter.name_id(n)==converter.name_id(name)),None)
        if actual is not None:return copy.deepcopy(record['fields'][actual])
        key=record['parent'];assert key,(category,name)
    raise AssertionError((category,key,name))

def fixtures(assets):
    identifiers,collector,order=schema();stock=json.loads((assets/'private/stock/skater-collections.json').read_text())
    base={'version':1,'collections':[]}
    for category,key in((SCORABLE,identifiers[0][0]),(COLLECTOR,'default'),(TUNING,'default')):
        fields={name:resolve(stock,category,key,name)for c,k,name,_ in order if c==category and k==key}
        base['collections'].append(dict(class_=category,key=key,parent='',source='scoring-parity',sha256='',fields=fields))
        base['collections'][-1]['class']=base['collections'][-1].pop('class_')
    result=[]
    def add(label,data,okay,position=None,later=None):result.append(dict(label=label,data=data,success=okay,first_position=position,second_position=later))
    def mutate(data,field,kind):
        category,key,name,typ=field;record=row(data,category,key);value=record['fields'][name]
        if kind=='missing':del record['fields'][name]
        elif kind=='type':
            value['type']='EA::Reflection::Float'if typ in('text','integer')else'EA::Reflection::UInt32'
            if typ=='text':value['data']='00000000'
        elif kind in('width','short'):
            value['data']=value['data']+'cafebabe'if kind=='width'else''
        elif kind in('nan','inf'):
            replacement='7fc12345'if kind=='nan'else'7f800000'
            at=32 if typ in('curve','raw_curve')else 0
            value['data']=value['data'][:at]+replacement+value['data'][at+8:]
        elif kind=='fail':
            if typ=='text':mutate(data,field,'type')
            else:mutate(data,field,'width')
        else:raise AssertionError(kind)
    add('single-complete-stock-definition',copy.deepcopy(base),True)
    add('all-original-stock-records',copy.deepcopy(stock),True)
    for position,field in enumerate(order):
        typ=field[3]
        for kind in('missing','type','width','short','nan','inf'):
            data=copy.deepcopy(base);mutate(data,field,kind)
            okay=(typ=='text'and kind not in('missing','type'))or(typ in('enum','word','curve','raw_curve')and kind=='type')or(typ in('integer','word','raw_curve')and kind in('nan','inf'))
            add(f'{position:02d}-{kind}',data,okay,position)
    # Observe every adjacent evaluation-order boundary, plus nonadjacent pairs
    # spanning all three independently loaded owners.
    pairs={(i,i+1)for i in range(len(order)-1)}|{(i,j)for i in range(7)for j in(7,25,68,69,70,84)if i<j}
    for first,later in sorted(pairs):
        data=copy.deepcopy(base);mutate(data,order[first],'fail');mutate(data,order[later],'fail')
        add(f'compound-{first:02d}-before-{later:02d}',data,False,first,later)
    data=copy.deepcopy(base);data['collections']=[r for r in data['collections']if r['class']!=SCORABLE];add('no-scorable-definitions',data,False)
    data=copy.deepcopy(base);row(data,SCORABLE,identifiers[0][0])['fields']['Hash_B2383F16252DFE8E']['data']='0000014c';add('enum-disagreement',data,False)
    for name in('Hash_59D91EAABF033A24','Hash_263B277F8CA17126'):
        data=copy.deepcopy(base);value=row(data,TUNING,'default')['fields'][name];words=[value['data'][i:i+8]for i in range(0,len(value['data']),8)];words[4:12]=['3f800000','00000000']+['40000000']*6;value['data']=''.join(words);add(f'{name}-descending',data,False)
        data=copy.deepcopy(base);value=row(data,TUNING,'default')['fields'][name];words=[value['data'][i:i+8]for i in range(0,len(value['data']),8)];words[4:12]=['80000000','00000000']+['3f800000']*6;value['data']=''.join(words);add(f'{name}-equal-knots-signed-zero',data,True)
    for alias in('scoring_trick','0x6918469984a8c596'):
        data=copy.deepcopy(base);r=row(data,SCORABLE,identifiers[0][0]);r['class']=alias;r['key']=f'Hash_{converter.name_id(r["key"]):016X}';add(f'normalized-{alias}',data,True)
    data=copy.deepcopy(base);r=row(data,SCORABLE,identifiers[0][0]);parent=copy.deepcopy(r);parent['key']='scoring-parity-parent';r['parent']=parent['key'];r['fields']={};data['collections'].append(parent);add('inherited-all-seven-definition-fields',data,True)
    data=copy.deepcopy(base);r=row(data,SCORABLE,identifiers[0][0]);r['parent']=r['key'];r['fields']={};add('cyclic-definition-inheritance',data,False)
    data=copy.deepcopy(base);r=row(data,SCORABLE,identifiers[0][0]);r['parent']='missing-scoring-parent';r['fields']={};add('missing-definition-parent',data,False)
    rng=random.Random(0x82da2340)
    for n in range(12):
        data=copy.deepcopy(base)
        for category,key,name,typ in order:
            value=row(data,category,key)['fields'][name]
            if typ in('float','integer','word'):
                word=struct.unpack('>I',struct.pack('>f',rng.uniform(-1e4,1e4)))[0]if typ=='float'else rng.getrandbits(32)
                value['data']=f'{word:08x}'
        row(data,SCORABLE,identifiers[0][0])['fields']['Hash_843613E915014627']['data']=f'Native ローカル trick {n}\x00 ✓'
        add(f'varied-raw-words-label-{n:02d}',data,True)
    return result,order

class Reader:
    def __init__(self,raw):assert len(raw)%4==0;self.words=struct.unpack('<'+'I'*(len(raw)//4),raw);self.at=0
    def word(self):w=self.words[self.at];self.at+=1;return w
    def take(self,n):r=self.words[self.at:self.at+n];assert len(r)==n;self.at+=n;return r
    def string(self):n=self.word();return struct.pack('<'+'I'*((n+3)//4),*self.take((n+3)//4))[:n].decode()
    def snapshot(self):return self.take(self.word())
    def status(self):return None if self.word()else self.string()

def decode(raw):
    r=Reader(raw);assert r.word()==332
    for _ in range(332):r.string();r.take(4)
    assert r.word()==62
    for _ in range(62):r.word();r.string();r.word()
    base=r.snapshot();attempts=[]
    for _ in range(3):attempts.append(dict(error=r.status(),state=r.snapshot()))
    assert r.at==len(r.words)and attempts[0]==attempts[1]
    assert attempts[-1]['error']is None and attempts[-1]['state']==base
    if attempts[0]['error']is not None:assert attempts[0]['state']==base
    return attempts[0]['error']

def prepare(output,assets):
    output.mkdir(parents=True,exist_ok=True);snapshot=output/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for p in[*sorted(CODE.glob('*.h')),*[CODE/(unit+'.cpp')for unit in UNITS],PLUGIN/'Tests/Native/scoring_data_probe.cpp']:shutil.copy2(p,snapshot/p.name)
    original=source('crates/skate-data/src/scoring.rs');template=PLUGIN/'Tests/Reference/scoring_data_probe.rs';text=template.read_text();assert text.count('// ORIGINAL_SCORING_DATA')==1
    generated=output/'scoring-data-reference.rs';generated.write_text(text.replace('// ORIGINAL_SCORING_DATA',original));assert original.encode()in generated.read_bytes()
    provenance=dict(reference_revision=REFERENCE_REVISION,original_scoring_data_sha256=hashlib.sha256(original.encode()).hexdigest(),probe_template_sha256=digest(template),native_source_sha256={p.name:digest(p)for p in snapshot.iterdir()},units=UNITS)
    # Keep every scoring definition, parent and tuning record unchanged. The
    # unrelated 6,533 stock records otherwise dominate repeated pure-loader
    # execution. --baseline-output asserts byte identity with the complete
    # bank for every already recorded original/native fixture.
    complete=assets/'private/stock/skater-collections.json';data=json.loads(complete.read_text())
    categories={converter.name_id(c)for c in(SCORABLE,COLLECTOR,TUNING)}
    retained=[r for r in data['collections']if converter.name_id(r['class'])in categories]
    identities={(converter.name_id(r['class']),converter.name_id(r['key']))for r in retained}
    for r in retained:
        if r['parent']:assert(converter.name_id(r['class']),converter.name_id(r['parent']))in identities
    scoring_assets=output/'stock-assets';path=scoring_assets/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(dict(version=data['version'],collections=retained))+'\n')
    provenance.update(complete_stock_json_sha256=digest(complete),scoring_stock_json_sha256=digest(path),complete_stock_records=len(data['collections']),retained_scoring_records=len(retained),stock_filter='Only unrelated categories removed; every scoring record/field/parent remains unchanged in original order. Entire full-bank output is independently compared where baseline evidence exists.')
    stock=output/'stock.native';stock.write_bytes(converter.encode_settings(path))
    cases,order=fixtures(assets);records=[]
    for index,case in enumerate(cases):
        folder=output/'fixtures'/f'{index:03d}-{case["label"]}';path=folder/'private/stock/skater-collections.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(case['data'])+'\n');bank=folder/'settings.native';bank.write_bytes(converter.encode_settings(path));records.append({k:v for k,v in case.items()if k!='data'}|dict(folder=str(folder),bank=str(bank),json_sha256=digest(path),native_sha256=digest(bank)))
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');(output/'fixtures.json').write_text(json.dumps(records,indent=2)+'\n')
    return snapshot,generated,records,order

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in('assets','output','target-dir'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--preflight',action='store_true');parser.add_argument('--baseline-output',type=Path);a=parser.parse_args();out=a.output.resolve();assets=a.assets.resolve();snapshot,generated,fixtures,order=prepare(out,assets)
    if a.preflight:print(json.dumps(dict(fixtures=len(fixtures),success=sum(f['success']for f in fixtures),read_positions=len(order),units=len(UNITS)),indent=2));return
    reference=build_probe(out,'scoring-data-reference',generated,a.target_dir,extra_sources=ALIASES);native=out/'scoring-data-native'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fno-fast-math','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror','-I',str(snapshot),*[str(snapshot/(u+'.cpp'))for u in UNITS],str(snapshot/'scoring_data_probe.cpp'),'-o',str(native)],check=True)
    total=0;combined=hashlib.sha256();results=[];first_errors={};baseline_cases=0
    for fixture in fixtures:
        folder=Path(fixture['folder']);expected=subprocess.check_output([str(reference),str(out/'stock-assets'),str(folder)]);actual=subprocess.check_output([str(native),str(out/'stock.native'),fixture['bank']]);(folder/'reference.bin').write_bytes(expected);(folder/'native.bin').write_bytes(actual)
        if a.baseline_output:
            previous=a.baseline_output.resolve()/'fixtures'/folder.name
            if(previous/'reference.bin').exists()and(previous/'native.bin').exists():
                assert(previous/'reference.bin').read_bytes()==expected,(fixture['label'],'full-bank original baseline changed')
                assert(previous/'native.bin').read_bytes()==actual,(fixture['label'],'full-bank native baseline changed')
                baseline_cases+=1
        if expected!=actual:
            byte=next((i for i,(x,y)in enumerate(zip(expected,actual))if x!=y),min(len(expected),len(actual)));failure=dict(fixture=fixture['label'],byte=byte,word=byte//4,reference_bytes=len(expected),native_bytes=len(actual));(out/'first-divergence.json').write_text(json.dumps(failure,indent=2)+'\n');raise AssertionError(failure)
        error=decode(expected);assert(error is None)==fixture['success'],(fixture['label'],error,fixture['success'])
        if (fixture['label'].endswith('-width')and error is not None)or fixture['label']=='01-type':first_errors[fixture['first_position']]=error
        if fixture['second_position']is not None:assert error==first_errors[fixture['first_position']],(fixture['label'],error,first_errors)
        total+=len(expected);combined.update(expected);results.append(dict(label=fixture['label'],error=error,bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest()))
    result=dict(passed=True,reference_revision=REFERENCE_REVISION,fixtures=len(fixtures),successful_fixtures=sum(f['success']for f in fixtures),read_positions=len(order),compound_fixtures=sum(f['second_position']is not None for f in fixtures),complete_bank_baseline_cases=baseline_cases,exact_bytes=total,output_sha256=combined.hexdigest(),results=results,scope='Complete original ScoringData/CollectorTuning loader and every retained field, 332 catalog/conversion rows, 62 collector fields, exact lookup/session rules/curve evaluation, ordered errors, staged failure and recovery. All scoring stock records unchanged; unrelated classes omitted only from repeated fixture initialization and verified against complete-bank baseline. Physical trick collectors and global scheduling remain separate.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='results'},indent=2))
if __name__=='__main__':main()
