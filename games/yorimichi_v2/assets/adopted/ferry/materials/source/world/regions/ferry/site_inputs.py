"""Complete source-bound sweep proof, usable before any final Harbor export."""
import json
import math
from pathlib import Path
import re

from atelier.atomic_files import atomic_json
from atelier.export_manifest import real_directory, sha
from atelier.model_files import member

PROBES = ('hidamari', 'brinecove', 'crossing')
SITE = 'ferry/terminals/site.json'


def path(root, relative, *, required=True):
    result = Path(root) / member(relative)
    real_directory(result.parent)
    if result.is_symlink() or (required and not result.is_file()):
        raise ValueError('Missing or linked ferry proof input: ' + relative)
    return result


def paths(build, repo):
    """Deferred complete membership after the ordinary sweep prerequisite completes."""
    build, repo = real_directory(build), real_directory(repo)
    site = path(build, SITE, required=False)
    result = {site, *(path(build, f'ferry/terminals/world_{key}.npz', required=False) for key in PROBES)}
    if not site.is_file():
        return sorted(result)
    value = json.loads(site.read_text())
    result.update(path(repo, key, required=False) for key in value['inputs']['code'])
    result.update(path(build, key, required=False) for rows in value['inputs']['exports'].values() for key in rows)
    return sorted(result)


def validate(build, repo):
    """@cc [owner:fontanierh,label:correctness] source-bound-ferry-site-before-cut
    Every final Harbor construction MUST validate successful sweep data against all
    recorded code, query/source products and all three exact world probes. Missing,
    changed, linked or escaping proof MUST fail before source mutation. Deferred
    declared membership MUST cover every file this validator reads. This proof
    validates the sweep; it MUST NOT claim that a downstream cut has succeeded.
    """
    site = path(build, SITE)
    value = json.loads(site.read_text())
    inputs = value.get('inputs', {})
    if (value.get('pass') is not True or set(inputs) != {'code', 'exports', 'world_probes'}
            or not isinstance(inputs['code'], dict) or not inputs['code']
            or not isinstance(inputs['exports'], dict) or set(inputs['exports']) != set(PROBES)
            or not isinstance(inputs['world_probes'], dict) or set(inputs['world_probes']) != set(PROBES)):
        raise ValueError('Incomplete or failed ferry sweep proof')
    records = [(path(repo, key), digest) for key, digest in inputs['code'].items()]
    for rows in inputs['exports'].values():
        if not isinstance(rows, dict) or not rows:
            raise ValueError('Missing ferry query/source proof')
        records.extend((path(build, key), digest) for key, digest in rows.items())
    records.extend((path(build, f'ferry/terminals/world_{key}.npz'), digest)
                   for key, digest in inputs['world_probes'].items())
    for source, wanted in records:
        if not isinstance(wanted, str) or not re.fullmatch('[0-9a-f]{64}', wanted) or sha(source) != wanted:
            raise ValueError('Ferry sweep input changed: ' + source.name)
    if set(paths(build, repo)) != {site, *(source for source, _ in records)}:
        raise ValueError('Ferry sweep proof membership differs')
    return value


def read_projection(value):
    """Read only the complete cut fields, without reopening sweep source/export files."""
    if (set(value) != {'schema', 'owner', 'stage', 'cuts'} or type(value['schema']) is not int
            or value['schema'] != 1 or value['owner'] != 'HD_Harbor' or value['stage'] != 'final'
            or not isinstance(value['cuts'], list) or not value['cuts']):
        raise ValueError('Incomplete final Harbor cut parameters')
    for cut in value['cuts']:
        if (not isinstance(cut, dict) or set(cut) != {'what', 'x', 'y', 'z_from'}
                or not isinstance(cut['what'], str) or not cut['what']
                or type(cut['z_from']) not in (int, float) or not math.isfinite(cut['z_from'])
                or any(not isinstance(cut[axis], list) or len(cut[axis]) != 2
                       or any(type(v) not in (int, float) or not math.isfinite(v) for v in cut[axis])
                       or cut[axis][0] >= cut[axis][1] for axis in ('x', 'y'))):
            raise ValueError('Invalid final Harbor cut geometry')
    return value['cuts']


def projection(build, repo):
    """Revalidate all proof before stopping proof-only changes at unchanged cut data."""
    site = validate(build, repo)
    value = dict(schema=1, owner='HD_Harbor', stage='final', cuts=site['hidamari']['berth']['world_cuts'])
    read_projection(value)
    return value


def record(build, repo, output, log):
    output = Path(output)
    real_directory(output.parent)
    if output.is_symlink() or (output.exists() and not output.is_file()):
        raise ValueError('Harbor cut projection requires a regular unlinked destination')
    value = projection(build, repo)
    if not output.exists() or output.read_text() != json.dumps(value, sort_keys=True) + '\n':
        atomic_json(output, value)
    log.write('Verified source-bound Harbor cut parameters\n')
