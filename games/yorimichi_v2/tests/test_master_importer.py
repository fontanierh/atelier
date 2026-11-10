"""The material-master importer pilot: the hippodrome builders, the wiring digest and its comparer, the planner's states, and
the pin check. Nothing here runs Unreal: the builders run against a recording stand-in for the unreal module, and the digest
is compared as pure data. The native run is the editor's job, and its exact steps are in the pilot's report."""
import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

HD = planner.load_families()['hippodrome']

spec = importlib.util.spec_from_file_location('v2_hippodrome_masters', SCRIPTS / 'material_masters' / 'hippodrome_masters.py')
builders = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builders)

spec = importlib.util.spec_from_file_location('v2_master_digest', SCRIPTS / 'master_digest.py')
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)

spec = importlib.util.spec_from_file_location('v2_import_run_master', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)


# --- the builders, against a recording stand-in for unreal --------------------------------------------------------------

class Recorder:
    """Every attribute is a stand-in, and every call is logged as (method name, shown arguments). A call returns a stand-in,
    except the names given in `answers`."""

    def __init__(self, name, log, answers):
        self._name, self._log, self._answers = name, log, answers

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return Recorder(name, self._log, self._answers)

    def __call__(self, *args):
        self._log.append((self._name, tuple(show(a) for a in args)))
        return self._answers.get(self._name, Recorder(f'{self._name}()', self._log, self._answers))


def show(value):
    if isinstance(value, Recorder):
        return f'<{value._name}>'
    return repr(value)


def fake_unreal(log):
    return Recorder('unreal', log, {'does_asset_exist': False})


def trace(builder, *args, **kwargs):
    log = []
    original = builders.unreal
    builders.unreal = fake_unreal(log)
    try:
        builder(*args, **kwargs)
    finally:
        builders.unreal = original
    return log


def methods(log):
    return [name for name, _ in log]


TEXTURE_SURFACE = ['does_asset_exist', 'get_asset_tools', 'MaterialFactoryNew', 'create_asset', 'delete_all_material_expressions',
                   'set_editor_property', 'create_material_expression', 'set_editor_property', 'set_editor_property',
                   'connect_material_property',
                   'create_material_expression', 'set_editor_property', 'connect_material_property',
                   'create_material_expression', 'set_editor_property', 'connect_material_property',
                   'create_material_expression', 'set_editor_property', 'connect_material_property',
                   'layout_material_expressions', 'recompile_material']


def test_the_module_imports_without_the_editor_and_defines_the_builders():
    assert builders.unreal is None       # no editor here: the import has done no work and touched no engine
    for name in ('surface', 'structure_material'):
        assert callable(getattr(builders, name))


def test_each_pilot_master_arguments_bind_to_its_builder():
    for master in HD['masters']:
        builder = getattr(builders, master['builder'])
        inspect.signature(builder).bind(master['package'], {r: object() for r in master['reads']}, **master['arguments'])


def test_a_texture_surface_wires_as_the_donor_surface_does():
    log = trace(builders.surface, '/Game/Hippodrome/Materials/M_HD_Grass', {'/Game/Hippodrome/Textures/T_Grass': 'texture'},
                texture='/Game/Hippodrome/Textures/T_Grass', roughness=0.95, two_sided=False)
    assert methods(log) == TEXTURE_SURFACE
    two_sided = [args for name, args in log if name == 'set_editor_property' and args[0] == "'two_sided'"]
    assert two_sided == [("'two_sided'", 'False')]
    constants = [args for name, args in log if name == 'set_editor_property' and args[0] == "'r'"]
    assert constants == [("'r'", '0.95'), ("'r'", '0.0'), ("'r'", '0.3')]


def test_a_colour_surface_wires_its_constant_then_the_same_three_constants():
    log = trace(builders.surface, '/Game/Hippodrome/Materials/M_HD_Stone', {}, colour_r=0.36, colour_g=0.35, colour_b=0.32,
                roughness=0.9, two_sided=True)
    assert methods(log)[:9] == ['does_asset_exist', 'get_asset_tools', 'MaterialFactoryNew', 'create_asset',
                                'delete_all_material_expressions', 'set_editor_property', 'create_material_expression',
                                'LinearColor', 'set_editor_property']
    assert log[7] == ('LinearColor', ('0.36', '0.35', '0.32', '1.0'))
    assert methods(log)[-2:] == ['layout_material_expressions', 'recompile_material']


