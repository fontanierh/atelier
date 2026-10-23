"""Extract the region-owned decoder's final visual and collision triangles."""
import sys
from pathlib import Path
WORLD=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WORLD))
import hashlib
import importlib.util
import json
from gondola.structures import inputs, affine

def extract(build):
    import numpy as np
    spec=importlib.util.spec_from_file_location('gondola_belmonte_geometry',WORLD/'regions/belmonte/source.py')
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    build = Path(build)
    before = inputs(build)
    surfaces = {'visual':[], 'collision':[]}
    for group in before['selection']['groups']:
        for kind,path in group['geometry'].items():
            triangles = source.triangles(build/path)
            for transform in group['transforms']:
                matrix,offset = affine(transform,before['selection']['origin_cm'])
                surfaces[kind].append(triangles@np.asarray(matrix).T+offset)
        print('GONDOLA STRUCTURES',group['asset'],len(group['transforms']),flush=True)
    if inputs(build) != before:
        raise ValueError('Belmonte structures changed during extraction')
    folder = build/'gondola/world'
    folder.mkdir(parents=True,exist_ok=True)
    output = folder/'structures.npz'
    arrays = {key:np.concatenate(rows) if rows else np.empty((0,3,3)) for key,rows in surfaces.items()}
    np.savez(output,**arrays)
    (folder/'structures.json').write_text(json.dumps({'inputs':before,
        'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'triangles':{key:len(value) for key,value in arrays.items()}},indent=2)+'\n')
    print('GONDOLA STRUCTURES COMPLETE',{key:len(value) for key,value in arrays.items()},flush=True)


if __name__ == '__main__':
    import yori
    extract(yori.OUT)
