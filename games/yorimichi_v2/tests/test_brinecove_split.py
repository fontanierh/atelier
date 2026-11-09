"""Brine Cove tile split: the pure parts (GLB reading, welded components, anchored assignment, partition proof)."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import brinecove_split as split  # noqa: E402


def glb(path, prims, materials=('BC_a', 'BC_b')):
    """Write a binary glTF; prims = [(material, [(x,y,z)...], [indices...])]."""
    blob, views, accessors, primitives = b'', [], [], []
    for material, positions, indices in prims:
        pos = b''.join(struct.pack('<fff', *p) for p in positions)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(pos)})
        accessors.append({'bufferView': len(views) - 1, 'componentType': 5126, 'count': len(positions), 'type': 'VEC3'})
        blob += pos
        idx = b''.join(struct.pack('<H', i) for i in indices)
        idx += b'\0' * (-len(idx) % 4)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(indices) * 2})
        accessors.append({'bufferView': len(views) - 1, 'componentType': 5123, 'count': len(indices), 'type': 'SCALAR'})
        blob += idx
        primitives.append({'attributes': {'POSITION': len(accessors) - 2}, 'indices': len(accessors) - 1,
                           'material': material})
    doc = json.dumps({'asset': {'version': '2.0'}, 'meshes': [{'primitives': primitives}], 'accessors': accessors,
                      'bufferViews': views, 'buffers': [{'byteLength': len(blob)}],
                      'materials': [{'name': m} for m in materials]}).encode()
    doc += b' ' * (-len(doc) % 4)
    body = struct.pack('<II', len(doc), 0x4E4F534A) + doc + struct.pack('<II', len(blob), 0x004E4942) + blob
    Path(path).write_bytes(b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body)


def quad(x, z, size=1.0, y=5.0):
    """Two triangles of a flat square at ground (x, z), 4 shared vertices."""
    return [(x, y, z), (x + size, y, z), (x + size, y, z + size), (x, y, z + size)], [0, 1, 2, 0, 2, 3]


def test_read_glb_and_triangles(tmp_path):
    verts, idx = quad(0, 0)
    glb(tmp_path / 'a.glb', [(0, verts, idx)])
    model = split.read_glb(tmp_path / 'a.glb')
    assert model['materials'] == ['BC_a', 'BC_b']
    assert {m for m, _ in split.triangles(model)} == {'BC_a'}
    assert len(list(split.triangles(model))) == 2


def test_lfs_pointer_is_refused(tmp_path):
    (tmp_path / 'p.glb').write_text('version https://git-lfs.github.com/spec/v1\n')
    try:
        split.read_glb(tmp_path / 'p.glb')
    except ValueError as error:
        assert 'LFS pointer' in str(error)
    else:
        raise AssertionError('a pointer file must not parse')


def model_of(*squares):
    prims = []
    for material, x, z in squares:
        verts, idx = quad(x, z)
        prims.append((material, verts, idx))
    return prims


def test_components_weld_shared_corners(tmp_path):
    # two squares sharing one corner weld into one component; a distant one is its own
    a, b, c = quad(0, 0), quad(1, 1), quad(50, 50)
    tris = [('BC_a', tuple(a[0][i] for i in a[1][k:k + 3])) for k in (0, 3)]
    tris += [('BC_a', tuple(b[0][i] for i in b[1][k:k + 3])) for k in (0, 3)]
    tris += [('BC_a', tuple(c[0][i] for i in c[1][k:k + 3])) for k in (0, 3)]
    comps = split.components(tris)
    assert sorted(len(x) for x in comps) == [2, 4]


def tris_at(x, z, material='BC_a', size=1.0, y=5.0):
    verts, idx = quad(x, z, size, y)
    return [(material, tuple(verts[i] for i in idx[k:k + 3])) for k in (0, 3)]


def test_anchored_assignment_nearest_extent_and_height():
    # layout y is the negated GLB z
    tris = tris_at(10, -10) + tris_at(40, -10) + tris_at(11, -11, size=60.0) + tris_at(10, -10, y=1.0)
    comps = split.components(tris)
    anchors = {'near': dict(x=10, y=10, radius=5, max_extent=5, min_height=4.0),
               'far': dict(x=40, y=10, radius=5, max_extent=5, min_height=4.0)}
    owned = split.assign_anchored(tris, comps, anchors)
    assert len(owned['near']) == 2 and len(owned['far']) == 2
    assert len(owned['']) == 4       # the 60 m slab (too long) and the low square (below min_height) stay behind


def test_anchored_assignment_excludes_materials():
    tris = tris_at(0, 0, material='BC_a') + tris_at(0.2, 0.2, material='BC_b', size=5)
    comps = split.components(tris)
    anchors = {'o': dict(x=0, y=0, radius=9, max_extent=9, min_height=0, exclude_materials=('BC_b',))}
    owned = split.assign_anchored(tris, comps, anchors)
    assert len(owned['o']) == 2 and len(owned['']) == 2


def test_partition_proof_detects_missing_and_changed_triangles():
    tris = tris_at(0, 0) + tris_at(5, 5)
    assert split.verify_partition(tris, [tris[:2], tris[2:]]) == []
    assert split.verify_partition(tris, [tris[:2]])                               # a lost triangle
    moved = tris_at(0, 0) + tris_at(5, 6)
    assert split.verify_partition(tris, [moved[:2], moved[2:]])                   # a moved vertex
    swapped = [('BC_b', c) for _, c in tris[:2]] + tris[2:]
    assert 'material split differs' in split.verify_partition(tris, [swapped])    # a changed material


def test_plan_batch_end_to_end(tmp_path):
    prims = model_of((0, 10, -10), (1, 40, -10), (0, 200, -200))
    glb(tmp_path / 'SM_BC_Props_9_9.glb', prims)
    objects = {'a': dict(x=10, y=10, radius=5, max_extent=5, min_height=0, tiles=('Props_9_9',)),
               'b': dict(x=40, y=10, radius=5, max_extent=5, min_height=0, tiles=('Props_9_9',))}
    report = split.plan_batch(tmp_path, objects)
    assert report['problems'] == []
    assert report['objects']['a']['triangles'] == 2 and report['objects']['b']['materials'] == ['BC_b']


def test_first_batch_is_bounded_and_unique():
    names = list(split.OBJECTS)
    assert 10 <= len(names) <= 20 and len(set(names)) == len(names)
    for name, spec in split.OBJECTS.items():
        assert spec['radius'] > 0 and spec['tiles'], name


def test_written_parts_read_back_as_the_same_triangles(tmp_path):
    prims = model_of((0, 10, -10), (1, 40, -10), (0, 200, -200))
    glb(tmp_path / 'SM_BC_Props_9_9.glb', prims)
    objects = {'a': dict(x=10, y=10, radius=5, max_extent=5, min_height=0, tiles=('Props_9_9',))}
    out = tmp_path / 'out'
    report = split.plan_batch(tmp_path, objects, out_dir=out)
    assert report['problems'] == []
    source = list(split.triangles(split.read_glb(tmp_path / 'SM_BC_Props_9_9.glb')))
    parts = [list(split.triangles(split.read_glb(f))) for f in sorted(out.glob('*/SM_BC_Props_9_9.glb'))]
    assert len(parts) == 2 and split.verify_partition(source, parts) == []


def test_exclude_zone_keeps_a_neighbouring_palm_out_of_the_object():
    # a crane part and a palm (planter, trunk, fronds) 12 m away, both inside the crane's radius; layout y is -z
    crane = tris_for(-334, 84, 'BC_wood')
    palm = tris_for(-330, 72, 'BC_clay') + tris_for(-330, 72, 'BC_palm_frond', height=11.0)
    tris = crane + palm
    comps = split.components(tris)
    anchor = dict(x=-326, y=83, radius=14, max_extent=25, min_height=4.5)
    plain = split.assign_anchored(tris, comps, {'crane': anchor})
    assert len(plain['crane']) == len(tris)                        # radius alone takes the palm too
    zoned = split.assign_anchored(tris, comps, {'crane': {**anchor, 'exclude_zones': ((-330, 72, 5.0),)}})
    assert len(zoned['crane']) == len(crane) and len(zoned['']) == len(palm)


def tris_for(x, y, material, height=5.0):
    z = -y
    sq = [(x, height, z), (x + 1, height, z), (x + 1, height, z + 1), (x, height, z + 1)]
    return [(material, (sq[0], sq[1], sq[2])), (material, (sq[0], sq[2], sq[3]))]


def test_the_batch_keeps_palm_zones_for_the_crane_and_the_shed():
    assert split.OBJECTS['crane-west']['exclude_zones'] == ((-330, 72, 5.0),)
    assert split.OBJECTS['fish-shed']['exclude_zones'] == ((300, 72, 5.0),)
