"""Parameter-collection records and their importer's rule: a generator-built collection names its builder and its pinned .py
generator, and a write is accepted only when it is exactly the generator's parameters with every saved id kept. Nothing
here runs Unreal: the comparer is pure data, and the native import is the editor's job."""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_collection_params', SCRIPTS / 'collection_params.py')
params = importlib.util.module_from_spec(spec)
spec.loader.exec_module(params)

spec = importlib.util.spec_from_file_location('v2_import_run_collection', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)

RECORD = ROOT / 'assets/material/seethrough/collection'
GENERATOR_SHA = hashlib.sha256(b'the pinned generator').hexdigest()


def collection_toml(*, authority='generated', importer='parameter-collection', version=1, settings='builder = "collection"\n'
                    'arguments = { create = true }\n', sources=None, outputs=('/Game/SeeThrough/MPC_SeeThrough',)):
    if sources is None:
        sources = f'[[sources]]\npath = "src/see_through.py"\nsha256 = "{GENERATOR_SHA}"\n'
    outs = ''.join(f'[[outputs]]\npackage = "{package}"\n' for package in outputs)
    recipe = f'[recipe]\nimporter = "{importer}"\nversion = {version}\n[recipe.settings]\n{settings}\n' \
        if authority == 'generated' else ''
    return (f'schema = 1\nid = "material/seethrough/collection"\nkind = "parameter-collection"\n'
            f'authority = "{authority}"\nowner = "shared/seethrough"\n{sources}{recipe}{outs}')


def load_text(tmp_path, text):
    path = tmp_path / 'asset.toml'
    path.write_text(text)
    return records.load_asset(path)


# --- the record ------------------------------------------------------------------------------------------------------

def test_the_kind_is_known_registered_and_in_the_published_schema():
    import json
    assert 'parameter-collection' in records.KINDS
    schema = json.loads((ROOT / 'schemas/asset.schema.json').read_text())
    assert 'parameter-collection' in schema['properties']['kind']['enum']
    assert run.IMPORTERS['parameter-collection'] == ('parameter-collection', 1)
    assert 'parameter-collection' in run.GENERATOR_BUILT


def test_a_well_formed_collection_loads(tmp_path):
    asset = load_text(tmp_path, collection_toml())
    assert asset.kind == 'parameter-collection' and asset.authority == 'generated'
    assert asset.recipe['settings'] == {'builder': 'collection', 'arguments': {'create': True}}


@pytest.mark.parametrize('kwargs, reason', [
    ({'authority': 'editor'}, 'generator-built'),
    ({'importer': 'material-master'}, 'importer "parameter-collection" version 1'),
    ({'version': 2}, 'importer "parameter-collection" version 1'),
    ({'sources': '[[sources]]\npath = "src/collection.json"\nsha256 = "' + GENERATOR_SHA + '"\n'}, '.py files'),
    ({'settings': 'builder = "Collection"\n'}, 'lower-case function name'),
    ({'settings': 'builder = "collection"\nreads = ["/Game/X"]\n'}, 'reads'),
    ({'settings': 'builder = "collection"\narguments = { names = ["a"] }\n'}, 'plain scalar'),
    ({'outputs': ('/Game/SeeThrough/SeeThrough',)}, 'MPC_<name>'),
    ({'outputs': ('/Game/SeeThrough/MPC_A', '/Game/SeeThrough/MPC_B')}, 'one output'),
])
def test_a_malformed_collection_is_refused(tmp_path, kwargs, reason):
    with pytest.raises(records.RecordError, match=reason):
        load_text(tmp_path, collection_toml(**kwargs))


def test_the_seethrough_record_pins_the_generator_records_see_through_py():
    asset = records.load_asset(RECORD / 'asset.toml')
    generator = records.load_asset(ROOT / 'assets/generator/seethrough/collection/asset.toml')
    pinned = {s.path: s.sha256 for s in generator.sources}
    assert [(s.path, s.sha256) for s in asset.sources] == [('src/see_through.py', pinned['src/see_through.py'])]
    assert records.sha256_file(RECORD / 'src/see_through.py') == asset.sources[0].sha256
    assert asset.references == ['generator/seethrough/collection']
    text = (RECORD / 'src/see_through.py').read_text()
    assert "MPC = FOLDER+'/MPC_SeeThrough'" in text and 'def collection(*, create=False):' in text
    for master in ('foliage', 'grass', 'painted'):
        reader = records.load_asset(ROOT / f'assets/master/japan/surfaces/{master}/asset.toml')
        assert 'material/seethrough/collection' in reader.input_dependencies
        assert '/Game/SeeThrough/MPC_SeeThrough' in records.material_master_reads(reader)


# --- the comparer ----------------------------------------------------------------------------------------------------

VECTORS = (('Focus', (0., 0., -100000., 90.)), ('Cut', (55., 35., 0., 0.)))
EXPECTED = params.expected_of(VECTORS)
FOCUS_ID, CUT_ID = '21734E426944BB49CF3452831CE175B1', '7C078CBCC34358843274E9875751DFBF'


