"""Certified output deltas need no additional content reads or native commands."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from atelier import build, build_changes, build_products, cli
from atelier.build import Product, Step
from test_build_audit import action  # noqa: F401 - tiny isolated audited Python/cache fixture
from test_build_products import project  # noqa: F401 - tiny two-product/consumer fixture


def stamp(ctx, name):
    return json.loads((ctx.stamps / f'{name}.json').read_text())


def test_one_changed_product_reports_exact_members_without_rebuilding_other_consumers(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    p.add('generate', [(p.ctx.out / 'a.txt', source.read_text), (p.ctx.out / 'b.txt', 'same')], inputs=[source])
    p.add('consumer', [(p.ctx.out / 'used.txt', 'used')], reads=['generate.b'])
    assert p.run() == 0
    assert all(x['status'] == 'unknown' for x in stamp(p.ctx, 'generate')['output_changes']['products'])
    p.calls.clear(); source.write_text('two')
    assert p.run() == 0 and p.calls == ['generate']
    changes = stamp(p.ctx, 'generate')['output_changes']['products']
    assert changes[0]['changed'] == ['<build>/a.txt'] and changes[0]['unchanged'] == 0
    assert changes[1]['changed'] == [] and changes[1]['unchanged'] == 1
    assert changes[0]['added'] == changes[0]['retired'] == []
    unchanged = (p.ctx.stamps / 'generate.json').read_bytes()
    assert p.run() == 0 and (p.ctx.stamps / 'generate.json').read_bytes() == unchanged
    assert build.build('fixture', force=True, echo=lambda _: None) == 0
    assert all(x['changed'] == [] and x['unchanged'] == 1
               for x in stamp(p.ctx, 'generate')['output_changes']['products'])


def test_complete_inventory_diff_covers_directories_renames_sidecars_and_type_changes(tmp_path):
    bundle, sidecar = tmp_path / 'bundle', tmp_path / 'asset.sidecar'
    bundle.mkdir(); (bundle / 'empty').mkdir(); (bundle / 'rename').write_text('same')
    (bundle / 'replace').write_text('file')
    sidecar.write_text('one')
    step = Step('generate', [], products=[Product('asset', (bundle, sidecar))])
    roots = {'asset': ['<build>/bundle', '<build>/asset.sidecar']}
    previous = {'fingerprint': 'a' * 64, 'product_roots': roots, 'products': build_products.records(step)}
    (bundle / 'empty').rmdir(); (bundle / 'new-empty').mkdir()
    (bundle / 'rename').rename(bundle / 'renamed')
    (bundle / 'replace').unlink(); (bundle / 'replace').mkdir()
    sidecar.write_text('two')
    report = build_changes.compare(previous, build_products.records(step), roots)['products'][0]
    assert report['added'] == ['<build>/bundle/new-empty', '<build>/bundle/renamed']
    assert report['retired'] == ['<build>/bundle/empty', '<build>/bundle/rename']
    assert report['changed'] == ['<build>/bundle/replace', '<build>/asset.sidecar']
    assert report['unchanged'] == 1  # the bundle directory itself


def test_restore_reports_content_delta_and_repairs_are_not_reported_as_changes(action):
    a = action
    a.code('output.write_text(source.read_text())')
    assert a.run() == 0
    a.source.write_text('two'); assert a.run() == 0
    execution = a.stamp()['output_changes']
    a.source.write_text('input'); assert a.run() == 0
    restored = a.stamp()['output_changes']
    assert execution['action'] == 'execution' and restored['action'] == 'cache restore'
    assert execution['products'] == restored['products']
    assert restored['products'][0]['changed'] == ['<build>/result.txt']
    a.output.write_text('damage'); assert a.run() == 0
    assert a.stamp()['output_changes']['products'][0]['changed'] == []
    assert a.stamp()['output_changes']['products'][0]['unchanged'] == 1
    entry = json.loads(a.store.action(a.stamp()['fingerprint']).read_text())
    assert set(entry) == {'schema', 'key', 'products'}


@pytest.mark.parametrize('mutation', ['old-stamp', 'bad-inventory', 'bad-digest', 'bad-roots', 'moved', 'reordered', 'file-parent'])
def test_ambiguous_baselines_remain_unknown_without_touching_files(tmp_path, monkeypatch, mutation):
    one, two = tmp_path / 'one', tmp_path / 'two'
    one.write_text('one'); two.write_text('two')
    step = Step('step', [], products=[Product('asset', (one, two))])
    roots = {'asset': ['<build>/one', '<build>/two']}
    current = build_products.records(step)
    previous = json.loads(json.dumps({'fingerprint': 'a' * 64, 'products': current, 'product_roots': roots}))
    if mutation == 'old-stamp': previous.pop('product_roots')
    if mutation == 'bad-inventory': previous['products']['asset']['inventory']['files'] = []
    if mutation == 'bad-digest': previous['products']['asset']['digest'] = 'b' * 64
    if mutation == 'bad-roots': previous['product_roots']['asset'] = {'unexpected': 'mapping'}
    if mutation == 'moved': previous['product_roots']['asset'][0] = '<build>/other'
    if mutation == 'reordered': previous['product_roots']['asset'].reverse()
    if mutation == 'file-parent':
        record = previous['products']['asset']
        record['inventory']['files']['0/child'] = dict(record['inventory']['files']['0/.'])
        record['digest'] = build_products.identity(record['inventory'])
    def forbidden(*args, **kwargs):
        raise AssertionError('the diagnostic read product bytes')
    monkeypatch.setattr(Path, 'open', forbidden)
    item = build_changes.compare(previous, current, roots)['products'][0]
    assert item['status'] == 'unknown' and item['reason']
    assert not {'added', 'changed', 'retired', 'unchanged'} & item.keys()


def test_removed_product_is_retired_from_certification_without_deleting_it(project):
    p = project
    output = p.ctx.out / 'old.txt'
    step = p.add('generate', [(output, 'same')])
    assert p.run() == 0
    step.products = []
    assert p.run() == 0
    record = stamp(p.ctx, 'generate')
    assert record['product_roots'] == record['products'] == {}
    item = record['output_changes']['products'][0]
    assert item['declaration'] == 'retired' and item['retired'] == ['<build>/old.txt']
    assert output.read_text() == 'same'
    step.products = [Product('new', (output,))]
    assert p.run() == 0
    item = stamp(p.ctx, 'generate')['output_changes']['products'][0]
    assert item['declaration'] == 'added' and item['added'] == ['<build>/old.txt']


def test_native_named_outputs_use_generic_inventories(tmp_path):
    output = tmp_path / 'asset.uasset'; output.write_bytes(b'asset')
    step = Step('import', [], products=[Product('asset', (output,))])
    roots = {'asset': ['<repo>/unreal/Content/asset.uasset']}
    products = build_products.records(step)
    previous = {'fingerprint': 'a' * 64, 'products': products, 'product_roots': roots}
    assert build_changes.compare(previous, products, roots)['products'][0]['unchanged'] == 1


def test_optional_sidecar_appearance_removal_and_absence_are_exact_members(tmp_path):
    output, bulk = tmp_path / 'asset.uasset', tmp_path / 'asset.ubulk'
    output.write_bytes(b'asset')
    ctx = SimpleNamespace(out=tmp_path)
    step = Step('import', [], products=[Product('asset', (output,), optional_paths=(bulk,))])
    roots, optional = build_changes.root_labels(ctx, step), build_changes.optional_roots(step)
    assert roots == {'asset': ['<build>/asset.uasset', '<build>/asset.ubulk']}
    assert optional == {'asset': [1]}
    previous = {'fingerprint': 'a' * 64, 'products': build_products.records(step),
                'product_roots': roots, 'product_optional_roots': optional}
    for state, expected in (('present', 'added'), ('absent', 'retired'), ('absent', None)):
        if state == 'present':
            bulk.write_bytes(b'bulk')
        else:
            bulk.unlink(missing_ok=True)
        current = build_products.records(step)
        item = build_changes.compare(previous, current, roots, optional=optional)['products'][0]
        assert item['status'] == 'compared' and item['unchanged'] == 1
        for kind in ('added', 'retired', 'changed'):
            assert item[kind] == (['<build>/asset.ubulk'] if kind == expected else [])
        previous['products'] = current


@pytest.mark.parametrize('change', ['missing-role', 'required-absent', 'absent-child', 'moved', 'reordered', 'invalid-role'])
def test_optional_sidecar_metadata_cannot_hide_incomplete_or_moved_roots(tmp_path, change):
    output, bulk = tmp_path / 'asset.uasset', tmp_path / 'asset.ubulk'
    output.write_bytes(b'asset')
    step = Step('import', [], products=[Product('asset', (output,), optional_paths=(bulk,))])
    roots = {'asset': ['<build>/asset.uasset', '<build>/asset.ubulk']}
    optional = {'asset': [1]}
    current = build_products.records(step)
    previous = json.loads(json.dumps({'fingerprint': 'a' * 64, 'products': current,
                                     'product_roots': roots, 'product_optional_roots': optional}))
    if change == 'missing-role': previous.pop('product_optional_roots')
    if change == 'invalid-role': previous['product_optional_roots'] = {'asset': None}
    if change in ('required-absent', 'absent-child'):
        record = previous['products']['asset']
        record['inventory']['files']['0/.' if change == 'required-absent' else '1/child'] = {'kind': 'absent'}
        record['digest'] = build_products.identity(record['inventory'])
    if change == 'moved': previous['product_roots']['asset'][1] = '<build>/other.ubulk'
    if change == 'reordered': previous['product_roots']['asset'].reverse()
    item = build_changes.compare(previous, current, roots, optional=optional)['products'][0]
    assert item['status'] == 'unknown'


def test_failed_generation_publishes_no_change_receipt(action):
    a = action
    a.code('output.write_text(source.read_text())'); assert a.run() == 0
    a.code("output.write_text('partial')\nraise RuntimeError('failed')")
    assert a.run() == 1 and not (a.ctx.stamps / 'generate.json').exists()
    assert build_changes.inspect(a.ctx, a.steps)['steps'][0]['changes'] is None


def test_historical_view_is_read_only_and_copied_receipts_remain_historical(action, monkeypatch, capsys):
    a = action
    a.code('output.write_text(source.read_text())'); assert a.run() == 0
    a.source.write_text('two'); assert a.run() == 0
    path = a.ctx.stamps / 'generate.json'
    saved = a.stamp(); saved['reused_from'] = 'donor'; path.write_text(json.dumps(saved))
    before = path.read_bytes(), path.stat().st_mtime_ns
    a.output.unlink()
    def forbidden(*args, **kwargs):
        raise AssertionError('historical inspection performed build work')
    monkeypatch.setattr(build, 'fingerprint_state', forbidden)
    monkeypatch.setattr(build_products, 'records', forbidden)
    assert cli.main(['build', 'fixture', '--changes', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['historical'] and report['steps'][0]['copied']
    assert report['steps'][0]['changes'] == saved['output_changes']
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not a.output.exists()
    (a.ctx.stamps / 'generate.restore.json').write_text('{}')
    item = build_changes.inspect(a.ctx, a.steps)['steps'][0]
    assert item['reason'] == 'interrupted restoration' and item['changes'] is None


@pytest.mark.parametrize('flag', ['--timings', '--force', '--touch', '--plan', '--explain', '--verify', '--list'])
def test_cli_rejects_conflicting_change_report_flags(flag):
    with pytest.raises(SystemExit, match='--changes combines only'):
        cli.main(['build', 'sandbox', '--changes', flag])


def test_report_leaves_a_fresh_checkout_uncreated(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'out', stamps=tmp_path / 'out/stamps')
    def context(game, *, create):
        assert not create
        return ctx
    monkeypatch.setattr(build, 'Context', context)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [Step('world', [])]))
    assert build_changes.show('fixture', echo=lambda _: None) == 0
    assert not ctx.out.exists()


def test_sandbox_shows_a_small_edit_and_restoration(tmp_path, monkeypatch):
    from atelier import paths
    repo = tmp_path / 'checkout'; game = repo / 'games/sandbox'; game.mkdir(parents=True)
    shutil.copytree(paths.GAMES / 'sandbox/world', game / 'world', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(paths.GAMES / 'sandbox/build.py', game / 'build.py')
    shutil.copyfile(paths.REPO / 'uv.lock', repo / 'uv.lock')
    monkeypatch.setattr(paths, 'REPO', repo); monkeypatch.setattr(paths, 'GAMES', repo / 'games')
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    for name in ('ATELIER_BUILD_ROOT', 'ATELIER_PYTHON', 'PYTHONHOME', 'PYTHONPATH'):
        monkeypatch.delenv(name, raising=False)
    assert build.build('sandbox', ['world'], echo=lambda _: None) == 0
    ctx = build.Context('sandbox')
    placement = (ctx.stamps / 'world.placements.json').read_bytes()
    (game / 'world/block.json').write_text('{"size_cm":[800,400,200]}')
    assert build.build('sandbox', ['world'], echo=lambda _: None) == 0
    changes = stamp(ctx, 'world.block')['output_changes']['products']
    assert any(item['changed'] for item in changes)
    assert (ctx.stamps / 'world.placements.json').read_bytes() == placement
    record = stamp(ctx, 'world.block')
    root = next(iter(record['product_roots'].values()))[0].replace('<build>/', '')
    (ctx.out / root).unlink()
    assert build.build('sandbox', ['world'], echo=lambda _: None) == 0
    restored = stamp(ctx, 'world.block')['output_changes']
    assert restored['action'] == 'cache restore' and all(not item['changed'] for item in restored['products'])
