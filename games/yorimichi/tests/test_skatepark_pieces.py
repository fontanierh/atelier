"""Complete logical/runtime ownership and bounded piece repair for the actual pier producer."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, mesh_geometry

GAME = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('bounded_skatepark_pieces', GAME / 'world/regions/skatepark/pieces.py')
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)
SPEC = importlib.util.spec_from_file_location('bounded_skatepark_build', GAME / 'skatepark_build.py')
HOST = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(HOST)


def logical():
    return dict(meshes=[dict(name=name, asset='/Game/SkatePark/' + name, blocks=i < 5) for i, name in enumerate(P.PARENTS)],
                rails=[{'points': [[1, 2, 3], [4, 5, 6]]}], spawns={'park': [7, 8, 9]},
                clearance=[[[0, 0], [1, 0], [1, 1]]], trees={'tree': [[1, 2, 3]]},
                origin=[100, -200, 7], board={'wheel': 'original-board'}, features={'quarter': [-1, 1]})


def mesh(count):
    vertices, faces = [], []
    for i in range(count):
        x = i * 8 - 80
        at = len(vertices)
        vertices.extend([(x, -2, 0), (x + 1, -2, 0), (x, -1, 1)])
        faces.append([at, at + 1, at + 2])
    return vertices, faces


def test_each_complete_face_has_one_bounded_spatial_child_with_stable_cell_names(monkeypatch):
    monkeypatch.setattr(P, 'TRIANGLE_LIMIT', 3)
    vertices, faces = mesh(12)
    grouped = P.groups('SM_SkatePier', vertices, faces)
    assert len(grouped) > 1
    assert sorted(i for _, members in grouped for i in members) == list(range(12))
    assert all(sum(len(faces[i]) - 2 for i in members) <= 3 for _, members in grouped)
    assert all(P.owned_name(name) and name != 'SM_SkatePier' for name, _ in grouped)
    more_vertices, more_faces = mesh(13)
    more_vertices[-3:] = [(10000, -2, 0), (10001, -2, 0), (10000, -1, 1)]
    extended = P.groups('SM_SkatePier', more_vertices, more_faces)
    # Adding a far cell does not rename existing fixed cells/pieces.
    assert {name for name, _ in grouped} <= {name for name, _ in extended}


def test_small_mesh_keeps_its_original_asset_name_and_order():
    vertices, faces = mesh(2)
    assert P.groups('SM_SkatePath', vertices, faces) == [('SM_SkatePath', (0, 1))]


def test_runtime_expansion_preserves_every_other_logical_field_and_collision_flag():
    source = logical(); before = copy.deepcopy(source)
    members = {name: [name] for name in P.PARENTS}
    parent = P.PARENTS[0]
    members[parent] = [parent + '_Piece' + c * 16 for c in ('a', 'b')]
    result = P.runtime_park(source, members)
    assert source == before
    assert {k: v for k, v in result.items() if k != 'meshes'} == {k: v for k, v in source.items() if k != 'meshes'}
    assert parent not in {row['name'] for row in result['meshes']}
    assert len(result['meshes']) == len(source['meshes']) + 1
    assert all(row['blocks'] is True for row in result['meshes'][:2])
    assert result['meshes'][-1]['blocks'] is False


def test_normal_generator_checks_the_authored_logical_input_without_rewriting_it(tmp_path):
    path = tmp_path / 'park.json'
    source = logical(); path.write_text(json.dumps(source) + '\n')
    before = path.read_bytes()
    P.validate_logical_contract(path, source)
    source['origin'] = tuple(source['origin'])
    P.validate_logical_contract(path, source)
    changed = copy.deepcopy(source); changed['spawns']['park'][0] += 1
    with pytest.raises(ValueError, match='logical contract changed'):
        P.validate_logical_contract(path, changed)
    assert path.read_bytes() == before


@pytest.mark.parametrize('damage', ['missing-parent', 'duplicate-piece', 'foreign-piece', 'parent-and-piece', 'collision'])
def test_invalid_runtime_membership_never_publishes(damage):
    source = logical(); members = {name: [name] for name in P.PARENTS}; parent = P.PARENTS[0]
    if damage == 'missing-parent': members.pop(parent)
    elif damage == 'duplicate-piece': members[parent] = [parent, parent]
    elif damage == 'foreign-piece': members[parent] = [P.PARENTS[1]]
    elif damage == 'parent-and-piece': members[parent].append(parent + '_Piece' + 'a' * 16)
    else: source['meshes'][0]['blocks'] = 1
    with pytest.raises(ValueError):
        P.runtime_park(source, members)


def exports(folder):
    rows = []
    for name in P.PARENTS:
        path = folder / (name + '.fbx'); path.write_bytes(name.encode())
        rows.append(dict(name=name, parent=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return rows


def test_superseded_parent_retires_only_after_all_current_exports_pass(tmp_path):
    rows = exports(tmp_path); parent = P.PARENTS[0]; child = parent + '_Piece' + 'a' * 16
    path = tmp_path / (child + '.fbx'); path.write_bytes(b'complete child')
    rows[0] = dict(name=child, parent=parent, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert P.retire_exports(tmp_path, rows) == [parent + '.fbx']
    assert path.exists() and not (tmp_path / (parent + '.fbx')).exists()


@pytest.mark.parametrize('damage', ['incomplete-roster', 'missing', 'changed', 'linked', 'foreign'])
def test_export_failure_preserves_every_old_owned_file(tmp_path, damage):
    rows = exports(tmp_path)
    stale = tmp_path / (P.PARENTS[0] + '_Piece' + 'b' * 16 + '.fbx'); stale.write_bytes(b'old complete')
    if damage == 'incomplete-roster': rows.pop()
    elif damage == 'missing': (tmp_path / (rows[0]['name'] + '.fbx')).unlink()
    elif damage == 'changed': (tmp_path / (rows[0]['name'] + '.fbx')).write_bytes(b'changed')
    elif damage == 'linked':
        path = tmp_path / (rows[0]['name'] + '.fbx'); path.unlink(); path.symlink_to(stale)
    else: (tmp_path / 'Foreign.fbx').write_bytes(b'foreign')
    with pytest.raises((ValueError, OSError)):
        P.retire_exports(tmp_path, rows)
    assert stale.read_bytes() == b'old complete'


def test_linked_output_ancestor_refuses_before_writes_or_retirement(tmp_path):
    external = tmp_path / 'external'; assets = external / 'assets'; assets.mkdir(parents=True)
    rows = exports(assets); old = assets / (P.PARENTS[0] + '_Piece' + 'a' * 16 + '.fbx')
    old.write_bytes(b'protected external file')
    link = tmp_path / 'skatepark'; link.symlink_to(external, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in assets.iterdir()}
    with pytest.raises(ValueError, match='ancestor'):
        P.preflight_tree(link / 'new-directory')
    with pytest.raises(ValueError, match='ancestor'):
        P.retire_exports(link / 'assets', rows)
    assert not (external / 'new-directory').exists()
    assert {p.name: p.read_bytes() for p in assets.iterdir()} == before


def test_native_presence_requires_every_package_and_optional_sidecar(tmp_path):
    out = tmp_path / 'build'; root = out / 'skatepark'; root.mkdir(parents=True)
    content = tmp_path / 'Content'; content.mkdir()
    runtime = logical(); runtime_path = root / 'runtime-park.json'; runtime_path.write_text(json.dumps(runtime))
    assets = [row['asset'] for row in runtime['meshes']]
    assets += ['/Game/SkatePark/Board/' + name for name in ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel')]
    for asset in assets:
        path = content / (asset[len('/Game/'):] + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.encode())
    sidecar = (content / (assets[0][len('/Game/'):] + '.ubulk')); sidecar.write_bytes(b'bulk')
    report = dict(park={row['name']: {} for row in runtime['meshes']}, assets=assets,
                  runtime_park_sha256=hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
                  files=mesh_geometry.package_inventory(content, assets))
    (root / 'import-report.json').write_text(json.dumps(report))
    owner = build.Step('unreal.skatepark', [], outputs=[root / 'import-report.json'],
                       verify=lambda: HOST.present(out, content))
    assert build.outputs_present(owner)
    sidecar.unlink()
    assert not build.outputs_present(owner)


def test_normal_recipe_declares_complete_piece_products_native_owner_and_runtime_staging(tmp_path):
    recipe = build.load_recipe('yorimichi')
    steps = {s.name: s for s in recipe.steps(SimpleNamespace(out=tmp_path, uproject=None))}
    product = next(p for p in steps['world.skatepark'].products if p.name == 'skatepark.meshes')
    assert product.name == 'skatepark.meshes'
    assert tmp_path / 'skatepark/assets' in product.roots()
    runtime = next(p for p in steps['world.skatepark'].products if p.name == 'skatepark.runtime')
    assert tmp_path / 'skatepark/runtime-park.json' in runtime.roots()
    assert 'skatepark.meshes' in steps['unreal.skatepark'].reads
    assert 'skatepark.runtime' in steps['data.stage'].reads
    assert 'skatepark.meshes' not in steps['data.stage'].reads
    assert 'skatepark.textures' in steps['unreal.skatepark'].reads
    assert recipe.WORLD / 'mesh_pieces.py' in steps['world.skatepark'].inputs
    # City pieces now use the same exact copier; their cutoffs and unrelated
    # producers still do not consume it merely because their outputs feed pieces.
    for source in ('HD_Terrain', 'HD_Streets', 'HD_Square'):
        assert recipe.WORLD / 'mesh_pieces.py' in steps['world.city_tiles.' + source].inputs
        assert recipe.WORLD / 'mesh_pieces.py' not in steps['world.hidamari.tiles.' + source].inputs
    for name in ('world.hidamari', 'world.city_tiles', 'world.city_trees'):
        assert recipe.WORLD / 'mesh_pieces.py' not in steps[name].inputs
    assert steps['unreal.skatepark'].commands[0].modules == recipe.IMPORT_CODE
    assert recipe.runtime_data.staged_source(tmp_path, 'skatepark/park.json') == tmp_path / 'skatepark/runtime-park.json'


def test_real_portable_texture_fingerprint_has_complete_offline_closure(tmp_path):
    recipe = build.load_recipe('yorimichi')
    steps = {s.name: s for s in recipe.steps(SimpleNamespace(out=tmp_path, uproject=None))}
    step = steps['world.skatepark_textures']
    assert step.commands[0].script.name == 'pier_texture_finish.py'
    assert not any('treehouse_art' in str(p) or '/atelier/ai/' in str(p) for p in step.inputs)
    # Exercise named-product source admission, not only the visible graph metadata.
    assert len(build.fingerprint(step, {})) == 64
