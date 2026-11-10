"""Material-instance records: the two used Japan leaves are generated records with a recipe, their parent and texture
are owned by other records, and no package has two owners. Nothing here runs Unreal; the editor step is faked."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
import records  # noqa: E402

spec = importlib.util.spec_from_file_location('v2_import_run_material', ROOT / 'tools' / 'import' / 'run.py')
run = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run
spec.loader.exec_module(run)

LEAVES = {'amber': 'MI_LeafAmber', 'crimson': 'MI_LeafCrimson'}
BASE = ROOT / 'assets/adopted/japan/materials/base-materials/asset.toml'
ATLASES = ROOT / 'assets/adopted/japan/textures/leaf-atlases/asset.toml'
FOLIAGE = ROOT / 'assets/adopted/japan/materials/foliage'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def material_toml(*, id='material/fake/leaf-amber', kind='material-instance', authority='generated',
                  deps='["adopted/fake/materials/base", "adopted/fake/textures/leaf"]', importer='material-instance',
                  settings='parent = "/Game/Japan/Materials/M_Foliage"\ntextures = { Tex = "/Game/Japan/Textures/T_leaf_amber" }\n'
                           'scalars = {}\nvectors = {}\n',
                  sources=''):
    deps_line = f'input_dependencies = {deps}\n' if deps is not None else ''
    return (f'schema = 1\nid = "{id}"\nkind = "{kind}"\nauthority = "{authority}"\nowner = "shared/fake/leaf-amber"\n'
            f'{deps_line}{sources}'
            f'[recipe]\nimporter = "{importer}"\nversion = 1\n[recipe.settings]\n{settings}'
            f'[[outputs]]\npackage = "/Game/Japan/Materials/MI_LeafAmber"\n')


def load_text(tmp_path, text):
    path = tmp_path / 'asset.toml'
    path.write_text(text)
    return records.load_asset(path)


# --- the real records ------------------------------------------------------------------------------------------

@pytest.mark.parametrize('name, package', LEAVES.items())
def test_each_used_leaf_is_a_generated_material_instance_with_its_recipe(name, package):
    asset = records.load_asset(ROOT / f'assets/material/japan/leaf-{name}/asset.toml')
    assert asset.id == f'material/japan/leaf-{name}'
    assert asset.kind == 'material-instance' and asset.authority == 'generated'
    assert asset.owner == f'shared/japan/materials/leaf-{name}'
    assert asset.sources == []
    assert [o.package for o in asset.outputs] == [f'/Game/Japan/Materials/{package}']
    assert asset.recipe == {
        'importer': 'material-instance', 'version': 1,
        'settings': {'parent': '/Game/Japan/Materials/M_Foliage',
                     'textures': {'Tex': f'/Game/Japan/Textures/T_leaf_{name}'},
                     'scalars': {}, 'vectors': {}}}
    assert asset.input_dependencies == ['adopted/japan/materials/base-materials', 'adopted/japan/textures/leaf-atlases']


def test_the_inputs_are_owned_by_the_records_they_name():
    base, atlases = records.load_asset(BASE), records.load_asset(ATLASES)
    outputs_of = {base.id: {o.package for o in base.outputs}, atlases.id: {o.package for o in atlases.outputs}}
    for name in LEAVES:
        asset = records.load_asset(ROOT / f'assets/material/japan/leaf-{name}/asset.toml')
        assert records.material_inputs(asset) == ['/Game/Japan/Materials/M_Foliage', f'/Game/Japan/Textures/T_leaf_{name}']
        assert records.material_input_problems(asset, outputs_of) == []


def test_the_texture_inputs_are_the_editor_saved_leaf_atlas_packages_with_verified_bytes():
    atlases = records.load_asset(ATLASES)
    verified = records.load_verified(ATLASES.with_name('verified.json'))
    for name in LEAVES:
        assert f'/Game/Japan/Textures/T_leaf_{name}' in {o.package for o in atlases.outputs}
        assert f'unreal/Content/Japan/Textures/T_leaf_{name}.uasset' in verified['files']


def test_the_foliage_record_no_longer_owns_the_used_leaves_and_its_verified_bytes_agree():
    foliage = records.load_asset(FOLIAGE / 'asset.toml')
    packages = {o.package for o in foliage.outputs}
    assert len(packages) == 17
    assert not packages & {f'/Game/Japan/Materials/{p}' for p in LEAVES.values()}
    verified = records.load_verified(FOLIAGE / 'verified.json')
    assert set(verified['files']) == {f'unreal/Content/Japan/Materials/{p.rsplit("/", 1)[1]}.uasset' for p in packages}


def test_the_canopies_name_the_leaf_record_they_bind_as_a_reference():
    for name in LEAVES:
        tree = records.load_asset(ROOT / f'assets/prop/japan-kit/tree-canopy-{name}/asset.toml')
        assert f'material/japan/leaf-{name}' in tree.references


def test_no_package_has_two_owners_across_the_japan_material_records():
    owners = {}
    for path in records.record_paths(ROOT):
        if 'japan' not in str(path):
            continue
        asset = records.load_asset(path)
        for output in asset.outputs:
            assert output.package not in owners, (output.package, owners.get(output.package), asset.id)
            owners[output.package] = asset.id
    for name, package in LEAVES.items():
        assert owners[f'/Game/Japan/Materials/{package}'] == f'material/japan/leaf-{name}'


# --- schema -----------------------------------------------------------------------------------------------------

def test_a_well_formed_material_instance_loads_with_no_sources(tmp_path):
    asset = load_text(tmp_path, material_toml())
    assert asset.sources == [] and asset.recipe['settings']['textures'] == {'Tex': '/Game/Japan/Textures/T_leaf_amber'}


@pytest.mark.parametrize('kwargs, reason', [
    (dict(deps=None), 'input_dependencies'),
    (dict(deps='[]'), 'input_dependencies'),
    (dict(importer='static-mesh'), 'importer "material-instance"'),
    (dict(settings='parent = "M_Foliage"\n'), 'parent'),
    (dict(settings='parent = "/Game/M_Foliage"\nextra = 1\n'), 'extra'),
    (dict(settings='parent = "/Game/M_Foliage"\ntextures = { "Tex" = "T_leaf_amber" }\n'), 'texture'),
    (dict(settings='parent = "/Game/M_Foliage"\nscalars = { FadeMode = true }\n'), 'scalar'),
    (dict(settings='parent = "/Game/M_Foliage"\nvectors = { Tint = [1.0, 1.0, 1.0] }\n'), 'vector'),
    (dict(settings='parent = "/Game/M_Foliage"\noverrides = {}\n'), 'overrides'),
])
def test_a_malformed_material_instance_is_refused(tmp_path, kwargs, reason):
    with pytest.raises(records.RecordError, match=reason):
        load_text(tmp_path, material_toml(**kwargs))


def test_a_material_instance_with_its_own_source_is_refused_when_it_has_no_inputs(tmp_path):
    with pytest.raises(records.RecordError, match='input_dependencies'):
        load_text(tmp_path, material_toml(deps=None, sources='[[sources]]\npath = "src/x.png"\nsha256 = "' + '0' * 64 + '"\n'))


def test_generated_content_without_a_source_is_still_refused_outside_material_instances(tmp_path):
    text = material_toml(kind='static-mesh', settings='').replace('[recipe.settings]\n', '')
    with pytest.raises(records.RecordError, match='at least one source'):
        load_text(tmp_path, text.replace('importer = "material-instance"', 'importer = "static-mesh"'))


def test_a_package_read_but_not_owned_by_an_input_is_reported(tmp_path):
    asset = load_text(tmp_path, material_toml(deps='["adopted/fake/materials/base"]'))
    problems = records.material_input_problems(asset, {'adopted/fake/materials/base': {'/Game/Japan/Materials/M_Foliage'}})
    assert problems == ['/Game/Japan/Textures/T_leaf_amber is read by material/fake/leaf-amber but no input dependency owns it']


# --- the importer --------------------------------------------------------------------------------------------------

def test_the_runner_knows_the_material_instance_importer():
    assert run.IMPORTERS['material-instance'] == ('material-instance', 1)


class FakeMaterialEditor:
    """Writes the planned instance packages as the editor would, recording the settings it was given."""

    def __init__(self):
        self.calls = []

    def __call__(self, game, asset, plan_file):
        plan = json.loads(plan_file.read_text())
        assert plan['importer'] == 'material-instance' and plan['sources'] == []
        self.calls.append(plan['settings'])
        for package in plan['packages']:
            write(records.package_files(game, package)[0], f'instance {package} {plan["settings"]}'.encode())


@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setenv('ATELIER_AGENT', run.BOOTSTRAP_WRITER)
    base = tmp_path / 'assets/adopted/fake/materials/base'
    leaf = tmp_path / 'assets/adopted/fake/textures/leaf'
    write(base / 'asset.toml', 'schema = 1\nid = "adopted/fake/materials/base"\nkind = "adopted"\nauthority = "editor"\n'
                              'owner = "shared/fake/materials/base"\n[[outputs]]\npackage = "/Game/Japan/Materials/M_Foliage"\n')
    write(leaf / 'asset.toml', 'schema = 1\nid = "adopted/fake/textures/leaf"\nkind = "adopted"\nauthority = "editor"\n'
                              'owner = "shared/fake/textures/leaf"\n[[outputs]]\npackage = "/Game/Japan/Textures/T_leaf_amber"\n')
    for folder, package in [(base, 'M_Foliage'), (leaf, 'T_leaf_amber')]:
        content = f'saved {package}'.encode()
        write(tmp_path / f'unreal/Content/{"Japan/Materials" if package.startswith("M_") else "Japan/Textures"}/{package}.uasset', content)
        write(folder / 'verified.json', json.dumps({
            'schema': 1, 'kind': 'editor-saved', 'engine': '5.8.2-1', 'dependencies': {},
            'files': {f'unreal/Content/{"Japan/Materials" if package.startswith("M_") else "Japan/Textures"}/{package}.uasset': sha(content)}}))
    write(tmp_path / 'assets/material/fake/leaf-amber/asset.toml', material_toml(
        deps='["adopted/fake/materials/base", "adopted/fake/textures/leaf"]'))
    return tmp_path


def do(game, editor):
    ordered, _ = run.plan(game, ['material/fake/leaf-amber'])
    by_id = {a.id: a for a in records.discover(game)[0]}
    return run.import_one(game, by_id['material/fake/leaf-amber'], by_id, engine='5.8.2-1', claim=None,
                          importer=editor, echo=lambda *_: None)


def test_an_import_writes_only_the_instance_and_records_the_inputs_it_read(game):
    editor = FakeMaterialEditor()
    assert do(game, editor) is True
    assert editor.calls == [{'parent': '/Game/Japan/Materials/M_Foliage',
                             'textures': {'Tex': '/Game/Japan/Textures/T_leaf_amber'}, 'scalars': {}, 'vectors': {}}]
    record = records.load_verified(game / 'assets/material/fake/leaf-amber/verified.json')
    assert record['kind'] == 'imported' and record['tool'] == 'material-instance@1'
    assert list(record['files']) == ['unreal/Content/Japan/Materials/MI_LeafAmber.uasset']
    assert set(record['dependencies']) == {'adopted/fake/materials/base', 'adopted/fake/textures/leaf'}


def test_an_unchanged_rerun_starts_no_editor(game):
    editor = FakeMaterialEditor()
    do(game, editor)
    assert do(game, editor) is False
    assert len(editor.calls) == 1


def test_a_changed_texture_owner_makes_the_instance_stale_and_reimports_it(game):
    editor = FakeMaterialEditor()
    do(game, editor)
    texture = game / 'assets/adopted/fake/textures/leaf/verified.json'
    data = json.loads(texture.read_text())
    data['files'] = {k: sha(b'resaved') for k in data['files']}
    texture.write_text(json.dumps(data))
    assert do(game, editor) is True
    assert len(editor.calls) == 2


def test_an_input_the_record_does_not_declare_stops_the_plan_before_any_editor(game):
    write(game / 'assets/material/fake/leaf-amber/asset.toml', material_toml(deps='["adopted/fake/materials/base"]'))
    with pytest.raises(run.ImportError_, match='T_leaf_amber'):
        run.plan(game, ['material/fake/leaf-amber'])
