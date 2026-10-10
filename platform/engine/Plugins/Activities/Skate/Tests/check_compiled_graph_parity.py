#!/usr/bin/env python3
"""Compare authored graphs all the way to executable topology and operation IDs.

Uses the unmodified reference host compiler, not a second test implementation of
the mapping. Run under atelier.safety because both probes are compiled here.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path
import struct
import subprocess
from check_gesture_parity import converter, PLUGIN
from check_graph_parity import element,attribute,original_graph
from reference_build import build_probe
from check_controller_parity import build_probes


def replay_authored(program,cpp,rust,output,name):
    conditions=struct.unpack_from('<I',program,12)[0]
    commands=65; stream=bytearray(struct.pack('<I',1)+program+struct.pack('<I',commands))
    rng=random.Random(0x47524150)
    for tick in range(commands):
        stream.extend(struct.pack('<IfI',int(tick==64),1/60,conditions))
        values=([0]*conditions if tick<16 else [1]*conditions if tick<32 else
                [rng.choice((0,1,2,255,256,257,0x80000000,0x80000001)) for _ in range(conditions)])
        stream.extend(struct.pack(f'<{conditions}I',*values))
    inputs=output/f'{name}-controller-input.bin';inputs.write_bytes(stream)
    files=[]
    for label,binary in (('reference',rust),('cpp',cpp)):
        path=output/f'{name}-controller-{label}.bin'
        with path.open('wb') as target,inputs.open('rb') as source:
            subprocess.run([str(binary)],stdin=source,stdout=target,check=True)
        files.append(path)
    expected,actual=(p.read_bytes() for p in files)
    if actual!=expected: raise AssertionError(f'{name}: authored graph controller trace differs')
    return dict(commands=commands,bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),
                host='deterministic test operations; concrete gameplay operations are tested separately')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,required=True)
    args=parser.parse_args(); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    code=PLUGIN/'Source/AtelierSkate/Private/Simulation'; cpp=output/'compiled-graph-cpp'
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(code),
                    str(code/'Graph.cpp'),str(code/'CompiledGraph.cpp'),str(PLUGIN/'Tests/Simulation/compiled_graph_probe.cpp'),'-o',str(cpp)],check=True)
    rust=build_probe(output,'compiled-graph-reference',PLUGIN/'Tests/Reference/compiled_graph_probe.rs',args.target_dir,bevy=True)
    controller_cpp,controller_rust=build_probes(output/'controller')
    sources=[(name,args.assets/'private/stock'/relative) for name,relative in converter.GRAPH_FILES]
    # A disabled unresolved target must still be rejected by the compiler.
    invalid=output/'unresolved.reference-graph'
    invalid.write_bytes(original_graph(element('state','root',children=[element('transition',attributes=[attribute('target','missing')])])))
    sources.append(('unresolved',invalid))
    results=[]
    for name,source in sources:
        simulation=output/f'{name}.graph';simulation.write_bytes(converter.encode_graph(converter.read_graph(source)))
        result=dict(name=name)
        for mode in ('program','operations'):
            expected=subprocess.run([str(rust),str(source),mode],capture_output=True)
            actual=subprocess.run([str(cpp),str(simulation),mode],capture_output=True)
            if (actual.returncode,actual.stdout,actual.stderr)!=(expected.returncode,expected.stdout,expected.stderr):
                (output/f'{name}-{mode}-reference.bin').write_bytes(expected.stdout)
                (output/f'{name}-{mode}-cpp.bin').write_bytes(actual.stdout)
                raise AssertionError(dict(name=name,mode=mode,reference_error=expected.stderr.decode(),cpp_error=actual.stderr.decode()))
            if (actual.returncode==3)!=(name=='unresolved'): raise AssertionError(f'Unexpected compiler result: {name}')
            (output/f'{name}.{mode}').write_bytes(actual.stdout)
            result[mode]=dict(exit=actual.returncode,bytes=len(actual.stdout),sha256=hashlib.sha256(actual.stdout).hexdigest())
            if mode=='program' and actual.returncode==0:
                result['counts']=dict(zip(('states','transitions','expressions','conditions','behaviors','root'),struct.unpack_from('<6I',actual.stdout)))
                result['controller']=replay_authored(actual.stdout,controller_cpp,controller_rust,output,name)
        results.append(result)
    report=dict(passed=True,comparison='exact executable topology, activation programs and operation remapping',graphs=results)
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
