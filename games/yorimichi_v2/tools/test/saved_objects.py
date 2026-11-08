"""Check a region's saved objects in the running slice game: each exactly once, as its saved actor (audit A1).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/saved_objects.py --session ID --region w09-brinecove --zone cove

The objects are the region's objects.toml (tools/migrate/objects.py). After travelling to --zone and --settle seconds
of streaming, every component of the game world drawing one of an object's group meshes must belong to that
object's one saved actor (an AV2ScenePatch whose SourceKey is `<tag>:<name>`): the runtime region spawning it as
well, or a second saved copy, is a duplicate; no component is a lost object. Each object's actor location and each
group's instance count are printed and kept in OUT/report.json with the launch revision, so an edit made in the
editor can be compared with what the game shows. Exit 0 only when every object is there exactly once. It saves
nothing.
"""
import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'platform' / 'studio'))
sys.path.insert(0, str(GAME / 'tools' / 'migrate'))
import towns  # noqa: E402
from launch import launch_revision, revision  # noqa: E402
from atelier import live  # noqa: E402
from atelier.live_sessions import Unreachable  # noqa: E402

HELPERS = r'''
import json, unreal
def objects_travel(key):
    m = [m for m in unreal.ObjectIterator(unreal.JapanMap) if not m.get_path_name().startswith('/Script/')][0]
    return m.teleport_to_zone(key)
def objects_found(meshes):
    """{mesh: [[actor class, actor source key or name, instances, actor location]]} for every drawing component."""
    world = unreal.LiveLibrary.game_world()
    found = {m: [] for m in meshes}
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        for c in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = c.static_mesh.get_name() if c.static_mesh else None
            # A patch's shadow twin repeats its group's instances, hidden, for shadows only: not a second copy.
            if mesh not in found or 'V2Role:ShadowTwin' in [str(t) for t in c.component_tags]:
                continue
            count = c.get_instance_count() if isinstance(c, unreal.InstancedStaticMeshComponent) else 1
            key = str(actor.get_editor_property('source_key')) if actor.get_class().get_name() == 'V2ScenePatch' else actor.get_name()
            l = actor.get_actor_location()
            found[mesh].append([actor.get_class().get_name(), key, count, [l.x, l.y, l.z]])
    return json.dumps(found)
'''


def py(code):
    for attempt in range(8):
        try:
            out = live.request('/python', code)
            break
        except Unreachable:
            if attempt == 7:
                raise
            time.sleep(3)
    if not out.get('ok'):
        raise RuntimeError(out.get('result') or out)
    return out.get('output', '').strip()


def mesh_of(group: str) -> str:
    """The mesh a group key draws: towns.group_keys' "<mesh>#<index>" and its cell pieces "<key>@<x>_<y>" name it."""
    return group.split('@', 1)[0].split('#', 1)[0]


def expected_instances(data: dict) -> dict[str, int]:
    """{group key: instances the runtime places}, with the runtime's own filters as towns.py mirrors them (district
    bounds for scenery, gondola clearance for plants) and its cell pieces, so a saved group drawing fewer is missing
    geometry."""
    # Only plant groups are clipped by the gondola clearance.
    segments = towns.clearance_segments() if any(e['plant'] for e in data['groups']) else []
    counts = {}
    for entry, key in zip(data['groups'], towns.group_keys(data)):
        cells = towns.kept_cells(data, entry, segments)
        counts[key] = sum(cells.values())
        if counts[key] > towns.PIECE_LIMIT:
            counts.update({towns.piece_key(key, *cell): n for cell, n in cells.items()})
    return counts


