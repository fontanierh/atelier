"""Current forest source/collision/LOD checks and one complete native retirement preflight."""
import json
import math
from pathlib import Path
from atelier import native_membership
from atelier.export_manifest import real_directory
from atelier.mesh_geometry import SIDECARS

ASSETS='/Game/Japan/Assets'
LODS='/Game/Japan/FoliageLODs'
PREFIXES=('Tree_Tuscan_','Tree_Forest_')
TRUNKS={}


def configure(trees):
    global TRUNKS
    TRUNKS={name:data['trunk_hulls'] for name,data in trees.items()}


def inventory(editor):
    return set().union(*(native_membership.inventory(editor,root,prefix) for root in (ASSETS,LODS) for prefix in PREFIXES))


def prepare_source(name,destination):
    """Only an actual admission miss may clear the old owner hulls before raw FBX import."""
    import unreal as U
    E=U.EditorAssetLibrary;meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    path=destination+'/'+name
    if E.does_asset_exist(path):
        mesh=E.load_asset(path)
        if meshes.get_simple_collision_count(mesh) or meshes.get_convex_collision_count(mesh):
            assert meshes.remove_collisions(mesh),(name,'raw source collision reset')
        assert meshes.get_simple_collision_count(mesh)==meshes.get_convex_collision_count(mesh)==0,name


def reusable_collision(mesh):
    import unreal as U
    meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    expected=0 if '_LOD' in mesh.get_name() else 1
    counts=meshes.get_simple_collision_count(mesh)==0 and meshes.get_convex_collision_count(mesh)==expected
    return counts and (expected==0 or (mesh.get_name() in TRUNKS and hulls_match(mesh,TRUNKS[mesh.get_name()])))


def hulls_match(mesh,hulls):
    import unreal as U
    actual=json.loads(U.CitySurfaceValidation.collision_vertices(mesh))
    expected=[]
    for hull in hulls:
        matrix=hull['matrix'];points=[]
        for point in hull['vertices']:
            v=[sum(matrix[i][j]*point[j] for j in range(3))+matrix[i][3] for i in range(3)]
            points.append([v[0]*100.,-v[1]*100.,v[2]*100.])
        expected.append(sorted(points))
    remaining=[sorted(points) for points in actual]
    if len(expected)!=len(remaining):return False
    for points in expected:
        found=next((i for i,candidate in enumerate(remaining) if len(candidate)==len(points) and all(
            abs(a-b)<=max(.001,2.**(math.frexp(max(abs(a),abs(b)))[1]-23))
            for left,right in zip(points,candidate) for a,b in zip(left,right))),None)
        if found is None:return False
        remaining.pop(found)
    return not remaining


def validate_current(trees):
    import unreal as U
    E=U.EditorAssetLibrary;meshes=U.get_editor_subsystem(U.StaticMeshEditorSubsystem)
    current=[]
    for name,data in trees.items():
        base=E.load_asset(ASSETS+'/'+name)
        if not base or base.get_num_lods()!=5 or not reusable_collision(base) or not hulls_match(base,data['trunk_hulls']):
            raise ValueError('Current forest base/collision differs: '+name)
        if meshes.get_collision_complexity(base)!=U.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX:
            raise ValueError('Forest trunk query policy changed: '+name)
        for level,count in enumerate(data['triangles']):
            if base.get_num_triangles(level)!=count or meshes.get_num_uv_channels(base,level)!=1:
                raise ValueError('Forest assembled level geometry differs: '+name)
            settings=meshes.get_lod_build_settings(base,level)
            if settings.get_editor_property('use_full_precision_u_vs'):
                settings.set_editor_property('use_full_precision_u_vs',False)
                meshes.set_lod_build_settings(base,level,settings)
            if meshes.get_lod_build_settings(base,level).get_editor_property('use_full_precision_u_vs'):
                raise ValueError('Forest UV precision did not persist: '+name)
            if level:
                source=E.load_asset(LODS+'/'+name+f'_LOD{level}')
                if not source or source.get_num_triangles(0)!=count or not reusable_collision(source):
                    raise ValueError('Forest source LOD differs: '+name)
                current.append(LODS+'/'+name+f'_LOD{level}')
        if not E.save_loaded_asset(base):raise ValueError('Forest current chain save failed: '+name)
        current.append(ASSETS+'/'+name)
    return current


def retire(editor,previous,current,content):
    real_directory(content)
    for package in previous|set(current):
        path=Path(content)/(package[6:]+'.uasset');real_directory(path.parent)
        if path.is_symlink() or (package in current and not path.is_file()):
            raise ValueError('Current/linked forest native primary')
    if any(not editor.does_asset_exist(p) for p in current):
        raise ValueError('Incomplete current forest membership')
    obsolete=previous-set(current)
    retired=native_membership.retire_replaced(editor,{p:current for p in obsolete}) if obsolete else []
    for package in retired:
        path=Path(content)/package[6:]
        if any(path.with_suffix(s).exists() or path.with_suffix(s).is_symlink() for s in SIDECARS):
            raise ValueError('Superseded forest package remains physically present')
    if inventory(editor)!=set(current):raise ValueError('Forest current membership differs')
    return retired
