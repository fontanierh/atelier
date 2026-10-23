"""Strict retained native DATA validation with explicit finite query noncoverage."""
from atomic_equivalence_io import canonical,require
import track_native_equivalence as proof
from track_query_scope import VIADUCTS


def validate(records,runtime,source_controls,*,progress=None):
    """@cc [owner:fontanierh,label:correctness] track-data-query-noncoverage
    Every saved source/GPU/cooked/hull/bounds/LOD/policy record MUST validate.
    Only the fourteen identified legacy viaduct positive rows MAY be reported as
    unsupported outcomes. All schemas, source inputs and other outcomes MUST pass.
    This MUST NOT turn failed native/query callers into complete equivalence.
    """
    expected=proof.runtime_inventory(runtime);require(set(records)==set(expected)==set(source_controls),'Incomplete retained137 census')
    proof.validate_controls(source_controls,runtime)
    failures=[];geometry={};complete=[];query_count=0
    for name,levels in expected.items():
        record=records[name];require(record['policy_scope']=='fixture','Production scope cannot be invented')
        proof.whole_bounds(record);raw=proof.native_raw_set(record,name)
        require(set(raw['render_lods'])==set(raw['source_lods'])==set(raw['source_presence'])==set(range(levels)),name+' incomplete source/GPU LOD census')
        require(all(raw['source_lods'][k] and raw['source_presence'][k]=={True} for k in range(levels)),name+' unavailable saved source MD')
        if proof.collision_lods(runtime)[name]>=0:require(raw['cooked'],name+' missing actual cooked collision')
        require(raw['probes']['logical']==name and isinstance(raw['probes']['seams'],list),'Wrong probe logical/schema')
        rows=raw['probes']['controls'];query_count+=len(rows);required={'ray_negative','capsule_negative'}
        if proof.collision_lods(runtime)[name]>=0:required|={'ray_positive','capsule_positive'}
        require(len(rows)==len(required) and {r['kind']for r in rows}==required,name+' incomplete query schema')
        observed=[dict(id=r['id'],kind=r['kind'],input=r['input'])for r in rows]
        require(canonical(observed)==canonical(source_controls[name]),name+' query input differs from immutable source controls')
        bad=[]
        for row in rows:
            require(set(row)=={'id','kind','input','target','hit'} and row['target']in record['meshes'],name+' query target/schema differs')
            hit=row['hit']
            if hit is not None:
                require(isinstance(hit,dict) and set(hit)=={'position','normal','distance','logical','blocking'}
                    and hit['logical']==name and hit['blocking']is True
                    and type(hit['distance'])in(int,float) and hit['distance']>=0
                    and all(isinstance(hit[k],list) and len(hit[k])==3 and all(type(v)in(int,float)for v in hit[k])
                        for k in ('position','normal')),name+' malformed actual hit')
            if row['kind'].endswith('_negative')!=(row['hit']is None):
                bad.append(dict(mesh=name,id=row['id'],kind=row['kind'],expected_hit=row['kind'].endswith('_positive'),actual_hit=row['hit']))
        failures.extend(bad)
        if not bad:complete.append(name)
        geometry[name]=dict(saved_source_lods=levels,gpu_lods=levels,cooked_complete=True,bounds_policy_complete=True)
        if progress is not None:progress(name)
    finite={(name,name+'.'+shape+'.positive',shape+'_positive')for name in VIADUCTS for shape in ('ray','capsule')}
    require({(r['mesh'],r['id'],r['kind'])for r in failures}==finite and len(failures)==14,
        'Query outcomes differ from the exact known fourteen positive noncoverage rows')
    require(len(complete)==130 and query_count==540,'Incomplete130-owner/540-row query census')
    return dict(geometry_data_validated=True,geometry_owners=137,geometry_lods=362,geometry=geometry,
        failed_query_rows=failures,positive_unproven_owners=list(VIADUCTS),query_complete_owners=complete,
        query_complete_owner_count=130,query_row_count=query_count,successful_query_row_count=query_count-len(failures),query_all_pass=False,native_complete=False,original_current_equivalence=False)
