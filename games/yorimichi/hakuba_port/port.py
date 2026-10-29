"""Port Yorimichi's built world regions into Hakuba as props and data-only regions.

    uv run python games/yorimichi/hakuba_port/port.py --build build/yorimichi REGION...

Each region's adapter (in `regions.py`) reads Yorimichi's build products and names the meshes to convert and where
each stands. This script converts every mesh in one guarded Blender run (`convert.py`), writes each one as a Hakuba
prop under `games/hakuba/assets/props/<name>/` and writes the region's
`games/hakuba/assets/world/src/regions/<region>/placements.json`. Each image a colour rule names (`mean` or `sample`)
becomes a Hakuba texture asset, `<region>-<image name>`, that the prop draws on its mesh's own UVs, as Yorimichi draws
it. Run `cargo export assets` in `games/hakuba` afterwards to export them.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HAKUBA = REPO / 'games' / 'hakuba'
BLENDER = os.environ.get('BLENDER', '/usr/local/bin/blender')
# Models at least this large across are drawn in middle-detail tiles too, seen from afar.
AFAR_M = 6.0
# The longest side a texture keeps, in texels.
LONGEST = 4096


@dataclass
class Model:
    """One mesh to convert: its source file, its colour rules (see `convert.py`), whether it is solid, an optional
    separate collision mesh, and the Hakuba texture assets its materials draw."""
    source: Path
    slots: dict = field(default_factory=dict)
    default: dict = field(default_factory=dict)
    solid: bool = True
    collision: object = None
    about: str = ''
    textures: list = field(default_factory=list)


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


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_texture(name, source, about):
    """`source` as the texture asset `name`, in BC7 blocks, its sides rounded up to powers of two of at most
    `LONGEST` texels."""
    from PIL import Image
    image = Image.open(source)
    image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
    size = [min(LONGEST, 1 << (side - 1).bit_length()) for side in image.size]
    if list(image.size) != size:
        image = image.resize(size, Image.LANCZOS)
    folder = HAKUBA / 'assets' / 'textures' / name / 'src'
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / 'texture.png')
    (folder / 'manifest.toml').write_text(
        f'# {about}\npath = "texture.png"\nsha256 = "{sha256(folder / "texture.png")}"\n'
        f'authoring_texture_sha256 = "{sha256(source)}"\n')
    (folder.parent / 'asset.toml').write_text(
        f'# {about}\nkind = "texture"\nsource = "src/texture.png"\ncompression = "bc7"\n')


def mean(path):
    """An image's mean linear RGB."""
    from PIL import Image
    rgb = np.asarray(Image.open(path).convert('RGB'), np.float64) / 255.0
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4).reshape(-1, 3).mean(axis=0).tolist()


def prune_textures(prefixes):
    """Delete the texture assets ported regions wrote (named `<prefix>-...`) that no asset names any more, such as
    those of slots on meshes without UVs or of terrain props `ground.py` removed."""
    assets = HAKUBA / 'assets'
    used = set()
    for toml in assets.glob('**/asset.toml'):
        for names in re.findall(r'^textures = (\[.*\])$', toml.read_text(), re.M):
            used.update(json.loads(names))
    for folder in sorted((assets / 'textures').iterdir()):
        if folder.name not in used and any(folder.name.startswith(prefix + '-') for prefix in prefixes):
            shutil.rmtree(folder)


def jobs(region, scratch):
    """The Blender jobs for `region`'s models, written to `scratch`. Each image a rule names becomes a texture asset,
    which the rule then names as `texture`, with the image's mean colour (`mean_rgb`) for a mesh without UVs."""
    textures, means, result = {}, {}, []
    for name, model in region.models.items():
        out = HAKUBA / 'assets' / 'props' / name / 'src' / 'model.glb'
        out.parent.mkdir(parents=True, exist_ok=True)
        rules = {}
        for slot, rule in [*model.slots.items(), (None, model.default)]:
            image = rule.get('mean') or rule.get('sample')
            if image:
                if image not in textures:
                    texture = f'{region.name}-{kebab(Path(image).stem)}'
                    while texture in textures.values():
                        texture += '-b'
                    textures[image] = texture
                    words = texture.removeprefix(region.name + '-').replace('-', ' ')
                    write_texture(texture, image, f'The {words} texture that the {region.name} props draw.')
                rule = {key: value for key, value in rule.items() if key not in ('mean', 'sample')}
                rule['texture'], rule['mean_rgb'] = textures[image], means.setdefault(image, mean(image))
            rules[slot] = rule
        default = rules.pop(None)
        job = {'source': str(model.source), 'output': str(out), 'slots': rules, 'default': default,
               'collision': model.solid}
        if model.collision:
            job['collision_source'] = str(model.collision)
        result.append(job)
    job_file = scratch / 'jobs.json'
    job_file.write_text(json.dumps(result))
    return job_file


def blender(job_file, scratch):
    """Run `convert.py` over `job_file` in one guarded Blender run; returns its output."""
    report = scratch / 'guard'
    command = [sys.executable, '-m', 'atelier.safety.guarded', '--report', str(report), '--timeout', '7200',
               '--small', '4', '--kind', 'job', '--purpose', 'hakuba port: convert region meshes', '--',
               BLENDER, '-b', '--threads', '3', '-P', str(HERE / 'convert.py'), '--', str(job_file)]
    subprocess.run(['nice', '-n', '10', *command], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (report / 'stdout.log').read_text()


def convert(region, scratch):
    """Convert every model of `region`; returns each prop's origin in the source frame and its size, and records the
    textures each one draws."""
    output = blender(jobs(region, scratch), scratch)
    origins, failures = {}, []
    for line in output.splitlines():
        if line.startswith('CONVERTED '):
            result = json.loads(line[len('CONVERTED '):])
            name = Path(result['output']).parents[1].name
            origins[name] = (result['origin'], result['size'])
            region.models[name].textures = result['textures']
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
        if model.textures:
            lines.append(f'textures = {json.dumps(sorted(model.textures))}')
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
            origins = convert(region, Path(scratch))
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
    prune_textures(args.region)


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    main()
