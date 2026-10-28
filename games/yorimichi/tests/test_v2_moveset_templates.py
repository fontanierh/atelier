"""Adventure move-set membership through FileSet templates: actual rows, projection bodies, derived rosters."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'tests')]
import v2_moveset_templates as templates  # noqa: E402
from test_v2_moveset_units import AnimSequence, Asset, MOVERS, body, editor, natives, recipe  # noqa: E402,F401

spec = importlib.util.spec_from_file_location('moveset_members_v2', ROOT / templates.BODY)
members = importlib.util.module_from_spec(spec); spec.loader.exec_module(members)


@pytest.fixture(scope='module')
def rows():
    """The actual recipe owns every export metadata and FBX root."""
    steps = recipe.adventure_steps(ROOT / 'build/yorimichi')
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def supplied():
    value = natives()
    for character in MOVERS:
        value[character.id].pop('export')
    return value


@pytest.fixture(scope='module')
def declared(rows):
    return templates.moveset_templates(rows, checkout=ROOT, natives=supplied())


def test_groups_follow_committed_rates_and_the_donor(declared):
    assert templates.bake_fps(ROOT) == 30
    assert set(declared['groups']) == {f'characters.{c.id.replace("-", "_")}_adventure.members.{kind}' for c in MOVERS
                                       for kind in ('clips', *(() if c.id == 'cairo' else ('own',)))}
    units = {u['id']: u for u in declared['units']}
    projector = units['characters.nox_adventure.members.own']
    assert projector['inputs'][0]['source'] == {'kind': 'item', 'unit': 'characters.nox_adventure', 'item': 'product0'}
    assert projector['params']['recipe']['paths'] == {
        'build/yorimichi/nox/adventure/export.json': 'inputs/export/products/0-0.tree.tar',
        'build/yorimichi/nox/adventure/fbx': 'inputs/export/products/0-1.tree.tar'}
    assert projector['params']['recipe']['commands'][0]['call']['defaults'][3:] == ['own', {'clips': 30, 'own': 60}]
    keys = {t['unit_prefix']: t for t in declared['templates']}
    raw, finish = (f['unit'] for f in keys['unreal.moveset.nox.own']['followers'])
    assert raw['params']['fbx']['custom_sample_rate'] == 60
    assert raw['params']['input_roots'] == {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}
    assert finish['params']['args'] == {'action': 'clip', 'name': '$piece', 'kind': 'own', 'fps': 60, 'meta': 'meta',
                                        'skeleton': 'skeleton', 'compression': 'compression'}
    # Each clip owner consumes only its own selected member, never the whole export Product.
    assert finish['params']['input_roots'] == {'meta': {'archive_member': 'meta.tree.tar', 'name': 'meta'}}
    for follower in (raw, finish):
        assert all(i['source']['unit'] != 'characters.nox_adventure' for i in follower['inputs'])
    assert {i['name']: i['source']['unit'] for i in finish['inputs']}['meta'] == '$export'
    assert finish['outputs'][0]['logical_path'] == MOVERS[2].adventure['dest'] + '/A_$piece'


def test_fixed_units_bind_actual_derived_clips(declared):
    keys = {(t['producer'], t['group'], t['unit_prefix']): t for t in declared['templates']}
    for token in (v for t in declared['tokens'].values() for v in t.values()):
        for source in token['derived_items']['templates']:
            follower = keys[(source['producer'], source['group'], source['unit_prefix'])]['followers'][source['follower']]['unit']
            assert source['item'] in {o['id'] for o in follower['outputs']}
    units = {u['id']: u for u in declared['units']}
    nox, cairo = declared['tokens']['nox'], declared['tokens']['cairo']
    assert units['unreal.moveset.nox.blend.Locomotion']['params']['args']['clips'] == nox['clips']
    assert units['unreal.moveset.nox.definition']['params']['args']['own'] == nox['own']
    assert units['unreal.moveset.nox.record']['params']['args']['clips'] == nox['clips']
    assert units['unreal.moveset.cairo.definition']['params']['args']['own'] == {} and 'own' not in cairo
    assert {i['name'] for i in units['unreal.moveset.cairo.definition']['inputs']} >= {'donor_DoubleJump', 'base', 'roster'}
    assert declared['aliases']['unreal.paul_adventure'][:2] == ('characters.paul_adventure.members.clips',
                                                                'characters.paul_adventure.members.own')


@pytest.mark.parametrize('damage', ['product', 'skeleton', 'command'])
def test_declaration_drift_refuses(rows, damage):
    rows, value = deepcopy(rows), supplied()
    found = {r['id']: r for r in rows}
    if damage == 'product':
        found['characters.paul_adventure']['products'][-1]['paths'].pop()
    elif damage == 'skeleton':
        value['nox'].pop('skeleton')
    else:
        found['unreal.modori_adventure']['commands'][0]['env'] = [['ADVENTURE_CHARACTER', 'paul']]
    with pytest.raises(ValueError):
        templates.moveset_templates(rows, checkout=ROOT, natives=value)


# ---- projection bodies ----------------------------------------------------------------------------------------------

def export_tree(tmp_path, *, own=True, clip_fps=30, own_fps=60):
    root = tmp_path / 'export'; (root / 'fbx').mkdir(parents=True)
    config = {'fps': 30, 'clips': {'Walk': {'frames': 40, 'fps': clip_fps}, 'Idle': {'frames': 60, 'fps': 30}},
              **({'own': {'DoubleJump': {'frames': 45, 'fps': own_fps}}} if own else {})}
    (root / 'export.json').write_text(json.dumps(config))
    for name in ('Walk', 'Idle', 'DoubleJump'):
        (root / 'fbx' / f'A_{name}.fbx').write_bytes(name.encode())
    return root


def project(root, tmp_path, kind, rates):
    output = tmp_path / 'out' / kind
    members.project(root / 'export.json', root / 'fbx', output, kind, rates)
    return output


def test_projection_emits_actual_fbx_members(tmp_path):
    root, rates = export_tree(tmp_path), {'clips': 30, 'own': 60}
    found = {}
    for kind in ('clips', 'own'):
        manifest = emit(project(root, tmp_path, kind, rates), tmp_path / 'files' / kind, parent='Nox_' + kind, extensions=['.json'])
        found[kind] = sorted(p['payload'] for p in manifest['pieces'])
    assert found == {'clips': ['Idle.json', 'Walk.json'], 'own': ['DoubleJump.json']}
    member = json.loads((tmp_path / 'files/own/DoubleJump.json').read_text())
    assert {k: member[k] for k in ('name', 'kind', 'frames', 'fps')} == {'name': 'DoubleJump', 'kind': 'own', 'frames': 45, 'fps': 60}


@pytest.mark.parametrize('damage', ['clip_rate', 'own_rate', 'donor_own', 'missing_own', 'fbx', 'overlap'])
def test_projection_refuses_an_export_that_differs(tmp_path, damage):
    root = export_tree(tmp_path, own=damage != 'missing_own', clip_fps=24 if damage == 'clip_rate' else 30,
                       own_fps=30 if damage == 'own_rate' else 60)
    rates = {'clips': 30} if damage == 'donor_own' else {'clips': 30, 'own': 60}
    if damage == 'fbx':
        (root / 'fbx/A_Idle.fbx').unlink()
    elif damage == 'overlap':
        config = json.loads((root / 'export.json').read_text()); config['own']['Walk'] = {'frames': 40, 'fps': 60}
        (root / 'export.json').write_text(json.dumps(config))
    with pytest.raises(ValueError):
        project(root, tmp_path, 'clips', rates)
    assert not (tmp_path / 'out').exists()


def test_select_unpacks_one_member_and_its_own_metadata(tmp_path):
    root = export_tree(tmp_path)
    output = project(root, tmp_path, 'clips', {'clips': 30, 'own': 60})
    selected = tmp_path / 'selected'; selected.mkdir(); (selected / 'Walk.json').write_bytes((output / 'Walk.json').read_bytes())
    members.select(selected, tmp_path / 'member', tmp_path / 'meta', 'Walk')
    assert (tmp_path / 'member/Walk.fbx').read_bytes() == b'Walk'
    assert json.loads((tmp_path / 'member/export.json').read_text()) == {
        'primary': 'Walk.fbx', 'sha256': hashlib.sha256(b'Walk').hexdigest()}
    assert json.loads((tmp_path / 'meta/meta.json').read_text()) == {'name': 'Walk', 'kind': 'clips', 'frames': 40, 'fps': 30}
    damaged = json.loads((selected / 'Walk.json').read_text()); damaged['sha256'] = '0' * 64
    (selected / 'Walk.json').write_text(json.dumps(damaged))
    with pytest.raises(ValueError):
        members.select(selected, tmp_path / 'member2', tmp_path / 'meta2', 'Walk')


# ---- derived rosters in the bodies ----------------------------------------------------------------------------------

def test_roster_reads_resolved_derived_items():
    value = {'derived_items': {'root': 'r', 'members': [{'piece': 'Walk', 'slot': 'derived_0', 'root': 'r/Walk'}]}}
    assert body._roster(value) == {'Walk': 'derived_0'} and body._roster({}) == {}
    with pytest.raises(ValueError):
        body._roster({'derived_items': {'root': 'r', 'templates': []}})


def test_derived_clip_finish_reads_frames_from_its_own_member(editor, tmp_path):
    skeleton, settings = Asset('/Game/Nox/SK_Nox_Skeleton'), Asset(body.COMPRESSION)
    raw = AnimSequence('/Game/_Raw/Moveset/nox/A_DoubleJump', skeleton=skeleton, sequence_length=45 / 60,
                       enable_root_motion=True, bone_compression_settings=None)
    editor.assets.update({raw.path: raw, skeleton.path: skeleton, settings.path: settings})
    meta = editor.root / 'inputs/meta'; meta.mkdir(parents=True)
    (meta / 'meta.json').write_text(json.dumps({'name': 'DoubleJump', 'kind': 'own', 'frames': 45, 'fps': 60}))
    destination = '/Game/Nox/Adventure/A_DoubleJump'
    context = NS(job_dir=str(editor.root), inputs={'raw': 'x', 'skeleton': 'x', 'compression': 'x', 'meta': str(meta)},
                 packages={'raw': [raw.path], 'skeleton': [skeleton.path], 'compression': [settings.path]}, outputs=[destination],
                 params={'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': destination,
                         'args': {'action': 'clip', 'name': 'DoubleJump', 'kind': 'own', 'fps': 60, 'meta': 'meta',
                                  'skeleton': 'skeleton', 'compression': 'compression'}})
    clip = body.run(context)
    assert clip.path == destination and clip.props['bone_compression_settings'] is settings
    del editor.assets[destination]
    context.params['args']['fps'] = 30
    with pytest.raises(ValueError, match='rate'):
        body.run(context)
