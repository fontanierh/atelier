#!/usr/bin/env python3
"""One-time migration assembler for the complete project-native skating bundle.

Normal builds consume the assembled tracked files directly. Original formats,
the Rust export tools and this assembler are unnecessary at runtime/build time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import convert_native_data as convert


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def climbing_bytes(value):
    result=bytearray(b'SKCLIP1\0')
    def word(v):result.extend(struct.pack('<I',v & 0xffffffff))
    def text(v):
        raw=v.encode('utf-8');word(len(raw));result.extend(raw)
    word(value['version']);word(len(value['clips']))
    for clip in value['clips']:
        text(clip['name']);result.extend(struct.pack('<f',clip['fps']))
        word(len(clip['names']))
        for name in clip['names']:text(name)
        word(len(clip['parents']))
        for parent in clip['parents']:word(parent)
        word(len(clip['frames']))
        for frame in clip['frames']:
            word(len(frame))
            for bone in frame:
                if len(bone)!=10:raise ValueError('Climbing samples require ten SQT lanes')
                result.extend(struct.pack('<10f',*bone))
    return bytes(result)


def assemble(assets,samples,metadata,camera,output):
    assets,samples,metadata,camera,output=map(Path,(assets,samples,metadata,camera,output))
    if output.exists():raise ValueError('Use a fresh output directory to preserve prior packages')
    manifest=json.loads((samples/'samples-manifest.json').read_text())
    if digest(samples/'rig.skate')!=manifest['rig_sha256']:raise ValueError('Rig export hash differs')
    for clip in manifest['clips']:
        if digest(samples/'clips'/(clip['name']+'.skate'))!=clip['native_sha256']:
            raise ValueError('Animation export hash differs: '+clip['name'])
    meta=json.loads((metadata/'metadata-manifest.json').read_text())
    for bank in meta['banks']:
        if digest(metadata/bank['file'])!=bank['sha256']:raise ValueError('Metadata export hash differs')
    physics=assets/'private/stock/physics-skeletons.json'
    if json.loads(physics.read_text())['source_sha256']!=meta['banks'][0]['source_sha256']:
        raise ValueError('Physics and animation source identities differ')
    if camera.read_bytes()[:8]!=b'ATCAM001':raise ValueError('Camera export is not native ATCAM001')
    output.mkdir(parents=True)
    (output/'settings.skate').write_bytes(convert.encode_settings(assets/'private/stock/skater-collections.json'))
    (output/'physics-skeletons.skate').write_bytes(convert.encode_physics_skeletons(physics))
    sets=convert.gesture_sets(assets/'private/stock/data/joystick')
    (output/'gestures.skate').write_bytes(convert.encode_gestures(sets))
    for name,path in convert.GRAPH_FILES:
        (output/(name+'.graph')).write_bytes(convert.encode_graph(convert.read_graph(assets/'private/stock'/path)))
    animation=output/'animation';animation.mkdir()
    shutil.copy2(samples/'rig.skate',animation/'rig.skate')
    for clip in manifest['clips']:
        relative=Path('clips')/(clip['name']+'.skate');target=animation/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(samples/relative,target)
    (output/'metadata').mkdir()
    for bank in meta['banks']:shutil.copy2(metadata/bank['file'],output/'metadata'/bank['file'])
    shutil.copy2(camera,output/'camera.skate')
    custom=assets/'private/custom'
    if (custom/'crouch-treflip.json').is_file():
        (output/'custom').mkdir(exist_ok=True)
        shutil.copy2(custom/'crouch-treflip.json',output/'custom/crouch-treflip.json')
    if (custom/'climbing.json').is_file():
        (output/'custom').mkdir(exist_ok=True)
        (output/'custom/climbing.skate').write_bytes(climbing_bytes(json.loads((custom/'climbing.json').read_text())))
    files={p.relative_to(output).as_posix():dict(bytes=p.stat().st_size,sha256=digest(p))
           for p in sorted(output.rglob('*'))if p.is_file()}
    report=dict(version=1,formats=['ATATTR01','ATGEST01','ATGRPH01','ATPHYS01','ATSKEL01','ATCLIP01','ATMETA01','ATCAM001'],
                source_identity=meta['banks'][0]['source_sha256'],files=files,
                clips=len(manifest['clips']),animation_frames=sum(c['frames']for c in manifest['clips']),
                patterns=sum(len(s['patterns'])for s in sets),
                metadata_banks=len(meta['banks']),bytes=sum(row['bytes']for row in files.values()))
    (output/'package-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('assets','samples','metadata','camera','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();report=assemble(a.assets,a.samples,a.metadata,a.camera,a.output)
    print(json.dumps({k:v for k,v in report.items()if k!='files'},indent=2))


if __name__=='__main__':main()