def test_a_surface_takes_a_texture_or_a_colour_and_refuses_both_or_neither():
    with pytest.raises(ValueError, match='exactly one'):
        builders.surface('/Game/Hippodrome/Materials/M_X', {}, roughness=.5, two_sided=False)
    with pytest.raises(ValueError, match='exactly one'):
        builders.surface('/Game/Hippodrome/Materials/M_X', {'t': 1}, roughness=.5, two_sided=False, texture='t', colour_r=1.)
    with pytest.raises(ValueError, match='colour_r, colour_g and colour_b'):
        builders.surface('/Game/Hippodrome/Materials/M_X', {}, roughness=.5, two_sided=False, colour_r=1.)


def test_the_structure_builder_wires_the_white_base_into_emissive_with_the_donor_constants():
    log = trace(builders.structure_material, '/Game/Hippodrome/Materials/M_HD_Structure',
                {'/Engine/EngineResources/WhiteSquareTexture': 'white'}, texture='/Engine/EngineResources/WhiteSquareTexture')
    assert methods(log) == ['does_asset_exist', 'get_asset_tools', 'MaterialFactoryNew', 'create_asset',
                            'delete_all_material_expressions',
                            'set_editor_property', 'create_material_expression', 'set_editor_property',
                            'set_editor_property', 'connect_material_property', 'create_material_expression',
                            'set_editor_property', 'connect_material_expressions', 'connect_material_property',
                            'create_material_expression', 'set_editor_property', 'connect_material_property',
                            'create_material_expression', 'set_editor_property', 'connect_material_property',
                            'recompile_material']
    assert ("'const_b'", '0.3') in [args for name, args in log if name == 'set_editor_property']
    assert ("'r'", '0.7') in [args for name, args in log if name == 'set_editor_property']
    assert ("'r'", '0.3') in [args for name, args in log if name == 'set_editor_property']


def test_no_builder_saves_its_material_the_importer_does():
    names = {name for master in HD['masters'] for name in [master['builder']]}
    for builder in names:
        log = trace(getattr(builders, builder), '/Game/Hippodrome/Materials/M_X', {'r': 'x'},
                    **({'texture': 'r'} if builder == 'structure_material' else {'roughness': .5, 'two_sided': False,
                                                                                  'colour_r': 1., 'colour_g': 1., 'colour_b': 1.}))
        assert 'save_loaded_asset' not in methods(log) and 'save_asset' not in methods(log)


# --- the wiring digest and its comparer, as pure data -------------------------------------------------------------------

def sample(connections=('A -> B.A',), props=(('two_sided', True),)):
    return {'settings': dict(props), 'expressions': ['{"class": "Constant", "props": {"r": 0.5}}',
                                                       '{"class": "Multiply", "props": {"const_b": 0.3}}'],
            'connections': list(connections), 'property_connections': ['MP_ROUGHNESS <- Constant.'],
            'topology': {'version': digest.TOPOLOGY_VERSION, 'roots': {'MP_ROUGHNESS': ['', 'fixture-root']}}}


def test_a_digest_is_accepted_against_itself_and_in_any_order():
    a = sample(connections=('X -> Y.A', 'P -> Q.B'))
    b = sample(connections=('P -> Q.B', 'X -> Y.A'))
    b['expressions'] = list(reversed(b['expressions']))
    assert digest.accept(a, b) == []


def test_a_different_connection_refuses_and_is_named():
    problems = digest.accept(sample(connections=('X -> Y.A',)), sample(connections=('X -> Y.B',)))
    assert any('connections only in the saved original: X -> Y.A' in p for p in problems)
    assert any('connections only in the rebuilt master: X -> Y.B' in p for p in problems)


def test_a_different_setting_refuses():
    problems = digest.accept(sample(props=(('two_sided', True),)), sample(props=(('two_sided', False),)))
    assert problems and problems[0].startswith('two_sided:')


def test_an_unreadable_digest_always_refuses():
    assert digest.accept({'error': "RuntimeError('x')"}, sample())
    assert digest.accept(sample(), {'error': 'boom'})


def test_a_missing_expression_refuses():
    a = sample()
    b = sample()
    b['expressions'] = b['expressions'][:1]
    assert any('expressions only in the saved original' in p for p in digest.accept(a, b))


def test_a_different_opacity_cutoff_refuses():
    """@cc [owner:fontanierh,label:correctness] master-digest-cutoff-compared
    A masked master whose saved cutoff differs from the rebuild's would change cutout edges if overwritten."""
    saved, rebuilt = sample(props=(('opacity_mask_clip_value', 0.333),)), sample(props=(('opacity_mask_clip_value', 0.5),))
    assert digest.accept(saved, rebuilt) == ['opacity_mask_clip_value: saved 0.333, rebuilt 0.5']
    assert digest.accept(rebuilt, sample(props=(('opacity_mask_clip_value', 0.5000001),))) == []


