"""Universal foliage ownership, geometry bounds and disabled-source invariants."""
import importlib.util
import json
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('foliage_system', GAME/'foliage_system.py')
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)


def source(count=900, kind='tree'):
    vertices, faces = [], []
    # A dense, multi-layer crown with an asymmetric silhouette.
    for i in range(count):
        x, y, z = (i % 11)*9., ((i//11) % 9)*11., 200.+(i % 17)*5.
        face = []
        for dx, dy, dz in ((0,0,0),(12,0,3),(0,12,6)):
            face.append(len(vertices))
            vertices.append(dict(p=[x+dx,y+dy,z+dz],n=[0.,0.,1.],uv=[.2,.3],c=[.8,.4,.02,1.]))
        faces.append(dict(v=face,s=1))
    # A distinct rigid trunk/planter triangle that every visual level must retain.
    face = []
    for p in ((0,0,0),(1,0,0),(0,0,100)):
        face.append(len(vertices));vertices.append(dict(p=list(p),n=[0.,-1.,0.],uv=[.4,.5],c=[.1,.05,.02,1.]))
    faces.append(dict(v=face,s=0))
    return dict(path='/Game/AnUnrelatedRegion/Tree_A.Tree_A', kind=kind, vertices=vertices,faces=faces,
                materials=[dict(path='Bark',foliage=False),dict(path='Leaves',foliage=True)])


@pytest.mark.parametrize('name', ['Tree_Maple_A','HD_ArcadeTree','SM_BC_Plant_Jungle','Palm','M_LeafMid',
                                  'Bush_Azalea','Flower','Grass_B','UnderstoryFern'])
def test_region_independent_classification(name):
    assert F.vegetation(name)


def test_mesh_identity_includes_namespace():
    assert F.asset_id('/Game/A/Tree_A.Tree_A') != F.asset_id('/Game/B/Tree_A.Tree_A')
    assert F.asset_id('/Game/A/Tree_A.Tree_A') == F.asset_id('/Game/A/Tree_A.Tree_A')


def test_closed_core_has_outward_winding_and_two_incident_faces_per_edge():
    vertices, faces = F.core([(-3,-4,-5),(3,4,5)], [.8,.4,.02,1.], 0)
    edges = {}
    for face in faces:
        a,b,c = [vertices[i]['p'] for i in face['v']]
        assert F.dot(F.cross(F.sub(c,a),F.sub(b,a)),a) > 0
        for x,y in zip(face['v'],face['v'][1:]+face['v'][:1]):
            key = tuple(sorted((x,y))); edges[key] = edges.get(key,0)+1
    assert len(faces) == 32
    assert set(edges.values()) == {2}


def test_dense_crown_has_bounded_levels_retains_rigid_geometry_and_does_not_mutate_source():
    original = source(4650)
    before = json.dumps(original,sort_keys=True)
    result = F.build(original)
    assert json.dumps(original,sort_keys=True) == before
    counts = [len(level['faces']) for level in result['levels']]
    assert counts == sorted(counts,reverse=True)
    assert counts[0] <= 8*32+160+1
    assert counts[-1] <= 33
    assert len(result['patch']['faces']) == 32
    assert original['faces'][-1]['s'] == 0
    rigid = original['faces'][-1]
    expected = [original['vertices'][i] for i in rigid['v']]
    lo, hi = F.bounds([v['p'] for v in original['vertices']])
    for level in result['levels']:
        actual = [f for f in level['faces'] if f['s']==0]
        assert len(actual)==1
        assert [level['vertices'][i] for i in actual[0]['v']] == expected
        for v in level['vertices']:
            assert all(lo[i]-1e-6 <= v['p'][i] <= hi[i]+1e-6 for i in range(3))


def test_thin_groundcover_does_not_gain_a_closed_canopy_or_duplicate_triangles():
    original = source(3, 'groundcover')
    result = F.build(original)
    for level in result['levels']:
        assert all(face['s'] < len(original['materials']) for face in level['faces'])
        positions = [tuple(tuple(level['vertices'][i]['p']) for i in f['v']) for f in level['faces']]
        assert len(positions) == len(set(positions))


def test_existing_tiny_far_proxy_is_preserved_and_shadow_still_has_closed_cores():
    original = source(900)
    original['far_proxy'] = source(2)
    result = F.build(original)
    assert result['levels'][-1]['faces'] == original['far_proxy']['faces']
    assert result['levels'][-1]['vertices'] == original['far_proxy']['vertices']
    assert any(f['s'] == len(original['materials'])+1 for f in result['shadow']['faces'])


def test_distant_branches_use_the_authored_reduced_body_instead_of_full_detail():
    original = source(900)
    lod = source(20)
    # A distinct reduced trunk proves the adapter did not keep the LOD0 body.
    for v in lod['vertices'][-3:]: v['p'][0] += .25
    original['rigid_lods'] = [lod,lod,lod]
    result = F.build(original)
    for level in result['levels'][1:]:
        rigid = [f for f in level['faces'] if f['s']==0]
        assert len(rigid)==1
        assert [level['vertices'][i]['p'] for i in rigid[0]['v']] == [v['p'] for v in lod['vertices'][-3:]]


def test_separate_trees_in_mixed_mesh_are_not_joined_across_a_clearing():
    original = source()
    other = source()
    offset = len(original['vertices'])
    original['vertices'].extend({**v,'p':[v['p'][0]+5000,*v['p'][1:]]} for v in other['vertices'])
    original['faces'].extend(dict(v=[i+offset for i in f['v']],s=f['s']) for f in other['faces'])
    result = F.build(original)
    for level in result['levels']:
        for f in level['faces']:
            x = [level['vertices'][i]['p'][0] for i in f['v']]
            assert max(x)-min(x) < 200


@pytest.mark.parametrize('mutation', [lambda s:s['vertices'][0]['p'].__setitem__(0,float('nan')),
                                     lambda s:s['faces'][0]['v'].__setitem__(0,-1),
                                     lambda s:s['faces'][0].__setitem__('s',99)])
def test_corrupt_sources_refuse_instead_of_creating_fallbacks(mutation):
    original=source();mutation(original)
    with pytest.raises(ValueError): F.build(original)


def test_instanced_component_creation_is_owned_by_shared_system():
    root = GAME/'unreal/Source/Yorimichi'
    offenders = []
    for path in root.rglob('*.cpp'):
        if path.name == 'FoliageSystem.cpp': continue
        if 'NewObject<UHierarchicalInstancedStaticMeshComponent>' in path.read_text():
            offenders.append(str(path.relative_to(GAME)))
    assert not offenders, f'Use UYorimichiFoliageSubsystem::NewInstances: {offenders}'


def test_cook_registry_and_normal_graph_are_not_optional():
    recipe=(GAME/'build.py').read_text()
    assert 'result.append(foliage_build.system_step(ctx,' in recipe
    assert '"/Game/FoliageSystem"' in (GAME/'unreal/Config/DefaultGame.ini').read_text()
    runtime=(GAME/'unreal/Source/Yorimichi/FoliageSystem.cpp').read_text()
    assert 'foliage_system/registry.json' in runtime
    assert 'Uncertified or stale foliage:' in runtime


def test_committed_brinecove_groundcover_corpus_and_mixed_materials_never_gain_cores(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    from brinecove import flora
    for name, builder in flora.prototypes().items():
        if not name.startswith('cover_'):
            continue
        mats = sorted(set(builder.mats))
        assert all(F.material_vegetation(m) for m in mats), name
        mesh = dict(path='/Game/Test/SM_BC_Plant_'+''.join(p.title() for p in name.split('_')),
                    kind='tree',  # Embedded groundcover must work without a groundcover mesh name.
                    vertices=[dict(p=[x*100 for x in v],n=[0.,0.,1.],uv=[0.,0.],c=[.2,.4,.1,1.])
                              for v in builder.verts],
                    materials=[dict(path=m,foliage=True) for m in mats], faces=[])
        for face, mat in zip(builder.faces,builder.mats):
            mesh['faces'].extend(dict(v=[face[0],face[i],face[i+1]],s=mats.index(mat))
                                 for i in range(1,len(face)-1))
        result=F.build(mesh)
        assert F.category(mesh['path']) == 'groundcover'
        for level in result['levels']:
            assert len(level['faces']) <= len(mesh['faces']), name
            assert all(f['s'] < len(mats) for f in level['faces']), name


@pytest.mark.parametrize('count', [65,72,128,256,415,417,900])
def test_small_material_groups_never_inflate_even_across_spatial_bucket_boundaries(count):
    original=source(count)
    for v in original['vertices']:
        v['p'][0]-=40.;v['p'][1]-=40.
    result=F.build(original)
    assert all(len(level['faces']) <= len(original['faces']) for level in result['levels'])


def test_treehouse_architecture_is_not_misclassified_as_a_tree():
    assert not F.vegetation('M_TreeHouse')
    assert not F.vegetation('Treehouse_Floor')
    assert F.vegetation('Treehouse_Leaf')


def test_palette_slots_share_one_crown_budget():
    original=source(4650)
    original['materials'].extend(dict(path='Leaf'+str(i),foliage=True) for i in range(6))
    for i,f in enumerate(original['faces'][:-1]): f['s']=1+i%7
    result=F.build(original)
    assert len(result['levels'][0]['faces'])<=8*32+160+1


def test_grass_painted_ground_retains_its_surface_while_standing_cards_register():
    assert not F.material_vegetation('MI_HD_grass')
    assert not F.material_vegetation('MI_Litter')
    assert F.material_vegetation('MI_Grass', masked=True)
    assert F.material_vegetation('AnyMaterial', foliage=True)
    assert F.vegetation('SM_Grass')
    assert F.material_vegetation('MI_cover_leaf')
    assert F.material_vegetation('MI_BC_cover_grass')
    assert F.material_vegetation('MI_BC_cover_grass_dry')


def test_current_city_tree_palettes_classify_decoded_fbx_colour_not_encoded_blue():
    import ast
    tree=ast.parse((GAME/'world/regions/hidamari/arcade.py').read_text())
    palettes=[ast.literal_eval(node.value.args[0]) for node in ast.walk(tree)
              if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='col' for t in node.targets)
              and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute)
              and node.value.func.attr=='choice' and isinstance(node.value.args[0],ast.List)]
    colours=next(p for p in palettes if len(p)==4)
    colours += [tuple(v*s for v,s in zip(c,(.95,.43,.7))) for c in colours[:]]
    for colour in colours:
        mesh=source(1);mesh['classification']='palette'
        mesh['materials'][1]['foliage']=False
        encoded=[v*12.92 if v<=.0031308 else 1.055*v**(1/2.4)-.055 for v in colour]
        for v in mesh['vertices'][:-3]: v['c']=[*encoded,1.]
        leaf,body=F.classified_faces(mesh)
        assert len(leaf)==1 and len(body)==1, colour
        assert F.build(mesh)['rigid_triangles']==1


@pytest.mark.parametrize('name,kind', [('Bush_Flower_A','shrub'),('SM_BC_Plant_Bloom1','shrub'),
                                     ('Tree_FloweringCherry','tree'),('Flower','groundcover'),
                                     ('SM_BC_Plant_CoverLeaf1','groundcover')])
def test_plant_role_keeps_flowering_bushes_and_trees_in_their_own_budget(name,kind):
    assert F.category(name)==kind


def test_missing_or_corrupt_material_cannot_be_certified_away_by_cached_meshes(tmp_path):
    root=tmp_path/'FoliageSystem';root.mkdir()
    mesh=root/'Tree.uasset';wrapper=root/'MI_Leaf.uasset'
    mesh.write_bytes(b'valid mesh');wrapper.write_bytes(b'valid wrapper')
    original=F.package_inventory(tmp_path)
    report=dict(algorithm='current',packages=original,assets=[dict(source='/Game/A/Tree.Tree')])
    assert F.cache_records(report,report,'current',original)
    wrapper.unlink()
    assert not F.cache_records(report,report,'current',F.package_inventory(tmp_path))
    wrapper.write_bytes(b'corrupt wrapper')
    assert not F.cache_records(report,report,'current',F.package_inventory(tmp_path))
    wrapper.write_bytes(b'valid wrapper')
    assert F.cache_records(report,report,'current',F.package_inventory(tmp_path))
    assert not F.cache_records(report,{},'current',original)
    assert not F.cache_records(report,report,'changed algorithm',original)
    # The adapter must use this decision, before it regenerates shared materials.
    adapter=(GAME/'unreal/Scripts/build_foliage_system.py').read_text()
    assert adapter.index('cached=F.cache_records(')<adapter.index('near,far,patch_material=canopy_material(')


@pytest.mark.parametrize('name', ['bamboo_cane','palm_trunk','TreeBark','flower_stem','ar_rice_canopy','hd_grass'])
def test_rigid_plant_parts_and_cloth_are_not_leaf_materials(name):
    assert not F.material_vegetation(name)
    if name=='ar_rice_canopy':
        assert not F.vegetation(name)


@pytest.mark.parametrize('flipped', [False,True])
def test_mixed_vertex_palette_roles_preserve_rigid_faces_and_ignore_colour(flipped):
    mesh=source(100);mesh['classification']='roles'
    for face in mesh['faces']:
        for index in face['v']:
            vertex=mesh['vertices'][index]
            vertex['uvs']=[vertex['uv']]*5+[[float(face['s']==1),1-F.roles.MARKER if flipped else F.roles.MARKER]]
            # A green wall and a white flower must not be classified by hue.
            vertex['c']=[1.,1.,1.,0.] if face['s']==1 else [0.,.5,0.,0.]
    leaf,rigid=F.classified_faces(mesh)
    assert len(leaf)==100 and len(rigid)==1
    assert F.build(mesh)['rigid_triangles']==1
    mesh['vertices'][0]['uvs'][5]=[1.,0.]
    with pytest.raises(ValueError,match='foliage face role'):
        F.classified_faces(mesh)


def test_authoring_role_export_reserves_only_uv5_and_retains_camera_layers():
    from types import SimpleNamespace as S
    class Layers(list):
        def new(self,name):
            self.append(S(name=name,data=[S(uv=[.2,.3]) for _ in range(6)]))
    layers=Layers()
    for i in range(5):layers.new('Camera'+str(i))
    before=[[entry.uv[:] for entry in layer.data] for layer in layers]
    obj=S(data=S(uv_layers=layers,polygons=[S(loop_indices=range(3)),S(loop_indices=range(3,6))]))
    source=S(name='Mixed',faces=[(0,1,2),(3,4,5)],keys=['bamboo_cane','bamboo_leaf'])
    F.roles.export_roles(obj,source)
    assert [[entry.uv for entry in layer.data] for layer in layers[:5]]==before
    assert [entry.uv for entry in layers[5].data]==[(0.,F.roles.MARKER)]*3+[(2.,F.roles.MARKER)]*3
    with pytest.raises(ValueError,match='reserved'):
        F.roles.export_roles(obj,source)
    colour=F.roles.PaletteColour((.1,.2,.3),'leaf')
    assert tuple(colour)==(.1,.2,.3) and F.material_vegetation(colour.foliage_key)


def test_embedded_thin_roles_never_receive_solid_crowns_from_neutral_building_material():
    mesh=source(900);mesh['classification']='roles'
    mesh['materials'][1]['path']='M_Village'
    for face in mesh['faces']:
        for index in face['v']:
            vertex=mesh['vertices'][index]
            vertex['uvs']=[vertex['uv']]*5+[[2. if face['s']==1 else 0.,F.roles.MARKER]]
    result=F.build(mesh)
    assert result['rigid_triangles']==1
    for level in result['levels']:
        assert all(face['s']<2 for face in level['faces'])
    assert len(result['levels'][-1]['faces'])<len(mesh['faces'])/10


def test_container_names_do_not_turn_empty_planters_into_vegetation():
    assert not F.vegetation('SM_BM_BP_BarrelPlanter')
    assert F.vegetation('SM_BC_Plant_Bloom1')
    assert F.roles.key_role('bamboo_leaf')==2
    assert F.roles.key_role('bamboo_cane')==0


def test_explicit_authored_mixed_prop_policy_preserves_all_surfaces_and_has_a_hard_budget(monkeypatch):
    mesh=source(100);mesh['classification']='authored'
    for vertex in mesh['vertices']:vertex['uvs']=[vertex['uv']]*5+[[3.,F.roles.MARKER]]
    before=json.dumps(mesh,sort_keys=True)
    result=F.build(mesh)
    assert json.dumps(mesh,sort_keys=True)==before
    assert all(level['vertices']==mesh['vertices'] and level['faces']==mesh['faces'] for level in result['levels'])
    assert result['shadow']['faces']==mesh['faces']
    monkeypatch.setattr(F.roles,'AUTHORED_BUDGET',100)
    with pytest.raises(ValueError,match='exceeds triangle budget'):F.build(mesh)
    monkeypatch.setattr(F.roles,'AUTHORED_BUDGET',12288)
    mesh['vertices'][0]['uvs'][5]=[1.,F.roles.MARKER]
    with pytest.raises(ValueError,match='authored foliage role'):F.build(mesh)
