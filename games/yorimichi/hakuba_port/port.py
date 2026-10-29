"""Port Yorimichi's built world regions into Hakuba as props and data-only regions.

    uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...

Each region's adapter (in `regions.py`) reads Yorimichi's build products and names the meshes to convert and where
each stands. This script converts every mesh in one guarded Blender run (`convert.py`), writes each one as a Hakuba
prop under `games/hakuba/assets/props/<name>/` and writes the region's
`games/hakuba/assets/world/src/regions/<region>/placements.json`. Run `cargo export assets` in `games/hakuba`
afterwards to export them.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HAKUBA = REPO / 'games' / 'hakuba'
BLENDER = os.environ.get('BLENDER', '/usr/local/bin/blender')
# Models at least this large across are drawn in middle-detail tiles too, seen from afar.
AFAR_M = 6.0


@dataclass
class Model:
    """One mesh to convert: its source file, its colour rules (see `convert.py`), whether it is solid, and an optional
    separate collision mesh."""
    source: Path
    slots: dict = field(default_factory=dict)
    default: dict = field(default_factory=dict)
    solid: bool = True
    collision: object = None
    about: str = ''


@dataclass
class Region:
    """A region's models, by Hakuba prop name, and its groups: (prop name, afar, [[x, y, z, yaw, scale], ...]), each
    instance the model's source origin on the map, its turn counter-clockwise in degrees and its scale. `afar` None
    leaves it to the model's size; a height of None stands the model on Hakuba's ground."""
    name: str
    about: str
    models: dict = field(default_factory=dict)
    groups: list = field(default_factory=list)


def kebab(name):
    """`TH_Dressing_cell_-2_2_Piece0` -> `dressing-cell-m2-2-piece0`, after the caller strips the region prefix."""
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', name).replace('_', '-').lower()
    return re.sub(r'-+', '-', name.replace('--', '-m')).strip('-')


def export_source(build, export, asset):
    """The FBX or GLB a Yorimichi export step wrote for `asset`."""
    folder = build / 'exports' / f'world.{export}.export' / asset
    found = sorted(p for p in folder.glob('*') if p.suffix.lower() in ('.fbx', '.glb'))
    if not found:
        raise SystemExit(f'{folder}: no exported mesh')
    return found[0]


def convert(models, scratch):
    """Convert every model in one guarded Blender run; returns each prop's origin in the source frame."""
    jobs = []
    for name, model in models.items():
        out = HAKUBA / 'assets' / 'props' / name / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        job = {'source': str(model.source), 'output': str(out), 'slots': model.slots, 'default': model.default,
               'collision': model.solid}
        if model.collision:
            job['collision_source'] = str(model.collision)
        jobs.append(job)
    job_file = scratch / 'jobs.json'
    job_file.write_text(json.dumps(jobs))
    report = scratch / 'guard'
    command = [sys.executable, '-m', 'atelier.safety.guarded', '--report', str(report), '--timeout', '7200',
               '--small', '4', '--kind', 'job', '--purpose', 'hakuba port: convert region meshes', '--',
               BLENDER, '-b', '--threads', '3', '-P', str(HERE / 'convert.py'), '--', str(job_file)]
    subprocess.run(['nice', '-n', '10', *command], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    origins, failures = {}, []
    for line in (report / 'stdout.log').read_text().splitlines():
        if line.startswith('CONVERTED '):
            result = json.loads(line[len('CONVERTED '):])
            origins[Path(result['output']).parents[1].name] = (result['origin'], result['size'])
        elif line.startswith('FAILED '):
            failures.append(json.loads(line[len('FAILED '):]))
    for failure in failures:
        print('failed:', failure['output'], failure['error'].strip(), file=sys.stderr)
    return origins


def write(region, origins):
    for name, model in region.models.items():
        folder = HAKUBA / 'assets' / 'props' / name
        about = model.about or f'A piece of {region.about}, ported with its colours painted per vertex.'
        lines = [f'# {about}', 'kind = "prop"', 'source = "src/model.glb"']
        if model.solid:
            lines.append('solid = true')
        (folder / 'asset.toml').write_text('\n'.join(lines) + '\n')
    groups = []
    for name, afar, instances in region.groups:
        (ox, oy, oz), size = origins[name]
        on_ground = any(instance[2] is None for instance in instances)
        if afar is None:
            afar = size >= AFAR_M
        placed = []
        for x, y, z, yaw, scale in instances:
            # The converter moved the origin to (ox, oy, oz) in the model's frame: stand it there.
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            placed.append([round(x + scale * (c * ox - s * oy), 4), round(y + scale * (s * ox + c * oy), 4),
                           round((z or 0.0) + scale * oz, 4), round(yaw, 4), round(scale, 4)])
        group = {'model': f'props/{name}', 'afar': afar, 'instances': placed}
        if on_ground:
            group['on_ground'] = True
        groups.append(group)
    folder = HAKUBA / 'assets' / 'world' / 'src' / 'regions' / region.name
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps({'groups': groups}, separators=(',', ':'))
    (folder / 'placements.json').write_text(text.replace('{"model"', '\n{"model"') + '\n')
    readme = folder / 'README.md'
    if not readme.exists():
        readme.write_text(f'# {region.name}\n\n{region.about[0].upper() + region.about[1:]}. `placements.json` stands each of '
                          'its props at its map position, height, turn and scale.\n')


def main():
    import regions
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    parser.add_argument('region', nargs='+', choices=sorted(regions.ADAPTERS))
    args = parser.parse_args()
    for name in args.region:
        region = regions.ADAPTERS[name](args.build.resolve())
        with tempfile.TemporaryDirectory() as scratch:
            origins = convert(region.models, Path(scratch))
        for name in set(region.models) - set(origins):
            # A mesh with nothing left to draw, such as one made only of dropped slots, is left out.
            del region.models[name]
            folder = HAKUBA / 'assets' / 'props' / name
            for path in sorted(folder.rglob('*'), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            folder.rmdir()
        region.groups = [group for group in region.groups if group[0] in region.models]
        write(region, origins)
        count = sum(len(i) for _, _, i in region.groups)
        print(f'{region.name}: {len(region.models)} props, {count} placements')


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    main()