def vector(name, default, ident):
    return {'name': name, 'default': [float(v) for v in default], 'id': ident}


def collection(*rows, scalars=()):
    return {'vectors': list(rows), 'scalars': list(scalars)}


def test_the_id_is_read_from_the_exported_struct_text():
    text = ('(DefaultValue=(R=0.000000,G=0.000000,B=-100000.000000,A=90.000000),ParameterName="Focus",'
            'Id=21734e426944bb49cf3452831ce175b1)')
    assert params.id_of_text(text) == FOCUS_ID
    with pytest.raises(RuntimeError):
        params.id_of_text('(ParameterName="Focus")')


def test_an_unchanged_collection_is_accepted():
    saved = collection(vector('Focus', VECTORS[0][1], FOCUS_ID), vector('Cut', VECTORS[1][1], CUT_ID))
    assert params.problems_before(EXPECTED, saved) == []
    assert params.accept(EXPECTED, saved, saved) == []


def test_a_new_collection_and_an_appended_parameter_are_accepted():
    built = collection(vector('Focus', VECTORS[0][1], FOCUS_ID), vector('Cut', VECTORS[1][1], CUT_ID))
    assert params.accept(EXPECTED, None, built) == []
    saved = collection(vector('Focus', VECTORS[0][1], FOCUS_ID))
    assert params.problems_before(EXPECTED, saved) == []
    assert params.accept(EXPECTED, saved, built) == []


def test_a_saved_collection_the_generator_cannot_make_is_refused_before_any_write():
    extra = collection(vector('Focus', VECTORS[0][1], FOCUS_ID), vector('Stray', (1, 1, 1, 1), CUT_ID))
    assert any('Stray' in p for p in params.problems_before(EXPECTED, extra))
    moved = collection(vector('Focus', (1, 0, 0, 0), FOCUS_ID))
    assert any('defaults to' in p for p in params.problems_before(EXPECTED, moved))
    twice = collection(vector('Focus', VECTORS[0][1], FOCUS_ID), vector('Focus', VECTORS[0][1], CUT_ID))
    assert any('listed 2 times' in p for p in params.problems_before(EXPECTED, twice))
    scalar = collection(scalars=[{'name': 'Strength', 'default': 1.0, 'id': CUT_ID}])
    assert any('scalar parameter Strength' in p for p in params.problems_before(EXPECTED, scalar))
    assert params.problems_before(EXPECTED, None) == []


def test_a_changed_id_a_missing_parameter_or_a_bad_id_refuses():
    saved = collection(vector('Focus', VECTORS[0][1], FOCUS_ID), vector('Cut', VECTORS[1][1], CUT_ID))
    renewed = collection(vector('Focus', VECTORS[0][1], 'A' * 32), vector('Cut', VECTORS[1][1], CUT_ID))
    assert any('changed id' in p for p in params.accept(EXPECTED, saved, renewed))
    short = collection(vector('Focus', VECTORS[0][1], FOCUS_ID))
    assert any('Cut is missing' in p for p in params.accept(EXPECTED, saved, short))
    zero = collection(vector('Focus', VECTORS[0][1], params.ZERO_ID), vector('Cut', VECTORS[1][1], CUT_ID))
    assert any('has no id' in p for p in params.accept(EXPECTED, None, zero))
    shared = collection(vector('Focus', VECTORS[0][1], CUT_ID), vector('Cut', VECTORS[1][1], CUT_ID))
    assert any('shares its id' in p for p in params.accept(EXPECTED, None, shared))


def test_the_seethrough_generator_parameters_are_the_ones_the_donor_collection_has():
    """The probe of the saved donor collection (11 vectors, no scalars) against the pinned VECTORS: names and defaults agree,
    so the import only re-saves and keeps every id."""
    text = (RECORD / 'src/see_through.py').read_text()
    start = text.index("TRAIL = (")
    names = {}
    exec(text[start:text.index('OPACITY =', start)], {}, names)
    expected = params.expected_of(names['VECTORS'])
    assert list(expected['vectors']) == ['Focus', 'Cut', 'Room', 'RoomSize', 'RoomShape', 'Trail0', 'Trail1', 'Trail2',
                                         'Trail3', 'Fade', 'Eye']
    assert expected['vectors']['Fade'] == [0.0, 30.0, 60.0, 250.0] and expected['scalars'] == {}


def test_the_importer_runs_the_pinned_builder_and_checks_before_and_after_the_write():
    source = (SCRIPTS / 'import_asset.py').read_text()
    body = source[source.index('def _parameter_collection(plan):'):source.index('def main():')]
    assert '_checked_master_sources(game, asset, plan)' in body
    assert body.index('problems_before') < body.index('builder(**') < body.index('save_asset') < body.index('accept(')
    assert "plan['importer'] == 'parameter-collection'" in source
