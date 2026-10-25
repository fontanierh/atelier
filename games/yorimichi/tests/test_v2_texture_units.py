"""C3 texture declarations consume original texture constructor products."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_texture_units as textures  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def rows():
    recipe = load(GAME / 'build.py', 'texture_unit_source_recipe')
    steps = recipe.texture_steps(SimpleNamespace(out=ROOT / 'build/yorimichi'))
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def test_actual_twenty_two_producers_become_separate_raw_and_finish_units(rows):
    result = textures.texture_units(rows, checkout=ROOT)
    assert len(result['units']) == 44 and len(result['textures']) == 22
    by_id = {unit['id']: unit for unit in result['units']}
    for name, ref in result['textures'].items():
        key = name.removeprefix('T_')
        raw_id = 'unreal.texture.raw.' + key
        raw, finish = by_id[raw_id], by_id[ref['unit']]
        assert raw['op'] == {'kind':'unreal.raw_import','version':'1'}
        assert finish['op'] == {'kind':'unreal.finish','version':'1'}
        assert raw['inputs'][0]['source'] == {'kind':'item','unit':'world.textures.'+key,'item':'product0'}
        assert finish['inputs'][0]['source'] == {'kind':'item','unit':raw_id,'item':'raw_texture'}
        filename = name + ('.jpg' if key in textures.JPEG else '.png')
        assert raw['params']['input_roots']['source'] == {'archive_member':'products/0-0.tree.tar','name':filename}
        assert raw['outputs'][0]['class'] == 'RawTexture' and raw['outputs'][0]['destination'] == 'store'
        assert all('install_path' not in file for file in raw['outputs'][0]['files'])
        assert finish['outputs'][0]['class'] == 'Texture' and finish['outputs'][0]['destination'] == 'checkout'
        assert finish['params']['package_sources'] == {'raw':'/Game/_Raw/Textures/'+name}
        assert ref == {'unit':'unreal.texture.finish.'+key,'item':'texture','package':'/Game/Japan/Textures/'+name}
        files = finish['outputs'][0]['files']
        assert len(files) == 6 and sum(file['required'] for file in files) == 1
        assert files[0]['path'].endswith('.uasset') and files[0]['required']
        for file, suffix in zip(files, textures.SIDECARS):
            assert file['path'] == 'content/Game/Japan/Textures/'+name+suffix
            assert file['install_path'] == 'games/yorimichi/unreal/Content/Japan/Textures/'+name+suffix
        assert result['staged'][raw_id] == {'source':'inputs/source'}
        assert result['staged'][ref['unit']] == {'raw':'inputs/raw'}


def test_alpha_and_mip_properties_apply_only_to_finished_original_silhouettes(rows):
    result = textures.texture_units(rows, checkout=ROOT)
    for raw, finish in zip(result['units'][::2], result['units'][1::2]):
        assert 'properties' not in raw['params']
        name = finish['params']['destination'].rpartition('/')[2]
        properties = finish['params']['properties']
        if name.startswith(('T_grass','T_leaf_','T_flower')):
            assert properties == {'do_scale_mips_for_alpha_coverage':True,
                                  'alpha_coverage_thresholds':{'unreal_type':'Vector4','args':[0,0,0,.4]},
                                  'mip_gen_settings':{'unreal_enum':'TextureMipGenSettings.TMGS_SIMPLE_AVERAGE'}}
        else:
            assert properties == {}


def test_code_membership_includes_actual_compiled_plugin_source_closure(rows):
    unit = textures.texture_units(rows[:1], checkout=ROOT)['units'][0]
    plugin = ROOT / textures.PLUGIN
    expected = {textures.PLUGIN + '/AtelierBuildWorker.uplugin'} | {
        path.relative_to(ROOT).as_posix() for path in (plugin / 'Source').rglob('*')
        if path.suffix in ('.cs','.cpp','.h')}
    assert len(expected) == 8
    assert set(unit['code']) == expected | {textures.OPS, *textures.SUPPORT}


@pytest.mark.parametrize('change', ['product','optional','output','filename','command','script','unknown','duplicate'])
def test_wrong_source_shape_refuses(rows, change):
    row = deepcopy(rows[0])
    if change == 'product': row['products'][0]['id'] = 'other'
    elif change == 'optional': row['products'][0]['optional_paths'] = ['another.png']
    elif change == 'output': row['outputs'].append('another.png')
    elif change == 'filename': row['products'][0]['paths'][0] = 'build/yorimichi/textures/wrong.png'
    elif change == 'command': row['commands'][0]['args'].append('--unknown')
    elif change == 'script': row['commands'][0]['script'] = {'path':'other.py'}
    elif change == 'unknown': row['id'] = 'world.textures.unknown'
    selected = [row, row] if change == 'duplicate' else [row]
    with pytest.raises(textures.Unsupported): textures.texture_units(selected, checkout=ROOT)


def test_selection_does_not_mutate_rows_or_scan_generated_content(rows, monkeypatch):
    before = deepcopy(rows)
    original = Path.rglob
    def scan(path, pattern):
        assert path == ROOT / textures.PLUGIN / 'Source'
        return original(path, pattern)
    monkeypatch.setattr(Path, 'rglob', scan)
    assert len(textures.texture_units(rows[:1], checkout=ROOT)['units']) == 2
    assert rows == before


def test_new_native_source_member_is_keyed_and_linked_source_refuses(rows, tmp_path):
    import shutil
    target = tmp_path / textures.PLUGIN
    target.parent.mkdir(parents=True)
    shutil.copytree(ROOT / textures.PLUGIN / 'Source', target / 'Source')
    shutil.copyfile(ROOT / textures.PLUGIN / 'AtelierBuildWorker.uplugin', target / 'AtelierBuildWorker.uplugin')
    ops = tmp_path / textures.OPS; ops.parent.mkdir(parents=True); ops.write_bytes((ROOT / textures.OPS).read_bytes())
    for name in textures.SUPPORT:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    added = target / 'Source/AtelierBuildWorker/Public/NewKeyedSource.h'; added.write_text('// current source\n')
    units = textures.texture_units(rows[:1], checkout=tmp_path)['units']
    assert all(added.relative_to(tmp_path).as_posix() in unit['code'] for unit in units)
    (added.parent / 'Linked.h').symlink_to(added)
    with pytest.raises(textures.Unsupported, match='link'):
        textures.texture_units(rows[:1], checkout=tmp_path)
