#!/usr/bin/env python3
"""Pack original-reader metadata exports as little-endian ATMETA01.

Every array and raw word is retained, including duplicate records and opaque
attribute payloads. The shipping C++ runtime does not parse JSON or ABIN.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


class Writer:
    def __init__(self): self.data=bytearray(b'ATMETA01')
    def word(self,value): self.data.extend(struct.pack('<I',value))
    def wide(self,value): self.data.extend(struct.pack('<Q',value))
    def string(self,value):
        encoded=value.encode('utf-8'); self.word(len(encoded)); self.data.extend(encoded)
    def words(self,values):
        self.word(len(values))
        for value in values: self.word(value)
    def strings(self,values):
        self.word(len(values))
        for value in values: self.string(value)
    def matrix(self,values):
        self.word(len(values))
        for value in values: self.words(value)
    def identity(self,value): self.string(value['name']); self.wide(value['source_offset'])


def pack_metadata(value):
    if value['version']!=1: raise ValueError('Unsupported animation metadata version')
    w=Writer(); w.string(value['source_bank']); w.string(value['source_sha256']); w.wide(value['source_bytes'])
    clips=value['clips']; w.word(len(clips))
    for clip in clips:
        w.identity(clip)
        for key in ('fps_bits','frames_bits','base_speed_bits','flags_word'): w.word(clip[key])
        w.word(len(clip['attributes']))
        for attribute in clip['attributes']:
            w.string(attribute['name']); w.word(attribute['type_id']); w.word(attribute['begin_bits']); w.word(attribute['end_bits'])
            w.wide(attribute['source_offset']); w.words(attribute['payload_words'])
    trees=value.get('phase_blends',[]); w.word(len(trees))
    for tree in trees: w.identity(tree); w.string(tree['parameter']); w.strings(tree['children'])
    trees=value.get('blend_spaces',[]); w.word(len(trees))
    for tree in trees:
        w.identity(tree); w.strings(tree['parameters']); w.strings(tree['children']); w.word(len(tree['simplexes']))
        for simplex in tree['simplexes']:
            w.words(simplex['children']); w.matrix(simplex['vertex_bits']); w.matrix(simplex['normal_bits']); w.words(simplex['scale_bits'])
    trees=value.get('selectors',[]); w.word(len(trees))
    for tree in trees:
        w.identity(tree); w.string(tree['parameter']); w.string(tree['default']); w.strings(tree['children']); w.strings(tree['values'])
    trees=value.get('selection_spaces',[]); w.word(len(trees))
    for tree in trees:
        w.identity(tree); w.word(len(tree['parameters']))
        for parameter in tree['parameters']:
            w.string(parameter['name'])
            for key in ('mode','weight_bits','minimum_bits','maximum_bits'): w.word(parameter[key])
        w.word(len(tree['candidates']))
        for candidate in tree['candidates']: w.string(candidate['child']); w.words(candidate['value_bits'])
    trees=value['unsupported_trees']; w.word(len(trees))
    for tree in trees: w.identity(tree); w.word(tree['type_id'])
    return bytes(w.data)


def convert_animation_metadata(source,destination):
    source=Path(source); destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    banks=[]
    for path in sorted(source.glob('bank-*.json')):
        value=json.loads(path.read_text()); data=pack_metadata(value)
        expected=path.with_suffix('.raw')
        if expected.exists() and data!=expected.read_bytes(): raise AssertionError(f'Original metadata export differs: {path.name}')
        simulation=destination/(path.stem+'.skate'); simulation.write_bytes(data)
        banks.append(dict(file=simulation.name,source_bank=value['source_bank'],source_sha256=value['source_sha256'],source_bytes=value['source_bytes'],
                          records={key:len(value.get(key,[])) for key in ('clips','phase_blends','blend_spaces','selectors','selection_spaces','unsupported_trees')},
                          attributes=sum(len(c['attributes']) for c in value['clips']),simulation_bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    if not banks: raise ValueError('No original animation metadata exports')
    report=dict(format='ATMETA01',banks=banks)
    (destination/'metadata-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--decoded',required=True,type=Path); parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(); print(json.dumps(convert_animation_metadata(args.decoded,args.output),indent=2))


if __name__=='__main__': main()
