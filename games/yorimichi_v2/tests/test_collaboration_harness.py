"""Collaboration cases C01, C04 and C19 without Unreal: agents in their own Git worktrees, merged into main.

Each agent is a `git worktree` of one temporary repository holding a small games/yorimichi_v2. It works under a
claim in a fake claim service (scopes, exact locked paths, holder) and writes only through the real routes:
targeted import (`tools/import/run.py`, editor import stubbed), the build's editor-script authorization and
write check (`build.py`, editor stubbed) and save validation. Its branch lands on main only when the change-set
report passes against its claim; the content check must then be clean on main.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402
from claims_fake import REAL_RUN, ClaimService  # noqa: E402


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recipe = load('v2_harness_recipe', 'build.py')
run = load('v2_harness_import', 'tools/import/run.py')
sv = load('v2_harness_save_validate', 'tools/content/save_validate.py')
check = load('v2_harness_check', 'tools/content/check.py')
changeset = load('v2_harness_changeset', 'tools/review/changeset.py')
authority = recipe._authority()

ENGINE = '5.8.2-test'
EXTS = records.PACKAGE_EXTENSIONS + records.COMPANION_EXTENSIONS
ACTORS = 'unreal/Content/__ExternalActors__/Maps/Island'
BENCH, RAIL = 'unreal/Content/Props/SM_Bench.uasset', 'unreal/Content/Props/SM_Rail.uasset'
PAINT, SEA = 'unreal/Content/Materials/M_Painted.uasset', 'unreal/Content/Materials/M_Sea.uasset'
SKATE_ACTOR, HARBOUR_ACTOR = f'{ACTORS}/0/AB/BENCH01.uasset', f'{ACTORS}/1/EF/HARBOUR01.uasset'
NEW_ACTOR = f'{ACTORS}/3/CD/KIOSK01.uasset'
ENV = ('ATELIER_AGENT', 'ATELIER_CLAIMS_TASK', 'V2_EDITOR_CLAIM', 'V2_EDITOR_PATHS', 'V2_EDITOR_SCOPES',
       'V2_EDITOR_SCRIPT', 'V2_SAVE_ALLOW', 'V2_SAVE_DENY')
PROPS = {   # generated assets: package and input dependencies (C19: material/sea is the shared definition)
    'prop/bench': ('/Game/Props/SM_Bench', []),
    'prop/rail': ('/Game/Props/SM_Rail', []),
    'prop/buoy': ('/Game/Props/SM_Buoy', ['material/sea']),
    'prop/pier': ('/Game/Props/SM_Pier', ['material/sea']),
    'prop/pier-lod': ('/Game/Props/SM_PierLod', ['prop/pier']),
}


def git(root, *args, check=True):
    result = REAL_RUN(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com', '-c', 'commit.gpgsign=false',
                       '-c', 'core.hooksPath=/dev/null', *args], cwd=root, capture_output=True, text=True)
    assert not check or result.returncode == 0, result.stdout + result.stderr
    return result


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def locks(*rels):
    """The repository paths a claim locks for these game-relative packages: each with its companions."""
    return {f'games/yorimichi_v2/{rel.rsplit(".", 1)[0]}{ext}' for rel in rels for ext in EXTS}


def package_rel(package):
    return f'unreal/Content/{package[len("/Game/"):]}.uasset'


def importer(game, asset, plan_file):
    """The stubbed editor import: package bytes follow the sources and the dependencies' verified state."""
    by_id = {a.id: a for a in records.discover(game)[0]}
    inputs = [records.sha256_file(asset.folder / s.path) for s in asset.sources]
    inputs += [records.state_fingerprint(records.load_verified(by_id[d].verified)) for d in asset.input_dependencies]
    for package in json.loads(plan_file.read_text())['packages']:
        write(records.package_files(game, package)[0], f'{asset.id} {" ".join(inputs)}')


def quiet(*_):
    pass


