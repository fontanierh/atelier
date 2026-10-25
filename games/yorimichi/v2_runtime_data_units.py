"""Replace only the actual data.stage callback with a normal bound recipe Call."""
from copy import deepcopy
import importlib.util
from pathlib import Path,PurePosixPath

BODY='games/yorimichi/world/runtime_data_v2.py'
ORIGINAL='games/yorimichi/runtime_data.py'
CONTENT='games/yorimichi/unreal/Content/Data/'


def _load(root,path,name):
    spec=importlib.util.spec_from_file_location(name,root/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def lower(rows,*,checkout):
    """@cc [owner:fontanierh,label:correctness] actual-runtime-data-row-replacement
    Replacement MUST preserve the actual data.stage row's original dependencies,
    required inputs and complete output roster. Source/destination pairs MUST come
    from original staged/staged_source APIs and use existing bound path defaults.
    All generated reads MUST have real declared owners before ordinary lower_inputs
    binds them. The old Context/log ABI and ambient content locator MUST NOT run.
    Course/scene/surface reader inputs MUST remain complete; no output/optional skip
    or generic worker/compiler ABI MAY be invented.
    """
    from atelier.build import Call,Step
    from atelier.build_v2.recipe_dependencies import extract
    root=Path(checkout).resolve();rows=list(rows);found=[row for row in rows if row['id']=='data.stage']
    if len(found)!=1:raise ValueError('Runtime staging requires its unique actual data.stage row')
    row=found[0]
    if (len(row['commands'])!=1 or row['commands'][0].get('kind')!='call'
            or row['commands'][0]['fn']['source']!=ORIGINAL or row['commands'][0]['fn']['qualname']!='stage_data'
            or row['products'] or row['verify'] is not None):raise ValueError('Runtime staging original callback/output declaration differs')
    runtime=_load(root,ORIGINAL,'runtime_stage_original_mapping')
    reads=[r for r in row['reads'] if r['product']=='skatepark.runtime']
    suffix=('skatepark','runtime-park.json')
    if len(reads)!=1 or len(reads[0]['paths'])!=1 or PurePosixPath(reads[0]['paths'][0]).parts[-2:]!=suffix:
        raise ValueError('Runtime staging requires its actual skatepark runtime source root')
    out=root/PurePosixPath(reads[0]['paths'][0]).parent.parent
    def relative(path):
        value=Path(path)
        if not value.is_absolute() or not value.is_relative_to(root) or '..' in value.parts:raise ValueError('Runtime source paths must be canonical checkout-relative')
        return value.relative_to(root).as_posix()
    names=runtime.staged(out);outputs=[CONTENT+name for name in names]
    if list(row['outputs'])!=outputs or len(set(outputs))!=len(outputs):raise ValueError('Runtime staging complete original output roster differs')
    table=tuple((runtime.staged_source(out,name),root/destination) for name,destination in zip(names,outputs))
    declared=[(path,owner['id']) for owner in rows if owner['id']!='data.stage' for path in
        [*owner['outputs'],*(path for product in owner['products'] for path in (*product['paths'],*product['optional_paths']))]]
    source_inputs=[]
    for source,_ in table:
        path=relative(source)
        if source.is_relative_to(out):
            owners=[(owned,owner) for owned,owner in declared if path==owned or path.startswith(owned+'/')]
            if not owners:raise ValueError('Runtime generated source lacks a declared producer: '+path)
            longest=max(len(owned) for owned,_ in owners)
            if len(set((owned,owner) for owned,owner in owners if len(owned)==longest))!=1:raise ValueError('Runtime generated source has ambiguous ownership: '+path)
        elif not source.is_file():raise ValueError('Missing committed runtime source: '+path)
        source_inputs.append({'path':path,'root':'checkout','optional':False})
    body=_load(root,BODY,'runtime_stage_bound_body')
    body.stage.__defaults__=(table,runtime.RACING_COURSES,runtime.ASSETS/'belmonte/source.json',runtime.RACING_VALIDATOR)
    authored=extract([Step('data.stage',[Call('stage_runtime_data',body.stage)])],checkout=root,build_root=out.parent,
        import_roots=(root/'platform/studio',root/'games/yorimichi/world'))[0]
    result=deepcopy(row);result['commands']=authored['commands'];result['code']=sorted(set(row['code'])|set(authored['code']))
    for incoming in source_inputs:
        if incoming not in result['inputs']:result['inputs'].append(incoming)
    # Original validation roles must be declared even though the new named body has no old globals.
    required={relative(runtime.RACING_COURSES),relative(runtime.RACING_VALIDATOR),relative(runtime.ASSETS/'belmonte/source.json'),
        *(relative(path) for path in runtime.courses.surface_inputs())}
    if not required<={entry['path'] for entry in result['inputs']}|set(result['code']):raise ValueError('Runtime original course/source validation closure is incomplete')
    return {'rows':[result],'aliases':{'data.stage':('data.stage',)}}
