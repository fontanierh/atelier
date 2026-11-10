"""The fxretail masters: the FX sprite and trail, the racing TV and the Mega Park retail parents (families fx, racing, megapark).

Nothing here runs Unreal. Each builder runs against a recording stand-in for the unreal module, and its call trace is compared
with the same donor code run against the same stand-in: the donor's functions and module bodies are read from the original game at
the V2 source baseline (git blob pins below), so the comparison is the donor's own graph, not a retyped copy of it. The megapark
donor is also committed in adopted/megapark/base-materials/source, which the megapark comparison reads. A clone without the donor
commit skips only the donor comparisons; the pins and the planner checks always run.
"""
import hashlib
import tomllib
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'unreal/Scripts'
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import master_records as planner  # noqa: E402

DONOR_COMMIT = '7eec0f98dd'
DONOR_PINS = {   # sha256 of the whole donor blob at DONOR_COMMIT (docs/inventory/master-sources.md)
    'import_combat_fx.py': 'bf9820e1db843baee6fc4454ecc6ca4da1aec637efe67a8fefcba57923fd1c7d',
    'racing_tv_material.py': 'ea890e75e712104451256f62acaae1bb304b2fd577d350d3a6bb5a223dc00344',
    'import_megapark.py': 'ac0c1df05fd3ff3b48862ad68a07c28189afb7fc3663652f7020a33106f80a7a',
}
COMMITTED_MEGAPARK = ROOT / 'assets/adopted/megapark/base-materials/source/unreal/Scripts/import_megapark.py'

FAMILIES = planner.load_families()
FX, RACING, MEGAPARK = FAMILIES['fx'], FAMILIES['racing'], FAMILIES['megapark']


