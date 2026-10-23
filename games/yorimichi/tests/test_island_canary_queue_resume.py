"""A queue-only retry cannot adopt previous native output or erase refusal evidence."""
import ast
import json
import os
from pathlib import Path
import uuid

import pytest

from atelier.export_manifest import real_directory

SOURCE = Path(__file__).resolve().parent / 'native/island_atomic_canary.py'


def preflight():
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'preflight')
    scope = dict(os=os, json=json, uuid=uuid, real_directory=real_directory)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope['preflight']


def queued(tmp_path):
    root = tmp_path.resolve() / 'run'; guard = root / 'guard'; guard.mkdir(parents=True)
    value = dict(schema=1, invocation_id=uuid.uuid4().hex, admission_seconds=None,
                 child_lifetime_seconds=None, execution_seconds=None)
    path = guard / 'execution-timings.json'; path.write_text(json.dumps(value))
    return root, path, value


def test_exact_no_child_queue_metadata_is_preserved_without_adopting_any_outputs(tmp_path):
    root, timing, value = queued(tmp_path)
    before = timing.read_bytes()
    preflight()(root, resume_queued=True)
    assert timing.read_bytes() == before
    assert root.with_name(root.name + '-queued-' + value['invocation_id'] + '.json').read_bytes() == before
    assert {p.name for p in root.iterdir()} == {'guard'}


@pytest.mark.parametrize('kind', ['default', 'products', 'stdout', 'health', 'linked', 'admitted', 'executed'])
def test_previous_native_or_unknown_evidence_refuses_queue_resume(tmp_path, kind):
    root, timing, value = queued(tmp_path)
    if kind == 'products': (root / 'products').mkdir()
    elif kind == 'stdout': (root / 'guard/stdout.log').write_text('native output')
    elif kind == 'health': (root / 'guard/memory-health-tree.json').write_text('{}')
    elif kind == 'linked':
        old = root.parent / 'kept.json'; timing.rename(old); timing.symlink_to(old)
    elif kind == 'admitted': value['admission_seconds'] = 1.; timing.write_text(json.dumps(value))
    elif kind == 'executed': value['execution_seconds'] = 0.; timing.write_text(json.dumps(value))
    with pytest.raises(ValueError): preflight()(root, resume_queued=kind != 'default')
