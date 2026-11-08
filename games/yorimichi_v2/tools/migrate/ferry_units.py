"""Write the ferry's editing units (assets/adopted/ferry/units.json) for its ownership split (audit A1).

    uv run python games/yorimichi_v2/tools/migrate/ferry_units.py [--check]

One unit per fixed terminal (`terminal-hidamari` FT_HD_*, `terminal-brinecove` FT_BC_*: parts, collision and brow), one
for the ferry ship (`ship`: hull, superstructure, collision, gate and wake; a vehicle, it moves), and the shared
`materials` (FT_*, FY_*, M_Ferry*), which also carries the generator of every ferry package. Each terminal's own
sources are the terminal builder and plan modules; the ship's are the ship builder and plan modules.
"""
from __future__ import annotations

import transport_units as T

ROOT = '/Game/Ferry/'
FA = 'assets/vehicles/ferry/'
TERMINAL = [FA + 'terminals/build.py', FA + 'terminals/site.py', 'world/regions/ferry/plan_terminal.py',
            'world/regions/ferry/terminal_sources.py', 'world/regions/ferry/terminal_constructor.py',
            'world/regions/ferry/export_terminal_collision.py']
OWN = {
    'terminal-hidamari': TERMINAL,
    'terminal-brinecove': TERMINAL,
    'ship': [FA + 'build.py', 'world/regions/ferry/plan_ship.py', 'world/regions/ferry/ship_sources.py',
             'world/regions/ferry/export_ship_collision.py'],
}
ABOUT = {
    'terminal-hidamari': 'the Hidamari ferry terminal: jetty, stage, waiting house, timetable board, collision and brow (berth 0)',
    'terminal-brinecove': 'the Brine Cove ferry terminal: landing, pavilion, ticket hut, fenders, props, collision and brow (berth 1)',
    'ship': 'the ferry ship: hull, superstructure, funnel, lifeboats, rails, masts, fittings, collision, gate and wake',
    'materials': 'ferry materials (terminal FT_*, ship FY_*), and the generator that made every ferry package',
}


def unit_of(name: str, package: str) -> str:
    folder = package[len(ROOT):].split('/')[0]
    if folder == 'Materials':
        return 'materials'
    if folder == 'Ship':
        return 'ship'
    if name.startswith('FT_HD_'):
        return 'terminal-hidamari'
    if name.startswith('FT_BC_'):
        return 'terminal-brinecove'
    raise ValueError(f'{name} fits no ferry unit')


def make(game):
    generator = T.donor_files('assets/vehicles/ferry', 'world/regions/ferry', 'world/regions/hidamari/ferry_source.py',
                              'world/walk_raster.py', 'world/region_plan_files.py', 'world/source_registry.py',
                              'assets/source-library.json')
    return T.build(game, 'ferry', ROOT, unit_of, ABOUT, {k: T.donor_files(*v) for k, v in OWN.items()}, generator,
                   'Ferry')


if __name__ == '__main__':
    raise SystemExit(T.main('ferry', make))
