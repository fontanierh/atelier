"""Cook declarations bind finished items, raw native records and sealed verification."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('v2_cook_units_test', ROOT / 'games/yorimichi/v2_cook_units.py')
cook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cook)


def ref(package, **kwargs):
    return {'unit': package + '.finish', 'item': 'asset', 'package': package, **kwargs}


def test_source_and_sealed_verifier_bind_exact_finished_transitive_items():
    rows = {'/Game/Maps/A': ref('/Game/Maps/A', dependencies=['/Game/M']),
            '/Game/M': ref('/Game/M', dependencies=['/Game/T'])}
    result = cook.author_units(rows, checkout=ROOT, dependencies=[ref('/Game/T')])
    producer, verifier = result['units'][2:]
    assert producer['params']['packages'] == ['/Game/Maps/A']
    assert {i['source']['unit'] for i in producer['inputs']} == {'/Game/Maps/A.finish', '/Game/M.finish', '/Game/T.finish'}
    assert producer['params']['recipe']['commands'] == []
    assert producer['params']['recipe']['verify'] is None
    assert any(p.endswith('Maps/A.umap') for p in producer['params']['recipe']['paths'])
    record, metadata = producer['outputs']
    assert record['class'] == 'NativeCookRecord' and record['files'][0]['path'].endswith('.cb')
    assert metadata['class'] == 'Data' and metadata['files'][0]['path'] == 'cook-root.tree.tar'
    assert verifier['inputs'][0]['source'] == {'kind': 'item', 'unit': producer['id'], 'item': 'record'}
    assert verifier['params'] == {'package': '/Game/Maps/A', 'mode': 'restore', 'settings': []}
    assert len(verifier['code']) == 9
    assert verifier['outputs'][0]['destination'] == 'external' and verifier['outputs'][0]['files'] == []
    assert 'source_key' not in repr(result)
    assert set(verifier['code']) - {cook.VERIFY} <= set(producer['code'])
    assert all((ROOT / name).is_file() for name in producer['code'])
    assert result['staged_inputs'][verifier['id']] == {'record': 'inputs/record'}


def test_package_ids_stable_independent_of_roster_and_order():
    a, b = ref('/Game/A'), ref('/Game/B')
    single = cook.author_units([a], checkout=ROOT)
    multiple = cook.author_units([b, a], checkout=ROOT)
    assert single['units'] == multiple['units'][:2]
    assert single['packages']['/Game/A'] == multiple['packages']['/Game/A']


@pytest.mark.parametrize('rows', [
    [{'package': '/Game/A', 'unit': 'x'}], [ref('/Game/../A')], [ref('/Game/A'), ref('/Game/A')],
    [ref('/Game/A', dependencies=['/Game/Missing'])],
    [ref('/Game/A', dependencies=['/Game/B']), ref('/Game/B', dependencies=['/Game/A'])],
])
def test_invalid_or_incomplete_native_owners_refuse(rows):
    with pytest.raises(ValueError):
        cook.author_units(rows, checkout=ROOT)


def test_recipe_runs_actual_prepare_and_raw_cb_tree_export_consumers(tmp_path):
    worker_spec = importlib.util.spec_from_file_location(
        'cook_declaration_native_worker', ROOT / cook.SCRIPT)
    worker = importlib.util.module_from_spec(worker_spec)
    worker_spec.loader.exec_module(worker)
    producer = cook.author_units([ref('/Game/A')], checkout=ROOT)['units'][0]
    recipe = producer['params']['recipe']
    assert [(row['kind'], row['required']) for row in recipe['outputs']] == [('file', True), ('tree', True)]
    # Inputs are optional sidecar paths until staged; prepare_view skips absent
    # paths using the real declared input-prefix contract.
    job = {**producer, 'code': [], 'inputs': [{'path': 'inputs/native_0'}]}
    (tmp_path / worker.recipe_job.RUNTIME).mkdir()
    view, protected, writes = worker.recipe_job.prepare_view(job, tmp_path)
    assert not protected
    record = recipe['outputs'][0]['path']
    (view / record).write_bytes(b'actual-raw-cb-transport')
    cooked = view / cook.COOK_ROOT
    cooked.mkdir()
    (cooked / 'ue.projectstore').write_bytes(b'cook-metadata')
    output = tmp_path / 'output'
    output.mkdir()
    def no_native_run(*args, **kwargs):
        raise AssertionError('declaration export must not run native tools')
    worker.export_outputs(recipe, view, output, no_native_run, raw_roots=(record,))
    assert (output / record).read_bytes() == b'actual-raw-cb-transport'
    restored = tmp_path / 'restored-cook'
    worker.recipe_job.unpack_root(output / 'cook-root.tree.tar', restored)
    assert (restored / 'ue.projectstore').read_bytes() == b'cook-metadata'
    assert set(writes) == {str(view / record), str(cooked)}
