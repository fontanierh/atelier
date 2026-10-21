"""Run the actual native adapter's classification with controlled asset relationships."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('classification_foliage',GAME/'foliage_system.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class Mesh:
    def __init__(self,name,slot='Ground',leaf=False):
        self.name=name;self.slot=slot;self.leaf=leaf;self.hull=None

    def get_name(self):return self.name

    def get_path_name(self):return '/Game/Generic/'+self.name+'.'+self.name

    def get_material(self,index):return SimpleNamespace(leaf=self.leaf)

    def get_editor_property(self,key):
        if key=='complex_collision_mesh':return self.hull
        assert key=='static_materials'
        return [SimpleNamespace(get_editor_property=lambda key:self.slot)]


def adapter(candidate,owners=(),soft=(),nonmesh=(),missing=()):
    loaded=[]
    packages={owner.get_path_name().split('.')[0]:owner for owner in [*owners,*soft,*nonmesh,*missing]}
    hard=[o.get_path_name().split('.')[0] for o in [*owners,*nonmesh,*missing]]
    soft_paths=[o.get_path_name().split('.')[0] for o in soft]
    nonmesh_paths={o.get_path_name().split('.')[0] for o in nonmesh}
    missing_paths={o.get_path_name().split('.')[0] for o in missing}

    def referencers(package,options):
        assert package==candidate.get_path_name().split('.')[0]
        assert options.include_hard_package_references
        assert not options.include_searchable_names
        assert not options.include_hard_management_references
        assert not options.include_soft_management_references
        return hard+(soft_paths if options.include_soft_package_references else [])

    def assets(package):
        return [SimpleNamespace(package_name=package,asset_class_path=SimpleNamespace(
            asset_name='Texture2D' if package in nonmesh_paths else 'StaticMesh'))]

    def load(package):
        loaded.append(package)
        return None if package in missing_paths else packages[package]

    script=GAME/'unreal/Scripts/build_foliage_system.py'
    functions=[n for n in ast.parse(script.read_text()).body
               if isinstance(n,ast.FunctionDef) and n.name in ('collision_geometry','classify')]
    namespace=dict(F=F,U=SimpleNamespace(AssetRegistryDependencyOptions=lambda **kw:SimpleNamespace(**kw)),
                   E=SimpleNamespace(load_asset=load),leaf_material=lambda material:material.leaf)
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(script),'exec'),namespace)
    registry=SimpleNamespace(get_referencers=referencers,get_assets_by_package_name=assets)
    return lambda:namespace['classify'](candidate,registry),loaded


@pytest.mark.parametrize('name',['FlowerBucket_Collision','FlowerBucket_Helper'])
@pytest.mark.parametrize('owner_name',['AOwner','ZOwner'])
def test_actual_hard_complex_collision_owner_disambiguates_only_name(name,owner_name):
    hull=Mesh(name);owner=Mesh(owner_name);owner.hull=hull
    unrelated=Mesh('AnotherOwner');unrelated.hull=Mesh('OtherHull')
    classify,_=adapter(hull,owners=[owner,unrelated])
    assert classify() is None


@pytest.mark.parametrize('relationship',['absent','soft','nonmesh','self','different_hull'])
def test_suffix_or_unrelated_references_never_exempt_a_named_plant(relationship):
    hull=Mesh('FlowerBucket_Collision');owner=Mesh('Owner');owner.hull=hull
    options={}
    if relationship=='soft':options['soft']=[owner]
    elif relationship=='nonmesh':options['nonmesh']=[owner]
    elif relationship=='self':hull.hull=hull;options['owners']=[hull]
    elif relationship=='different_hull':owner.hull=Mesh('OtherHull');options['owners']=[owner]
    classify,loaded=adapter(hull,**options)
    assert classify()==([0],'material')
    if relationship in ('soft','nonmesh'):assert not loaded


@pytest.mark.parametrize('slot,leaf,expected',[
    (F.roles.AUTHORED_PREFIX+'Flat',False,([], 'authored')),
    (F.roles.SLOT_PREFIX+'Leaves',False,([], 'roles')),
    ('Leaves',True,([0],'material')),
    (F.roles.RIGID_PREFIX+'Ground',False,None),
])
def test_explicit_roles_and_foliage_materials_win_over_collision_usage(slot,leaf,expected):
    hull=Mesh('FlowerBucket_Collision',slot,leaf);owner=Mesh('Owner');owner.hull=hull
    classify,loaded=adapter(hull,owners=[owner])
    assert classify()==expected
    assert not loaded


def test_unreadable_hard_mesh_owner_fails_classification():
    hull=Mesh('FlowerBucket_Collision');owner=Mesh('Owner');owner.hull=hull
    classify,_=adapter(hull,missing=[owner])
    with pytest.raises(ValueError,match='Cannot inspect collision owner'):classify()


def test_real_hidamari_export_names_do_not_classify_streets_as_trees():
    tree=ast.parse((GAME/'world/regions/hidamari/build.py').read_text())
    names={node.value for node in ast.walk(tree) if isinstance(node,ast.Constant)
           and isinstance(node.value,str) and node.value.startswith('HD_')}
    assert {'HD_Streets','HD_Planter','HD_ArcadeTree'} <= names
    plants={'HD_ArcadeTree','HD_PlazaTreeGold','HD_PlazaTreeOrange','HD_Bamboo'}
    assert {name for name in names if F.vegetation(name)} == plants
    for name in names-plants:
        classify,_=adapter(Mesh(name))
        assert classify() is None,name


@pytest.mark.parametrize('name', ['HD_Streets','SM_CityStreet','SM_Backstreet','Treehouse_Floor',
                                'SM_BarrelPlanter','SM_PineappleCrate'])
def test_words_embedded_in_non_plant_names_are_not_vegetation(name):
    assert not F.vegetation(name)
    assert not F.material_vegetation(name,masked=True)


@pytest.mark.parametrize('name', ['StreetTree02','SM_Trees','SM_Bushes','HD_Grasses','UnderstoryFern',
                                'SM_BC_Plant_CoverLeaf1','M_LeafMid','Treehouse_Leaves'])
def test_word_boundaries_plural_and_numbered_plants_remain_discoverable(name):
    assert F.vegetation(name)
