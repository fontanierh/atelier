"""Reviewed source-pair bridges for local partial foliage hints, never task success."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


WITNESS_SHA256 = 'f6124fac22625bae23640a2c0580aad730716789411546721cd7f9e53b53aefa'
MAX_SOURCE = 8 * 1024 * 1024
USED_SLOT_PREPASS = '    // Imported meshes can retain unused seed-material slots. They still belong\n    // in the slot table, but no exported corner samples their palette.\n    TSet<int32> UsedSlots;\n    for (const FTriangleID Triangle : Description.Triangles().GetElementIDs())\n    {\n        const FName Name=SlotNames[Description.GetTrianglePolygonGroup(Triangle)];\n        int32 Used=Source->GetMaterialIndex(Name);\n        if (Used==INDEX_NONE)\n            for (int32 I=0;I<Source->GetStaticMaterials().Num();++I)\n                if (Source->GetStaticMaterials()[I].ImportedMaterialSlotName==Name) { Used=I;break; }\n        if (!Source->GetStaticMaterials().IsValidIndex(Used)) return false;\n        UsedSlots.Add(Used);\n    }\n'


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
        if (not isinstance(row, dict) or not isinstance(row.get('sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ValueError('Invalid historical source binding')
        if set(row) == {'path', 'blob', 'sha256'}:
            if not isinstance(row['blob'], str) or not re.fullmatch('[0-9a-f]{40}', row['blob']):
                raise ValueError('Invalid historical Git binding')
            _member(root, row['path'])
            result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), 'cat-file', 'blob', row['blob']],
                                    capture_output=True, timeout=10, check=False)
            if result.returncode:
                return None
            raw = result.stdout
        elif set(row) == {'module_record', 'sha256'} and isinstance(row['module_record'], str):
            # This exact retained compiled-module record is evidence, never an
            # instruction or a replacement for the current compiled identity.
            raw = row['module_record'].encode()
            record = json.loads(raw)
            if (not isinstance(record, dict) or set(record) != {'module', 'digest', 'files'}
                    or record['module'] != 'Yorimichi' or not isinstance(record['files'], dict)
                    or not isinstance(record['digest'], str) or not re.fullmatch('[0-9a-f]{64}', record['digest'])):
                raise ValueError('Invalid retained module record')
        else:
            raise ValueError('Invalid historical source binding')
        if len(raw) > MAX_SOURCE or hashlib.sha256(raw).hexdigest() != row['sha256']:
            return None
        value.update(raw)
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
    # The exact prepass skips palettes only for slots that no triangle uses.
    # Every emitted corner still resolves its slot and samples the same palette.
    if USED_SLOT_PREPASS in after:
        after = after.replace(USED_SLOT_PREPASS, '', 1)
        after = after.replace('UsedSlots.Contains(I) && (LeafSlots.Contains(I) || (Classification!=TEXT("material") && Classification!=TEXT("authored")))', '(LeafSlots.Contains(I) || (Classification!=TEXT("material") && Classification!=TEXT("authored")))', 1)
    return palette == copied and before == after.replace('#if WITH_EDITOR\n', '', 1)


def legacy_policies(game_root, *, engine_version, environment, runtime):
    """@cc [owner:fontanierh,label:correctness] reviewed-unit-transport-equivalence
    Only these immutable reviewed source pairs MAY reproduce historical unit policies.
    The reviewed startup upload drain/telemetry and CPU vertex-copy release MAY change
    only resource lifetime for owned prepared render-only variants in an uncooked game.
    The reviewed unused physics/navigation release MAY clear only variant-owned body
    and navigation allocations after refusing shared ownership or a pending cook; it
    MUST prevent later collision reconstruction and MUST NOT serialize or save packages.
    Original/shared collision, indices, GPU handles/counts and runtime query ownership MUST
    remain intact; geometry generation, snapshots and current source/settings/material
    admission MUST stay unchanged.
    Selected-mode loading and deferred unload/reload MAY change runtime residency only.
    The new separately owned compaction step MAY create distinct packages; it MUST NOT
    change the old preparation geometry or admit them as old source inputs. Excluding
    that derivative root from discovery MUST preserve the old source roster.
    The reviewed unused-slot prepass MAY avoid palette work only for slots referenced
    by no exported triangle; it MUST preserve every emitted corner/sample.
    Every current source pin, ordered original Git byte, exact retained compiled-module
    record and current engine/runtime context MUST match; missing evidence MUST miss.
    Historical code MUST NOT execute. Results are lookup hints, never certificates:
    the caller MUST still validate current source identity, complete package bytes,
    native saved geometry, settings and materials. Receiving success MAY rewrite only
    the local hint under the fresh policy. A changed transport MUST bind a fresh policy.
    """
    try:
        game = Path(game_root).absolute()
        root = game.parents[1]
        payload = _source(_member(root, game.relative_to(root).as_posix()+'/foliage_unit_policy_witness.json'))
        if hashlib.sha256(payload).hexdigest() != WITNESS_SHA256 or not _transport(root):
            return ()
        witness = json.loads(payload)
        if (not isinstance(witness, dict) or witness.get('schema') != 2
                or not isinstance(witness.get('policies'), list) or not 1 <= len(witness['policies']) <= 3):
            return ()
        values = []
        for previous in witness['policies']:
            value = _calculate(root, dict(schema=1,current=witness['current'],previous=previous),
                               engine_version=engine_version, environment=environment, runtime=runtime)
            if value and value not in values:
                values.append(value)
        return tuple(values)
    except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError):
        return ()


def legacy_policy(game_root, **context):
    """Compatibility for the former single-policy caller; all evidence checks still apply."""
    values = legacy_policies(game_root, **context)
    return values[0] if values else None
