"""Pinned editor geometry round trips; no Blender, game or native physics needed."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2.editor import diagnostic, frontend  # noqa: E402

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='editor compiler needs Node.js')


def document(pieces):
    return {'schema': 'craterpark-editor/1', 'terrain': 'dug', 'rev': 1,
            'lines': [{'id': 'L1', 'color': '#3366aa'}], 'pieces': pieces}


def piece(kind, name=None, **params):
    return {'id': name or kind, 'type': kind, 'line': 'L1', 'x': 1000, 'z': 800,
            'y': 100, 'heading': 23, 'slope': -5, 'params': params, 'next': []}


def inputs(tmp_path, doc):
    src = tmp_path / 'input'
    src.mkdir()
    data = src / 'data'
    data.mkdir()
    meta = {'inner': {'x0': 700, 'z0': 500, 'G': 20, 'nx': 32, 'nz': 32, 'cell_centred': True,
                      'layers': {'natural': 'natural.bin', 'dug': 'dug.bin'}},
            'outer': {'x0': 0, 'z0': 0, 'G': 100, 'nx': 32, 'nz': 32, 'cell_centred': False, 'file': 'outer.bin'}}
    (data / 'terrain.json').write_text(json.dumps(meta))
    for name, h in [('natural', 20), ('dug', -10), ('outer', 5)]:
        np.full((32, 32), h, '<f4').tofile(data / f'{name}.bin')
    path = src / 'park.json'
    path.write_text(json.dumps(doc))
    return path


def compile_at(tmp_path, doc):
    path = inputs(tmp_path, doc)
    before = path.read_bytes()
    snapshot = frontend.snapshot(path, tmp_path / 'snapshot')
    scene = frontend.compile_snapshot(snapshot, tmp_path / 'node')
    assert path.read_bytes() == before
    return scene


def validate(doc):
    code = "const B=require(process.argv[1]); B.validate(JSON.parse(require('fs').readFileSync(0,'utf8')));"
    return subprocess.run([NODE, '-e', code, str(frontend.HERE / 'bridge.cjs')],
                          input=json.dumps(doc), capture_output=True, text=True, timeout=10)


def test_all_nine_types_round_trip(tmp_path):
    specs = [piece('run', bank=17, turn=70, width=18, width_end=32, wl={'h': 9, 'R': 6}),
             piece('rollin', drop=45, turn=-30), piece('jump', rail=True),
             piece('kicker'), piece('landing'), piece('qp', h=9, R=6),
             piece('bowl', outline=[[-30, -25], [18, -26], [28, 0], [15, 22], [-25, 30]], wall_h=8),
             piece('deck'), piece('rail')]
    scene = compile_at(tmp_path, document(specs))
    target = tmp_path / 'proof.glb'
    diagnostic.write_glb(scene, target)
    report = diagnostic.compare(scene, target)
    assert set(report['by_type']) == {p['type'] for p in specs}
    assert report['parity_ok'] and not report['accepted']
    assert all(r['editor_float32_exact'] and r['surface_max_error_bound_m'] < .0002
               and r['centerline_max_error_m'] == 0 for r in report['pieces'])
    assert sum(len(p.mesh.F) for p in scene.pieces) > 1000
    # All raw arrays are reusable compiler Meshes, with exact Node normals and topology.
    for entry, p in zip(scene.metadata['pieces'], scene.pieces):
        np.testing.assert_array_equal(frontend.read_array(tmp_path / 'node', entry['arrays']['pos'], 3), p.mesh.V)


def test_attach_uses_unrounded_parent_exit_and_next_does_not_join(tmp_path):
    parent = piece('run', 'parent', len=13.1234, slope=-12, vR=10)
    child = piece('run', 'child')
    child.update(attach='parent', x=-999, y=-999, z=-999, heading=-100, slope=20)
    flight = piece('kicker', 'flight')
    flight['next'] = ['child']
    scene = compile_at(tmp_path, document([child, flight, parent]))
    c, f, p = scene.pieces
    assert c.metadata['pose'] == p.metadata['exit']
    assert f.metadata['next'] == ['child']
    assert f.metadata['exit'] != c.metadata['pose']
    assert any(abs(v-round(v, 3)) > 1e-6 for v in c.metadata['pose'].values())


def test_jump_retains_open_gap_and_qp_vertical(tmp_path):
    scene = compile_at(tmp_path, document([piece('jump', open=30), piece('qp', h=9, R=6)]))
    jump, qp = scene.pieces
    b = jump.metadata
    assert len(b['segs']) == 2
    assert b['info']['knuckle']['d'] - b['info']['lip']['d'] == pytest.approx(30)
    lip, knuckle = b['info']['lip']['d'], b['info']['knuckle']['d']
    forward = np.array([np.cos(np.radians(23)), 0, np.sin(np.radians(23))])
    d = (jump.mesh.V - [1000, 100, 800]) @ forward
    assert not np.any((d > lip + 1e-8) & (d < knuckle - 1e-8))
    stations = qp.metadata['stations']
    assert any(abs(a['d']-c['d']) < 1e-8 and c['y']-a['y'] > 2.9
               for a, c in zip(stations, stations[1:]))
    assert qp.metadata['exit']['h'] == pytest.approx(-157)


def test_terrain_choice_affects_solid_deck_and_display(tmp_path):
    doc = document([piece('deck')])
    dug = compile_at(tmp_path, doc)
    other = tmp_path / 'other'
    other.mkdir()
    doc['terrain'] = 'natural'
    natural = compile_at(other, doc)
    assert dug.pieces[0].mesh.V[:, 1].min() == -11
    assert natural.pieces[0].mesh.V[:, 1].min() == 19
    np.testing.assert_allclose(natural.terrain[0].V[:, 1] - dug.terrain[0].V[:, 1], 30)


@pytest.mark.parametrize('mutate,message', [
    (lambda d: d['pieces'][0].update(type='future'), 'unknown piece type'),
    (lambda d: d['pieces'][0]['params'].update(wings=True), 'unknown parameter'),
    (lambda d: d['pieces'][0]['params'].update(wl={'radius2': 4}), 'unknown parameter'),
    (lambda d: d['pieces'][0].update(attach='missing'), 'missing attach'),
    (lambda d: d['pieces'][0].update(attach='run'), 'attach cycle'),
    (lambda d: d['pieces'][0].update(next=['missing']), 'missing next'),
    (lambda d: d['pieces'].append(deepcopy(d['pieces'][0])), 'duplicate'),
    (lambda d: d.update(terrain='new-layer'), 'terrain choice'),
    (lambda d: d['pieces'][0]['params'].update(width='18'), 'finite number'),
])
def test_rejects_unknown_and_broken_designs(mutate, message):
    doc = document([piece('run')])
    mutate(doc)
    result = validate(doc)
    assert result.returncode != 0 and message in result.stderr


def test_changed_snapshot_or_live_geometry_fails_closed(tmp_path):
    path = inputs(tmp_path, document([piece('run')]))
    (path.parent / 'pieces.js').write_text('changed geometry')
    with pytest.raises(ValueError, match='pinned compiler'):
        frontend.snapshot(path, tmp_path / 'bad-pin')
    (path.parent / 'pieces.js').unlink()
    frozen = frontend.snapshot(path, tmp_path / 'snapshot')
    (frozen / 'park.json').write_text('{}')
    with pytest.raises(ValueError, match='changed'):
        frontend.compile_snapshot(frozen, tmp_path / 'node')


def test_modified_export_is_not_a_pass(tmp_path):
    scene = compile_at(tmp_path, document([piece('run')]))
    target = tmp_path / 'proof.glb'
    diagnostic.write_glb(scene, target)
    scene.pieces[0].mesh.V = scene.pieces[0].mesh.V.copy()
    scene.pieces[0].mesh.V[0, 0] += .01
    with pytest.raises(ValueError, match='parity failed'):
        diagnostic.compare(scene, target)


APP = Path(__file__).resolve().parents[1] / 'tools' / 'craterpark_editor'


def test_repository_editor_uses_the_pinned_compiler_and_ships_its_designs():
    pin = json.loads((Path(frontend.__file__).parent / 'pin.json').read_text())
    assert frontend.sha((APP / 'pieces.js').read_bytes()) == pin['pieces_sha256']
    page = (APP / 'index.html').read_text()
    for script in ('vendor/three.min.js', 'vendor/OrbitControls.js', 'pieces.js', 'app.js'):
        assert f'src="{script}"' in page and (APP / script).is_file()
    terrain = json.loads((APP / 'data' / 'terrain.json').read_text())
    assert all((APP / 'data' / name).is_file() for name in [*terrain['inner']['layers'].values(), terrain['outer']['file']])
    designs = sorted((APP / 'designs').glob('craterpark-rev*.json'))
    assert designs and all(json.loads(d.read_text())['schema'] == 'craterpark-editor/1' for d in designs)