def load_builder(family):
    spec = importlib.util.spec_from_file_location(f'v2_{family["name"]}_masters', SCRIPTS / 'material_masters' / family['builder'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDERS = {family['name']: load_builder(family) for family in (FX, RACING, MEGAPARK)}


# --- a recording stand-in for unreal -----------------------------------------------------------------------------------

class Recorder:
    """Every attribute is a stand-in with a stable identity (so `==` between two reads of one attribute holds), and every call
    is logged as (leaf name, shown arguments). A call returns the stand-in named in `answers`, or a fresh one."""

    def __init__(self, name, log, answers):
        self._name, self._log, self._answers, self._children = name, log, answers, {}

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name not in self._children:
            self._children[name] = Recorder(name, self._log, self._answers)
        return self._children[name]

    def __call__(self, *args):
        self._log.append((self._name, tuple(show(a) for a in args)))
        return self._answers.get(self._name, Recorder(f'{self._name}()', self._log, self._answers))


def show(value):
    if isinstance(value, Recorder):
        return f'<{value._name}>'
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(show(v) for v in value) + ']'
    return repr(value)


def fresh(answers=None):
    log = []
    return log, Recorder('unreal', log, dict({'does_asset_exist': False}, **(answers or {})))


def normalise(log):
    """The graph's calls: from the first delete_all_material_expressions on, without loads, logs, directory makes and saves. The
    donor's and the builder's set-up differ only in how they create or reuse the asset, which this drops; every expression, setting,
    connection and value after it must match."""
    entries = [e for e in log if e[0] not in ('load_asset', 'log', 'make_directory', 'save_loaded_asset', 'save_asset')]
    start = next(i for i, (name, _) in enumerate(entries) if name == 'delete_all_material_expressions')
    return entries[start:]


def donor_source(name, first=None, last=None):
    """The donor file's text at DONOR_COMMIT (git), or its committed copy for megapark; the whole file, or lines first..last."""
    if name == 'import_megapark.py':
        data = COMMITTED_MEGAPARK.read_bytes()
    else:
        try:
            data = subprocess.run(['git', 'show', f'{DONOR_COMMIT}:games/yorimichi/unreal/Scripts/{name}'], cwd=ROOT,
                                  capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            pytest.skip(f'the donor {name} at {DONOR_COMMIT} is not in this clone')
    assert hashlib.sha256(data).hexdigest() == DONOR_PINS[name], f'{name} is not the pinned donor blob'
    lines = data.decode().split('\n')
    return '\n'.join(lines if first is None else lines[first - 1:last])


# --- the donor, run against the same stand-in ---------------------------------------------------------------------------

def run_fx_donor(name, blend, texture_name):
    """import_combat_fx.py: material() and node() (lines 37-49), sprite_material (52-69). Returns (trace, material)."""
    log, U = fresh()
    ns = {'U': U, 'E': U.EditorAssetLibrary, 'AT': U.AssetToolsHelpers.get_asset_tools(), 'M': U.MaterialEditingLibrary,
          'DEST': '/Game/FX', 'textures': {'Glow': Recorder('T_FX_Glow', log, U._answers),
                                           'Dust': Recorder('T_FX_Dust', log, U._answers)}}
    exec(compile(donor_source('import_combat_fx.py', 37, 49) + '\n' + donor_source('import_combat_fx.py', 52, 69),
                 'import_combat_fx.py', 'exec'), ns)
    blend_value = U.BlendMode.BLEND_ADDITIVE if blend == 'additive' else U.BlendMode.BLEND_TRANSLUCENT
    mat = ns['sprite_material'](name, blend_value, ns['textures'][texture_name])
    return normalise(log), mat


def run_fx_trail_donor():
    """import_combat_fx.py lines 87-96: the trail, a module body run on the same material() and node() helpers."""
    log, U = fresh()
    ns = {'U': U, 'E': U.EditorAssetLibrary, 'AT': U.AssetToolsHelpers.get_asset_tools(), 'M': U.MaterialEditingLibrary,
          'DEST': '/Game/FX', 'textures': {'Trail': Recorder('T_FX_Trail', log, U._answers)}}
    exec(compile(donor_source('import_combat_fx.py', 37, 49) + '\n' + donor_source('import_combat_fx.py', 87, 96),
                 'import_combat_fx.py', 'exec'), ns)
    return normalise(log)


def run_racing_donor():
    """racing_tv_material.py: the module body (lines 1-57, its import line dropped, its save and log left to the importer)."""
    log, U = fresh()
    U._answers['load_asset'] = Recorder('Black', log, U._answers)   # the engine Black texture, as the donor's load returns it
    source = donor_source('racing_tv_material.py', 1, 57).replace('import unreal\n', '', 1)
    exec(compile(source, 'racing_tv_material.py', 'exec'), {'unreal': U})
    return normalise(log)


def run_megapark_donor(alpha):
    """import_megapark.py material(alpha, defaults), lines 68-163, with the donor's defaults (lines 183-188) as stand-ins."""
    log, U = fresh()
    ns = {'unreal': U, 'E': U.EditorAssetLibrary, 'AT': U.AssetToolsHelpers.get_asset_tools(), 'MEL': U.MaterialEditingLibrary,
          'ROOT': '/Game/MegaPark'}
    exec(compile(donor_source('import_megapark.py', 68, 163), 'import_megapark.py', 'exec'), ns)
    white, linear = Recorder('T_DefaultWhite', log, U._answers), Recorder('T_DefaultLinear', log, U._answers)
    black, normal = Recorder('T_DefaultBlack', log, U._answers), Recorder('T_DefaultNormal', log, U._answers)
    defaults = {'Diffuse': white, 'Decal': white, 'Macro': white, 'Lightmap': linear,
                'Normal': normal, 'Detail': normal, 'Specular': black, 'Transparent': white}
    ns['material'](alpha, defaults)
    return normalise(log)


# --- the builders, traced the same way ----------------------------------------------------------------------------------

def trace_builder(family, master, reads_names):
    builder = getattr(BUILDERS[family['name']], master['builder'])
    log, U = fresh()
    reads = {package: Recorder(package.rsplit('/', 1)[1], log, U._answers) for package in reads_names}
    original = BUILDERS[family['name']].unreal
    BUILDERS[family['name']].unreal = U
    try:
        builder(master['package'], reads, **master['arguments'])
    finally:
        BUILDERS[family['name']].unreal = original
    return normalise(log), log


def master_of(family, master_id):
    return next(m for m in family['masters'] if m['id'] == master_id)


# --- the modules and the families ---------------------------------------------------------------------------------------

def test_the_builder_modules_import_without_the_editor_and_define_their_builders():
    for family in (FX, RACING, MEGAPARK):
        module = BUILDERS[family['name']]
        assert module.unreal is None, family['name']   # no editor here: the import has done no work
        for master in family['masters']:
            assert callable(getattr(module, master['builder'])), master['builder']


def test_the_families_load_and_each_master_argument_binds_to_its_builder():
    loaded = planner.load_families()
    for name in ('fx', 'racing', 'megapark'):
        assert name in loaded
        for master in loaded[name]['masters']:
            builder = getattr(BUILDERS[name], master['builder'])
            inspect.signature(builder).bind(master['package'], {r: object() for r in master['reads']}, **master['arguments'])


def test_each_family_names_its_adopted_owner_its_builder_and_a_fallback_among_its_masters():
    expected = {'fx': ('adopted/fx', 'shared/fx', 'master/fx/additive', 'fx_masters.py'),
                'racing': ('adopted/racing', 'shared/racing', 'master/racing/tv', 'racing_masters.py'),
                'megapark': ('adopted/megapark/base-materials', 'shared/megapark/base-materials',
                             ['master/megapark/opaque', 'master/megapark/masked', 'master/megapark/translucent'],
                             'megapark_masters.py')}
    for family in (FX, RACING, MEGAPARK):
        adopted, owner, fallback, builder = expected[family['name']]
        assert family['adopted'] == adopted and family['owner'] == owner and family['fallback'] == fallback
        assert family['builder'] == builder
        assert set(planner.fallback_ids(family)) <= {m['id'] for m in family['masters']}
        for master in family['masters']:   # each master record carries the adopted record's owner and license
            record = records.load_asset(ROOT / 'assets' / master['id'] / 'asset.toml')
            assert (record.owner, record.license) == (family['owner'], family['license']), master['id']
            assert [o.package for o in record.outputs] == [master['package']]


def test_each_master_reads_are_outputs_of_its_inputs_in_the_real_records():
    """@cc [owner:fontanierh,label:correctness] fxretail-reads-owned-by-inputs
    Every non-engine package a master reads MUST be an output of one of its declared input records."""
    for family in (FX, RACING, MEGAPARK):
        for master in family['masters']:
            outputs_of = {}
            for dep in master['inputs']:
                dep_record = records.load_asset(ROOT / 'assets' / dep / 'asset.toml')
                outputs_of[dep] = {o.package for o in dep_record.outputs}
            planned = records.load_asset(_planned_text_path(family, master))
            assert records.material_input_problems(planned, outputs_of) == [], master['id']
            for read in master['reads']:
                if not read.startswith('/Engine/'):
                    assert any(read in outputs for outputs in outputs_of.values()), (master['id'], read)


def _planned_text_path(family, master):
    """The planned record's text written to a tree of its own, so the validator reads the planner's bytes, not a copy."""
    import tempfile
    folder = Path(tempfile.mkdtemp()) / master['id']
    folder.mkdir(parents=True)
    (folder / 'asset.toml').write_text(planner.record_text(family, master, planner.builder_sha(family)))
    return folder / 'asset.toml'


def test_the_planned_records_load_as_material_masters_pinned_to_their_builder():
    for family in (FX, RACING, MEGAPARK):
        for master in family['masters']:
            asset = records.load_asset(_planned_text_path(family, master))
            assert asset.kind == 'material-master' and asset.authority == 'generated'
            assert asset.recipe['settings']['builder'] == master['builder']
            assert [s.sha256 for s in asset.sources] == [planner.builder_sha(family)]
            assert [o.package for o in asset.outputs] == [master['package']]
            assert sorted(asset.input_dependencies) == sorted(master['inputs'])


def test_the_planner_is_done_on_the_real_tree_and_has_nothing_left_to_write():
    """The three families were materialized: fx and racing retired their adopted records, megapark kept its record as the
    generator record that holds the region generator's pinned sources."""
    for family in (FX, RACING, MEGAPARK):
        assert planner.state(ROOT, family) == 'done', family['name']
        assert planner.claim_ops(ROOT, family) == {'writes': {}, 'deletes': []}, family['name']
    assert not (ROOT / f'assets/{FX["adopted"]}/asset.toml').exists()
    assert not (ROOT / f'assets/{RACING["adopted"]}/asset.toml').exists()
    generator = records.load_asset(ROOT / f'assets/{MEGAPARK["adopted"]}/asset.toml')
    assert generator.kind == 'generator' and generator.outputs == [] and generator.sources
    assert not (ROOT / f'assets/{MEGAPARK["adopted"]}/verified.json').exists()


# --- the wiring, against the donor -------------------------------------------------------------------------------------

def test_fx_sprite_masters_wire_as_the_donor_sprite_material_does():
    additive = master_of(FX, 'master/fx/additive')
    dust = master_of(FX, 'master/fx/dust')
    donor_add, _ = run_fx_donor('/Game/FX/M_FX_Additive', 'additive', 'Glow')
    donor_dust, _ = run_fx_donor('/Game/FX/M_FX_Dust', 'translucent', 'Dust')
    built_add, _ = trace_builder(FX, additive, [additive['reads'][0]])
    built_dust, _ = trace_builder(FX, dust, [dust['reads'][0]])
    assert built_add == donor_add
    assert built_dust == donor_dust
    assert ('set_editor_property', ("'blend_mode'", '<BLEND_ADDITIVE>')) in built_add
    assert ('set_editor_property', ("'blend_mode'", '<BLEND_TRANSLUCENT>')) in built_dust


def test_the_fx_trail_wires_as_the_donor_module_body_does_with_its_intensity_of_four():
    trail = master_of(FX, 'master/fx/trail')
    built, _ = trace_builder(FX, trail, [trail['reads'][0]])
    assert built == run_fx_trail_donor()
    assert ('set_editor_property', ("'default_value'", '4.0')) in built


def test_the_racing_tv_wires_as_the_donor_module_body_does():
    tv = master_of(RACING, 'master/racing/tv')
    built, _ = trace_builder(RACING, tv, [tv['reads'][0]])
    assert built == run_racing_donor()
    assert ('set_editor_property', ("'default_value'", '1.0')) in built
    assert ('set_editor_property', ("'two_sided'", 'False')) in built


@pytest.mark.parametrize('master_id,alpha,blend,two_sided,mask_pin', [
    ('master/megapark/opaque', 0, '<BLEND_OPAQUE>', 'False', False),
    ('master/megapark/masked', 1, '<BLEND_MASKED>', 'True', False),
    ('master/megapark/translucent', 2, '<BLEND_TRANSLUCENT>', 'True', False),
])
def test_the_megapark_retail_masters_wire_as_the_donor_material_does(master_id, alpha, blend, two_sided, mask_pin):
    master = master_of(MEGAPARK, master_id)
    built, log = trace_builder(MEGAPARK, master, master['reads'])
    assert built == run_megapark_donor(alpha)
    assert ('set_editor_property', ("'blend_mode'", blend)) in built
    assert ('set_editor_property', ("'two_sided'", two_sided)) in built
    assert ('set_editor_property', ("'opacity_mask_clip_value'", '0.5')) in built


def test_the_megapark_masked_master_pins_its_opacity_mask_and_the_translucent_its_opacity():
    """The donor's last property pin, lines 158-161: alpha 1 to opacity mask, alpha 2 to opacity, opaque to none."""
    for master_id, pin in (('master/megapark/masked', 'MP_OPACITY_MASK'), ('master/megapark/translucent', 'MP_OPACITY')):
        built, _ = trace_builder(MEGAPARK, master_of(MEGAPARK, master_id), master_of(MEGAPARK, master_id)['reads'])
        assert any(name == 'connect_material_property' and args[1] == "''" and args[2].endswith(pin + '>') for name, args in built)
    built, _ = trace_builder(MEGAPARK, master_of(MEGAPARK, 'master/megapark/opaque'), master_of(MEGAPARK, 'master/megapark/opaque')['reads'])
    assert not any(name == 'connect_material_property' and 'OPACITY' in args[2] for name, args in built)


def test_no_builder_saves_its_material_the_importer_does():
    for family in (FX, RACING, MEGAPARK):
        for master in family['masters']:
            _, log = trace_builder(family, master, master['reads'])
            names = {name for name, _ in log}
            assert 'save_loaded_asset' not in names and 'save_asset' not in names, master['id']


def test_the_donor_is_pinned_and_the_committed_megapark_copy_is_the_same_bytes():
    assert hashlib.sha256(COMMITTED_MEGAPARK.read_bytes()).hexdigest() == DONOR_PINS['import_megapark.py']


# --- the reference rewrites, against the real records --------------------------------------------------------------------

def test_no_record_depends_on_the_racing_record_and_the_fx_instances_depend_on_the_parents_they_use():
    """@cc [owner:fontanierh,label:correctness] master-records-dependency-rewrite
    material/fx-instances names adopted/fx in input_dependencies; its instances parent to the additive and dust masters, so it
    depends on those two after the claim."""
    for path in records.record_paths(ROOT):
        asset = records.load_asset(path)
        assert RACING['adopted'] not in asset.references + asset.input_dependencies, path
        assert FX['adopted'] not in asset.references + asset.input_dependencies, path
    data = tomllib.loads((ROOT / 'assets/material/fx-instances/asset.toml').read_text())
    assert {'master/fx/additive', 'master/fx/dust'} <= set(data['input_dependencies'])


def test_the_megapark_mentions_keep_the_generator_and_the_dependencies_move_to_the_opaque_master():
    """The generator record stays, so a record that references it keeps that reference (41 records: the cells and
    shared-textures-common; the adopted seam record that also did is retired by JAPANMI);
    the four instance records (the two-sided seams of JAPANMI included) name M_RetailOpaque in their recipe and depend on
    that master instead."""
    counts = {'generator': 0, 'opaque-dependency': 0}
    for path in records.record_paths(ROOT):
        asset = records.load_asset(path)
        assert MEGAPARK['adopted'] not in asset.input_dependencies, path
        if MEGAPARK['adopted'] in asset.references:
            counts['generator'] += 1
        if 'master/megapark/opaque' in asset.input_dependencies:
            counts['opaque-dependency'] += 1
    assert counts == {'generator': 41, 'opaque-dependency': 4}
