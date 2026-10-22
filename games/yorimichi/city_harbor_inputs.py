"""Select the final audited Harbor without spreading proof-only rebuilds."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path


def _path(root, relative, *, must_exist=True):
    if not isinstance(relative, str):
        raise ValueError('Noncanonical Harbor proof path')
    part = Path(relative)
    if (part.is_absolute() or part.as_posix() != relative
            or '..' in part.parts or '\\' in relative):
        raise ValueError('Noncanonical Harbor proof path')
    path = Path(root)/part
    if any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents)):
        raise ValueError('Linked Harbor proof path')
    if must_exist and not path.is_file():
        raise ValueError('Missing Harbor proof input: '+relative)
    return path


def paths(out, repo):
    """Every file the final-source validator actually reads, plus raw metadata."""
    out, repo = Path(out), Path(repo)
    found = {_path(out, name, must_exist=False) for name in ('hidamari/manifest.json', 'hidamari/assets/HD_Harbor.fbx',
        'hidamari/ferry/HD_Harbor.fbx', 'hidamari/ferry/cut.json', 'ferry/terminals/site.json')}
    found.add(_path(repo, 'games/yorimichi/world/regions/hidamari/ferry_cut.py', must_exist=False))
    found.add(_path(repo, 'games/yorimichi/world/regions/hidamari/ferry_source.py', must_exist=False))
    site_path = out/'ferry/terminals/site.json'
    if not site_path.is_file():
        return sorted(found)  # deferred membership is resolved again after prerequisites
    site = json.loads(site_path.read_text())
    inputs = site['inputs']
    found.update(_path(repo, name, must_exist=False) for name in inputs['code'])
    found.update(_path(out, name, must_exist=False) for records in inputs['exports'].values() for name in records)
    found.update(_path(out, 'ferry/terminals/world_'+name+'.npz', must_exist=False) for name in inputs['world_probes'])
    return sorted(found)


def snapshot(out, repo):
    """@cc [owner:fontanierh,label:correctness;performance] harbor-final-source-cutoff
    The selector MUST validate the complete current ferry cut/site/probe/code/export
    proof before publishing consumed final geometry metadata. Stale or missing proof
    MUST fail. Successfully revalidated proof-only changes MUST leave the selected
    final bytes/counts/bounds/collision projection unchanged. Raw Harbor MUST NOT be
    selected in place of the validated final opening.
    """
    out, repo = Path(out), Path(repo)
    if any(not path.is_file() for path in paths(out, repo)):
        raise ValueError('Missing Harbor proof input')
    helper = _path(repo, 'games/yorimichi/world/regions/hidamari/ferry_source.py')
    spec = importlib.util.spec_from_file_location('city_final_harbor_source', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    final = module.validated_harbor(out, repo)
    raw = json.loads((out/'hidamari/manifest.json').read_text())['HD_Harbor']
    cut = json.loads((out/'hidamari/ferry/cut.json').read_text())
    counts = cut['triangles']
    if (type(raw['triangles']) is not int or raw['triangles'] < 1
            or type(counts['before']) is not int or counts['before'] != raw['triangles']
            or type(counts['after']) is not int or counts['after'] < 1
            or type(raw['collision_boxes']) is not int or raw['collision_boxes'] != 0
            or type(raw['materials']) is not int or raw['materials'] != 1
            or cut.get('untouched_outside_cuts') is not True):
        raise ValueError('Invalid final Harbor geometry metadata')
    if (any(not isinstance(raw[key], list) or len(raw[key]) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in raw[key])
            for key in ('min', 'max'))
            or any(a > b for a, b in zip(raw['min'], raw['max']))):
        raise ValueError('Invalid final Harbor bounds')
    # The splitter checks these unchanged outside-cut extremes against the
    # actual final FBX; this projection never substitutes raw triangle counts.
    return dict(source='HD_Harbor', source_path=str(final.relative_to(out)),
                source_sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                triangles=counts['after'], min=raw['min'], max=raw['max'], collision_boxes=0)
