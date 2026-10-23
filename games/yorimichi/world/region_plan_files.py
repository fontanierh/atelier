"""Bounded ownership of a logical planner's flat generated payload directory."""
import json
from pathlib import Path
import stat

from atelier.atomic_files import atomic_json
from atelier.export_manifest import name, real_directory

PLAN = 'plan.json'
JOURNAL = '.plan-transaction.json'


def files(root):
    root = real_directory(root)
    if not root.exists():
        return set()
    result = set()
    for path in root.iterdir():
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Logical plans require flat regular unlinked members')
        result.add(path.name)
    return result


def payloads(parent, values):
    parent = name(parent)
    result = set()
    for value in values:
        if (not isinstance(value, str) or not value.endswith('.npz')
                or value != name(Path(value).stem) + '.npz'
                or not (value == parent + '.npz' or value.startswith(parent + '_cell_'))):
            raise ValueError('Foreign logical payload ownership')
        if value.casefold() in {v.casefold() for v in result}:
            raise ValueError('Duplicate logical payload ownership')
        result.add(value)
    if not result:
        raise ValueError('Logical payload ownership must be complete and nonempty')
    return result


def begin(root, parent, expected):
    """@cc [owner:fontanierh,label:correctness] planner-owned-retirement-preflight
    Refuse foreign files, directories and links before writing any payload. A previous
    complete plan or this owner's exact transaction journal MUST establish ownership
    of every preexisting payload. Interrupted writes MAY repair only those recorded
    members; a fresh nonempty unrecorded folder MUST NOT be adopted or erased.
    """
    root = real_directory(root)
    current = files(root)
    wanted = payloads(parent, expected)
    owned = set()
    if PLAN in current:
        previous = json.loads((root / PLAN).read_text())
        if previous.get('parent') != parent or previous.get('schema') != 1 or previous.get('complete') is not True:
            raise ValueError('Foreign previous logical plan')
        owned.update(payloads(parent, [row['payload'] for row in previous['pieces']]))
    if JOURNAL in current:
        journal = json.loads((root / JOURNAL).read_text())
        if set(journal) != {'schema', 'parent', 'payloads'} or journal['schema'] != 1 or journal['parent'] != parent:
            raise ValueError('Foreign logical planning transaction')
        owned.update(payloads(parent, journal['payloads']))
    if current - owned - {PLAN, JOURNAL}:
        raise ValueError('Foreign members in logical planning output')
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / JOURNAL, dict(schema=1, parent=parent, payloads=sorted(owned | wanted)))
    return wanted


def finish(root, value):
    root = real_directory(root)
    current = files(root)
    journal = json.loads((root / JOURNAL).read_text())
    parent = value['parent']
    if journal.get('schema') != 1 or journal.get('parent') != parent:
        raise ValueError('Foreign logical planning transaction')
    owned = payloads(parent, journal['payloads'])
    wanted = payloads(parent, [row['payload'] for row in value['pieces']])
    if not wanted <= current or not wanted <= owned or current - owned - {PLAN, JOURNAL}:
        raise ValueError('Logical planning ownership changed before publication')
    atomic_json(root / PLAN, value)
    for relative in sorted((current & owned) - wanted):
        (root / relative).unlink()
    (root / JOURNAL).unlink()
    if files(root) != wanted | {PLAN}:
        raise ValueError('Unexpected logical planning publication members')