def test_the_digest_records_every_property_a_builder_writes():
    """@cc [owner:fontanierh,label:correctness] master-digest-covers-builders
    Each literal rendering property a material-master builder writes directly or through node/_node keywords is a digest
    setting or expression property. input_name is a Custom node input recorded through inputs; desc is editor metadata
    and does not affect appearance."""
    import ast
    written = set()
    for path in (SCRIPTS / 'material_masters').glob('*.py'):
        for call in ast.walk(ast.parse(path.read_text())):
            if not isinstance(call, ast.Call):
                continue
            if isinstance(call.func, ast.Attribute) and call.func.attr == 'set_editor_property' and call.args:
                name = call.args[0]
                if isinstance(name, ast.Constant) and isinstance(name.value, str):
                    written.add(name.value)
            elif isinstance(call.func, ast.Name) and call.func.id in {'node', '_node'}:
                written.update(keyword.arg for keyword in call.keywords if keyword.arg is not None)
    assert written - set(digest.SETTINGS) - set(digest.EXPRESSION_PROPERTIES) - {'input_name', 'desc'} == set()


def test_an_unwired_expression_of_the_saved_original_is_not_rebuilt_and_still_accepted():
    """@cc [owner:fontanierh,label:correctness] master-digest-unwired-not-compared
    An unwired non-parameter expression in the saved original MUST NOT reject an otherwise matching rebuild."""
    saved = sample()
    saved['unwired'] = ['{"class": "Constant", "props": {"r": 0.0}}']
    assert digest.accept(saved, sample()) == []


def test_a_parameter_only_on_an_unwired_expression_still_refuses():
    """@cc [owner:fontanierh,label:correctness] master-digest-parameters-compared
    A parameter present only in the saved original MUST reject a rebuild even when its expression is unwired."""
    param = '{"class": "TextureSampleParameter2D", "props": {"parameter_name": "Extra"}}'
    saved = sample()
    saved['unwired'], saved['parameters'] = [param], [param]
    problems = digest.accept(saved, sample())
    assert problems == [f'parameters only in the saved original: {param}']


def test_a_parameter_repeated_on_an_unwired_copy_is_one_parameter():
    param = '{"class": "TextureSampleParameter2D", "props": {"parameter_name": "BaseColorTexture"}}'
    saved, rebuilt = sample(), sample()
    saved['parameters'], rebuilt['parameters'] = [param, param], [param]
    assert digest.accept(saved, rebuilt) == []


def test_the_comparer_reads_two_reports_per_package(tmp_path):
    saved = {'/Game/Hippodrome/Materials/M_HD_Grass': {'wiring': sample()},
             '/Game/Hippodrome/Materials/M_HD_Dirt': {'wiring': sample(connections=('X -> Y.A',))}}
    rebuilt = {'/Game/Hippodrome/Materials/M_HD_Grass': {'wiring': sample()},
               '/Game/Hippodrome/Materials/M_HD_Dirt': {'wiring': sample(connections=('X -> Y.B',))}}
    result = digest.compare_reports(saved, rebuilt)
    assert result['/Game/Hippodrome/Materials/M_HD_Grass'] == []
    assert result['/Game/Hippodrome/Materials/M_HD_Dirt']
    rebuilt_missing = {'/Game/Hippodrome/Materials/M_HD_Grass': {'wiring': sample()}}
    assert digest.compare_reports(saved, rebuilt_missing)['/Game/Hippodrome/Materials/M_HD_Dirt'] == \
        ['missing from the rebuilt report']
    saved_file, rebuilt_file = tmp_path / 'saved.json', tmp_path / 'rebuilt.json'
    saved_file.write_text(json.dumps(saved))
    rebuilt_file.write_text(json.dumps(rebuilt))
    assert digest.main([str(saved_file), str(rebuilt_file)]) == 1
    assert digest.main([str(saved_file), str(saved_file)]) == 0


def test_the_report_names_the_wiring_digest_and_the_editor_reads_are_guarded():
    text = (SCRIPTS / 'report_masters.py').read_text()
    assert "row['wiring'] = master_digest.read(material)" in text
    assert digest.U is None   # outside the editor the digest module imports and its editor read is never reached


# --- the planner: unprepared, done, and half-moved ----------------------------------------------------------------------

