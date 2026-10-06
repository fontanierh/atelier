"""Make a painted sheet the in-game map: python games/yorimichi/world/map/promote_map.py build/yorimichi/map/painted_1.png

Writes map.png (the texture the game loads), map.jpg (served to phones) and painted.txt (which sheet, so build_map.py
keeps it when the rough sheet is regenerated). The painted sheet covers exactly the bounds in map.json, so nothing
else changes; after any world change, repaint (repaint_island.py, docs/WORLD_MAP.md "Local repaints") and check its
registration-check.jpg before promoting again."""
import argparse, os, shutil, time, json
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402
from PIL import Image
ap = argparse.ArgumentParser(); ap.add_argument('sheet'); ap.add_argument('--out', default=str(yori.OUT / 'map')); a = ap.parse_args()
im = Image.open(a.sheet).convert('RGB')
im.save(os.path.join(a.out, 'map.png'), optimize=True)
im.save(os.path.join(a.out, 'map.jpg'), quality=88, progressive=True)
open(os.path.join(a.out, 'painted.txt'), 'w').write(f'{os.path.abspath(a.sheet)} {im.width}x{im.height} {time.strftime("%Y-%m-%d %H:%M")}\n')
# the painted sheet is not reproducible from data (gpt-image-2), so it also lives in the repo: build_map.py uses it while the world bounds match
docs = str(yori.MAP / 'painted'); os.makedirs(docs, exist_ok=True)
im.save(os.path.join(docs, 'world_map.png'), optimize=True)
with open(os.path.join(a.out,'map.json')) as f: meta=json.load(f)
bounds=meta['bounds']
with open(os.path.join(docs,'world_map_registration.json'),'w') as f:json.dump({key:meta.get(key,[]) for key in ['bounds','projection_x','projection_y']},f,indent=2)
with open(os.path.join(docs,'world_map_bounds.json'),'w') as f: json.dump(bounds,f)
prov = os.path.join(os.path.dirname(os.path.abspath(a.sheet)), 'paint_provenance.json')
if os.path.exists(prov): shutil.copy2(prov, os.path.join(docs, 'world_map_provenance.json'))
check = os.path.join(os.path.dirname(os.path.abspath(a.sheet)), 'paint_check_' + os.path.basename(a.sheet).split('_')[-1].split('.')[0] + '.jpg')
if os.path.exists(check): shutil.copy2(check, os.path.join(docs, 'world_map_check.jpg'))
print('promoted', a.sheet, im.size, '->', os.path.join(a.out, 'map.png'), 'and docs/map/world_map.png')
