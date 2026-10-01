#!/usr/bin/env python3
"""Complete original host state capability/transition table, all enum pairs.

Compile and execute through the shared render/memory guard. Core enum identity
and the host registry remain distinct; actual Enter/Exit effects are separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from check_animation_trees_parity import source_at_reference
from reference_build import build_probe
from session_parity import PLUGIN

SOURCE='crates/skate-host/src/physics/player_state/registry.rs'
STATES=(100,101,102,103,104,105,200,201,202,300,400,401,402,403,404,405,500,501,502,503,600,601,602,700,701,702)

def inspect(raw):
    words=struct.unpack('<'+'I'*(len(raw)//4),raw);at=0;capabilities=[];transitions=[]
    for state in STATES:
        row=words[at:at+4];at+=4;assert row[0]==state and all(v<2 for v in row[1:]);capabilities.append(row)
    for current in STATES:
        for requested in STATES:
            row=words[at:at+3];at+=3;assert row[:2]==(current,requested) and row[2]<2;transitions.append(row)
    assert at==len(words)
    assert {r[0] for r in capabilities if not r[1]}=={104,105,202}
    assert next(r for r in capabilities if r[0]==700)==(700,1,0,1)
    assert all(not enabled for current,requested,enabled in transitions if current==700 and requested!=100)
    assert any(current==700 and requested==100 and enabled for current,requested,enabled in transitions)
    return dict(capabilities=len(capabilities),pairs=len(transitions),allowed=sum(row[2] for row in transitions),rejected=sum(not row[2] for row in transitions))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--target-dir',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('result.json','first-divergence.json'):(out/name).unlink(missing_ok=True)
    original=source_at_reference(SOURCE);template=PLUGIN/'Tests/Reference/player_state_registry_probe.rs';generated=out/'player-state-registry-reference.rs';generated.write_text(template.read_text().replace('// ORIGINAL_HOST',original));assert original in generated.read_text()
    reference=build_probe(out,'player-state-registry-reference',generated,a.target_dir)
    live=PLUGIN/'Source/AtelierSkate/Private/Native';snapshot=out/'native-source'
    if snapshot.exists():shutil.rmtree(snapshot)
    snapshot.mkdir()
    for path in (live/'NativeMath.h',live/'PhysicalPhase.h',live/'PhysicalPhase.cpp',live/'PlayerStateRegistry.h',live/'PlayerStateRegistry.cpp',PLUGIN/'Tests/Native/player_state_registry_probe.cpp'):shutil.copy2(path,snapshot/path.name)
    native=out/'player-state-registry-native';subprocess.run(['clang++','-std=c++17','-O2','-fno-exceptions','-ffp-contract=off','-fno-fast-math','-Wall','-Wextra','-Werror','-I',str(snapshot),str(snapshot/'PhysicalPhase.cpp'),str(snapshot/'PlayerStateRegistry.cpp'),str(snapshot/'player_state_registry_probe.cpp'),'-o',str(native)],check=True)
    expected=subprocess.check_output([str(reference)]);actual=subprocess.check_output([str(native)]);(out/'reference.bin').write_bytes(expected);(out/'native.bin').write_bytes(actual)
    if expected!=actual:
        index=next((i for i,(x,y) in enumerate(zip(expected,actual)) if x!=y),min(len(expected),len(actual)));(out/'first-divergence.json').write_text(json.dumps(dict(byte=index,reference_bytes=len(expected),native_bytes=len(actual)),indent=2)+'\n');raise AssertionError('Host state support table differs')
    report=dict(passed=True,exact_words=len(expected)//4,sha256=hashlib.sha256(expected).hexdigest(),coverage=inspect(expected),original=dict(path=SOURCE,sha256=hashlib.sha256(original.encode()).hexdigest()),native_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir()},boundary='Whole unchanged original host registry; all 26 capabilities and 676 transition pairs. Actual lifecycle effects and global player-frame publication remain separate concrete-owner integration checks.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
