"""unreal.skate_clips as native units: the actual rows, the original scoped helpers, projection over a real clip subset."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_skate_clip_units as units  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module); return module


members = load(units.BODY, 'skate_clip_members_test')
body = load(units.SCRIPT, 'skate_clip_body_test')
BANKS, COUNT = units.roster(ROOT)
# The classes the native controller admits for authored assets, with the three root is adding (#30417).
AUTHORED = {'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Map', 'Blueprint', 'BlendSpace1D',
            'AdventureMoveSet', 'AnimBoneCompressionSettings', 'WandererDefinition', 'SoundAttenuation', 'DataAsset', 'JsonData',
            'Animation', 'AnimCurveCompressionSettings', 'MirrorDataTable'}
OTHERS = {'Data', 'RawSkeletalMesh', 'Skeleton', 'SkeletalMesh'}


@pytest.fixture(scope='module')
def rows():
    spec = importlib.util.spec_from_file_location('skate_clip_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['skate_clip_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [s for s in recipe.steps(context) if s.name in ('skate.runtime', 'unreal.skate_clips')]
    for step in steps:
        step.needs = [n for n in step.needs if n == 'skate.runtime']; step.after = []; step.reads = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def declared(rows):
    return units.skate_clip_units(rows, checkout=ROOT)


def test_every_owner_from_the_actual_rows(declared):
    assert COUNT == 3324 and {b: len(n) for b, n in BANKS.items()} == {0: 2672, 1: 652}
    found = {u['id']: u for u in declared['units']}
    constants = members.constants(ROOT / units.ORIGINALS[0], ('STILLS', 'CONTROL'))
    assert sorted(found) == sorted([
        'skate_clips.rig', 'skate_clips.members.b0', 'skate_clips.members.b1', 'unreal.skate_clips.rider.raw',
        'unreal.skate_clips.rider', 'unreal.skate_clips.ACL_SkateRideExact', 'unreal.skate_clips.CC_SkateRideExact',
        'unreal.skate_clips.MDT_SkateRider', *(f'unreal.skate_clips.still.{n}' for n in constants['STILLS']),
        'unreal.skate_clips.control', 'unreal.skate_clips.manifest', 'unreal.skate_clips.report'])
    package = found['skate_clips.members.b0']['inputs'][0]
    assert package['source'] == {'kind': 'item', 'unit': 'skate.runtime', 'item': 'output1'} and 'whole' in package
    assert found['skate_clips.members.b0']['params']['recipe']['paths']['build/yorimichi/skate-simulation/package'] == \
        'inputs/package/outputs/1.tree.tar'
    raw = found['unreal.skate_clips.rider.raw']['params']
    assert raw['kind'] == 'skeletal_mesh' and raw['create_physics_asset'] is False and 'fbx' not in raw
    assert found['unreal.skate_clips.rider']['params']['partners'] == {'skeleton': '/Game/SkateRide/SKEL_SkateRider'}
    assert found['unreal.skate_clips.manifest']['outputs'][0]['files'][0]['install_path'] == units.CLIPS_FILE
    assert found['unreal.skate_clips.report']['params']['args']['count'] == 3324
    still = found['unreal.skate_clips.still.OLLIE_HIGH_G']['params']['args']['sequence']['derived_items']['templates'][0]
    assert still == {'producer': 'skate_clips.members.b0', 'group': 'members', 'unit_prefix': 'unreal.skate_clips.b0',
                     'follower': 0, 'item': 'asset', 'piece': 'OLLIE_HIGH_G'}
    templates = {t['unit_prefix']: t for t in declared['templates']}
    assert sorted(templates) == ['unreal.skate_clips.b0', 'unreal.skate_clips.b1']
    clip, verify = (f['unit'] for f in templates['unreal.skate_clips.b1']['followers'])
    assert clip['outputs'][0]['logical_path'] == '/Game/SkateRide/Clips/B1/$piece' and clip['params']['args']['bank'] == 1
    assert {i['name'] for i in clip['inputs']} == {'member', 'bundle', 'skeleton', 'mesh', 'bone', 'curve'}
    assert {i['name']: i['source']['unit'] for i in verify['inputs']}['sequence'] == '$previous'
    for template in declared['templates']:
        for follower in template['followers']:
            assert all(i['source']['unit'] not in ('skate.runtime', template['producer']) for i in follower['unit']['inputs'])
    assert declared['aliases']['unreal.skate_clips'] == tuple(found)


def test_emitted_output_classes_are_registered(declared):
    followers = [f['unit'] for t in declared['templates'] for f in t['followers']]
    for unit in [*declared['units'], *followers]:
        allowed = AUTHORED if unit['op']['kind'] == 'unreal.author' else OTHERS
        assert {o['class'] for o in unit['outputs']} <= allowed, unit['id']
        if unit['op']['kind'] == 'unreal.author' and unit['outputs'][0]['class'] == 'JsonData':
            assert len(unit['outputs']) == 1 and len(unit['outputs'][0]['files']) == 1


@pytest.mark.parametrize('damage', ['batch', 'outputs', 'producer'])
def test_declaration_drift_refuses(rows, damage):
    rows = deepcopy(rows)
    found = {r['id']: r for r in rows}
    if damage == 'batch':
        found['unreal.skate_clips']['commands'][0]['env'] = [['SKATE_RIDE_BATCH', '2/2']]
    elif damage == 'outputs':
        found['unreal.skate_clips']['outputs'] = found['unreal.skate_clips']['outputs'][:1]
    else:
        found['skate.runtime']['products'] = [{'id': 'x', 'paths': ['y']}]
    with pytest.raises(Unsupported):
        units.skate_clip_units(rows, checkout=ROOT)


# ---- the original scoped helpers ------------------------------------------------------------------------------------

def test_original_helpers_are_scoped_reads():
    source = (ROOT / units.ORIGINALS[0]).read_text()
    for names in (body.IMPORT, members.RECORDS):
        members.original(ROOT / units.ORIGINALS[0], names, {'U': None, 'N': None, 'math': None, 'json': None})
    members.original(ROOT / units.ORIGINALS[1], body.VERIFY, {'U': NS(AnimDataEvalType=NS(COMPRESSED=1)), 'N': None})
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compression_assets')
    bone, curve = (ast.unparse(body._split(function, t)) for t in ('bone', 'curve'))
    assert "create('ACL_SkateRideExact'" in bone and 'CC_SkateRideExact' not in bone
    assert "create('CC_SkateRideExact'" in curve and 'ACL_SkateRideExact' not in curve
    document = ast.unparse(body.still_document((ROOT / units.ORIGINALS[1]).read_text()))
    assert 'write_text' not in document and 'POSES' not in document and 'return dict(clip=name, fps=fps, frames=frames)' in document
    head = ast.unparse(body._statements(source, 'setup', ('reference', 'head')))
    assert head.startswith('reference = []') and 'head = dict(' in head and 'delete_directory' not in head
    report = ast.unparse(body._statements((ROOT / units.ORIGINALS[1]).read_text(), 'main',
                                          ('clips', 'overall', 'worst_clip', 'over', 'stored_all', 'report')))
    assert report.startswith("clips = state['clips']") and 'report = dict(' in report and 'write_text' not in report
    manifest = ast.unparse(body._statements(source, 'main', ('manifest',)))
    assert manifest.startswith('manifest = dict(') and manifest.count('\n') == 0


def test_report_aggregates_like_the_original(tmp_path):
    def measured(t):
        return dict(frames=2, fps=30., translation_cm=t, rotation_rad=0., scale=0., where={}, curve_error=0.,
                    curves_missing=[], euler_storage=[], bones={})
    source = (ROOT / units.ORIGINALS[1]).read_text()
    scope = {'LIMITS': members.constants(ROOT / units.ORIGINALS[1], ('LIMITS',))['LIMITS'], 'rig': NS(bones=[1, 2]),
             'state': {'clips': {'A': measured(.001), 'B': measured(.02)}, 'control': {'clip': 'A'}}, 'manifest': {'partial': False}}
    exec(compile(body._statements(source, 'main', ('clips', 'overall', 'worst_clip', 'over', 'stored_all', 'report')), 'main', 'exec'), scope)
    report = scope['report']
    assert report['clips'] == 2 and report['passed'] is False and report['over_limit'] == {'translation_cm': ['B']}
    assert report['worst_clip']['translation_cm'] == 'B' and report['partial'] is False


# ---- projection over the actual assembled package ------------------------------------------------------------------

@pytest.fixture(scope='module')
def package(tmp_path_factory):
    """skate.runtime's own assembly of the committed simulation data (about ten seconds)."""
    import subprocess
    root = tmp_path_factory.mktemp('skate')
    subprocess.run([sys.executable, str(ROOT / units.PACKAGER), '--assemble', str(root / 'package'),
                    '--output', str(root / 'verification.json')], check=True, capture_output=True)
    return root / 'package'


