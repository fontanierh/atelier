"""Write the Belmonte train line's fixed-scenery units (assets/adopted/belmontetrack/units.json; audit A1).

    uv run python games/yorimichi_v2/tools/migrate/train_units.py [--check]

The track runtime (BelmonteTrack, data belmonte_track/track.json) spawns every `SM_TK_*` and `SM_ST_*` package of
/Game/BelmonteTrack. Units: the Belmonte station (head house, sheds, coaches, forecourt) and its overbridge, the
track sections (the 80 route chunks in four runs of twenty in route order, the spiral tunnel, the two other tunnels,
the viaducts, the banks, the loop), the small repeated parts (sleeper, portal, buffer stop, stop board, turnout, tunnel
lamp: instanced, one unit) and the shared `materials`, which also carries the generator of every track package.
The train vehicles (/Game/BelmonteTrain) are a different folder and are not split here.
"""
from __future__ import annotations

import re

import transport_units as T

ROOT = '/Game/BelmonteTrack'
W = 'world/train/'
STATION = [W + 'station.py', W + 'station_site.py', W + 'station_render.py', 'docs/BELMONTE_STATION.md']
TRACK = [W + 'track.py', W + 'track_build.py', W + 'plan_track.py', W + 'construct_track.py', W + 'export_track_piece.py',
         W + 'track_projection.py', W + 'route.py']
OWN = {'station-belmonte': STATION, 'overbridge': [W + 'overbridge.py', *STATION[:2]]}
for run in ('0-19', '20-39', '40-59', '60-79'):
    OWN['chunks-' + run] = TRACK
for name in ('tunnel-spiral', 'tunnel-t1', 'tunnel-t2'):
    OWN[name] = TRACK + [W + 'earthworks.py', W + 'corridor.py']
OWN['viaducts'] = TRACK + [W + 'earthworks.py']
OWN['banks'] = TRACK + [W + 'earthworks.py']
OWN['loop'] = TRACK
OWN['track-small'] = TRACK + [W + 'fittings.py']
ABOUT = {
    'station-belmonte': 'the Belmonte station: head house, sheds, coaches and forecourt (SM_ST_*; platforms are part of them)',
    'overbridge': 'the Belmonte station overbridge',
    'tunnel-spiral': 'the spiral tunnel linings (26 sections)',
    'tunnel-t1': 'tunnel T1 linings', 'tunnel-t2': 'tunnel T2 linings',
    'viaducts': 'the 7 viaduct sections', 'banks': 'the 5 bank sections', 'loop': 'the terminus loop',
    'track-small': 'the repeated small track parts: sleeper, portal, buffer stop, stop board, turnout, tunnel lamp',
    'materials': 'track and station materials, and the generator that made every track package',
}
ABOUT.update({f'chunks-{r}': f'route chunks {r} (rail bed and rails, in route order)'
              for r in ('0-19', '20-39', '40-59', '60-79')})


def unit_of(name: str, package: str) -> str:
    if package.startswith(ROOT + '/Materials/'):
        return 'materials'
    if name.startswith('SM_ST_Overbridge'):
        return 'overbridge'
    if name.startswith('SM_ST_'):
        return 'station-belmonte'
    chunk = re.match(r'SM_TK_Chunk_(\d+)$', name)
    if chunk:
        n = int(chunk.group(1)) // 20 * 20
        return f'chunks-{n}-{n + 19}'
    for prefix, unit in (('SM_TK_Tunnel_Spiral', 'tunnel-spiral'), ('SM_TK_Tunnel_T1', 'tunnel-t1'),
                         ('SM_TK_Tunnel_T2', 'tunnel-t2'), ('SM_TK_Viaduct', 'viaducts'), ('SM_TK_Bank', 'banks'),
                         ('SM_TK_Loop', 'loop')):
        if name.startswith(prefix):
            return unit
    if name in ('SM_TK_Sleeper', 'SM_TK_Portal', 'SM_TK_BufferStop', 'SM_TK_StopBoard', 'SM_TK_Turnout',
                'SM_TK_TunnelLamp'):
        return 'track-small'
    raise ValueError(f'{name} fits no track unit')


def make(game):
    generator = T.donor_files('world/train', 'train_atomic_build.py', 'assets/belmonte/source.json',
                              'world/source_registry.py', 'assets/source-library.json')
    return T.build(game, 'belmontetrack', ROOT, unit_of, ABOUT, {k: T.donor_files(*v) for k, v in OWN.items()},
                   generator, 'Belmonte track')


if __name__ == '__main__':
    raise SystemExit(T.main('belmontetrack', make))