class Agent:
    def __init__(self, team, name, task, base='main', root=None):
        self.team, self.name, self.task = team, name, task
        self.root, self.branch = root or team.tmp / name, f'{name}/{task}'
        self.game = self.root / 'games/yorimichi_v2'
        if root is None:
            git(team.main, 'worktree', 'add', '-q', '-b', self.branch, str(self.root), base)
            git_dir = Path(git(self.root, 'rev-parse', '--absolute-git-dir').stdout.strip())
            (git_dir / 'atelier-claims-task').write_text(task + '\n')    # `atelier claims use-task`

    def act(self):
        os.environ['ATELIER_AGENT'] = self.name

    def write(self, rel, data):
        write(self.game / rel, data)

    def import_(self, *ids):
        self.act()
        ordered, _ = run.plan(self.game, list(ids))
        done = []
        for asset in ordered:
            by_id = {a.id: a for a in records.discover(self.game)[0]}
            done.append(run.import_one(self.game, by_id[asset.id], by_id, engine=ENGINE, claim=self.task,
                                       importer=importer, echo=quiet))
        return done

    def editor_save(self, files, scopes=''):
        """One claimed editor script run through the build's guard, the editor's save stubbed by plain writes."""
        self.act()
        recipe.GAME = self.game
        os.environ.update(V2_EDITOR_CLAIM=self.task, V2_EDITOR_SCOPES=scopes,
                          V2_EDITOR_PATHS=' '.join(f'games/yorimichi_v2/{rel}' for rel in files))
        ctx = type('Ctx', (), {'out': self.team.tmp / 'out' / self.name})()
        try:
            recipe._authorize_editor(ctx, io.StringIO())
            for rel, data in files.items():
                self.write(rel, data)
            recipe._check_editor_writes(ctx, io.StringIO())
        finally:
            for name in ('V2_EDITOR_CLAIM', 'V2_EDITOR_SCOPES', 'V2_EDITOR_PATHS'):
                os.environ.pop(name, None)

    def validate(self, subject, add=()):
        self.act()
        return sv.validate(self.game, subject, claim=self.task, add=list(add), echo=quiet)

    def commit(self, message):
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '-m', message)

    def changed(self):
        return set(git(self.root, 'diff', '--name-only', 'main...HEAD').stdout.split())

    def report(self):
        return changeset.report(self.game, 'main...HEAD', scopes=self.team.claims.tasks[self.task]['scopes'])[0]


class Team:
    def __init__(self, tmp, claims):
        self.tmp, self.claims = tmp, claims
        self.main = tmp / 'main'
        self.game = self.main / 'games/yorimichi_v2'

    def agent(self, name, task, scopes=(), paths=(), base='main'):
        if task not in self.claims.tasks:
            self.claims.grant(task, name, scopes, locks(*paths))
        return Agent(self, name, task, base)

    def seed(self):
        """The base on main, written by a lead under one claim through the same routes."""
        game = self.game
        git(self.main.parent, 'init', '-q', '-b', 'main', str(self.main))
        write(self.main / '.gitignore', 'games/yorimichi_v2/unreal/Saved/\n')
        for asset_id, (package, deps) in PROPS.items():
            folder = game / 'assets/props' / asset_id.split('/')[1]
            write(folder / 'src/model.glb', f'{asset_id} v1')
            write(folder / 'asset.toml', f'''schema = 1
id = "{asset_id}"
kind = "static-mesh"
authority = "generated"
owner = "region/w04-skatepark"
input_dependencies = {json.dumps(deps)}
[[sources]]
path = "src/model.glb"
sha256 = "{records.sha256_file(folder / 'src/model.glb')}"
[recipe]
importer = "static-mesh"
version = 1
[[outputs]]
package = "{package}"
''')
        for name, rel in (('painted', PAINT), ('sea', SEA)):
            write(game / f'assets/materials/{name}/asset.toml', f'''schema = 1
id = "material/{name}"
kind = "material"
authority = "editor"
owner = "shared/material/{name}"
[[outputs]]
package = "/Game/{rel[len("unreal/Content/"):-len(".uasset")]}"
''')
            write(game / rel, f'material/{name} v1')
        for name, bounds, actor in (('w04-skatepark', [0, 0, 10000, 10000], SKATE_ACTOR),
                                    ('w05-harbour', [10000, 0, 20000, 10000], HARBOUR_ACTOR)):
            write(game / f'world/regions/{name}/region.toml', f'''schema = 1
id = "region/{name}"
bounds_cm = {json.dumps(bounds)}
neighbours = []
maps = ["/Game/Maps/Island"]
''')
            write(game / actor, f'{name} actor v1')
        lead = Agent(self, 'lead', 'T0', root=self.main)
        self.claims.grant('T0', 'lead', ['asset', 'region'],
                          locks(PAINT, SEA, SKATE_ACTOR, HARBOUR_ACTOR, *(package_rel(p) for p, _ in PROPS.values())))
        lead.validate('material/painted')
        lead.validate('material/sea')
        lead.validate('region/w04-skatepark', add=[SKATE_ACTOR])
        lead.validate('region/w05-harbour', add=[HARBOUR_ACTOR])
        assert lead.import_(*PROPS) == [True] * len(PROPS)
        git(self.main, 'add', '-A')
        git(self.main, 'commit', '-q', '-m', 'base')
        assert self.problems() == []

    def problems(self):
        return check.check(self.game, full=True)[0]

    def stale(self):
        found = self.problems()
        assert {p.code for p in found} <= {'STALE_IMPORT'}, found
        return {p.subject for p in found}

    def land(self, agent):
        """Merge an agent's branch into main once its change-set report passes; the content check on main after."""
        report = agent.report()
        assert report.problems == [], report.markdown('main', agent.branch)
        git(self.main, 'merge', '--no-ff', '--no-edit', agent.branch)     # a conflict fails here
        return self.problems()


