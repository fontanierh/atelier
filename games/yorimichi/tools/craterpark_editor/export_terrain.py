"""Crater terrain for the park editor.

Writes data/terrain.json + float32 grids:
  inner_natural.bin, inner_dug.bin  2 m grid over the crater (from v4/ground_shaped.npz: natural, natural + v4 funnel dig)
  outer.bin                         5 m grid over the surroundings (v4-support/collision_source_grid.npz)
plus the crater crest polygon. Heights are native y (world altitude = y + 680).
"""
import json
from pathlib import Path
import numpy as np

H = Path(__file__).resolve().parent
ROOT = H.parent
OUT = H / 'data'
OUT.mkdir(exist_ok=True)

s = np.load(ROOT / 'v4/ground_shaped.npz')
nat, dug = s['natural'].astype('<f4'), s['dug'].astype('<f4')
nz, nx = nat.shape
x0, z0, G = float(s['x0']), float(s['z0']), float(s['G'])
(OUT / 'inner_natural.bin').write_bytes(nat.tobytes())
(OUT / 'inner_dug.bin').write_bytes(dug.tobytes())

c = np.load(ROOT / 'v4-support/collision_source_grid.npz')
ox, oz, oy = c['native_x'], c['native_z'], c['native_y'].astype('<f4')
(OUT / 'outer.bin').write_bytes(oy.tobytes())

site = json.loads((ROOT / 'v4-support/site_extended.json').read_text())
rim = np.array(site['rim']['geometry']['coordinates'][0])[::2].round(1).tolist()

meta = {
    'lift': 680.0,
    'inner': {'x0': x0, 'z0': z0, 'G': G, 'nx': nx, 'nz': nz, 'cell_centred': True,
              'layers': {'natural': 'inner_natural.bin', 'dug': 'inner_dug.bin'}},
    'outer': {'x0': float(ox[0]), 'z0': float(oz[0]), 'G': float(ox[1] - ox[0]), 'nx': len(ox), 'nz': len(oz),
              'cell_centred': False, 'file': 'outer.bin'},
    'rim': rim,
    'note': 'native y; world altitude = y + 680. inner grid sample (i, j) sits at x0 + (i + .5) G, z0 + (j + .5) G; '
            'outer grid sample (i, j) at x0 + i G, z0 + j G. "dug" = natural + the v4 funnel dig toward the old bowl.',
}
(OUT / 'terrain.json').write_text(json.dumps(meta))
print('inner', nx, nz, G, 'outer', len(ox), len(oz), 'rim pts', len(rim))
