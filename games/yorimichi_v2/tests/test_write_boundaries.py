"""Every build step that writes packages authorizes at its own boundary and checks what it wrote."""
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recipe = load('v2_build_recipe', 'build.py')
authority = recipe._authority()


@pytest.fixture
def writer(monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', authority.BOOTSTRAP_WRITER)
    monkeypatch.delenv('ATELIER_CLAIMS_TASK', raising=False)
    for name in ('V2_EDITOR_CLAIM', 'V2_EDITOR_PATHS', 'V2_SAVE_ALLOW'):
        monkeypatch.delenv(name, raising=False)
    yield
    os.environ.pop('V2_SAVE_ALLOW', None)   # set by the code under test, not by monkeypatch


def test_a_directly_selected_import_rechecks_its_plan(tmp_path, monkeypatch, writer):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'asset': 'prop/bench', 'claim': None, 'packages': ['/Game/Props/SM_Bench'],
                                'write_paths': []}))
    monkeypatch.setenv('V2_IMPORT_PLAN', str(plan))
    recipe._authorize_import(None, io.StringIO())
    allowed = Path(os.environ['V2_SAVE_ALLOW']).read_text().split()
    assert any(a.endswith('games/yorimichi_v2/unreal/Content/Props/SM_Bench.uasset') for a in allowed)
    seen = []
    monkeypatch.setattr(authority.subprocess, 'run', lambda command, **_: seen.append(command)
                        or type('R', (), {'returncode': 1})())
    plan.write_text(json.dumps({'asset': 'prop/bench', 'claim': 'T3', 'packages': ['/Game/Props/SM_Bench'],
                                'write_paths': []}))
    with pytest.raises(authority.Unauthorized, match='does not exactly cover'):
        recipe._authorize_import(None, io.StringIO())
    assert 'games/yorimichi_v2/unreal/Content/Props/SM_Bench.uasset' in seen[0]   # derived, not trusted
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    plan.write_text(json.dumps({'asset': 'prop/bench', 'claim': None, 'packages': ['/Game/Props/SM_Bench']}))
    with pytest.raises(authority.Unauthorized, match='not the bootstrap writer'):
        recipe._authorize_import(None, io.StringIO())


def test_migration_is_bootstrap_only(monkeypatch, writer):
    recipe._authorize_migration(None, io.StringIO())
    monkeypatch.setenv('ATELIER_AGENT', 'someone-else')
    with pytest.raises(authority.Unauthorized):
        recipe._authorize_migration(None, io.StringIO())


def test_a_claimed_editor_script_must_stay_inside_its_paths(tmp_path, monkeypatch, writer):
    game = tmp_path / 'game'
    (game / 'unreal/Content/V2').mkdir(parents=True)
    monkeypatch.setattr(recipe, 'GAME', game)
    monkeypatch.setattr(authority.subprocess, 'run', lambda command, **_: type('R', (), {'returncode': 0})())
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    monkeypatch.setenv('V2_EDITOR_PATHS', 'games/yorimichi_v2/unreal/Content/V2/A.uasset')
    ctx = type('Ctx', (), {'out': tmp_path / 'out'})()
    recipe._authorize_editor(ctx, io.StringIO())
    assert Path(os.environ['V2_SAVE_ALLOW']).read_text().strip().endswith('games/yorimichi_v2/unreal/Content/V2/A.uasset')
    (game / 'unreal/Content/V2/A.uasset').write_bytes(b'a')
    log = io.StringIO()
    recipe._check_editor_writes(None, log)
    assert 'wrote games/yorimichi_v2/unreal/Content/V2/A.uasset' in log.getvalue()
    recipe._authorize_editor(ctx, io.StringIO())
    (game / 'unreal/Content/V2/B.uasset').write_bytes(b'b')
    with pytest.raises(RuntimeError, match='outside its claimed paths: games/yorimichi_v2/unreal/Content/V2/B.uasset'):
        recipe._check_editor_writes(None, io.StringIO())


def test_a_claimed_editor_script_must_declare_its_paths(monkeypatch, writer):
    monkeypatch.setenv('V2_EDITOR_CLAIM', 'T9')
    with pytest.raises(RuntimeError, match='needs V2_EDITOR_PATHS'):
        recipe._authorize_editor(None, io.StringIO())


def test_a_claim_must_name_its_paths(writer):
    with pytest.raises(authority.Unauthorized, match='must name the paths'):
        authority.authorize([], 'T1', 'probe')
