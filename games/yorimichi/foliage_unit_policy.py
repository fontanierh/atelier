"""One reviewed source-pair bridge for local partial foliage hints, never task success."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


WITNESS_SHA256 = '8471f5fa8ff16775419378dfc89edd1ffb568693f16b8b14503d6cd7d0e26f1a'
MAX_SOURCE = 8 * 1024 * 1024


def _member(root, name):
    if not isinstance(name, str): raise ValueError('Invalid policy source path')
    relative = PurePosixPath(name)
    if (relative.is_absolute() or str(relative) != name or not name or '\\' in name
            or any(part in ('.', '..') for part in relative.parts)):
        raise ValueError('Invalid policy source path')
    path = root.joinpath(*relative.parts)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Linked policy source')
    return path


def _source(path):
    if not path.is_file() or path.stat().st_size > MAX_SOURCE:
        raise ValueError('Missing or oversized policy source')
    return path.read_bytes()


def _calculate(root, witness, *, engine_version, environment, runtime):
    """Reproduce the historical concatenation only after every current pair pin matches."""
    if (not isinstance(witness, dict) or type(witness.get('schema')) is not int or witness['schema'] != 1
            or not isinstance(witness.get('current'), dict) or not 1 <= len(witness['current']) <= 64
            or not isinstance(witness.get('previous'), list) or not 1 <= len(witness['previous']) <= 64
            or not isinstance(engine_version, str) or not engine_version
            or not isinstance(environment, dict) or not isinstance(runtime, dict)
            or set(runtime) != {'platform', 'architecture', 'python'}
            or not all(isinstance(runtime[k], str) and runtime[k] for k in ('platform', 'architecture'))
            or not isinstance(runtime['python'], list) or len(runtime['python']) != 3
            or any(type(value) is not int or value < 0 for value in runtime['python'])):
        raise ValueError('Invalid legacy unit policy witness/context')
    for name, expected in witness['current'].items():
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid current source digest')
        if hashlib.sha256(_source(_member(root, name))).hexdigest() != expected:
            return None
    value = hashlib.sha256()
    for row in witness['previous']:
        if (not isinstance(row, dict) or set(row) != {'path', 'blob', 'sha256'}
                or not isinstance(row['blob'], str) or not re.fullmatch('[0-9a-f]{40}', row['blob'])
                or not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ValueError('Invalid historical source binding')
        _member(root, row['path'])
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), 'cat-file', 'blob', row['blob']],
                                capture_output=True, timeout=10, check=False)
        if (result.returncode or len(result.stdout) > MAX_SOURCE
                or hashlib.sha256(result.stdout).hexdigest() != row['sha256']):
            return None
        value.update(result.stdout)
    value.update(engine_version.encode())
    value.update(json.dumps(environment, sort_keys=True, allow_nan=False).encode())
    value.update(json.dumps(runtime, sort_keys=True, allow_nan=False).encode())
    return value.hexdigest()


def _transport(root):
    """The copied palette and source geometry body must remain byte-identical."""
    old = _source(_member(root, 'games/yorimichi/unreal/Source/YorimichiImport/FoliageBuilder.cpp')).decode()
    new = _source(_member(root, 'games/yorimichi/unreal/Source/Yorimichi/Dev/FoliageSourceWriter.cpp')).decode()
    start = 'TSharedPtr<FJsonValue> Number'
    palette = old.split(start, 1)[1].split('bool Read(', 1)[0].strip()
    copied = new.split(start, 1)[1].split('}\n#endif', 1)[0].strip()
    before = old.split('bool UYorimichiFoliageBuilder::ExportSource(', 1)[1].split('    FString Text;\n', 1)[0]
    after = new.split('bool UYorimichiFoliageSourceWriter::ExportSource(', 1)[1].split('    auto& Files=', 1)[0]
    return palette == copied and before == after.replace('#if WITH_EDITOR\n', '', 1)


def legacy_policy(game_root, *, engine_version, environment, runtime):
    """@cc [owner:fontanierh,label:correctness] reviewed-unit-transport-equivalence
    Only this immutable reviewed source pair MAY reproduce a historical unit policy.
    Every current source pin, ordered original Git source byte and current engine/runtime
    context MUST match; missing evidence MUST be a miss. Historical code MUST NOT execute.
    The result is a lookup hint, not a certificate: the caller MUST still validate current
    source identity, complete package bytes, native saved geometry, settings and materials.
    Successful receiving validation MAY rewrite only the local hint under the fresh policy.
    """
    try:
        game = Path(game_root).absolute()
        root = game.parents[1]
        payload = _source(_member(root, game.relative_to(root).as_posix()+'/foliage_unit_policy_witness.json'))
        if hashlib.sha256(payload).hexdigest() != WITNESS_SHA256:
            return None
        if not _transport(root):
            return None
        return _calculate(root, json.loads(payload), engine_version=engine_version,
                          environment=environment, runtime=runtime)
    except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError):
        return None
