"""Tree house Tripo props into game meshes (Blender, headless).

    atelier build yorimichi world.treehouse_props

For every prop in tools/treehouse_props.py with a GLB in assets/treehouse/props/<slug>/:
turn it so its front faces -y (TURN), scale its longest side to its size in metres, stand it on z = 0 centred on
its footprint, give it white vertex colours and one material slot, add a collision box for the solid ones, and write
build/yorimichi/treehouse/props/TH_P_<slug>.fbx and .png (its texture) and props.json (gain: the texture's mean brightness
brought to the palette's, measured over the surface, not the atlas). Also renders four views per prop (front, right, back,
left) for checking the turn; `python games/yorimichi/world/regions/treehouse/props.py sheet` puts them in one
picture (Blender has no PIL).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, sys
from pathlib import Path
sys.path.insert(0, str(yori.GAME/'tools'))
try:
    import bpy
except ImportError:
    bpy = None
from treehouse_props import PROPS, OUT as SRC
from treehouse.prop_geometry import fit

OUT = yori.OUT/'treehouse'/'props'
# degrees about z applied after import so the prop's front faces -y (checked on the previews)
TURN = {'backpack': -90, 'bell': -90, 'futon': 180, 'kamado': -90, 'bookshelf': -90, 'crate_desk': -90}
SIZE = {'log_table': 1.35}
# the palette brightness (linear luminance) each prop's texture is brought to
TARGET = dict(kamado=.055, stump_kettle=.05, telescope=.06, backpack=.07, bell=.07, globe=.09, basket=.08, barrel=.05,
              futon=.20, log_table=.055, bookshelf=.055, crate_desk=.055, planter=.065)
SOLID = {'kamado', 'stump_kettle', 'barrel', 'log_table', 'bookshelf', 'crate_desk', 'planter'}




def one(slug):
    return fit(slug, SRC/slug/f'{slug}.glb', f'TH_P_{slug}', SIZE.get(slug, PROPS[slug][3]), TURN.get(slug, 0.),
               TARGET[slug], slug in SOLID, OUT)






def sheet():
    """The four views of every prop in one picture, a prop per row."""
    from PIL import Image, ImageDraw
    slugs = [s for s in PROPS if (OUT/f'view-{s}-0front.png').exists()]; S = 220
    im = Image.new('RGB', (4*S, S*len(slugs)), (235, 235, 235)); d = ImageDraw.Draw(im)
    for row, slug in enumerate(slugs):
        for i, name in enumerate(('front', 'right', 'back', 'left')):
            im.paste(Image.open(OUT/f'view-{slug}-{i}{name}.png').convert('RGB').resize((S, S)), (i*S, row*S))
            d.text((i*S+5, row*S+5), f'{slug} {name}', fill=(0, 0, 0))
    im.save(OUT/'preview.jpg', quality=88)


def main():
    report = {}
    for slug in PROPS:
        if (SRC/slug/f'{slug}.glb').exists():
            key, info = one(slug); report[key] = info; print(key, info, flush=True)
    (OUT/'props.json').write_text(json.dumps(report, indent=1)+'\n')
    print('TREEHOUSE PROPS COMPLETE', len(report), flush=True)


if __name__ == '__main__':
    sheet() if sys.argv[-1] == 'sheet' else main()
