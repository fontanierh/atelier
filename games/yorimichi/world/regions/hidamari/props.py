"""Hidamari's Tripo street props into game meshes (Blender, headless).

    atelier build yorimichi world.hidamari_props

For every prop in tools/hidamari_props.py with a GLB in assets/hidamari/props/<slug>/, the tree house's steps
(world/regions/treehouse/props.py fit): turned so its front faces -y (TURN), its longest side scaled to its size in
metres, stood on z = 0 centred on its footprint, white vertex colours, one material slot and a collision box for the
solid ones. Writes build/yorimichi/hidamari/props/HD_P_<slug>.fbx and .png (its texture), four check views each, and
props.json (gain: the texture's mean brightness brought to TARGET). layout.py places them (HD_P_<slug> in city.json).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, sys
sys.path.insert(0, str(yori.GAME/'tools'))
from hidamari_props import PROPS, OUT as SRC
from treehouse import props as kit

OUT = yori.OUT/'hidamari'/'props'
# degrees about z applied after import so the prop's front faces -y (checked on the views)
TURN = {s: -90 for s in ('kei_truck', 'vending_machine', 'bus_stop', 'garbage_station', 'jizo', 'komainu', 'potted_plants',
                         'produce_stand', 'sake_barrels', 'water_basin')}
# the palette brightness (linear luminance) each prop's texture is brought to; .07 unless given
TARGET = dict(vending_machine=.16, postbox=.06, stone_lantern=.10, komainu=.10, jizo=.08, water_basin=.08,
              phone_booth=.10, kei_truck=.18, scooter=.12)
SOLID = {'vending_machine', 'kei_truck', 'postbox', 'phone_booth', 'stone_lantern', 'komainu', 'jizo', 'water_basin',
         'sake_barrels', 'produce_stand', 'garbage_station', 'bus_stop'}


def main():
    report = {}
    for slug, (_, size) in PROPS.items():
        glb = SRC/slug/f'{slug}.glb'
        if not glb.exists(): continue
        key, info = kit.fit(slug, glb, f'HD_P_{slug}', size, TURN.get(slug, 0.), TARGET.get(slug, .07), slug in SOLID, OUT)
        report[key] = info; print(key, info, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'props.json').write_text(json.dumps(report, indent=1)+'\n')
    print('HIDAMARI PROPS COMPLETE', len(report), flush=True)


if __name__ == '__main__':
    main()
