"""Write the gondola's editing units (assets/adopted/gondola/units.json) for its ownership split (audit A1).

    uv run python games/yorimichi_v2/tools/migrate/gondola_units.py [--check]

The runtime (GondolaService, data gondola/runtime.json) spawns each fixed part from a `static[]` row. One unit per
fixed object: each fitted support tower (`GD_L<line>_<n>_Tower`, one mesh each), each station's foundation and ground
access (`station-<id>`), each rope line's mesh (`rope-l<line>`), and the three station shells the six stations share
(`shell-valley`, `shell-rim`, `shell-crater`), the cabin and the parametric tower kit. `materials` and `textures` stay
shared; `materials` also carries the generator of every gondola package. Each unit's own sources are the generator
modules that make only it (tower.py for towers, stations.py for shells, site.py for the fitted world parts).
"""
from __future__ import annotations

import re

import transport_units as T

ROOT = '/Game/Gondola/'
GA = 'assets/vehicles/gondola/'
OWN = {
    'cabin': [GA + 'cabin.py', GA + 'params.py'],
    'kit-towers': [GA + 'tower.py', GA + 'params.py'],
    'shell-valley': [GA + 'stations.py', GA + 'params.py'],
    'shell-rim': [GA + 'stations.py', GA + 'params.py'],
    'shell-crater': [GA + 'stations.py', GA + 'params.py'],
    'textures': [GA + 'textures.py'],
}
SITE = ['world/regions/gondola/site.py', 'world/regions/gondola/layout.py', 'world/gondola/structures.py']
ABOUT = {
    'cabin': 'the gondola cabin kit: body, doors, grip, hanger and collision',
    'kit-towers': 'the parametric support tower kit, 10 m to 28 m, with collisions (templates, not placed)',
    'shell-valley': 'the valley station shell (building, fittings, machinery, platform, collision), used by Hidamari and Belmonte',
    'shell-rim': 'the rim station shell, used by the Southeast, Northwest and Crater Park rim stations',
    'shell-crater': 'the crater-floor station shell, used by the floor station',
    'materials': 'gondola materials, and the generator that made every gondola package',
    'textures': 'gondola shared textures',
}
SHELL = {'Valley': 'shell-valley', 'Rim': 'shell-rim', 'Crater': 'shell-crater'}


def unit_of(name: str, package: str) -> str:
    folder = package[len(ROOT):].split('/')[0]
    if folder == 'Materials':
        return 'materials'
    if folder == 'Textures':
        return 'textures'
    if folder == 'Kit':
        if name.startswith('GD_Cabin'):
            return 'cabin'
        if name.startswith('GD_Tower'):
            return 'kit-towers'
        return SHELL[re.match(r'GD_Station(\w+?)_', name).group(1)]
    tower = re.match(r'GD_L(\d)_(\d)_Tower$', name)
    if tower:
        return f'tower-l{tower.group(1)}-{tower.group(2)}'
    rope = re.match(r'GD_L(\d)_Rope_LOD0$', name)
    if rope:
        return f'rope-l{rope.group(1)}'
    station = re.match(r'GD_(\w+?)_(?:Foundation|Access)$', name)
    if station:
        return 'station-' + station.group(1).replace('_', '-')
    raise ValueError(f'{name} fits no gondola unit')


def make(game):
    own = {k: T.donor_files(*v) for k, v in OWN.items()}
    about = dict(ABOUT)
    units = {unit_of(p.rsplit('/', 1)[1], p) for p in _packages(game)}
    for u in units:
        if u.startswith(('tower-', 'station-')):
            own[u] = T.donor_files(*SITE, GA + ('tower.py' if u.startswith('tower-') else 'stations.py'))
            about[u] = (f'support tower {u[6:].replace("-", " ")}: fitted mesh' if u.startswith('tower-')
                        else f'{u[8:]} station: its foundation and ground access meshes (the shell is shared)')
        elif u.startswith('rope-'):
            own[u] = T.donor_files(*SITE, GA + 'rope.py')
            about[u] = f'rope line {u[5:]}: the haul-rope mesh (LOD 0)'
    generator = T.donor_files('assets/vehicles/gondola', 'world/gondola', 'world/regions/gondola',
                              'world/regions/hidamari/gondola.py', 'world/regions/belmonte/gondola.py',
                              'world/walk_raster.py', 'world/source_registry.py', 'assets/source-library.json')
    return T.build(game, 'gondola', ROOT, unit_of, about, own, generator, 'Gondola')


def _packages(game):
    return sorted(o.package for a in T.records.discover(game)[0] if a.id.startswith('adopted/gondola/')
                  for o in a.outputs)


if __name__ == '__main__':
    raise SystemExit(T.main('gondola', make))
