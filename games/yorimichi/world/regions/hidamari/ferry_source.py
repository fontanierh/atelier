"""Hidamari's final harbour source: the audited rail opening, with its source identity checked before import."""
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify(base, records):
    if not records:
        raise ValueError('Hidamari ferry access proof is missing source identities')
    for relative, wanted in records.items():
        path = base / relative
        if not path.is_file() or sha(path) != wanted:
            raise ValueError(f'Hidamari ferry access source changed: {relative}')


def validated_harbor(build, repo):
    """@cc [owner:fontanierh,label:correctness] hidamari-ferry-package-source
    Refuse missing/failed cuts or changed cut code, base mesh, sweep proof and final bytes.

    The normal Hidamari importer is the sole writer of HD_Harbor. Reimporting the world MUST
    select this same validated opening; a later transport import MUST NOT patch the package.
    """
    build, repo = Path(build), Path(repo)
    target = build / 'hidamari/ferry/HD_Harbor.fbx'
    cut = json.loads((target.parent / 'cut.json').read_text())
    site_path = build / 'ferry/terminals/site.json'
    site = json.loads(site_path.read_text())
    if (cut.get('failures') != [] or not cut.get('cuts') or
            not all(c.get('cap_normals_pass') is True for c in cut['cuts']) or site.get('pass') is not True):
        raise ValueError('Hidamari ferry access cut or sweep failed')
    if cut.get('source') != 'hidamari/assets/HD_Harbor.fbx' or cut.get('site') != 'ferry/terminals/site.json':
        raise ValueError('Hidamari ferry access proof names a different source')
    paths = (repo / 'games/yorimichi/world/regions/hidamari/ferry_cut.py',
             build / cut['source'], site_path)
    expected = {str(p.relative_to(repo)) if p.is_relative_to(repo) else p.name: sha(p) for p in paths}
    if cut.get('inputs') != expected or not target.is_file() or sha(target) != cut.get('output_sha256'):
        raise ValueError('Hidamari ferry access cut inputs or final mesh changed')
    _verify(repo, site['inputs']['code'])
    probes = site['inputs'].get('world_probes')
    if not probes or set(probes) != {'hidamari', 'brinecove', 'crossing'}:
        raise ValueError('Hidamari ferry sweep is missing world probe identities')
    _verify(build / 'ferry/terminals', {f'world_{name}.npz': value for name, value in probes.items()})
    for records in site['inputs']['exports'].values():
        _verify(build, records)
    return target
