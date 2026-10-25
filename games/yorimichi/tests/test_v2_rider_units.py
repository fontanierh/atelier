"""Ride clips (unreal.<k>_bike / _horse) as native units: the actual rows, member projection, bodies on a fake editor."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build import Product
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'tests')]
import v2_rider_units as units  # noqa: E402
from test_v2_character_units import MOVERS, recipe  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(units.BODY, 'rider_members_test')
body = load(units.SCRIPT, 'rider_body_test')
PLAYABLE = [c for c in MOVERS if c.playable]


def natives():
    return {'compression': {'unit': 'unreal.animation.compression', 'item': 'asset', 'package': units.COMPRESSION},
            **{c.id: {'skeleton': {'unit': f"unreal.character.{c.id.replace('-', '_')}.mesh", 'item': 'skeleton',
                                   'package': f'{c.unreal_path}/SK_{c.name}_Skeleton'}} for c in PLAYABLE}}


@pytest.fixture(scope='module')
def rows():
    """The actual eight ride rows and producers; the export Product Root adds to build.py is supplied here."""
    out, steps = ROOT / 'build/yorimichi', []
    for character in PLAYABLE:
        for step in recipe.mover_export_steps(character, out) + recipe.mover_import_steps(character, out):
            ride = step.name.rsplit('_', 1)[-1]
            if ride in ('bike', 'horse') and step.name.startswith(('characters.', 'unreal.')):
                if step.name.startswith('characters.'):
                    step.products = [*step.products, Product(step.name + '.export', tuple(
                        out / character.output / ride / n for n in ('export.json', 'fbx')))]
                steps.append(step)
    names = {s.name for s in steps}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []; step.reads = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return units.rider_units(rows, checkout=ROOT, natives=natives())


def test_eight_rides_from_the_actual_rows(declared):
    assert sorted(declared['aliases']) == sorted(f"unreal.{c.id.replace('-', '_')}_{r}" for c in PLAYABLE for r in ('bike', 'horse'))
    assert len(declared['aliases']) == 8 and units.fps(ROOT, 'bike') == units.fps(ROOT, 'horse') == 60
    found = {u['id']: u for u in declared['units']}
    horse = found['characters.cairo_horse.members.clips']
    assert horse['inputs'][0]['source'] == {'kind': 'item', 'unit': 'characters.cairo_horse', 'item': 'product0'}
    defaults = horse['params']['recipe']['commands'][0]['call']['defaults']
    assert defaults[3] == 60 and 'HorseIdle' in defaults[4] and 'HorseMount' in defaults[4]
    bike = found['characters.cairo_bike.members.clips']
    assert bike['params']['recipe']['commands'][0]['call']['defaults'][4] is None
    assert declared['tokens']['unreal.cairo_horse']['folder'] == '/Game/CairoHorse'
    record = found['unreal.ride.cairo.horse.record']
    assert record['params']['args']['clips'] == declared['tokens']['unreal.cairo_horse']['clips']


def test_followers_consume_only_their_member(declared):
    keys = {t['unit_prefix']: t for t in declared['templates']}
    raw, finish = (f['unit'] for f in keys['unreal.ride.nox.bike']['followers'])
    assert raw['params']['fbx']['custom_sample_rate'] == 60 and raw['params']['skeleton'] == 'skeleton'
    assert {i['name']: i['source']['unit'] for i in raw['inputs']} == {'source': '$export', 'skeleton': 'unreal.character.nox.mesh'}
    assert finish['outputs'][0]['logical_path'] == '/Game/NoxBike/A_$piece'
    assert finish['params']['args']['meta'] == 'meta' and finish['params']['input_roots'] == {
        'meta': {'archive_member': 'meta.tree.tar', 'name': 'meta'}}
    for template in declared['templates']:
        for follower in template['followers']:
            assert all(not i['source']['unit'].startswith('characters.') for i in follower['unit']['inputs'])
    for value in declared['tokens'].values():
        source = value['clips']['derived_items']['templates'][0]
        assert keys[source['unit_prefix']]['producer'] == source['producer']


@pytest.mark.parametrize('damage', ['product', 'skeleton', 'env', 'roster'])
def test_declaration_drift_refuses(rows, damage):
    rows, value = deepcopy(rows), natives()
    found = {r['id']: r for r in rows}
    if damage == 'product':
        found['characters.paul_bike']['products'][0]['paths'].pop()
    elif damage == 'skeleton':
        value['modori'].pop('skeleton')
    elif damage == 'env':
        found['unreal.nox_horse']['commands'][0]['env'] = [['RIDE', 'bike'], ['RIDE_CHARACTER', 'nox']]
    else:
        found['unreal.cairo_horse']['outputs'] = found['unreal.cairo_horse']['outputs'][:-1]
    with pytest.raises(ValueError):
        units.rider_units(rows, checkout=ROOT, natives=value)


# ---- projection -----------------------------------------------------------------------------------------------------

def export_tree(tmp_path, *, fps=60):
    root = tmp_path / 'ride'; (root / 'fbx').mkdir(parents=True)
    config = {'fps': fps, 'source_sha256': 'abc', 'clips': {
        'HorseIdle': {'frames': 60, 'loop': True, 'duration': 1.0}, 'HorseMount': {'frames': 45, 'loop': False, 'duration': .75}}}
    (root / 'export.json').write_text(json.dumps(config))
    for name in config['clips']:
        (root / 'fbx' / f'A_{name}.fbx').write_bytes(name.encode())
    return root


def test_projection_and_selection(tmp_path):
    root = export_tree(tmp_path)
    members.project(root / 'export.json', root / 'fbx', tmp_path / 'out', 60, ['HorseIdle', 'HorseMount'])
    manifest = emit(tmp_path / 'out', tmp_path / 'files', parent='Cairo_horse', extensions=['.json'])
    assert sorted(p['name'] for p in manifest['pieces']) == ['HorseIdle', 'HorseMount']
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'HorseMount.json').write_bytes((tmp_path / 'out/HorseMount.json').read_bytes())
    members.select(selected, tmp_path / 'member', tmp_path / 'meta', 'HorseMount')
    assert (tmp_path / 'member/HorseMount.fbx').read_bytes() == b'HorseMount'
    assert json.loads((tmp_path / 'member/export.json').read_text()) == {
        'primary': 'HorseMount.fbx', 'sha256': hashlib.sha256(b'HorseMount').hexdigest()}
    assert json.loads((tmp_path / 'meta/meta.json').read_text()) == {'name': 'HorseMount', 'frames': 45, 'loop': False,
                                                                    'duration': .75, 'fps': 60}


@pytest.mark.parametrize('damage', ['fps', 'roster', 'fbx'])
def test_projection_refuses_an_export_that_differs(tmp_path, damage):
    root = export_tree(tmp_path, fps=30 if damage == 'fps' else 60)
    roster = ['HorseIdle'] if damage == 'roster' else None
    if damage == 'fbx':
        (root / 'fbx/A_HorseIdle.fbx').unlink()
    with pytest.raises(ValueError):
        members.project(root / 'export.json', root / 'fbx', tmp_path / 'out', 60, roster)
    assert not (tmp_path / 'out').exists()


# ---- bodies ---------------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Sequence(Asset):
    def get_play_length(self): return self.props['length']


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves = {}, []
    def duplicate(source, target):
        assets[target] = type(assets[source])(target, **assets[source].props); return assets[target]
    unreal = NS(AnimSequence=Sequence, EditorAssetLibrary=NS(
        load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
        duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    target = tmp_path / units.COMPRESSION_SCRIPT; target.parent.mkdir(parents=True)
    target.write_text('def apply_to(sequence): sequence.set_editor_property("bone_compression_settings", _settings)\n')
    return NS(assets=assets, saves=saves, root=tmp_path)


def clip_context(editor, duration):
    skeleton, settings = Asset('/Game/Cairo/SK_Cairo_Skeleton'), Asset(units.COMPRESSION)
    raw = Sequence('/Game/_Raw/Ride/cairo/horse/A_HorseMount', skeleton=skeleton, length=.75, enable_root_motion=True)
    editor.assets.update({a.path: a for a in (skeleton, settings, raw)})
    meta = editor.root / 'meta'; meta.mkdir(exist_ok=True)
    (meta / 'meta.json').write_text(json.dumps({'name': 'HorseMount', 'frames': 45, 'loop': False, 'duration': duration, 'fps': 60}))
    return NS(job_dir=str(editor.root), outputs=['/Game/CairoHorse/A_HorseMount'],
              inputs={'raw': 'x', 'skeleton': 'x', 'compression': 'x', 'meta': str(meta)},
              packages={'raw': [raw.path], 'skeleton': [skeleton.path], 'compression': [settings.path], 'meta': []},
              params={'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': '/Game/CairoHorse/A_HorseMount',
                      'args': {'action': 'clip', 'name': 'HorseMount', 'fps': 60, 'meta': 'meta', 'skeleton': 'skeleton',
                               'compression': 'compression'}})


def test_clip_finish_is_the_original_with_its_own_length_check(editor):
    clip = body.run(clip_context(editor, .76))   # within 1.5 frames at 60 fps
    assert clip.props['enable_root_motion'] is False and clip.props['bone_compression_settings'].path == units.COMPRESSION
    del editor.assets['/Game/CairoHorse/A_HorseMount']
    with pytest.raises(ValueError, match='length'):
        body.run(clip_context(editor, .80))


def test_record_is_the_original_report(editor, tmp_path):
    for name, length in (('HorseIdle', 1.0), ('HorseMount', .75)):
        editor.assets[f'/Game/CairoHorse/A_{name}'] = Sequence(f'/Game/CairoHorse/A_{name}', length=length)
    root = export_tree(tmp_path)
    context = NS(job_dir=str(tmp_path), outputs=[], data_outputs=(body.RECORD,), inputs={'export': str(root), 'd0': 'x', 'd1': 'x'},
                 packages={'d0': ['/Game/CairoHorse/A_HorseIdle'], 'd1': ['/Game/CairoHorse/A_HorseMount']},
                 params={'args': {'action': 'record', 'export': 'export', 'clips': {'derived_items': {'root': 'r', 'members': [
                     {'piece': 'HorseIdle', 'slot': 'd0', 'root': 'r/HorseIdle'}, {'piece': 'HorseMount', 'slot': 'd1', 'root': 'r/HorseMount'}]}}},
                         'settings': []})
    assert body.run(context) == {body.RECORD: {'fps': 60, 'source_sha256': 'abc', 'clips': {
        'HorseIdle': {'length': 1.0, 'frames': 60, 'loop': True}, 'HorseMount': {'length': .75, 'frames': 45, 'loop': False}}}}