@pytest.fixture
def team(tmp_path, monkeypatch):
    saved = {name: os.environ.pop(name, None) for name in ENV}
    claims = ClaimService()
    monkeypatch.setattr(subprocess, 'run', claims)
    monkeypatch.setattr(sv, 'engine_identity', lambda: ENGINE)
    monkeypatch.setattr(recipe, 'GAME', recipe.GAME)
    t = Team(tmp_path, claims)
    t.seed()
    yield t
    for name, value in saved.items():
        os.environ.pop(name, None)
        if value is not None:
            os.environ[name] = value


def test_c01_three_agents_on_one_machine_land_in_sequence(team):
    a = team.agent('agent-a', 'T1', ['asset/prop/bench'], [BENCH])
    b = team.agent('agent-b', 'T2', ['asset/material/painted'], [PAINT])
    c = team.agent('agent-c', 'T3', ['region/w04-skatepark'], [SKATE_ACTOR])
    a.write('assets/props/bench/src/model.glb', 'prop/bench v2')
    assert a.import_('prop/bench') == [True]
    b.editor_save({PAINT: 'material/painted v2'})
    assert b.validate('material/painted')
    with pytest.raises(authority.Unauthorized, match='does not exactly cover'):   # a new actor needs its lock first
        c.editor_save({NEW_ACTOR: 'kiosk'}, scopes='region/w04-skatepark')
    team.claims.extend('T3', locks(NEW_ACTOR))
    c.editor_save({NEW_ACTOR: 'kiosk', SKATE_ACTOR: 'w04-skatepark actor v2'}, scopes='region/w04-skatepark')
    assert c.validate('region/w04-skatepark', add=[NEW_ACTOR])
    for agent in (a, b, c):
        agent.commit(f'{agent.name}: claimed edit')
        assert check.check(agent.game, full=True)[0] == []
    touched = [agent.changed() for agent in (a, b, c)]
    assert all(touched) and not (touched[0] & touched[1] or touched[0] & touched[2] or touched[1] & touched[2])
    for agent in (a, b, c):
        assert team.land(agent) == []
    files = {**records.load_verified(team.game / 'assets/props/bench/verified.json')['files'],
             **records.load_verified(team.game / 'world/regions/w04-skatepark/actors.verified.json')['files']}
    assert NEW_ACTOR in files and BENCH in files
    assert (team.game / PAINT).read_text() == 'material/painted v2'


def test_c01_writes_outside_a_claim_are_refused(team):
    a = team.agent('agent-a', 'T1', ['asset/prop/bench'], [BENCH])
    c = team.agent('agent-c', 'T3', ['region/w04-skatepark'], [SKATE_ACTOR])
    with pytest.raises(authority.Unauthorized, match='no active scope covering asset/material/painted'):
        a.editor_save({PAINT: 'painted by the wrong agent'})
    assert (a.game / PAINT).read_text() == 'material/painted v1'
    a.write(PAINT, 'painted by the wrong agent')                       # saved outside any route
    with pytest.raises(sv.ValidationError, match='no active scope covering asset/material/painted'):
        a.validate('material/painted')
    c.write('assets/props/bench/src/model.glb', 'prop/bench by the region agent')
    # The region claim covers its own prop by scope (the record's owner), but holds no locks on its packages.
    with pytest.raises(run.ImportError_, match='does not exactly cover these paths'):
        c.import_('prop/bench')
    assert (c.game / BENCH).read_bytes() == (team.game / BENCH).read_bytes()
    with pytest.raises(sv.ValidationError, match='belongs to region/w05-harbour'):
        c.validate('region/w04-skatepark', add=[HARBOUR_ACTOR])
    os.environ['ATELIER_AGENT'] = authority.BOOTSTRAP_WRITER           # D04 does not apply inside a claimed checkout
    with pytest.raises(authority.Unauthorized, match="works under claims task 'T1'"):
        authority.authorize([f'games/yorimichi_v2/{BENCH}'], None, 'probe', repo=a.root)
    a.commit('agent-a: stray material edit')
    assert {'OUT_OF_SCOPE', 'PACKAGE_WITHOUT_RECORD'} <= {p.code for p in a.report().problems}
    assert {(p.code, p.subject) for p in check.check(a.game, full=True)[0]} == {('OUTPUT_CHANGED', 'material/painted')}


