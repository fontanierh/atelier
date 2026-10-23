"""Pure fault injection for Track input/owner/receiving proof boundaries; no native jobs."""
import ast
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import track_native_equivalence as proof
from run_track_native_equivalence import strict_cleanup


def runtime():
    result = dict(meshes={}, pieces=[], instances=[])
    for n in range(137):
        name = f'SM_TK_Test_{n}'; levels = 3 if n < 112 else 2 if n == 112 else 1
        result['meshes'][name] = dict(lods=[f'meshes/{name}_LOD{k}.glb' for k in range(levels)],
            screen_sizes=[1., .3, .05][:levels], materials=['MI_B_wood'])
        result['pieces'].append(dict(name=name, collision=levels - 1 if n < 2 else -1))
    return result


def test_complete_code_inputs_accept_empty_init_without_weakening_artifact_rules(tmp_path):
    path = tmp_path / '__init__.py'; path.write_bytes(b'')
    proof.check_input(path, proof.sha(path))
    with pytest.raises(ValueError): proof.artifact(dict(path=str(path), sha256=proof.sha(path)))
    digest = proof.sha(path); path.write_bytes(b'changed')
    with pytest.raises(ValueError): proof.check_input(path, digest)
    path.unlink(); path.symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError): proof.check_input(path, digest)


def test_production_census_retains_every_authored_lod_but_never_injects_marker():
    value = runtime(); assert len(proof.runtime_inventory(value)) == 137
    assert sum(proof.runtime_inventory(value).values()) == 362
    for bad in ('missing', 'marker', 'lod', 'screen', 'escape'):
        changed = copy.deepcopy(value); first = next(iter(changed['meshes']))
        if bad == 'missing': changed['meshes'].pop(first)
        elif bad == 'marker': changed['meshes']['SM_TK_Marker'] = changed['meshes'].pop(first)
        elif bad == 'lod': changed['meshes'][first]['lods'].pop()
        elif bad == 'screen': changed['meshes'][first]['screen_sizes'][-1] = .3
        else: changed['meshes'][first]['lods'][0] = '../outside.glb'
        with pytest.raises(ValueError): proof.runtime_inventory(changed)


def test_two_literal_namespace_mapping_preserves_the_entire_real_importer_ast():
    path = HERE.parents[1] / 'unreal/Scripts/import_belmonte_track.py'
    original = proof.owner_tree(path)
    root = '/Game/AtelierValidation/Track_0123456789ab/Prerequisites/Materials'
    mapped = proof.owner_tree(path, root)
    assert ast.dump(original) != ast.dump(mapped)
    seen = []
    for node in ast.walk(mapped):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(root):
            seen.append(node.value); node.value = '/Game/Belmonte/Materials' + node.value.removeprefix(root)
    assert len(seen) == 2 and ast.dump(original) == ast.dump(mapped)
    with pytest.raises(ValueError): proof.owner_tree(path, '/Game/Belmonte/Materials')


def test_changed_importer_refuses_before_loading_any_definition(tmp_path):
    original = HERE.parents[1] / 'unreal/Scripts/import_belmonte_track.py'
    changed = tmp_path / 'importer.py'; changed.write_bytes(original.read_bytes() + b'\nforeign_change = True\n')
    with pytest.raises(ValueError, match='exact reviewed'): proof.owner_tree(changed)


def test_deletion_observer_records_real_packages_without_replacing_api_results():
    root = '/Game/AtelierValidation/Track_0123456789ab/Library'; calls = []; owned = set()
    editor = SimpleNamespace(list_assets=lambda *args, **kw: [root + '/Source/Part.Part'],
        delete_directory=lambda path: calls.append(path) or False, save_loaded_asset=object())
    boundary = proof.ObserveDeletion(editor, root, owned)
    assert boundary.delete_directory(root + '/Source') is False
    assert calls == [root + '/Source'] and owned == {root + '/Source/Part'}
    assert boundary.save_loaded_asset is editor.save_loaded_asset
    with pytest.raises(ValueError): boundary.delete_directory('/Game/Foreign')
    assert len(calls) == 1


