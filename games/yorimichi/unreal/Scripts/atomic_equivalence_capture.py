"""Capture actual bounded native evidence from caller-owned components, without changing assets.

Call capture(components, logical, output, controls=..., seams=..., policy_scope='fixture')
after the real owner has imported, validated and saved its assets. Components and imports
belong to the receiving fixture; this module neither synthesizes geometry nor mutates their
materials/collision/culling. Supply actual production-created components for production policy.
The host tools/atomic_equivalence.py independently validates every raw page and query record.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'world'))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.mesh_geometry import SIDECARS  # noqa: E402


def artifact(path):
    path=Path(path);real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Native evidence must be a regular owned file')
    return dict(path=str(path.absolute()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _value(text):
    if not isinstance(text,str) or not text:raise ValueError('Native readback refused missing/unsupported data')
    value=json.loads(text,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite native evidence')))
    if isinstance(value,dict) and 'refusal' in value:raise ValueError('Native readback refused: '+str(value))
    return value


def _bounds_policy(row):
    def valid(value):
        return (isinstance(value,dict) and set(value)=={'origin','extent','sphere_radius'}
            and all(isinstance(value.get(k),list) and len(value[k])==3
                and all(type(v) in (int,float) and math.isfinite(v) for v in value[k]) for k in ('origin','extent'))
            and all(v>=0 for v in value['extent']) and type(value.get('sphere_radius')) in (int,float)
            and math.isfinite(value['sphere_radius']) and value['sphere_radius']>=0)
    if (not valid(row.get('component_bounds')) or type(row.get('bounds_scale')) not in (int,float)
            or not math.isfinite(row['bounds_scale']) or row['bounds_scale']<=0 or type(row.get('lod_coordinated')) is not bool
            or (row['lod_coordinated'] and (not valid(row.get('logical_bounds')) or row['logical_bounds']!=row['component_bounds']))
            or (not row['lod_coordinated'] and row.get('logical_bounds') is not None)):
        raise ValueError('Missing actual component bounds/sphere or logical LOD policy')


def valid_mesh_path(path):
    match=re.fullmatch(r'/Game/(?:[A-Za-z0-9_]+/)*(?P<name>[A-Za-z][A-Za-z0-9_-]*)\.(?P=name)',path)
    if not match:return False
    name=match.group('name')
    if '_cell_' in name:
        prefix,cell=name.split('_cell_',1)
        return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',prefix) and re.fullmatch(
            r'(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?',cell))
    return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name))


def capture(components,logical,output,*,controls,seams=(),policy_scope='fixture',inputs=(),page_size=16384,api=None,unreal_module=None):
    """@cc [owner:fontanierh,label:correctness] observed-native-equivalence-pages
    Read ONLY caller-owned actual saved meshes/components. Every available render LOD and
    source description, actual GPU tangent/binormal/UV/color data and full cooked collision
    MUST be captured through the compiled native reader. Missing/unsupported data MUST fail;
    counts or generated substitute geometry MUST NOT replace it. Positive/negative/seam
    probes MUST query their exact selected component with the declared real shape/segment.
    Retain exact input bytes before/after. Do not mark fixture policy as production policy.
    This collector MUST NOT import, save, regenerate, change or destroy native assets/actors.
    """
    if unreal_module is None:
        import unreal as unreal_module
    if api is None:api=unreal_module.NativeAtomicEquivalence
    components=tuple(components)
    if (not components or not isinstance(logical,str) or not logical or policy_scope not in ('fixture','production')
            or type(page_size) is not int or not 0<page_size<=32768):raise ValueError('Invalid native capture scope')
    root=real_directory(Path(output).absolute())
    if root.exists() or root.is_symlink():raise ValueError('Native capture requires a fresh exclusive output')
    before=[artifact(path) for path in inputs]
    content=real_directory(Path(unreal_module.Paths.project_content_dir()).absolute())
    editor=unreal_module.get_editor_subsystem(unreal_module.StaticMeshEditorSubsystem)
    if editor is None:raise ValueError('Actual stored LOD settings are unavailable')
    saved_files=[]
    by_component={component.get_path_name():component for component in components}
    if len(by_component)!=len(components):raise ValueError('Duplicate native component')
    by_mesh={};policies=[];root.mkdir(parents=True)
    for component in components:
        mesh=component.get_editor_property('static_mesh')
        if mesh is None:raise ValueError('Selected native component has no mesh')
        mesh_path=mesh.get_path_name()
        if not valid_mesh_path(mesh_path):
            raise ValueError('Native capture only accepts exact saved project mesh paths')
        package=mesh_path.split('.')[0]
        primary=content/(package[len('/Game/'):]+'.uasset')
        saved_files.append(artifact(primary))
        for suffix in SIDECARS:
            if suffix=='.uasset':continue
            sidecar=primary.with_suffix(suffix)
            if sidecar.exists() or sidecar.is_symlink():saved_files.append(artifact(sidecar))
        by_mesh[mesh_path]=mesh
        row=_value(api.component_policy(component))
        _bounds_policy(row)
        if row['lod_coordinated']!=(mesh.get_num_lods()>1):raise ValueError('Observed LOD policy contradicts actual render LOD census')
        if row.get('component')!=component.get_path_name() or row.get('mesh')!=mesh_path:
            raise ValueError('Component policy identity changed')
        owner=component.get_owner()
        row['owner_class']=owner.get_class().get_path_name() if owner is not None else None
        row['policy_scope']=policy_scope
        if policy_scope=='production' and (not isinstance(row['owner_class'],str) or not row['owner_class'].startswith('/Script/Yorimichi.')):
            raise ValueError('Production policy requires an actual production owner; fixture actors cannot claim it')
        path=root/'components'/(hashlib.sha256(component.get_path_name().encode()).hexdigest()+'.json')
        atomic_json(path,row);policies.append(artifact(path))
    pages=[]
    for mesh_path,mesh in sorted(by_mesh.items()):
        stem=hashlib.sha256(mesh_path.encode()).hexdigest()
        lods=mesh.get_num_lods()
        if type(lods) is not int or lods<1:raise ValueError('Missing actual native LOD inventory')
        screen_sizes=list(editor.get_lod_screen_sizes(mesh))
        if len(screen_sizes)!=lods:raise ValueError('Stored native LOD screen-size inventory is incomplete')
        nanite=unreal_module.AssetRegistryHelpers.create_asset_data(mesh).get_tag_value('NaniteEnabled')
        if nanite!='False':raise ValueError('Native reader requires the actual non-Nanite render surface, not a fallback proxy')
        for lod in range(lods):
            first=0;total=None
            while total is None or first<total:
                row=_value(api.snapshot(mesh,logical,first,page_size,lod))
                if (row.get('asset')!=mesh_path or row.get('logical')!=logical or row.get('first')!=first
                        or row.get('maximum')!=page_size or row.get('lod')!=lod
                        or not isinstance(row.get('settings'),dict) or row['settings'].get('lods')!=lods):
                    raise ValueError('Native geometry page identity differs')
                body=mesh.get_editor_property('body_setup')
                if body is None:raise ValueError('Missing actual saved native collision body')
                row['settings']['double_sided_geometry']=bool(body.get_editor_property('double_sided_geometry'))
                row['settings']['lod_screen_sizes']=screen_sizes
                row['settings']['nanite_enabled']=False  # Actual registry readback above, never an assumed import option.
                counts=[row.get(key) for key in ('source_count','render_count','cooked_count')]
                if any(type(value) is not int or value<0 for value in counts) or not counts[1]:
                    raise ValueError('Native geometry requires positive actual rendered triangles')
                expected=max(counts)
                if total is not None and total!=expected:raise ValueError('Native geometry changed during pagination')
                total=expected
                for field,count in zip(('source','render','cooked'),counts):
                    value=row.get(field)
                    triangles=value.get('triangles') if isinstance(value,dict) else value
                    if field=='source' and value is None and count==0 and row.get('source_available') is False:continue
                    if not isinstance(triangles,list) or len(triangles)!=max(0,min(page_size,count-first)):
                        raise ValueError('Native geometry page omitted actual triangles: '+field)
                path=root/'pages'/(stem+'-lod'+str(lod)+'-'+str(first)+'.json')
                atomic_json(path,row);pages.append(artifact(path));first+=page_size
                print('NATIVE EQUIVALENCE page '+logical+' '+mesh_path+' LOD'+str(lod)+' '+str(min(first,total))+'/'+str(total),flush=True)
    probe_rows=[];seen=set()
    for control in controls:
        if (not isinstance(control,dict) or set(control)!={'id','kind','input','target'} or control['id'] in seen
                or control['target'] not in by_component):raise ValueError('Invalid selected-component native control')
        seen.add(control['id']);component=by_component[control['target']];query=control['input']
        if query.get('channel')!='selected_component':
            raise ValueError('Native direct-component probes require channel=selected_component; world channel filtering is not observed')
        capsule='capsule' in control['kind'];radius=query.get('radius_cm',0.) if capsule else 0.
        half_height=query.get('half_height_cm',0.) if capsule else 0.
        rotation=query.get('orientation',[0.,0.,0.,1.])
        observed=_value(api.probe(component,unreal_module.Vector(*query['start']),unreal_module.Vector(*query['end']),
            unreal_module.Quat(*rotation),radius,half_height,query['trace_complex']))
        mesh_path=component.get_editor_property('static_mesh').get_path_name()
        if (observed.get('component')!=component.get_path_name() or observed.get('mesh')!=mesh_path
                or observed.get('selected_component') is not True):raise ValueError('Native query escaped selected component')
        hit=None
        if observed.get('blocking') is True:
            hit={key:observed[key] for key in ('position','normal','distance')}
            hit.update(logical=logical,blocking=True)
        elif observed.get('blocking') is not False:raise ValueError('Native query omitted blocking result')
        probe_rows.append(dict(id=control['id'],kind=control['kind'],input=query,target=mesh_path,hit=hit))
    probe_path=root/'probes.json';atomic_json(probe_path,dict(logical=logical,controls=probe_rows,seams=list(seams)))
    if [artifact(path) for path in inputs]!=before:raise ValueError('Native capture source/payload inputs changed')
    unique_saved={row['path']:row for row in saved_files}
    if any(artifact(row['path'])!=row for row in unique_saved.values()):raise ValueError('Saved native package bytes changed during readback')
    result=dict(format='unreal_atomic_native_v2',logical=logical,raw_pages=pages,component_policies=policies,
        probes=artifact(probe_path),meshes=sorted(by_mesh),policy_scope=policy_scope,inputs=before,saved_packages=list(unique_saved.values()))
    atomic_json(root/'native-descriptor.json',result)
    print('NATIVE EQUIVALENCE CAPTURE COMPLETE '+logical,flush=True)
    return result


def main():
    import os
    import unreal
    spec_path=Path(os.environ['ATELIER_ATOMIC_NATIVE_SPEC']);real_directory(spec_path.parent)
    if spec_path.is_symlink() or not spec_path.is_file():raise ValueError('Native capture spec must be regular')
    payload=spec_path.read_bytes();spec=json.loads(payload)
    if set(spec)!={'schema','logical','components','output','controls','seams','policy_scope','inputs'} or spec['schema']!=1:
        raise ValueError('Invalid native capture command spec')
    components=[unreal.load_object(None,path) for path in spec['components']]
    if not all(components):raise ValueError('Selected current native components are missing')
    result=capture(components,spec['logical'],spec['output'],controls=spec['controls'],seams=spec['seams'],
        policy_scope=spec['policy_scope'],inputs=[spec_path,*map(Path,spec['inputs'])])
    if spec_path.read_bytes()!=payload:raise ValueError('Native capture spec changed')
    return result


if __name__=='__main__':main()
