from pathlib import Path

import pytest

from atelier import build
from atelier.build_products import Product
from atelier.build_v2 import recipe_dependencies as rd


def _helper_module(tmp_path):
    (tmp_path / 'tools').mkdir(exist_ok=True)
    (tmp_path / 'tools' / 'helper.py').write_text('VALUE = 1\n')
    script = tmp_path / 'tools' / 'make.py'
    script.write_text('import helper\nprint(helper.VALUE)\n')
    return script


def _steps(tmp_path):
    script = _helper_module(tmp_path)
    out = tmp_path / 'build' / 'game'
    data = tmp_path / 'data.json'
    data.write_text('{}')
    (tmp_path / 'tools' / 'stagefn.py').write_text('CALLS = []\n\ndef stage(ctx, log):\n    CALLS.append(1)\n')
    import importlib.util
    spec = importlib.util.spec_from_file_location('stagefn_' + tmp_path.name, tmp_path / 'tools' / 'stagefn.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stage, calls = module.stage, module.CALLS

    producer = build.Step('a.make', [build.Python(script, ('--out', out / 'a.json'))], inputs=[data],
                          products=[Product('a.data', (out / 'a.json',))], outputs=[out / 'a.json'])
    consumer = build.Step('b.stage', [build.Call('b.stage', stage)], needs=['a.make'], reads=['a.data'],
                          after=['a.make'], optional_inputs=[tmp_path / 'maybe.json'], replan=True)
    blender = build.Step('c.export', [build.Blender(script, ('--piece', 'P1'), threads=3, factory_startup=True,
                                                    env=(('PYTHONHASHSEED', '0'),))])
    return [producer, consumer, blender], calls, out


def test_rows_have_exact_keys_relative_paths_and_resolved_reads(tmp_path):
    steps, calls, out = _steps(tmp_path)
    rows = rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')
    assert [tuple(r) for r in rows] == [rd.ROW_KEYS] * 3
    a, b, c = rows
    assert a['commands'][0] == {'kind': 'python', 'script': {'path': 'tools/make.py'},
                                'args': ['--out', {'path': 'build/game/a.json'}]}
    assert a['code'] == ['tools/helper.py', 'tools/make.py']
    assert a['inputs'] == [{'path': 'data.json', 'root': 'checkout', 'optional': False}]
    assert a['products'] == [{'id': 'a.data', 'paths': ['build/game/a.json'], 'optional_paths': []}]
    assert a['outputs'] == ['build/game/a.json']
    assert b['reads'] == [{'producer': 'a.make', 'product': 'a.data', 'paths': ['build/game/a.json']}]
    assert (b['needs'], b['after'], b['replan']) == (['a.make'], ['a.make'], True)
    assert b['inputs'] == [{'path': 'maybe.json', 'root': 'checkout', 'optional': True}]
    assert b['deferred'] == [] and b['references'] == []
    fn = b['commands'][0]['fn']
    assert fn['qualname'].endswith('stage') and not fn['source'].startswith('/')
    assert c['commands'][0]['threads'] == 3 and c['commands'][0]['env'] == [['PYTHONHASHSEED', '0']]
    assert calls == []  # Calls are described, never executed


def test_unknown_read_and_outside_paths_refuse(tmp_path):
    steps, _, _ = _steps(tmp_path)
    steps[1].reads = ['missing.product']
    with pytest.raises(rd.Unsupported, match='b.stage: read missing.product has no producer'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')
    steps, _, _ = _steps(tmp_path)
    steps[0].inputs = [Path('/etc/hosts')]  # not under a known portable root
    with pytest.raises(rd.Unsupported, match='outside the checkout'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')


def test_references_are_typed_and_unmodelled_queries_refuse(tmp_path):
    steps, _, _ = _steps(tmp_path)
    steps[1].references = ['a.data']
    row = rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')[1]
    assert row['references'] == [{'producer': 'a.make', 'product': 'a.data', 'paths': ['build/game/a.json']}]
    assert row['reads'] == [{'producer': 'a.make', 'product': 'a.data', 'paths': ['build/game/a.json']}]
    steps[1].queries = ['q']
    with pytest.raises(rd.Unsupported, match='b.stage'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')
    report = rd.coverage(steps, checkout=tmp_path, build_root=tmp_path / 'build')
    assert (report['steps'], report['extracted'], report['refused']) == (3, 2, 1)


def test_unknown_command_type_refuses(tmp_path):
    steps, _, _ = _steps(tmp_path)
    steps[2].commands = [object()]
    with pytest.raises(rd.Unsupported, match='c.export: unsupported command type object'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')


def test_duplicate_product_owner_refuses(tmp_path):
    steps, _, out = _steps(tmp_path)
    steps[2].products = [Product('a.data', (out / 'other.json',))]
    with pytest.raises(rd.Unsupported, match='two producers'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')


def test_retired_v1_cache_hooks_are_omitted_not_refused(tmp_path):
    steps, _, _ = _steps(tmp_path)
    steps[0].checkpoint_restore = lambda *a: None
    steps[0].candidate_scope = object()
    assert rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')[0]['id'] == 'a.make'


def test_unstable_closure_object_refuses(tmp_path):
    steps, _, _ = _steps(tmp_path)
    opaque = object()
    steps[1].commands = [build.Call('b.stage', lambda ctx, log: opaque)]
    with pytest.raises(rd.Unsupported, match='unsupported Call value of type object'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')


def test_exact_declared_export_format_survives_and_unknown_refuses(tmp_path):
    steps, _, _ = _steps(tmp_path)
    steps[0].export_format = 'glb'
    rows = rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')
    assert rows[0]['export_format'] == 'glb'
    assert rows[1]['export_format'] is None
    steps[0].export_format = 'png'
    with pytest.raises(rd.Unsupported, match='unsupported declared export format'):
        rd.extract(steps, checkout=tmp_path, build_root=tmp_path / 'build')
