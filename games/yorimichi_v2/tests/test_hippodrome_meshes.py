"""adopted/hippodrome/meshes: the four painted props' embedded textures and restyled instances become their own records,
and the six unused course instances are retired (tools/migrate/hippodrome_meshes.py). Nothing here runs Unreal; the
native before/after reads are the import's evidence."""
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'content'))
sys.path.insert(0, str(ROOT / 'tools' / 'migrate'))
import records  # noqa: E402
import hippodrome_meshes as hm  # noqa: E402

GLB = ROOT / 'assets/prop/hippodrome/tote-board/src/SM_HD_ToteBoard.glb'
pytestmark = pytest.mark.skipif(records.is_lfs_pointer(GLB), reason='the prop GLBs are Git LFS pointers here')


@pytest.fixture(scope='module')
def rows():
    return hm.plan(ROOT)


def test_each_painted_prop_gives_one_jpeg_texture_and_one_instance_from_its_pinned_glb(rows):
    assert set(rows) == set(hm.PARTS)
    for part, row in rows.items():
        assert row['image'][:3] == b'\xff\xd8\xff' and hashlib.sha256(row['image']).hexdigest() == row['sha']
        name = hm.PARTS[part]
        assert row['instance'] == f'{hm.MESHES}/SM_HD_{name}/HD_{name}'
        assert row['texture'].startswith(f'{hm.MESHES}/SM_HD_{name}/Color_') and row['source'].endswith('.jpg')
    assert hm.expected_packages(rows) | set() == {r[k] for r in rows.values() for k in ('texture', 'instance')} | set(hm.UNUSED)
    assert len(hm.expected_packages(rows)) == 14


def test_the_planned_records_load_and_bind_the_restyled_parent_and_texture(rows, tmp_path):
    """@cc [owner:fontanierh,label:correctness] hippodrome-restyled-instances
    Each instance is the donor's restyle: parent M_HD_Structure, BaseColorTexture its prop's embedded image, nothing
    else overridden, depending on the structure master and its texture record; each texture pins the embedded bytes."""
    for part, row in rows.items():
        tex = tmp_path / f'{part}-tex.toml'
        tex.write_text(hm.texture_text(part, row))
        asset = records.load_asset(tex)
        assert asset.kind == 'texture' and [o.package for o in asset.outputs] == [row['texture']]
        assert [(s.path, s.sha256) for s in asset.sources] == [(f'src/{row["source"]}', row['sha'])]
        assert asset.recipe['settings'] == {'srgb': True, 'compression': 'TC_DEFAULT', 'lod_group': 'TEXTUREGROUP_WORLD',
                                            'address': 'wrap'}
        mat = tmp_path / f'{part}-mat.toml'
        mat.write_text(hm.material_text(part, row))
        asset = records.load_asset(mat)
        assert asset.kind == 'material-instance' and [o.package for o in asset.outputs] == [row['instance']]
        assert asset.input_dependencies == [hm.STRUCTURE_RECORD, hm.texture_id(part)]
        assert asset.recipe['settings'] == {'parent': hm.STRUCTURE, 'textures': {'BaseColorTexture': row['texture']},
                                            'scalars': {}, 'vectors': {}}


def test_the_tree_is_moved_or_unmoved_and_a_moved_tree_holds_exactly_the_plan(rows):
    current = hm.state(ROOT, rows)
    assert current in ('unmoved', 'moved')
    if current == 'unmoved':
        ops = hm.build_writes(ROOT, rows)
        assert sum(rel.endswith('/asset.toml') and rel.startswith(('assets/texture/', 'assets/material/'))
                   for rel in ops['writes']) == 8
        assert f'{hm.ADOPTED_REL}/asset.toml' in ops['deletes']
        return
    for part, row in rows.items():
        assert (ROOT / f'assets/{hm.texture_id(part)}/asset.toml').read_text() == hm.texture_text(part, row)
        assert (ROOT / f'assets/{hm.material_id(part)}/asset.toml').read_text() == hm.material_text(part, row)
        assert (ROOT / f'assets/{hm.texture_id(part)}/src/{row["source"]}').read_bytes() == row['image']
        prop = records.load_asset(ROOT / hm.prop_rel(part))
        assert prop.input_dependencies == [hm.material_id(part)]
    for rel in hm.READ_LISTS:
        assert not set((ROOT / rel).read_text().split()) & set(hm.UNUSED)
