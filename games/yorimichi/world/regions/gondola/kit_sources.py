"""Publish independent Gondola source-command and audit data, without mesh geometry."""
import argparse
from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT), str(WORLD)]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from commands import Recorder, data  # noqa: E402
import params as P  # noqa: E402

RENDER = tuple(key for key in P.asset_names() if not key.endswith('_Collision'))
COLLISION = tuple(key for key in P.asset_names() if key.endswith('_Collision'))


@contextmanager
def recording(*modules):
    previous = [module.Mesh for module in modules]
    try:
        for module in modules: module.Mesh = Recorder
        yield
    finally:
        for module, mesh in zip(modules, previous): module.Mesh = mesh


def project():
    cabin = importlib.import_module('cabin')
    stations = importlib.import_module('stations')
    tower = importlib.import_module('tower')
    p = dict(P.DEFAULTS); d = P.derived(p)
    meshes = {}; proxies = {}; audit = dict(parameters=p, derived=d)
    with recording(cabin, stations, tower):
        c = cabin.Cabin(p, d); parts, doors = c.build(); meshes.update(parts)
        proxies['GD_Cabin_Collision'] = c.proxies()
        audit['cabin'] = dict(seats=c.seats, doors=doors, groove=c.groove, grip_info=c.grip_info,
                              layout=c.layout())
        for height in p['tower_heights']:
            t = tower.Tower(p, height); mesh = t.build(); meshes[mesh.name] = mesh
            proxies[mesh.name + '_Collision'] = t.proxies()
            audit[mesh.name] = dict(seats=t.seats, attachment=t.attachment())
        for key in ('valley', 'rim', 'crater'):
            st = stations.STATIONS[key](key, p, d)
            meshes.update(st.make())
            proxies[f'GD_Station{st.NAME}_Collision'] = st.proxies + st.platform_proxies()
            # Remaining source fields are metadata and exact pre-export queries, not geometry.
            audit[key] = dict(seats=st.seats, levels=st.levels, stairs=st.stairs,
                access=st.access, surfaces=st.surfaces, points=st.points, slabs=st.slabs,
                slab_z={name: [[x,y,z(x,y)] for x,y in poly] if callable(z) else z
                        for name,poly in st.slabs if (z := st.slab_z.get(name)) is not None},
                attachment=st.attachment())
    if set(meshes) != set(RENDER) or set(proxies) != set(COLLISION):
        raise ValueError('Gondola source-command inventory differs from canonical membership')
    values = {key: dict(schema=1, asset=key, commands=mesh.commands)
              for key, mesh in meshes.items()}
    values.update({key: dict(schema=1, asset=key, proxies=value) for key, value in proxies.items()})
    values['audit'] = dict(schema=1, asset='audit', metadata=data(audit))
    return data(values)


def publish(output):
    values = project()
    output = real_directory(output, create=True)
    for path in output.iterdir():
        if path.name not in {key + '.json' for key in values} or path.is_symlink() or not path.is_file():
            raise ValueError('Foreign Gondola source-command member')
    for key, value in values.items(): atomic_json(output / (key + '.json'), value)
    print('GONDOLA SOURCE COMMANDS COMPLETE', len(RENDER), len(COLLISION), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    publish(args.output)


if __name__ == '__main__': main()