def test_c04_a_claimed_task_handed_to_another_agent(team):
    a = team.agent('agent-a', 'T4', ['asset/prop/rail'], [RAIL])
    a.write('assets/props/rail/src/model.glb', 'prop/rail v2, first pass')
    assert a.import_('prop/rail') == [True]
    a.commit('agent-a: rail first pass')
    b = team.agent('agent-b', 'T4', base=a.branch)                    # continues the preserved branch
    b.write('assets/props/rail/src/model.glb', 'prop/rail v3')
    with pytest.raises(run.ImportError_, match='does not exactly cover'):
        b.import_('prop/rail')
    team.claims.transfer('T4', 'agent-b')                              # coordinator `recover --action transfer`
    a.write('assets/props/rail/src/model.glb', 'prop/rail v3, still from agent-a')
    before = authority.content_snapshot(a.game)
    with pytest.raises(run.ImportError_, match='does not exactly cover'):
        a.import_('prop/rail')
    assert authority.content_snapshot(a.game) == before
    assert b.import_('prop/rail') == [True]
    b.commit('agent-b: rail finished')
    assert team.land(b) == []
    record = records.load_verified(team.game / 'assets/props/rail/verified.json')
    assert record['files'][RAIL] == records.sha256_file(team.game / RAIL)
    assert (team.game / 'assets/props/rail/src/model.glb').read_text() == 'prop/rail v3'
    assert git(team.main, 'merge-base', '--is-ancestor', a.branch, 'main').returncode == 0


def test_c19_a_shared_definition_update_makes_exactly_its_dependents_stale(team):
    unrelated = {rel: (team.game / rel).read_bytes() for rel in (
        'assets/props/bench/verified.json', 'assets/props/rail/verified.json', 'assets/materials/painted/verified.json',
        'world/regions/w04-skatepark/actors.verified.json', BENCH, RAIL, PAINT)}
    s = team.agent('agent-s', 'T5', ['asset/material/sea'], [SEA])
    s.editor_save({SEA: 'material/sea v2'})
    assert s.validate('material/sea')
    s.commit('agent-s: sea material v2')
    assert team.stale() == set()
    team.land(s)
    stale = team.stale()
    assert stale == {'prop/buoy', 'prop/pier'}                         # direct dependents, from the check
    assert [x.id for x in run.plan(team.game, sorted(stale))[0]] == ['prop/buoy', 'prop/pier', 'prop/pier-lod']
    assert [x.id for x in run.plan(team.game, ['prop/bench'])[0]] == ['prop/bench']
    d1 = team.agent('agent-d1', 'T6', ['asset/prop/buoy'], [package_rel(PROPS['prop/buoy'][0])])
    d2 = team.agent('agent-d2', 'T7', ['asset/prop/pier', 'asset/prop/pier-lod'],
                    [package_rel(PROPS['prop/pier'][0]), package_rel(PROPS['prop/pier-lod'][0])])
    with pytest.raises(run.ImportError_, match='no active scope covering asset/prop/pier'):
        d1.import_('prop/pier')
    assert d1.import_('prop/buoy') == [True]
    assert d2.import_('prop/pier') == [True, True]                     # the pier's new bytes make its LOD stale
    for agent in (d1, d2):
        agent.commit(f'{agent.name}: reimport against the new sea material')
    assert {p.subject for p in team.land(d1)} == {'prop/pier'}
    assert team.land(d2) == []
    assert {rel: (team.game / rel).read_bytes() for rel in unrelated} == unrelated
