"""Footstep attenuation and FootstepSet owners over finished surface waves: original values, no scans or top level."""
import importlib.util
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_footstep_units as footsteps  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402

spec = importlib.util.spec_from_file_location('footsteps_v2', GAME / 'world/footsteps_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
SURFACES = ['barefoot', 'dirt_gravel', 'grass', 'leaves', 'mud_water', 'stone', 'wood']


def waves():
    return {surface: footsteps._token(surface) for surface in SURFACES}


def test_owners_bind_every_surface_token_and_original_classes():
    result = footsteps.author_units(checkout=ROOT, waves=waves())
    attenuation, library = result['units']
    assert attenuation['outputs'][0]['logical_path'] == '/Game/Japan/Audio/A_Footstep'
    assert attenuation['outputs'][0]['class'] == 'SoundAttenuation' and attenuation['inputs'] == []
    assert library['outputs'][0]['logical_path'] == '/Game/Japan/Audio/DA_Footsteps'
    assert library['outputs'][0]['class'] == 'DataAsset'
    assert library['inputs'] == [{'role': 'content', 'name': 'attenuation',
                                  'source': {'kind': 'item', 'unit': footsteps.ATTENUATION_UNIT, 'item': 'asset'}}]
    args = library['params']['args']
    assert sorted(args['surfaces']) == SURFACES and args['surfaces']['grass'] == footsteps._token('grass')
    assert args['surfaces']['leaves']['derived_items']['templates'][0] == {
        'producer': 'audio.footsteps.files.leaves', 'group': 'waves', 'unit_prefix': 'unreal.sound.raw.footsteps.leaves',
        'follower': 0, 'item': 'sound'}
    for unit in result['units']:
        assert {footsteps.SCRIPT, footsteps.ORIGINAL, footsteps.SAVE} <= set(unit['code'])
        assert all(row['install_path'].startswith('games/yorimichi/unreal/Content/Japan/Audio/') for row in unit['outputs'][0]['files'])
    assert result['module_requirements'] == {footsteps.LIBRARY_UNIT: [
        {'name': 'Yorimichi', 'kind': 'Runtime', 'loading_phase': 'Default'}]}
    assert result['aliases'] == {} and result['closes'] == [footsteps.ATTENUATION, footsteps.LIBRARY]
    assert result['packages'][footsteps.LIBRARY]['dependencies'] == [
        {'unit': footsteps.ATTENUATION_UNIT, 'item': 'asset', 'package': footsteps.ATTENUATION}]


def test_tokens_match_the_published_wave_templates():
    import v2_audio_templates
    row = {'id': 'audio.footsteps'}
    expected = {}
    for cue in v2_audio_templates.cue_settings('audio.footsteps', checkout=ROOT):
        producer = row['id'] + '.files.' + cue
        expected[cue] = {'derived_items': {'templates': [{'producer': producer, 'group': 'waves',
            'unit_prefix': 'unreal.sound.raw.footsteps.' + cue, 'follower': 0, 'item': 'sound'}],
            'root': 'build/v2-derived/audio/footsteps/' + cue}}
    assert expected == waves()


@pytest.mark.parametrize('change', ['missing', 'extra', 'resolved', 'item', 'listed'])
def test_partial_or_reshaped_wave_tokens_refuse(change):
    value = waves()
    if change == 'missing': del value['leaves']
    elif change == 'extra': value['snow'] = footsteps._token('snow')
    elif change == 'resolved': value['grass'] = {'derived_items': {'root': 'x', 'members': []}}
    elif change == 'item': value['grass']['derived_items']['templates'][0]['item'] = 'raw_sound'
    elif change == 'listed': value['grass'] = [{'unit': 'u', 'item': 'sound', 'package': '/Game/x'}]
    with pytest.raises(Unsupported):
        footsteps.author_units(checkout=ROOT, waves=value)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, name): return self.props[name]
    def set_editor_property(self, name, value): self.props[name] = value


class SoundWave(Asset): pass
class SoundAttenuation(Asset): pass
class JapanFootstepSet(Asset): pass


class Bank:
    def __init__(self, steps): self.steps = steps
    def get_editor_property(self, name): return getattr(self, name)


