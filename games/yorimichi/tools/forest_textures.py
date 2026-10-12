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
        rgba=np.dstack([rgb,np.rint(alpha*255).astype('uint8')])
        target=OUT/f'T_{slot}.png';Image.fromarray(rgba).save(target)
        coverage=float((alpha>.5).mean())
        assert .08<coverage<.7,(species,coverage)
        report[slot]={'file':target.name,'source_sha256':provenance['source_sha256'],
                      'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'coverage':coverage}
    (OUT/'textures.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FOREST TEXTURES COMPLETE',report,flush=True)


if __name__ == '__main__':main()
