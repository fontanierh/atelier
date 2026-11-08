"""Stage the committed fitted train furniture without a private cache or a Blender dependency."""
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

from train import layout as L

SOURCE = L.CONTRACT.parents[1]
TOLERANCE = .02  # metres, as in fit_furniture.py


def stage(destination, source=SOURCE):
    """@cc [owner:fontanierh,label:correctness] committed-furniture-only
    Every contract asset MUST be staged from its committed GLB and fitting report after the whole
    source inventory passes checksum and fit checks. Missing or invalid sources MUST fail before
    copying; never substitute a procedural box or publish references to unbuilt LODs.
    """
    source, destination = Path(source), Path(destination)
    manifest = tomllib.loads((source / 'source.toml').read_text())
    specs = {a['id']: a for a in L.contract()['assets']}
    if manifest['version'] != 1 or set(manifest['assets']) != set(specs):
        raise ValueError('train furniture source inventory differs from the dimension contract')
    files = []
    for aid, spec in specs.items():
        entry = manifest['assets'][aid]
        for key, name in (('path', f'{aid}.glb'), ('report', f'{aid}.json')):
            if entry[key] != f'furniture/{name}':
                raise ValueError(f'{aid}: source {key} must be furniture/{name}')
            path = source / entry[key]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = entry['sha256' if key == 'path' else 'report_sha256']
            if digest != expected:
                raise ValueError(f'{aid}: {key} checksum mismatch')
            files.append(path)
        report = json.loads((source / entry['report']).read_text())
        glb = source / entry['path']
        if (report['ok'] is not True or report['output_id'] != aid or report['pivot'] != spec['pivot']
                or report['glb'] != dict(file=glb.name, bytes=glb.stat().st_size, sha256=entry['sha256'])
                or 'lods' in report):
            raise ValueError(f'{aid}: invalid fitting report or generated LOD metadata')
        for axis, target in spec['dimensions_m'].items():
            if not abs(report['target_m'][axis] - target) <= .005 or not abs(report['fitted_m'][axis] - target) <= TOLERANCE:
                raise ValueError(f'{aid}: {axis} differs from the dimension contract')
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copyfile(path, destination / path.name)
    return len(specs)
