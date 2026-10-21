"""Execute the actual mixed-model boundary with complete per-corner data."""
import ast
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import sys

from atelier.mesh_partition import face_groups

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world/regions'))
from brinecove.geom import Builder  # noqa: E402


def production():
    path = GAME / 'world/regions/brinecove/build.py'
    tree = ast.parse(path.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'bounded_parts']
    scope = dict(Builder=Builder, R=SimpleNamespace(OUTER=(0, 0, 256, 256)), TILE=256.,
                 MIXED_TRIANGLE_LIMIT=8, face_groups=face_groups)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
    return scope['bounded_parts']


def builder():
    part = Builder('SM_BC_TownLower_0_0')
    part.foliage_roles = {}
    for index in range(16):
        x, y = (index % 4) * 64., (index // 4) * 64.
        part.anchor = (x, y)
        part.face([(x, y, 0), (x + 5, y, 2), (x + 5, y + 5, 2), (x, y + 5, 0)],
                  'stone' if index % 2 else 'wood', [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, -1, 0)] * 4)
        part.foliage_roles[index] = ('trunk', index)
    return part


def signatures(part):
    return Counter((tuple(part.verts[i] for i in face), tuple(part.uvs[i] for i in face),
                    tuple(part.normals[i] for i in face), part.mats[index], part.anchors[index],
                    part.foliage_roles[index]) for index, face in enumerate(part.faces))


def test_mixed_mesh_pieces_preserve_every_face_attribute_and_collision_policy():
    part = builder()
    output = production()({(0, 0, False): part}, 'TownLower')
    actual = Counter()
    for key, piece in output.items():
        assert key[:3] == (0, 0, False)
        assert piece.name == part.name + '_Piece' + key[3]
        assert sum(len(face) - 2 for face in piece.faces) <= 8
        actual.update(signatures(piece))
    assert len(output) == 4 and actual == signatures(part)
    assert len(part.faces) == 16  # No mutation of the source builder.


def test_ground_and_small_models_keep_original_builder_and_asset_name():
    part = builder()
    output = production()({(0, 0, False): part}, 'Ground')
    assert output == {(0, 0, False, ''): part}
    tiny = Builder('SM_BC_Props_0_0_Soft')
    tiny.face([(0, 0, 0), (1, 0, 0), (0, 1, 0)], 'leaf_green')
    assert production()({(0, 0, True): tiny}, 'Props') == {(0, 0, True, ''): tiny}


def test_ordinary_recipe_fingerprints_the_shared_partition_code(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('bounded_piece_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
    step = recipe.brinecove_steps(tmp_path)[0]
    assert recipe.paths.STUDIO / 'atelier/mesh_partition.py' in step.inputs


def test_mixed_water_foliage_keeps_parent_shadow_policy_for_every_piece():
    part = builder()
    part.mats = ['water' if index < 8 else 'leaf_green' for index in range(len(part.faces))]
    pieces = production()({(0, 0, True): part}, 'TownLower')
    assert any(set(piece.mats) == {'water'} for piece in pieces.values())
    assert all(piece.parent_water is False for piece in pieces.values())


def test_full_split_preserves_cleanup_and_settling_before_partition():
    from brinecove.geom import distinct_corners
    path = GAME / 'world/regions/brinecove/build.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('split', 'soft')]
    scope = dict(Builder=Builder, R=SimpleNamespace(OUTER=(0, 0, 256, 256)), TILE=256.,
                 distinct_corners=distinct_corners, rocks=SimpleNamespace(FIXED='fixed'),
                 SOFT=('leaf_',), SEA_LEVEL=('water',), bounded_parts=production())
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), scope)
    part = builder()
    # Collapsed apex corners are cleaned before partition, as in the original exporter.
    part.face([(250, 250, 0), (260, 250, 0), (250, 260, 0), (250, 260, 0)], 'stone')
    transformed, outside, drowned, degenerate = scope['split'](part, 'TownLower', lambda x, y: (2., 2.))
    assert outside == drowned == degenerate == 0
    assert sum(len(piece.faces) for piece in transformed.values()) == len(part.faces)
    assert all(vertex[2] >= 2. for piece in transformed.values() for vertex in piece.verts)
    assert all(sum(len(face) - 2 for face in piece.faces) <= 8 for piece in transformed.values())


def test_actual_runtime_group_keeps_parent_shadow_collision_and_identity_placement():
    path = GAME / 'world/regions/brinecove/build.py'
    tree = ast.parse(path.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    group = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'group')
    loop = next(node for node in ast.walk(main) if isinstance(node, ast.For)
                and any(isinstance(name, ast.Name) and name.id == 'is_soft' for name in ast.walk(node.target)))
    water = next(node for node in loop.body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'water')
    append = next(node for node in loop.body if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'groups.append')
    identity = {'translation_cm': [0, 0, 0], 'rotation_xyzw': [0, 0, 0, 1], 'scale': [1, 1, 1]}
    part = builder(); part.mats = ['water'] * 8 + ['leaf_green'] * 8
    for key, piece in production()({(0, 0, True): part}, 'TownLower').items():
        scope = dict(ROOT='/Game/Brinecove', IDENTITY=identity, part=piece,
                     slots=list(dict.fromkeys(piece.mats)), is_soft=key[2], prefix='TownLower', groups=[])
        exec(compile(ast.Module(body=[group, water, append], type_ignores=[]), str(path), 'exec'), scope)
        record, = scope['groups']
        assert record['collision'] is False and record['shadow'] is True
        assert record['transforms'] == [identity] and record['cull_cm'] == 120000