def make_game(tmp_path, *, adopted=True, records_present=()):
    game = tmp_path / 'game'
    if adopted:   # the adopted record as it stood before the migration retired it from the real tree
        dest = game / 'assets' / HD['adopted']
        dest.mkdir(parents=True)
        outputs = ''.join(f'\n[[outputs]]\npackage = "{m["package"]}"\n' for m in HD['masters'])
        (dest / 'asset.toml').write_text(f'schema = 1\nid = "{HD["adopted"]}"\nkind = "adopted"\nauthority = "editor"\n'
                                         f'owner = "shared/hippodrome/materials"\nprovenance = "donor"\nlicense = "owner"\n'
                                         + outputs)
        (dest / 'verified.json').write_text('{}\n')
    for master in HD['masters']:
        if master['id'] in records_present:
            folder = game / 'assets' / master['id']
            (folder / 'src').mkdir(parents=True)
            (folder / 'src' / 'hippodrome_masters.py').write_bytes(planner.builder_path(HD).read_bytes())
            (folder / 'asset.toml').write_text(planner.record_text(HD, master, planner.builder_sha(HD)))
    return game


def apply_ops(game, ops):
    for rel, data in ops['writes'].items():
        path = game / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for rel in ops['deletes']:
        (game / rel).unlink()


def test_the_planner_is_unprepared_before_the_claim_and_plans_five_records(tmp_path):
    game = make_game(tmp_path)
    assert planner.state(game, HD) == 'unprepared'
    ops = planner.claim_ops(game, HD)
    assert len([p for p in ops['writes'] if p.endswith('asset.toml')]) == 5
    assert len([p for p in ops['writes'] if p.endswith('src/hippodrome_masters.py')]) == 5
    assert sorted(ops['deletes']) == [f'assets/{HD["adopted"]}/asset.toml', f'assets/{HD["adopted"]}/verified.json']


def test_the_planned_records_load_as_material_masters_and_name_their_pinned_builder(tmp_path):
    game = make_game(tmp_path)
    apply_ops(game, planner.claim_ops(game, HD))
    for master in HD['masters']:
        asset = records.load_asset(game / 'assets' / master['id'] / 'asset.toml')
        assert asset.kind == 'material-master' and asset.authority == 'generated'
        assert asset.recipe['settings']['builder'] == master['builder']
        assert [s.sha256 for s in asset.sources] == [planner.builder_sha(HD)]
        assert [o.package for o in asset.outputs] == [master['package']]
        owned = {dep: set(master['reads']) for dep in asset.input_dependencies}
        assert records.material_input_problems(asset, owned) == []
        assert sorted(asset.input_dependencies) == sorted(master['inputs'])


def test_the_planner_is_done_after_the_claim_and_then_writes_nothing(tmp_path):
    game = make_game(tmp_path)
    apply_ops(game, planner.claim_ops(game, HD))
    assert not (game / f'assets/{HD["adopted"]}/asset.toml').exists()
    assert planner.state(game, HD) == 'done'
    assert planner.claim_ops(game, HD) == {'writes': {}, 'deletes': []}


def referencing_record(game, slug, slot):
    folder = game / 'assets' / 'prop' / 'hippodrome' / slug
    folder.mkdir(parents=True)
    (folder / 'asset.toml').write_text(
        f'schema = 1\nid = "prop/hippodrome/{slug}"\nkind = "static-mesh"\nauthority = "generated"\n'
        f'owner = "shared/hippodrome/{slug}"\nprovenance = "donor"\nlicense = "owner"\n'
        f'references = ["{HD["adopted"]}", "texture/hippodrome/dirt"]\n\n'
        f'[[sources]]\npath = "src/x.glb"\nsha256 = "{"0" * 64}"\n\n'
        f'[recipe]\nimporter = "static-mesh"\nversion = 1\n\n[recipe.settings]\nslot_materials = ["{slot}"]\n\n'
        f'[[outputs]]\npackage = "/Game/Hippodrome/SM_{slug}"\n')
    return folder / 'asset.toml'


def test_the_claim_points_every_reference_at_the_masters_the_record_slots(tmp_path):
    """@cc [owner:fontanierh,label:correctness] master-records-no-dangling-reference
    Moving a family MUST replace references to its retired record with the slotted masters or declared fallback,
    preserve unrelated references, and leave a repeated move with no writes or deletions."""
    game = make_game(tmp_path)
    surface = referencing_record(game, 'lane', HD['masters'][2]['package'])
    loose = referencing_record(game, 'tower', '/Game/Hippodrome/Meshes/SM_HD_Tower/HD_Tower')
    apply_ops(game, planner.claim_ops(game, HD))
    assert records.load_asset(surface).references == ['master/hippodrome/dirt', 'texture/hippodrome/dirt']
    assert records.load_asset(loose).references == [HD['fallback'], 'texture/hippodrome/dirt']
    assert planner.claim_ops(game, HD) == {'writes': {}, 'deletes': []}


