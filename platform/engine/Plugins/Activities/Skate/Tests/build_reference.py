#!/usr/bin/env python3
"""Freeze and build the reference revision, without modifying the running game.

Run through atelier.safety. Output and Cargo cache belong under build/. The source
snapshot is extracted from Git, so later working-tree changes cannot affect it.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
from session_parity import PLUGIN, REFERENCE_REVISION, digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,required=True)
    parser.add_argument('--toolchain',default='1.97.1')
    args=parser.parse_args()
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    tree=subprocess.check_output(['git','rev-parse',f'{revision}:{relative}'],cwd=root,text=True).strip()
    output=args.output.resolve()
    if output.exists(): raise ValueError('Use a new output directory to preserve the frozen reference')
    output.mkdir(parents=True)
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root)
    source=output/'source'; source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source,filter='data')
    source_hashes={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*')) if p.is_file()}
    target=args.target_dir.resolve()
    command=['cargo','+'+args.toolchain,'build','--release','--locked','--jobs','2','--manifest-path',
             str(source/'atelier-host/Cargo.toml'),'--target-dir',str(target)]
    subprocess.run(command,check=True)
    for name,expected in source_hashes.items():
        if digest(source/name)!=expected: raise ValueError(f'Reference source changed while building: {name}')
    binary_name='atelier-skate-runtime'+('.exe' if os.name=='nt' else '')
    binary=output/binary_name; shutil.copy2(target/'release'/binary_name,binary)
    report=dict(format=1,reference_revision=revision,source_tree=tree,source_archive_sha256=hashlib.sha256(archive).hexdigest(),
                binary=binary_name,binary_sha256=digest(binary),architecture=platform.machine(),
                compiler=subprocess.check_output(['rustc','+'+args.toolchain,'-vV'],text=True).strip(),
                profile='release',locked=True,jobs=2,source_files=source_hashes,
                rustflags=os.environ.get('RUSTFLAGS',''),encoded_rustflags=os.environ.get('CARGO_ENCODED_RUSTFLAGS',''))
    (output/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_files'},indent=2),flush=True)


if __name__=='__main__': main()
