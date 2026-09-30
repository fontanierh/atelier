#!/usr/bin/env python3
"""Compare native graph values, lookup and binding with the unmodified Rust reader.

Compiles both probes: run through atelier.safety. Original input and native data
are read independently. Whole-graph execution is checked separately after porting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
from check_gesture_parity import converter, PLUGIN


def attribute(name, text='', bits=0, boolean=0):
    return dict(name=name, text=text, float_bits=bits, boolean_byte=boolean)


def element(tag, name=None, attributes=(), children=()):
    return dict(tag=tag, attributes=([attribute('name',name)] if name is not None else [])+list(attributes), children=list(children))


def original_graph(root):
    """Synthetic source inputs are serialized into the original binary grammar."""
    result=bytearray()
    def string(value):
        result.extend(value.encode('utf-8')+b'\0')
    pending=[root]
    while pending:
        node=pending.pop()
        string(node['tag']); result.extend(struct.pack('>I',len(node['attributes'])))
        for value in node['attributes']:
            string(value['name']); string(value['text'])
            result.extend(struct.pack('>IB',value['float_bits'],value['boolean_byte']))
        result.extend(struct.pack('>I',len(node['children'])))
        pending.extend(reversed(node['children']))
    return bytes(result)


def fixtures(collision):
    yield 'typed-duplicates-collision', element('state','',[
        attribute('enabled','false',0x7fc00123,7), attribute('enabled','true',0,0),
        attribute('active','',0xff800000,255), attribute('', '',0x80000000,13),
        attribute(collision[0],'first',0x7fc00001,41),attribute(collision[1],'second',0x80000001,99)])
    conditions=[element('condition',f'condition-{i}',[attribute('mask',mask)],
                        [element('param',attributes=[attribute('value','',0x3f800000+i,2)])])
                for i,mask in enumerate(('precond','sustain','always','postcond','','Sustain','unknown'))]
    children=[element('state','same',children=[element('state','same')]),
              element('state','disabled',[attribute('enabled',boolean=0)],
                      [element('state','inherited',[attribute('enabled',boolean=255)])]),
              element('state','branch',children=[element('state','leaf',[attribute('interruptable','root')])]),
              element('behaviour','behavior',children=[element('param','p1'),element('param','p2')]),
              element('expression',attributes=[attribute('op','or')],children=conditions),
              element('expression',attributes=[attribute('op','and')],children=[
                  element('expression',attributes=[attribute('op','not')],children=[element('condition','nested')])])]
    for i,target in enumerate(('same','root','branch.leaf','disabled.inherited','missing','','branch..leaf')):
        children.append(element('transition',f't{i}',[attribute('target',target),attribute('priority',('','med','high','urgent')[i%4])],
                                [element('expression'),element('hook','hook',children=[element('param','p')])]))
    yield 'binding-and-paths',element('state','root',children=children)
    yield 'interrupt-self',element('state','root',children=[element('state','child',[attribute('interruptable','child')])])
    yield 'invalid-interrupt-sibling',element('state','root',children=[element('state','a',[attribute('interruptable','b')]),element('state','b')])
    yield 'invalid-interrupt-missing',element('state','root',[attribute('interruptable','absent')])
    yield 'invalid-tag',element('state','root',children=[element('unsupported')])
    yield 'invalid-transition-root',element('transition')
    yield 'invalid-state-parent',element('state','root',children=[element('expression',children=[element('state','child')])])
    yield 'invalid-param-parent',element('state','root',children=[element('param')])
    yield 'invalid-param-children',element('state','root',children=[element('behaviour','x',children=[element('param',children=[element('param')])])])
    yield 'invalid-condition-parent',element('state','root',children=[element('condition','x')])
    # Deeply nested valid input exercises the iterative decoder and binding.
    root=element('state','bottom')
    for i in range(1500):
        root=element('state',f'level-{i}',children=[root])
    yield 'deep-tree',root


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    code=PLUGIN/'Source/AtelierSkate/Private/Native'
    cpp,rust=output/'graph-cpp',output/'graph-reference'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(code),str(code/'Graph.cpp'),
                    str(PLUGIN/'Tests/Native/graph_probe.cpp'),'-o',str(cpp)],check=True)
    # Preserve Rust's module-directory layout; all source files are copied verbatim.
    oracle=output/'oracle'; (oracle/'state_graph').mkdir(parents=True,exist_ok=True)
    original=PLUGIN/'ThirdParty/skate-runtime/crates/skate-data/src'
    shutil.copyfile(PLUGIN/'Tests/Reference/graph_probe.rs',oracle/'main.rs')
    shutil.copyfile(original/'state_graph.rs',oracle/'state_graph.rs')
    for filename in ('attributes.rs','binding.rs'):
        shutil.copyfile(original/'state_graph'/filename,oracle/'state_graph'/filename)
    subprocess.run(['rustc','+1.97.1','--edition=2024','-O',str(oracle/'main.rs'),'-o',str(rust)],check=True)
    sources=[(name,args.assets/'private/stock'/relative) for name,relative in converter.GRAPH_FILES]
    names={'','sustain','always','postcond','precond','Always','sustain '}
    for _,source in sources:
        for node in converter.read_graph(source):
            names.add(node['tag'])
            for value in node['attributes']:
                names.update((value['name'],value['text']))
    # Probe the entire byte-hash tail and UTF-8 lengths, plus many arbitrary keys.
    for length in range(180):
        names.update(('a'*length,'あ'*length,'é'*length))
    rng=random.Random(0x47524150)
    names.update(f'collision-{rng.getrandbits(96):024x}' for _ in range(200000))
    names=sorted(name for name in names if '\n' not in name and '\r' not in name)
    corpus=('\n'.join(names)+'\n').encode()
    expected=subprocess.check_output([str(rust),'hash'],input=corpus)
    actual=subprocess.check_output([str(cpp),'hash'],input=corpus)
    if actual!=expected:
        for name,a,b in zip(names,actual.splitlines(),expected.splitlines()):
            if a!=b: raise AssertionError(dict(name=name,actual=a.decode(),expected=b.decode()))
        raise AssertionError('Hash output count differs')
    seen={}; collision=None
    for name,row in zip(names,expected.splitlines()):
        key=row.split()[1]
        if key in seen:
            collision=(seen[key],name); break
        seen[key]=name
    if collision is None: raise AssertionError('The fixed corpus must exercise an actual attribute hash collision')
    for name,root in fixtures(collision):
        source=output/f'{name}.reference-graph'; source.write_bytes(original_graph(root)); sources.append((name,source))
    results=[]
    for name,source in sources:
        elements=converter.read_graph(source)
        native=output/f'{name}.graph'; native.write_bytes(converter.encode_graph(elements))
        result=dict(name=name,elements=len(elements),attributes=sum(len(e['attributes']) for e in elements))
        for mode in ('dump','bind'):
            expected=subprocess.run([str(rust),str(source),mode],capture_output=True)
            actual=subprocess.run([str(cpp),str(native),mode],capture_output=True)
            if (actual.returncode,actual.stdout,actual.stderr)!=(expected.returncode,expected.stdout,expected.stderr):
                for label,run in (('reference',expected),('cpp',actual)):
                    (output/f'{name}-{mode}-{label}.bin').write_bytes(run.stdout)
                raise AssertionError(dict(name=name,mode=mode,reference_exit=expected.returncode,cpp_exit=actual.returncode,
                                          reference_error=expected.stderr.decode(),cpp_error=actual.stderr.decode()))
            if mode=='dump' and expected.returncode!=0: raise AssertionError('Data comparison failed')
            if mode=='bind' and (expected.returncode==3)!=name.startswith('invalid-'):
                raise AssertionError(f'Unexpected fixture binding result: {name}')
            result[mode]=dict(exit=actual.returncode,sha256=hashlib.sha256(actual.stdout).hexdigest())
        results.append(result)
    good=(output/'action.graph').read_bytes()
    for i,data in enumerate((b'',good[:15],good[:-1],good+b'\0',good[:12]+b'\xff'*4+good[16:])):
        bad=output/f'invalid-data-{i}.graph'; bad.write_bytes(data)
        if subprocess.run([str(cpp),str(bad),'dump'],capture_output=True).returncode!=2:
            raise AssertionError('Native decoder accepted invalid data')
    report=dict(passed=True,comparison='exact attributes, lookup values, binding and state search outputs',
                hash_inputs=len(names),collision=collision,graphs=results)
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__': main()
