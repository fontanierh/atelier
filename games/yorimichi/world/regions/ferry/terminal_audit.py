"""Original terminal safety gates from exact pre-export meshes and final query products."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from regions.ferry.terminal_sources import OWNERS, KIT, final_world  # noqa: E402
from regions.ferry.terminal_constructor import kit  # noqa: E402
import region_query  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def mesh_from(context, key, row):
    mesh = context.F.Mesh(key)
    for field, value in row.items(): setattr(mesh, field, value)
    return mesh


def audit(root, sources, query_root, harbor_query):
    current = load('ferry_terminal_current_audit', KIT / 'build.py')
    current.configure_site()
    worlds = {owner: current.FS.load_world(owner, out=root) for owner in OWNERS}
    worlds['hidamari'] = final_world(worlds['hidamari'], region_query.load(harbor_query, owner='HD_Harbor', stage='final'))
    current.FS.load_world = lambda owner: worlds[owner]
    primitives = json.loads((sources / 'primitives.json').read_text())
    mats = current.F.make_materials()
    ships = []
    for key in current.SHIP_PARTS:
        name = 'FY_' + key.title()
        row = json.loads((root.parent / 'ship-query-data' / (name + '.json')).read_text())
        mesh = current.F.Mesh(name); mesh.verts = row['vertices']; mesh.faces = row['faces']
        # Original terminal clearance uses ship render geometry; its source slot labels are irrelevant to BVH.
        mesh.mats = [row['materials'][0]] * len(mesh.faces)
        obj, _ = current.F.to_object(mesh, mats)
        for collection in list(obj.users_collection): collection.objects.unlink(obj)
        ships.append(obj)
    fixtures = current.F.SM.audit_fixtures()
    failures = ['Original audit fixture failed'] if not all(row['ok'] for row in fixtures) else []
    manifest = dict(sources=current.code_sources(), materials=current.F.MATERIALS, sill_z=current.SILL,
        site_inputs=current.SITE['inputs'], audit_fixtures=fixtures, terminals={},
        units='metres, z up; Hidamari in world metres, Brinecove region-local',
        limits=dict(step_max=current.WC.STEP_MAX, headroom_min=current.WC.HEADROOM_MIN,
                    width_min=current.WC.WIDTH_MIN, capsule_radius=current.WC.RADIUS))
    walks, collision_data = {}, {}
    for owner in OWNERS:
        layout = load('terminal_audit_' + owner, yori.WORLD / 'regions' / owner / 'ferry_terminal.py')
        rows = {key: json.loads((query_root / (key + '.json')).read_text()) for key in layout.CONSTRUCTORS}
        if any(row.get('schema') != 1 or row.get('asset') != key or row.get('owner') != owner for key, row in rows.items()):
            raise ValueError('Foreign terminal audit query')
        source = json.loads((sources / (owner + '_collision.json')).read_text())
        context, complete = kit(primitives, source)
        namespace = dict(math=__import__('math')); exec(source['program'], namespace)
        namespace['fixed_collision'](context, source['parameters']); complete()
        hulls = [hull for row in rows.values() for hull in row['fixed_hulls']] + context.COL
        collision_data[owner] = dict(schema=1, asset='FT_' + ('HD' if owner == 'hidamari' else 'BC') + '_Collision',
            owner=owner, anchor=next(iter(rows.values()))['anchor'], hulls=hulls)
        source = json.loads((sources / (owner + '_walk.json')).read_text())
        context, complete = kit(primitives, source)
        exec(source['program'], namespace)
        metadata = {key: value for row in rows.values() for key, value in row['metadata'].items()}
        walk = namespace['walk_plan'](context, source['parameters'], metadata['stair'], metadata['brow']); complete()
        meshes = {key: mesh_from(current, key, row['raw']) for key, row in rows.items()}
        geometry = list(meshes.values()); bases = [seat['at'] for mesh in geometry for seat in mesh.seats]
        seat_rows, seat_bad = current.F.SM.seat_failures(geometry, current.world_near(owner, bases) if bases else ())
        count, cop = current.F.SM.coplanar_overlaps(geometry, limit=400)
        xy = np.asarray([vertex[:2] for mesh in geometry for vertex in mesh.verts])
        summary, carried_bad = current.F.SM.carried_failures(geometry,
            current.world_near(owner, [xy.min(0), xy.max(0)]))
        collection = bpy.data.collections.new(owner); bpy.context.scene.collection.children.link(collection)
        objects = []
        for key, mesh in meshes.items():
            anchor = walk['anchor']; mesh.verts[:] = [(x-anchor[0], y-anchor[1], z-anchor[2]) for x, y, z in mesh.verts]
            current.F.check(mesh)
            obj, _ = current.F.to_object(mesh, mats); obj.location = anchor; objects.append(obj)
        ground, cuts = current.context_ground(owner, walk['route'])
        ground_obj = bpy.data.objects.new('ctx_' + owner, ground); collection.objects.link(ground_obj)
        moored = current.ship_at(ships, current.SITE[owner]['berth'], collection)
        clash = current.ship_clash(objects, moored)
        walking = current.walk_audit(objects + [ground_obj] + moored, walk)
        seats = dict(count=len(seat_rows), failures=seat_bad, rule=dict(gap_max_m=current.F.SM.SEAT_GAP, slack_m=current.F.SM.SEAT_SLACK))
        coplanar = dict(count=count, samples=cop)
        carried = dict(**summary, failures=carried_bad, rule=dict(touch_m=current.F.SM.CARRY_TOUCH, carrier='exported world, less world cuts'))
        walks[owner] = dict(**walk, audit=walking, ship_clash=clash, world_cuts_pending=cuts, seats=seats, coplanar=coplanar, carried=carried)
        manifest['terminals'][owner] = dict(**{key: walk[key] for key in ('anchor', 'frame', 'stair', 'brow', 'board', 'gate')},
            mesh_order=list(layout.MESH_ORDER),
            meshes={key: dict(triangles=row['triangles'], materials=row['materials'], authored_hulls=row['authored_hulls'], **row['report']) for key, row in rows.items()},
            walk=walking, ship_clash=clash, world_cuts_pending=cuts, seats=seats, coplanar=coplanar, carried=carried,
            collision=dict(convex_hulls=len(hulls), brow_convex_hulls=sum(len(row['moving_hulls']) for row in rows.values())),
            triangles=sum(row['triangles'] for row in rows.values()))
        if seat_bad or count or carried_bad or not walking['pass'] or not clash['pass'] or any(row['report']['open_edges'] for row in rows.values()):
            failures.append(owner + ': original closure/seating/coplanar/carried/walk/ship-clash gate failed')
        print('FERRY TERMINAL ORIGINAL AUDIT', owner, 'PASS' if not failures else 'FAIL', flush=True)
    manifest['failures'] = failures
    if failures: raise ValueError(str(failures))
    return manifest, walks, collision_data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--harbor-query', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    manifest, walks, collisions = audit(yori.OUT / 'ferry/terminals', args.sources, args.queries, args.harbor_query)
    atomic_json(args.output, manifest)
    atomic_json(args.output.parent / 'walk.json', walks)
    for owner, value in collisions.items(): atomic_json(args.output.parent / (owner + '-collision-data.json'), value)


if __name__ == '__main__': main()