def test_bank_members_are_each_clips_own_view(package, tmp_path):
    scripts, manifest = ROOT / units.SCRIPTS, ROOT / units.MANIFEST
    members.project(package, manifest, scripts, tmp_path / 'b1', 1)
    files = sorted(p.stem for p in (tmp_path / 'b1').iterdir())
    assert files == sorted(BANKS[1]) and len(files) == 652
    name = files[0]
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / f'{name}.json').write_bytes((tmp_path / f'b1/{name}.json').read_bytes())
    members.select(selected, tmp_path / 'member', name)
    assert (tmp_path / 'member/clip.skate').read_bytes() == (package / f'animation/clips/1/{name}.skate').read_bytes()
    member = json.loads((tmp_path / 'member/member.json').read_text())
    N = members.module(scripts / 'simulation.py', 'skate_ride_simulation')
    expected = {c.name: c for bank in N.Bundle(package).metadata() for c in bank.clips}.get(name)
    assert members.clip_metadata(N, member['metadata']) == expected
    assert member['record']['bank'] == 1 and member['record']['frames'] == N.load_clip((tmp_path / 'member/clip.skate').read_bytes()).frame_count
    members.rig(package, scripts, tmp_path / 'rig/mesh', tmp_path / 'rig/bundle')
    receipt = json.loads((tmp_path / 'rig/mesh/export.json').read_text())
    assert receipt['primary'] == 'SK_SkateRider.glb' and sorted(p.name for p in (tmp_path / 'rig/mesh').iterdir()) == ['SK_SkateRider.glb', 'export.json']
    assert (tmp_path / 'rig/bundle/animation/rig.skate').read_bytes() == (package / 'animation/rig.skate').read_bytes()


def test_projection_refuses_a_clip_that_differs_from_the_committed_manifest(package, tmp_path):
    import shutil
    copy = tmp_path / 'package'
    shutil.copytree(package, copy)
    target = copy / f'animation/clips/1/{BANKS[1][0]}.skate'
    target.write_bytes(target.read_bytes() + b'\0')
    with pytest.raises(ValueError, match='committed checksum'):
        members.members(copy, ROOT / units.MANIFEST, ROOT / units.SCRIPTS, 1)