def check(listed: dict, found: dict, expected: dict[str, int]) -> dict:
    """{object id: problems} from objects.toml's objects, the game's components per mesh and the instances each
    group must draw (expected_instances). Groups sharing a mesh (`#index` groups, cell pieces) are checked together
    per object: its actor draws their summed instances, and no actor but the objects listing that mesh draws it."""
    owners: dict[str, set] = {}
    for item in listed['objects']:
        for group in item['groups'] if 'groups' in item else [item['group']]:
            owners.setdefault(mesh_of(group), set()).add(f'{listed["tag"]}:{item["id"].rsplit("/", 1)[1]}')
    problems = {}
    for item in listed['objects']:
        key = f'{listed["tag"]}:{item["id"].rsplit("/", 1)[1]}'
        groups = item['groups'] if 'groups' in item else [item['group']]
        by_mesh: dict[str, list[str]] = {}
        for group in groups:
            by_mesh.setdefault(mesh_of(group), []).append(group)
        wrong = []
        for mesh, keys in by_mesh.items():
            rows = found.get(mesh, [])
            mine = [r for r in rows if r[0] == 'V2ScenePatch' and r[1] == key]
            want = sum(expected.get(k, 0) for k in keys)
            if not mine:
                wrong.append(f'{mesh}: 0 saved copies')
            elif any(expected.get(k, 0) < 1 for k in keys):
                wrong.append(f'{mesh}: the runtime file places no instance of {[k for k in keys if expected.get(k, 0) < 1]}')
            elif sum(r[2] for r in mine) != want:
                wrong.append(f'{mesh}: {sum(r[2] for r in mine)} instance(s) drawn, {want} expected')
            others = [r for r in rows if not (r[0] == 'V2ScenePatch' and r[1] in owners[mesh])]
            if others:
                wrong.append(f'{mesh}: also drawn by {", ".join(f"{r[0]} {r[1]}" for r in others[:3])}')
        if len({tuple(r[3]) for m in by_mesh for r in found.get(m, []) if r[1] == key}) > 1:
            wrong.append('its groups are in more than one actor')
        if wrong:
            problems[item['id']] = wrong
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--region', required=True, help='region folder name, e.g. w09-brinecove')
    parser.add_argument('--zone', required=True, help='map zone to travel to first, e.g. cove')
    parser.add_argument('--settle', type=float, default=25.0, help='seconds for the region to stream in')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'saved-objects')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the check to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    listed = tomllib.loads((GAME / 'world' / 'regions' / args.region / 'objects.toml').read_text())
    # Runtime-group objects that have their record are saved; the rest are still the runtime's (not migrated yet).
    groups = [i for i in listed['objects'] if 'group' in i or 'groups' in i]
    listed['objects'] = [i for i in groups if (GAME / 'assets' / i['id'] / 'asset.toml').is_file()]
    if len(listed['objects']) < len(groups):
        print(f'PENDING {len(groups) - len(listed["objects"])} object(s) of {args.region} have no record yet: '
              'the runtime still draws them', flush=True)
    meshes = sorted({mesh_of(m) for i in listed['objects'] for m in (i['groups'] if 'groups' in i else [i['group']])})
    py(HELPERS)
    if py(f'print(objects_travel({args.zone!r}))') != 'True':
        print(f'travel to {args.zone} was refused', file=sys.stderr)
        return 2
    time.sleep(args.settle)
    found = json.loads(py(f'print(objects_found({meshes!r}))'))
    expected = expected_instances(json.loads((GAME / 'unreal/Content/Data' / listed['data']).read_text()))
    problems = check(listed, found, expected)
    for item in listed['objects']:
        key = f'{listed["tag"]}:{item["id"].rsplit("/", 1)[1]}'
        rows = [r for m in meshes for r in found.get(m, []) if r[1] == key]
        at = rows[0][3] if rows else None
        print(f'OBJECT {item["id"]} at {at} instances {sum(r[2] for r in rows)} '
              f'{"ok" if item["id"] not in problems else problems[item["id"]]}', flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'session': args.session, 'revision': source, 'region': args.region, 'found': found,
              'problems': problems, 'passed': not problems}
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('SAVED OBJECTS', 'PASSED' if not problems else 'FAILED', flush=True)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