@pytest.mark.parametrize('bad', ['missing', 'bytes', 'size', 'link', 'directory', 'ground'])
def test_actual_material_inputs_refuse_without_creating_any_output(tmp_path, bad):
    textures = tmp_path / 'textures'; textures.mkdir(); path = textures / 'Ground.png'; path.write_bytes(b'actual donor bytes')
    report = dict(materials={'Ground': dict(name='MI_Ground', texture='Ground.png', atlas=False, terrain=True,
        water=False, white_vertex=False, colour=[1, 1, 1, 1], tint=[1, 1, 1, 1], layers={}, tile_m=1, brightness=1)},
        files={'textures/Ground.png': dict(sha256=proof.sha(path), size=path.stat().st_size)})
    assert proof.material_inputs(report, tmp_path) == (['MI_Ground'], {'Ground.png'})
    if bad == 'missing': path.unlink()
    elif bad == 'bytes': path.write_bytes(b'changed')
    elif bad == 'size': report['files']['textures/Ground.png']['size'] += 1
    elif bad == 'link': path.unlink(); path.symlink_to(tmp_path / 'external')
    elif bad == 'directory': path.unlink(); path.mkdir()
    else: report['materials']['Ground']['terrain'] = False
    with pytest.raises((ValueError, FileNotFoundError)): proof.material_inputs(report, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {'textures'}


@pytest.mark.parametrize('field', ['source_lods', 'render_lods', 'cooked', 'hulls', 'policy', 'settings', 'source_presence', 'sphere', 'probe'])
def test_paired_census_never_weakens_saved_geometry_or_bounds(tmp_path, monkeypatch, field):
    value = runtime(); records = dict(original={}, current={})
    for name, levels in proof.runtime_inventory(value).items():
        mesh = '/Game/Fixture/' + name + '.' + name
        policy = tmp_path / (name + '.json')
        policy.write_text(json.dumps(dict(mesh=mesh, mesh_bounds=[[-1, -1, -1], [1, 1, 1]], bounds_scale=1,
            component_bounds=dict(origin=[0, 0, 0], extent=[1, 1, 1], sphere_radius=2), lod_coordinated=False)))
        kinds = ['ray_negative', 'capsule_negative']
        if proof.collision_lods(value)[name] >= 0: kinds += ['ray_positive', 'capsule_positive']
        row = dict(meshes=[mesh], component_policies=[dict(path=str(policy), sha256=proof.sha(policy))], policy_scope='fixture',
            **{k: [] for k in proof.FIELDS})
        row.update(render_lods={k: ['actual'] for k in range(levels)}, source_lods={k: ['saved'] for k in range(levels)},
            probes=dict(logical=name, controls=[dict(kind=k, hit=None if k.endswith('_negative') else {'blocking': True}) for k in kinds]))
        records['original'][name] = row; records['current'][name] = copy.deepcopy(row)
    monkeypatch.setattr(proof, 'native_raw_set', lambda record, name: record)
    accepted = proof.compare(records, value)
    assert accepted['native_geometry_complete'] and accepted['meshes'] == 137 and accepted['authored_lods'] == 362
    assert not accepted['complete'] and not accepted['native_complete'] and not accepted['production_runtime_complete']
    name = next(iter(value['meshes'])); row = records['current'][name]
    if field == 'sphere':
        policy = tmp_path / 'changed.json'; old = json.loads(proof.artifact(row['component_policies'][0]))
        old['component_bounds']['sphere_radius'] = 2.1; policy.write_text(json.dumps(old))
        row['component_policies'] = [dict(path=str(policy), sha256=proof.sha(policy))]
    elif field == 'probe': row['probes']['controls'].pop()
    elif field in ('source_lods', 'render_lods'): row[field][0].append('changed actual corner')
    else: row[field].append('changed actual evidence')
    with pytest.raises(ValueError): proof.compare(records, value)


@pytest.mark.parametrize('bad', ['bytes', 'link', 'directory', 'foreign'])
def test_host_cleanup_refuses_every_changed_member_before_any_unlink(tmp_path, bad):
    package = '/Game/AtelierValidation/Track_0123456789ab'
    content = tmp_path / 'Content'; root = content / package.removeprefix('/Game/'); root.mkdir(parents=True)
    first = root / 'First.uasset'; first.write_bytes(b'first actual fixture package')
    second = root / 'Second.uasset'; second.write_bytes(b'second actual fixture package')
    allowed = [package + '/First', package + '/Second']
    record = dict(root=str(root), remaining=proof.fixture_files(root, allowed, package), allowed_packages=allowed)
    if bad == 'bytes': second.write_bytes(b'changed')
    elif bad == 'link': second.unlink(); second.symlink_to(first)
    elif bad == 'directory': second.unlink(); second.mkdir()
    else: (root / 'Foreign.uasset').write_bytes(b'foreign')
    with pytest.raises(ValueError): strict_cleanup(dict(content=str(content), package=package), record)
    assert first.read_bytes() == b'first actual fixture package'
