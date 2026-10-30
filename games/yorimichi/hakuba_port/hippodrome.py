"""Build the Hidamari Hippodrome's course and structures for the `hippodrome` adapter, without Blender.

    uv run python games/yorimichi/hakuba_port/hippodrome.py --build build/yorimichi

Yorimichi's `world.hippodrome` steps write the venue as `hippodrome/region`: a GLB for each of its meshes (`glb/`), the
course textures (`textures/`) and the venue data (`hippodrome.json`) placing every mesh round the course origin. Those
steps no longer run: their scripts miss the regions folder on Python's path, and the query step passes a string where
the build's file writer takes a path. This writes the same folder by calling the venue's own constructors: the queried
platform heights (`project_queries.project`), each mesh's `construct()` from its `plan_*.py`, `venue_data.textures` and
`venue_data.metadata`, reading the far hills the build wrote to the same folder. Each structure's model draws one
embedded image, which is written beside the course textures as `<its material>.<format>` for the adapter to sample.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

YORIMICHI = Path(__file__).resolve().parents[1]
REGION = YORIMICHI / 'world' / 'regions' / 'hippodrome'
FORMATS = {'image/jpeg': 'jpg', 'image/png': 'png'}


def embedded(glb):
    """{material name: (format, image bytes)} for each material of `glb` drawing an image stored in the file."""
    data = glb.read_bytes()
    size = int.from_bytes(data[12:16], 'little')
    gltf, blob = json.loads(data[20:20 + size]), data[28 + size:]
    images = {}
    for material in gltf.get('materials', []):
        texture = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
        if texture is None:
            continue
        image = gltf['images'][gltf['textures'][texture['index']]['source']]
        if 'bufferView' not in image:
            continue
        view = gltf['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        images[material['name']] = (FORMATS[image['mimeType']], blob[start:start + view['byteLength']])
    return images


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--build', type=Path, required=True, help="Yorimichi's build folder, build/yorimichi")
    build = parser.parse_args().build.resolve()
    out = build / 'hippodrome' / 'region'
    os.environ['ATELIER_BUILD_ROOT'] = str(build.parent)
    sys.path[:0] = [str(YORIMICHI), str(YORIMICHI / 'world'), str(YORIMICHI / 'world' / 'regions')]
    from hippodrome import project_queries, venue_data
    from hippodrome.query_context import load
    (out / 'glb').mkdir(parents=True, exist_ok=True)
    project_queries.project(out / 'queries.json')
    load(out / 'queries.json')
    for plan in sorted(REGION.glob('plan_*.py')):
        key = re.search(r"main\('(SM_HD_\w+)'", plan.read_text())
        if not key:
            continue
        spec = importlib.util.spec_from_file_location(plan.stem, plan)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data, info = module.construct()
        (out / 'glb' / f'{key[1]}.glb').write_bytes(data)
        print(f'{key[1]}: {info["triangles"]} triangles')
    venue_data.textures(out / 'textures')
    for glb in sorted((out / 'glb').glob('*.glb')):
        for material, (suffix, image) in embedded(glb).items():
            (out / 'textures' / f'{material}.{suffix}').write_bytes(image)
    (out / 'hippodrome.json').write_text(json.dumps(venue_data.metadata(), indent=1) + '\n')


if __name__ == '__main__':
    main()