@pytest.fixture
def editor(tmp_path, monkeypatch):
    for relative in (body.ORIGINAL, body.SAVE):
        target = tmp_path / relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    content = tmp_path / 'project/Content'; content.mkdir(parents=True)
    assets = {}
    def create(name, folder, cls, factory):
        asset = cls(folder + '/' + name, **({'attenuation': Asset('settings')} if cls is SoundAttenuation else {}))
        assets[asset.path] = asset; return asset
    def save(asset, only_if_is_dirty=True):
        path = content / (asset.path.removeprefix('/Game/') + '.uasset')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'uasset'); return True
    unreal = NS(SoundWave=SoundWave, SoundAttenuation=SoundAttenuation, JapanFootstepSet=JapanFootstepSet,
                JapanFootstepBank=Bank, Name=str, Vector=lambda *v: v,
                AttenuationShape=NS(SPHERE='sphere'), AttenuationDistanceModel=NS(NATURAL_SOUND='natural'),
                SoundSpatializationAlgorithm=NS(SPATIALIZATION_DEFAULT='default'),
                SoundAttenuationFactory=lambda: 'factory', DataAssetFactory=lambda: Asset('factory'),
                log=lambda message: None,
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      save_loaded_asset=save),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(assets=assets, root=tmp_path, content=content)


def context(editor, outputs, args, inputs=None, packages=None):
    return NS(job_dir=str(editor.root), inputs=inputs or {}, packages=packages or {}, outputs=outputs,
              content=str(editor.content), params={'args': args, 'settings': []})


def test_attenuation_runs_the_original_definition_and_saves_under_job_content(editor):
    built = body.run(context(editor, [body.ATTENUATION], {'action': 'attenuation'}))
    settings = built.props['attenuation'].props
    assert settings == {'attenuation_shape': 'sphere', 'falloff_distance': 2600., 'attenuation_shape_extents': (350., 0., 0.),
                        'distance_algorithm': 'natural', 'db_attenuation_at_max': -60., 'enable_occlusion': False,
                        'spatialization_algorithm': 'default'}
    assert (editor.content / 'Japan/Audio/A_Footstep.uasset').is_file()


def library_case(editor):
    editor.assets[body.ATTENUATION] = SoundAttenuation(body.ATTENUATION)
    surfaces, inputs, packages = {}, {'attenuation': 'x'}, {'attenuation': [body.ATTENUATION]}
    for surface in ('grass', 'leaves'):
        members = []
        for piece in ('b-step', 'b'):
            slot = f'derived_{len(inputs) - 1}'
            package = f'/Game/Japan/Audio/Footsteps/{surface}/{piece}'
            editor.assets[package] = SoundWave(package)
            inputs[slot], packages[slot] = 'x', [package]
            members.append({'piece': piece, 'slot': slot, 'root': f'build/v2-derived/audio/footsteps/{surface}/{piece}'})
        surfaces[surface] = {'derived_items': {'root': 'build/v2-derived/audio/footsteps/' + surface, 'members': members}}
    return context(editor, [body.LIBRARY], {'action': 'library', 'attenuation': 'attenuation', 'surfaces': surfaces},
                   inputs, packages)


def test_library_binds_declared_waves_in_original_file_order(editor):
    library = body.run(library_case(editor))
    banks = library.props['surfaces']
    # sorted(glob('*.wav')): 'b-step.wav' sorts before 'b.wav'.
    assert [w.path.rsplit('/', 1)[1] for w in banks['grass'].steps] == ['b-step', 'b']
    assert library.props['attenuation'] is editor.assets[body.ATTENUATION]
    assert library.props['default_surface'] == 'grass' and library.props['canopy_surface'] == 'leaves'
    assert library.props['material_surfaces']['Tatami'] == 'barefoot' and library.props['material_surfaces']['Litter'] == 'leaves'
    assert (editor.content / 'Japan/Audio/DA_Footsteps.uasset').is_file()


@pytest.mark.parametrize('failure', ['unresolved', 'undeclared', 'folder', 'class', 'existing', 'outputs'])
def test_library_refuses_inconsistent_inputs(editor, failure):
    case = library_case(editor)
    surfaces = case.params['args']['surfaces']
    if failure == 'unresolved':
        surfaces['grass'] = footsteps._token('grass')
    elif failure == 'undeclared':
        case.inputs['extra'] = 'x'; case.packages['extra'] = ['/Game/x']
    elif failure == 'folder':
        editor.assets['/Game/Japan/Audio/Footsteps/grass/b'].path = '/Game/Japan/Audio/Footsteps/leaves/b'
    elif failure == 'class':
        editor.assets['/Game/Japan/Audio/Footsteps/grass/b'] = Asset('/Game/Japan/Audio/Footsteps/grass/b')
    elif failure == 'existing':
        editor.assets[body.LIBRARY] = JapanFootstepSet(body.LIBRARY)
    elif failure == 'outputs':
        case.outputs = [body.LIBRARY, body.ATTENUATION]
    with pytest.raises(ValueError):
        body.run(case)
