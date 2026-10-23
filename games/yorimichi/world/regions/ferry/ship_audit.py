"""Run the original whole-ship audits from explicit pre-export constructor data."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402
from regions.ferry.ship_sources import BUILD, BUILDERS  # noqa: E402


def queries(root):
    root = real_directory(root)
    expected = {key + '.json' for key in BUILDERS}
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError('Incomplete or foreign ferry query inventory')
    values = {}
    for key in BUILDERS:
        path = root / (key + '.json')
        if path.is_symlink() or not path.is_file():
            raise ValueError('Ferry queries must be regular data files')
        value = json.loads(path.read_text())
        if value.get('schema') != 1 or value.get('asset') != key:
            raise ValueError('Foreign selected ferry query')
        count = sum(len(face) - 2 for face in value['faces'])
        if count != value['triangles'] or value['report']['open_edges']:
            raise ValueError('Incomplete or failed ferry query geometry')
        values[key] = value
    return values


def audit(program, values):
    """Preserve registry ordering and every original seating/overlap/walk failure gate."""
    if list(values) != list(BUILDERS):
        raise ValueError('Ferry audits require the complete ordered original ship roster')
    namespace = dict(__file__=str(BUILD), __name__='ferry_original_audits')
    exec(compile(program, str(BUILD), 'exec'), namespace)
    namespace['SEATS'] = [row for value in values.values() for row in value['seats']]
    namespace['BLOCKS'] = [row for value in values.values() for row in value['blocks']]
    namespace['BOAT_FACES'] = values['FY_Lifeboats']['boat_faces']
    meshes = {key: SimpleNamespace(verts=value['vertices'], faces=value['faces']) for key, value in values.items()}
    proxies = namespace['collision_proxies']()
    seats, hits = namespace['seating_check'](meshes)
    contacts = hits.pop('fitting_rail_contacts')
    bad = [row for row in seats if row['status'] != 'ok']
    if bad or any(hits.values()) or contacts:
        raise ValueError(f'Original ferry deck audit failed: seats={bad}, overlaps={hits}, contacts={contacts}')
    layout = namespace['walk_layout'](proxies, seats, hits)
    lo = [min(vertex[i] for value in values.values() for vertex in value['vertices']) for i in range(3)]
    hi = [max(vertex[i] for value in values.values() for vertex in value['vertices']) for i in range(3)]
    gate_x, gate_w = namespace['GATES'][0]
    deck_z, boat_z, deck_half = (namespace[key] for key in ('deck_z', 'boat_z', 'deck_half'))
    st = namespace['stair_plan']()
    return dict(schema=1, complete=True, proxies=proxies, deck_layout=layout,
                dimensions=dict(min=[round(v, 3) for v in lo], max=[round(v, 3) for v in hi],
                    length=round(hi[0] - lo[0], 2), beam=round(hi[1] - lo[1], 2),
                    height_above_waterline=round(hi[2], 2), draft=round(-lo[2], 2)),
                boarding_openings=[dict(side=side, centre=[gate_x, round(sign * deck_half(gate_x), 3), round(deck_z(gate_x), 3)],
                    width=gate_w, clear_height='open above', outward=[0, sign, 0])
                    for side, sign in (('starboard', -1), ('port', 1))],
                decks=dict(main_deck_z=dict(stern=round(deck_z(-38), 2), midships=round(deck_z(0), 2), bow=round(deck_z(38), 2)),
                    boat_deck_z_midships=round(boat_z(0), 2), monkey_island_z=round(boat_z(19) + namespace['WH_H'] + .3, 2),
                    rail_height=namespace['RAIL_H']),
                stair=dict(risers=st['risers'], rise=round(st['rise'], 3), tread=st['tread'], width=st['width'],
                    angle_deg=round(st['angle_deg'], 1), foot=[round(st['foot_x'], 3), round(st['foot_z'], 3)],
                    top=[round(st['top_x'], 3), round(st['top_z'], 3)]),
                deck_audit=dict(fittings_checked=len(seats), failures=0, lifeboat_overlaps=hits,
                                fitting_rail_contacts=contacts),
                meshes={key: {field: value[field] for field in ('triangles', 'materials', 'min', 'max')} |
                        dict(vertices=len(value['vertices']), **value['report']) for key, value in values.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--collision-data', type=Path, required=True)
    parser.add_argument('--deck-layout', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    if args.source.is_symlink() or not args.source.is_file():
        raise ValueError('Ferry audit source must be regular')
    source = json.loads(args.source.read_text())
    if source.get('schema') != 1 or source.get('asset') != 'audit':
        raise ValueError('Foreign ferry audit source')
    values = queries(args.queries)
    before = {key: sha(args.queries / (key + '.json')) for key in values}
    value = audit(source['program'], values)
    if before != {key: sha(args.queries / (key + '.json')) for key in values}:
        raise ValueError('Ferry queries changed during original audits')
    value['inputs'] = before
    atomic_json(args.collision_data, dict(schema=1, asset='FY_Collision', proxies=value.pop('proxies')))
    atomic_json(args.deck_layout, value.pop('deck_layout'))
    atomic_json(args.output, value)
    print('FERRY SHIP ORIGINAL AUDITS COMPLETE', flush=True)


if __name__ == '__main__': main()
