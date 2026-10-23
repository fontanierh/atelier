"""The Belmonte railway track for Unreal: the Train Builder's track.json (world/train/track_build.py) turned into what
the game places (Content/Data/belmonte_track/track.json, read by ABelmonteTrack) and what the importer
(unreal/Scripts/import_belmonte_track.py) imports.

    uv run python games/yorimichi/tools/belmonte_track_data.py      # -> build/yorimichi/belmonte-track/runtime/track.json

Units are Unreal's: centimetres, x east, y south (Blender's y flipped), yaw clockwise (Blender's negated). Pieces are
placed at their origin without rotation (their meshes are relative to it); instances carry [x, y, z, yaw, scale] where
the scale is along the instance's local y (a sleeper's length, a turnout's mirror). Editor-only meshes (the chainage
markers) are left out.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRACK = ROOT / 'build' / 'yorimichi' / 'belmonte-track'
MESH_ROOT = '/Game/BelmonteTrack'

# LOD screen sizes (Unreal's: about radius / distance) and draw distances by kind of piece. Track chunks are ~100 m long
# (radius ~50 m): LOD1 from ~170 m, LOD2 from ~1 km, culled at 2.5 km like the trains.
SCREEN_SIZES = {1: [1.0], 2: [1.0, .3], 3: [1.0, .3, .05]}
CULL_CM = {'piece': 250000., 'portal': 150000., 'small': 20000., 'sleeper': 12000., 'lamp': 15000.}
# The tunnels' exposure compensation (EV) and the sky's indirect light left inside (see build()).
TUNNEL_BIAS = -3.5
TUNNEL_INDIRECT = .25
# Collision for instanced pieces that people can bump into (the pieces' own collision is in track.json).
SOLID = {'SM_TK_BufferStop', 'SM_TK_Portal', 'SM_TK_StopBoard'}


def to_ue(x, y, z):
    return [round(x * 100, 2), round(-y * 100, 2), round(z * 100, 2)]


def mesh_path(name):
    return f'{MESH_ROOT}/{name}.{name}'


def lod_index(collision):
    """'LOD2' -> 2; None (no collision) -> -1."""
    return int(collision[3:]) if collision else -1


def instance(row):
    x, y, z, yaw, scale = (list(row) + [1.0])[:5]
    return [*to_ue(x, y, z), round(-yaw, 3), scale]


def box(volume):
    """An oriented box: centre (cm), yaw (Unreal), half extents (cm) along its own x (the track), y and z."""
    return {'centre': to_ue(*volume['centre']), 'yaw': round(-volume['yaw'], 3),
            'half': [round(h * 100, 1) for h in volume['half_extent']]}


def build(track):
    meshes = {name: m for name, m in track['meshes'].items() if name not in set(track.get('editor_only', []))}
    pieces = []

    def piece(p, kind):
        pieces.append({'name': p['name'], 'mesh': mesh_path(p['name']), 'at': to_ue(*p['origin']), 'kind': kind,
                       'layer': p.get('layer') or '', 'collision': lod_index(p.get('collision'))})
    for c in track['chunks']:
        piece(c, 'loop' if c['name'] == 'SM_TK_Loop' else 'chunk')
    for t in track['tunnels']:
        for lining in t['lining']:
            piece(dict(lining, layer=t['name']), 'lining')
    for v in track['viaducts']:
        for p in v['pieces']:
            piece(p, 'viaduct')
    for b in track.get('banks', []):
        piece(b, 'bank')
    if track.get('overbridge'):
        piece(track['overbridge'], 'overbridge')
    for p in (track.get('station') or {}).get('pieces', []):
        piece(p, 'station')
    groups = []
    for name, rows in track['instances'].items():
        if name not in meshes:
            continue
        kind = 'sleeper' if name == 'SM_TK_Sleeper' else 'lamp' if name == 'SM_TK_TunnelLamp' else \
            'portal' if name == 'SM_TK_Portal' else 'small'
        # Sleepers: one hierarchical group per main chunk; tunnel lamps: one per tunnel; the rest one group each.
        parts = sorted(rows.items(), key=lambda kv: (len(kv[0]), kv[0])) if isinstance(rows, dict) else [('', rows)]
        for key, items in parts:
            groups.append({'mesh': mesh_path(name), 'kind': kind, 'key': str(key), 'hierarchical': kind == 'sleeper',
                           'collision': name in SOLID, 'shadow': kind not in ('sleeper', 'lamp'),
                           'cull_cm': CULL_CM[kind], 'instances': [instance(r) for r in items]})
    lighting = track.get('tunnel_lighting') or {}
    spec = lighting.get('light', {})
    tunnels = []
    for t in track['tunnels']:
        tunnels.append({'name': t['name'], 'start': t['start'], 'end': t['end'],
                        'lights': [to_ue(*p) for p in (lighting.get('lights') or {}).get(t['name'], [])],
                        'volumes': [box(lining['volume']) for lining in t['lining'] if lining.get('volume')],
                        'load_boxes': [box(b) for b in t.get('load_boxes', [])]})
    exposure = lighting.get('exposure', {})
    return {
        'version': 1,
        'meshes': {name: {'asset': mesh_path(name), 'lods': m['lods'], 'materials': m.get('materials', []),
                          'screen_sizes': SCREEN_SIZES.get(len(m['lods']), SCREEN_SIZES[3])[:len(m['lods'])]}
                   for name, m in meshes.items()},
        'pieces': pieces,
        'instances': groups,
        'cull_cm': CULL_CM,
        'tunnels': tunnels,
        'light': {'kelvin': spec.get('colour_k', 2700), 'candela': spec.get('intensity_cd', 80.0),
                  'radius_cm': spec.get('attenuation_m', 14.0) * 100, 'source_radius_cm': spec.get('source_radius_m', .08) * 100,
                  'shadows': bool(spec.get('cast_shadows', False))},
        # Inside, the exposure drops by `bias` EV (it applies with auto exposure off, as the manual exposure
        # compensation) and the lamps are brightened by as much: the sky's unshadowed fill in the lining falls to near
        # black while the lamps' pools keep their brightness and the portals' daylight stays bright.
        'exposure': {'min_ev': exposure.get('min_ev', -1.0), 'max_ev': exposure.get('max_ev', 1.0),
                     'bias': exposure.get('bias', TUNNEL_BIAS), 'indirect': TUNNEL_INDIRECT},
        # Lights come on within this distance of the camera while it is inside a tunnel's volumes or load boxes.
        'light_range_cm': 25000.,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--track', type=Path, default=TRACK)
    parser.add_argument('--source', type=Path, help='explicit completed track source/assembly document')
    args = parser.parse_args(argv)
    data = build(json.loads((args.source or args.track / 'track.json').read_text()))
    missing = [lod for m in data['meshes'].values() for lod in m['lods'] if not (args.track / lod).exists()]
    if missing:
        sys.exit(f'missing track meshes: {missing[:5]}')
    out = args.track / 'runtime' / 'track.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(',', ':')))
    lights = sum(len(t['lights']) for t in data['tunnels'])
    print(f"BELMONTE TRACK DATA meshes={len(data['meshes'])} pieces={len(data['pieces'])} "
          f"groups={len(data['instances'])} instances={sum(len(g['instances']) for g in data['instances'])} "
          f"tunnels={len(data['tunnels'])} lights={lights} volumes={sum(len(t['volumes']) for t in data['tunnels'])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