def test_a_half_moved_set_refuses_rather_than_extending(tmp_path):
    game = make_game(tmp_path, records_present=('master/hippodrome/grass',))
    with pytest.raises(planner.PlanError, match='half-moved'):
        planner.state(game, HD)


# --- the pin check: a builder that differs from its record is refused before any write ----------------------------------

def test_a_master_whose_builder_differs_from_its_pin_is_refused(tmp_path):
    game = make_game(tmp_path)
    apply_ops(game, planner.claim_ops(game, HD))
    folder = game / 'assets' / 'master/hippodrome/grass'
    asset = records.load_asset(folder / 'asset.toml')
    run.check_master_pins(asset)   # the pinned bytes pass
    (folder / 'src' / 'hippodrome_masters.py').write_text('# edited\n')
    with pytest.raises(run.ImportError_, match='differs from its pinned sha256'):
        run.check_master_pins(asset)


def test_the_runner_registers_the_material_master_importer_at_version_one():
    assert run.IMPORTERS['material-master'] == ('material-master', 1)


def test_an_engine_default_is_an_allowed_read_and_owns_nothing(tmp_path):
    text = planner.record_text(HD, HD['masters'][0], hashlib.sha256(b'x').hexdigest())
    path = tmp_path / 'asset.toml'
    path.write_text(text)
    asset = records.load_asset(path)
    assert records.material_master_reads(asset) == ['/Engine/EngineResources/WhiteSquareTexture']
    assert records.material_input_problems(asset, {}) == []


# --- the family registry --------------------------------------------------------------------------------------------------

def test_every_committed_master_record_is_what_its_family_plans():
    """@cc [owner:fontanierh,label:correctness] master-records-equal-plan
    Every committed master record and pinned builder MUST equal the current family plan and builder source."""
    for family in planner.load_families().values():
        for master in family['masters']:
            path = ROOT / 'assets' / master['id'] / 'asset.toml'
            if path.is_file():
                assert path.read_text() == planner.record_text(family, master, planner.builder_sha(family)), master['id']
                assert (path.parent / planner.builder_rel(family)).read_bytes() == planner.builder_path(family).read_bytes()


def test_an_adopted_record_that_owns_other_packages_too_refuses(tmp_path):
    game = make_game(tmp_path)
    toml = game / 'assets' / HD['adopted'] / 'asset.toml'
    toml.write_text(toml.read_text() + '\n[[outputs]]\npackage = "/Game/Hippodrome/Materials/MI_Other"\n')
    with pytest.raises(planner.PlanError, match='split it by hand'):
        planner.state(game, HD)


def test_a_family_names_its_builder_and_a_fallback_among_its_masters(tmp_path):
    folder = tmp_path / 'families'
    folder.mkdir()
    family = dict(HD, name='broken', fallback='master/elsewhere')
    (folder / 'broken.py').write_text(f'FAMILY = {family!r}\n')
    with pytest.raises(planner.PlanError, match='fallback'):
        planner.load_families(folder)


def test_custom_node_inputs_are_recorded_by_name_from_an_engine_array():
    """@cc [owner:fontanierh,label:correctness] master-digest-custom-inputs
    The engine hands Custom inputs over as an Array of CustomInput structs whose name is readable only through
    get_editor_property; the digest records the names, so a renamed or extra input refuses."""
    CustomInput = type('CustomInput', (), {'__init__': lambda self, n: setattr(self, 'n', n),
                                           'get_editor_property': lambda self, key: self.n})
    Array = type('Array', (list,), {})
    assert digest._value(Array([CustomInput('C'), CustomInput('D')])) == ['C', 'D']


def test_the_importer_clears_the_original_graph_and_saves_only_the_fresh_build():
    """@cc [owner:fontanierh,label:correctness] master-import-idempotent
    delete_all_material_expressions leaves unwired leftovers in 5.8, so a rebuild over them grows the package on every
    import. The importer deletes each expression, refuses unless the graph is empty, and refuses a save whose unwired
    expressions differ from the fresh build's."""
    text = (SCRIPTS / 'import_asset.py').read_text()
    body = text[text.index('def _material_master_with_builder('):]
    body = body[:body.index('\ndef ')]
    assert 'MEL.delete_material_expression(original, expression)' in body
    assert 'survive deletion; nothing saved' in body
    assert "back.get('unwired', [])) != sorted(fresh.get('unwired', []))" in body
    assert body.index('delete_material_expression') < body.index('builder(package, reads, **arguments)')
