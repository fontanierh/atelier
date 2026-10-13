"""Finish Sunburst twig atlases for the shared masked foliage material."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]
SOURCE = GAME / 'assets/environment/textures'
OUT = ROOT / 'build/yorimichi/forest/textures'
NAMES = {'olive': 'LeafOlive', 'oak': 'LeafOak', 'cypress': 'LeafCypress', 'pine': 'LeafStonePine'}
GAIN = {'olive': 1.35, 'oak': 1.05, 'cypress': 1.2, 'pine': 1.12}


def extend_colour(rgb, alpha):
    """Keep black cut-out backgrounds out of filtered twig colours."""
    result=rgb.astype(float).copy()
    filled=alpha>.5
    assert filled.any(),'A twig atlas cell contains no leaves'
    mean=np.average(result[filled],axis=0,weights=alpha[filled])
    for _ in range(12):
        total=np.zeros_like(result);weight=np.zeros_like(alpha)
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            valid=np.roll(filled,(dy,dx),(0,1))
            if dy>0:valid[:dy,:]=False
            if dy<0:valid[dy:,:]=False
            if dx>0:valid[:,:dx]=False
            if dx<0:valid[:,dx:]=False
            total+=np.roll(result,(dy,dx),(0,1))*valid[:,:,None];weight+=valid
        extend=~filled&(weight>0)
        result[extend]=total[extend]/weight[extend,None];filled|=extend
    result[~filled]=mean
    return np.clip(np.rint(result),0,255).astype('uint8')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for species, slot in NAMES.items():
        path = SOURCE / f'leaf-{species}.jpg'
        provenance = json.loads(path.with_suffix('.provenance.json').read_text())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == provenance['source_sha256'], path
        rgb = np.asarray(Image.open(path).convert('RGB')).copy()
        # The source is an isolated twig on black. Its luminance distinguishes
        # material from empty space; trim the cell dividers and edge padding.
        value = rgb.max(2).astype(float)
        alpha = np.clip((value-8)/18, 0., 1.)
        h,w = alpha.shape
        for edge in (0,h//2,h-1):alpha[max(0,edge-2):edge+3,:]=0
        for edge in (0,w//2,w-1):alpha[:,max(0,edge-2):edge+3]=0
        # Finish each cell independently so padding never mixes species views.
        for y0,y1 in ((0,h//2),(h//2,h)):
            for x0,x1 in ((0,w//2),(w//2,w)):
                rgb[y0:y1,x0:x1]=extend_colour(rgb[y0:y1,x0:x1],alpha[y0:y1,x0:x1])
        encoded=rgb.astype(float)/255
        linear=np.where(encoded<=.04045,encoded/12.92,((encoded+.055)/1.055)**2.4)
        linear=np.clip(linear*GAIN[species],0,1)
        encoded=np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055)
        rgb=np.rint(encoded*255).astype('uint8')
        rgba=np.dstack([rgb,np.rint(alpha*255).astype('uint8')])
        target=OUT/f'T_{slot}.png';Image.fromarray(rgba).save(target)
        coverage=float((alpha>.5).mean())
        assert .08<coverage<.7,(species,coverage)
        report[slot]={'file':target.name,'source_sha256':provenance['source_sha256'],
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'coverage':coverage,
                      'linear_gain':GAIN[species],'edge_colour':'per-cell alpha-preserving extension'}
    (OUT/'textures.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FOREST TEXTURES COMPLETE',report,flush=True)


if __name__ == '__main__':main()
