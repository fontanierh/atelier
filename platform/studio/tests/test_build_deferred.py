"""Selected legacy membership uses fresh observations, without tools or native launches."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_inputs, build_plan, paths
from atelier.build import Call, DeferredInputs, Product, Step
from atelier.build_deferred import observe
from atelier.build_products import Graph


SUPPORT = Path(__file__)


def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file())


def imports(script):
    return build_inputs.local_imports(script)


def provider(root, **kwargs):
    return DeferredInputs('members', files, (root,), support=(SUPPORT,), **kwargs)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    out = tmp_path / 'build/standin'
    ctx = SimpleNamespace(game='standin', out=out, logs=out / 'logs', stamps=out / 'stamps')
    steps, calls = [], []
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    return SimpleNamespace(root=tmp_path, ctx=ctx, steps=steps, calls=calls,
                           run=lambda wanted=(): build.build('standin', wanted, echo=lambda message: None))


def test_unselected_provider_never_runs_and_graph_does_not_mutate_recipe(project):
    p = project
    def forbidden(root):
        pytest.fail('unselected membership enumerated')
    deferred = DeferredInputs('members', forbidden, (p.root,), support=(SUPPORT,))
    a = Step('slow', [], inputs=[SUPPORT], deferred_inputs=[deferred])
    b = Step('chosen', [])
    p.steps.extend([a, b])
    with pytest.raises(ValueError, match='explicit input observation'):
        build.required_inputs(a)
    for _ in range(2):
        assert Graph(p.steps).select(['chosen']) == [b]
    report = build_plan.inspect(p.ctx, p.steps, ['chosen'])
    assert [s['step'] for s in report['steps']] == ['chosen']
    assert not p.ctx.out.exists()
    assert p.run(['chosen']) == 0
    assert a.inputs == [SUPPORT] and a.deferred_inputs == [deferred]


def test_membership_empty_appearance_move_removal_and_support_code(project):
    root = project.root / 'inputs'; root.mkdir()
    code = project.root / 'support.py'; code.write_text('version = 1')
    declaration = replace(provider(root), support=(SUPPORT, code))
    step = Step('a', [], deferred_inputs=[declaration])
    empty = build.fingerprint(step, {})
    assert build.fingerprint(replace(step, deferred_inputs=[replace(declaration, name='other')]), {}) != empty
    sibling = project.root / 'other'; sibling.mkdir()
    assert build.fingerprint(replace(step, deferred_inputs=[replace(declaration, settings=(sibling,))]), {}) != empty
    item = root / 'a' / 'same.txt'; item.parent.mkdir(); item.write_text('content')
    appeared = build.fingerprint(step, {})
    assert appeared != empty
    moved = root / 'b' / item.name; moved.parent.mkdir(); item.rename(moved)
    assert build.fingerprint(step, {}) != appeared  # Equal basename/bytes still changes selected membership.
    moved.unlink()
    assert build.fingerprint(step, {}) == empty
    code.write_text('version = 2')
    assert build.fingerprint(step, {}) != empty


def test_one_observation_freezes_membership_but_next_observation_is_fresh(project):
    root = project.root / 'inputs'; root.mkdir()
    (root / 'a').write_text('a')
    step = Step('a', [], deferred_inputs=[provider(root)])
    observed = observe(step)
    old = build.fingerprint(step, {}, observation=observed)
    (root / 'b').write_text('b')
    assert build.fingerprint(step, {}, observation=observed) == old
    assert build.fingerprint(step, {}) != old
    assert step.inputs == [] and len(observed.members) == 1


def test_collector_implementation_choice_is_part_of_identity(project):
    def reverse(root):
        return list(reversed(files(root)))
    root = project.root / 'inputs'; root.mkdir()
    step = Step('a', [], deferred_inputs=[provider(root)])
    other = replace(step, deferred_inputs=[replace(provider(root), collect=reverse)])
    assert build.fingerprint(step, {}) != build.fingerprint(other, {})


def test_fresh_import_provider_discovers_added_helper(project):
    script = project.root / 'script.py'; script.write_text('import added_helper\n')
    step = Step('a', [], deferred_inputs=[DeferredInputs('imports', imports, (script,),
                support=(SUPPORT, Path(build_inputs.__file__)))])
    before = build.fingerprint(step, {})
    helper = project.root / 'added_helper.py'; helper.write_text('value = 1\n')
    after = build.fingerprint(step, {})
    assert after != before and helper in observe(step).members
    helper.unlink()
    assert build.fingerprint(step, {}) == before


def test_observe_after_prerequisites_and_plan_matches_next_normal_build(project):
    p = project
    members = p.root / 'generated'
    result = p.root / 'result.txt'
    def produce(ctx, log):
        p.calls.append('producer'); members.mkdir(); (members / 'new.txt').write_text('new')
    def consume(ctx, log):
        p.calls.append('consumer'); result.write_text((members / 'new.txt').read_text())
    a = Step('producer', [Call('produce', produce)], outputs=[members / 'new.txt'])
    b = Step('consumer', [Call('consume', consume)], deferred_inputs=[provider(members)],
             needs=['producer'], outputs=[result])
    p.steps.extend([a, b])
    assert p.run(['consumer']) == 0 and p.calls == ['producer', 'consumer']
    stamp = json.loads((p.ctx.stamps / 'consumer.json').read_text())
    assert stamp['input_state']['deferred_inputs']['members'] == ['<repo>/generated/new.txt']
    report = build_plan.inspect(p.ctx, p.steps, ['consumer'])
    assert [s['status'] for s in report['steps']] == ['current', 'current']
    p.calls.clear()
    assert p.run(['consumer']) == 0 and p.calls == []
    assert stamp == json.loads((p.ctx.stamps / 'consumer.json').read_text())


@pytest.mark.parametrize('mutation', ['add', 'remove', 'edit'])
def test_mid_command_membership_or_bytes_change_has_no_success_stamp(project, mutation):
    p = project
    members = p.root / 'members'; members.mkdir()
    item = members / 'a'; item.write_text('a')
    output = p.root / 'result'
    def mutate(ctx, log):
        if mutation == 'add': (members / 'b').write_text('b')
        if mutation == 'remove': item.unlink()
        if mutation == 'edit': item.write_text('edit')
        output.write_text('result')
    p.steps.append(Step('consumer', [Call('mutate', mutate)], outputs=[output],
                        deferred_inputs=[provider(members)]))
    assert p.run() == 1
    assert output.exists() and not (p.ctx.stamps / 'consumer.json').exists()


@pytest.mark.parametrize('field,value', [
    ('products', [Product('p', (Path('output'),))]), ('reads', ['p']), ('references', ['p']),
    ('cache', True), ('audit', True), ('batch', build.Batch('a')), ('pool_roots', [Path('pool')]),
    ('optional_inputs', [Path('optional')]), ('queries', [build.BBoxQuery('q', 'c', (0,0,0,1,1,1))]),
    ('toolchain', True),
])
def test_unsupported_actions_refuse_before_enumerating(field, value, tmp_path):
    def forbidden(root):
        pytest.fail('invalid declaration enumerated')
    step = Step('a', [], deferred_inputs=[DeferredInputs('a', forbidden, (tmp_path,), support=(SUPPORT,))])
    with pytest.raises(ValueError, match='require a legacy action'):
        Graph([replace(step, **{field: value})])


@pytest.mark.parametrize('change', ['duplicate', 'empty-support', 'wrong-support', 'mutable-settings', 'bad-result'])
def test_invalid_declarations_fail_clearly(tmp_path, change):
    p = provider(tmp_path)
    if change == 'empty-support': p = replace(p, support=())
    if change == 'wrong-support': p = replace(p, support=(tmp_path / 'other.py',))
    if change == 'mutable-settings': p = replace(p, settings=([tmp_path],))
    if change == 'bad-result':
        def wrong(root): return iter(())
        p = replace(p, collect=wrong)
    step = Step('a', [], deferred_inputs=[p, p] if change == 'duplicate' else [p])
    with pytest.raises(ValueError, match='deferred|Deferred'):
        build.fingerprint(step, {})


def test_plain_legacy_fingerprint_is_unchanged(project):
    source = project.root / 'source'; source.write_text('source')
    step = Step('legacy', ['command'], inputs=[source], needs=['a'], after=['order'])
    expected = hashlib.sha256(repr(step.commands).encode())
    build._hash_path(expected, source)
    expected.update(b'dependency')
    assert build.fingerprint(step, {'a': 'dependency', 'order': 'ignored'}) == expected.hexdigest()


def test_observation_metadata_is_portable_with_unicode_checkout_paths(tmp_path, monkeypatch):
    keys = []
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    for name in ('first é', 'second ü'):
        repo = tmp_path / name; repo.mkdir()
        source = repo / 'source'; source.mkdir(); (source / 'input').write_text('same')
        monkeypatch.setattr(paths, 'REPO', repo)
        keys.append(build.fingerprint(Step('a', [], deferred_inputs=[provider(source)]), {}))
    assert keys[0] == keys[1]


def test_deferred_host_support_is_identity_machinery_pinned_for_trusted_publication():
    from atelier import artifact_publisher, build_cache
    support = Path(build.__file__).with_name('build_deferred.py')
    step = Step('plain', [])
    stable = build_cache.tool_context(step, lambda path: 'stable')
    # Observation code computes identities; it never shapes outputs, so editing it keeps keys.
    assert build_cache.tool_context(step, lambda path: 'changed' if path == support else 'stable') == stable
    assert support in artifact_publisher.TOOL_SUPPORT
