"""Current per-mesh admission and combined exact Treehouse surface retirement."""
import hashlib
import json
from pathlib import Path
import sys
import unreal
from atelier import native_membership
from atelier.mesh_geometry import package_inventory
from mesh_import import import_mesh
from forest_native import hulls_match

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import treehouse_surfaces as surfaces  # noqa: E402

HULLS={}


def configure(out):
    global HULLS
    root=Path(out)
    props=json.loads((root/'props/props.json').read_text())
    trees=json.loads((root/'trees/trees.json').read_text())
    HULLS={name:row['authored_hulls'] for name,row in props.items()}
    HULLS.update({name:[] for name in trees})
    HULLS.update({row['name']:[] for row in surfaces.rows(root.parent)})


def reusable(mesh):
    sub=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    name=mesh.get_name()
    return (name in HULLS and sub.get_simple_collision_count(mesh)==0
        and sub.get_convex_collision_count(mesh)==len(HULLS[name]) and hulls_match(mesh,HULLS[name]))


def prepare(name,destination):
    editor=unreal.EditorAssetLibrary;sub=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor.does_asset_exist(destination+'/'+name):
        mesh=editor.load_asset(destination+'/'+name)
        if sub.get_simple_collision_count(mesh) or sub.get_convex_collision_count(mesh):
            assert sub.remove_collisions(mesh),(name,'source hull reset')
        assert sub.get_simple_collision_count(mesh)==sub.get_convex_collision_count(mesh)==0,name


def receive(path,destination,name):
    mesh=import_mesh(path,destination,name,fresh_slots=True,before_import=lambda:prepare(name,destination),reuse_validator=reusable)
    assert reusable(mesh),(name,'current authored collision')
    if mesh.get_num_lods()!=1:mesh.set_num_source_models(1)
    return mesh


def inventory(editor):
    result=set()
    for folder,parent in ((surfaces.STRUCTURE,'TH_Structure'),(surfaces.DRESSING,'TH_Dressing')):
        for path in editor.list_assets(folder,recursive=False,include_folder=False):
            name=path.removeprefix(folder+'/').split('.')[0]
            if not surfaces.valid_name(parent,name) or path!=folder+'/'+name+'.'+name:
                raise ValueError('Foreign package in exclusive Treehouse surface owner')
            result.add(folder+'/'+name)
    for parent in surfaces.PARENTS:
        package='/Game/Japan/Assets/'+parent
        if editor.does_asset_exist(package):result.add(package)
    return result


def retire(editor,previous,current,rows,content):
    """@cc [owner:fontanierh,label:correctness] combined-treehouse-current-before-parent-retirement
    Every current surface, prop, canopy, material and texture MUST be validated and
    saved before one retirement preflight covers both oversized parents and every
    obsolete owned child. A foreign reference MUST refuse before any deletion.
    Success MUST require exact current membership and physical parent/sidecar absence.
    """
    if not current or len(set(current))!=len(current) or current!=[row['package'] for row in rows]:
        raise ValueError('Incomplete current Treehouse surface roster')
    package_inventory(content,current)
    obsolete=previous-set(current)
    replacements={package:current for package in obsolete}
    replacements.update({'/Game/Japan/Assets/'+parent:[row['package'] for row in rows if row['parent']==parent]
                         for parent in ('TH_Structure','TH_Dressing')})
    retired=native_membership.retire_replaced(editor,replacements)
    if not surfaces.retired_parents_absent(content) or any(not surfaces.absent(content,p) for p in obsolete):
        raise ValueError('Retired Treehouse surface bytes remain')
    if inventory(editor)!=set(current):raise ValueError('Current Treehouse surface membership differs')
    return retired


def finish_uv_precision(mesh,sub,parent):
    """Preserve the original explicit five-channel fade precision and legacy single-UV format."""
    expected=parent in ('TH_Frame','TH_Dressing')
    settings=sub.get_lod_build_settings(mesh,0)
    if settings.get_editor_property('use_full_precision_u_vs')!=expected:
        settings.set_editor_property('use_full_precision_u_vs',expected)
        sub.set_lod_build_settings(mesh,0,settings)
    assert sub.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')==expected,mesh.get_name()


def import_surfaces(out,materials,trunk_material,report):
    root=Path(out);content=Path(__file__).resolve().parents[1]/'Content'
    editor=unreal.EditorAssetLibrary;sub=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    rows=surfaces.rows(root.parent);previous=inventory(editor);current=[]
    for row in rows:
        name=row['name'];parent=row['parent'];package=row['package'];destination=package.rsplit('/',1)[0]
        mesh=receive(root/row['fbx'],destination,name)
        assert mesh.get_num_lods()==1 and mesh.get_num_triangles(0)==row['triangles'],name
        assert sub.get_num_uv_channels(mesh,0)==len(row['uv_channels']),(name,'all original UV channels')
        slots=list(mesh.get_editor_property('static_materials'))
        actual=[str(slot.get_editor_property('imported_material_slot_name')) for slot in slots]
        assert len(set(actual))==len(actual) and set(row['used_slots'])<=set(actual)<=set(row['slots']),(name,'material membership')
        for index,slot in enumerate(actual):
            material=trunk_material if parent=='TH_Trunks' and slot=='TH_bark' and trunk_material else materials.get(slot.removeprefix('TH_'))
            assert material is not None,(name,slot)
            if mesh.get_material(index)!=material:mesh.set_material(index,material)
            assert mesh.get_material(index)==material,name
        flag=(unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX if parent=='TH_Dressing'
              else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        body=mesh.get_editor_property('body_setup')
        if body.get_editor_property('collision_trace_flag')!=flag:body.set_editor_property('collision_trace_flag',flag)
        finish_uv_precision(mesh,sub,parent)
        assert reusable(mesh) and body.get_editor_property('collision_trace_flag')==flag,name
        assert mesh.get_editor_property('lod_for_collision')==0 and mesh.get_editor_property('complex_collision_mesh') is None,name
        if parent!='TH_Dressing':assert unreal.CitySurfaceValidation.validate_collision(mesh,row['triangles'],False),(name,'actual cooked collision')
        low,high=row['min'],row['max'];box=mesh.get_bounding_box()
        expected=((low[0]*100,-high[1]*100,low[2]*100),(high[0]*100,-low[1]*100,high[2]*100))
        assert all(abs(getattr(point,axis)-want[i])<.2 for point,want in zip((box.min,box.max),expected)
                   for i,axis in enumerate(('x','y','z'))),name
        assert editor.save_loaded_asset(mesh,only_if_is_dirty=True),name
        package_inventory(content,[package]);current.append(package)
        report['meshes'][name]=dict(parent=parent,slots=actual,collision='none' if parent=='TH_Dressing' else 'complex',uv_channels=len(row['uv_channels']))
        mesh=body=None
    # Preserve the complete props/tree/material/texture ownership boundary before
    # the one combined obsolete/whole-parent reference preflight.
    from treehouse_pieces import expected_assets
    report['assets']=expected_assets(root.parent)
    report['files']=package_inventory(content,report['assets'])
    retired=retire(editor,previous,current,rows,content)
    report['surfaces']=current;report['retired']=retired
    report['dressing']=[row['package'] for row in rows if row['parent']=='TH_Dressing']
    for file,key in (('pieces.json','pieces_sha256'),('surfaces.json','surfaces_sha256')):
        report[key]=hashlib.sha256((root/file).read_bytes()).hexdigest()
