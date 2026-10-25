"""Stage the original cockpit, prepared model table and exact authored playable grip bytes."""
import importlib.util
import json
from pathlib import Path
import re
import shutil


def _module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def run(context):
    """@cc [owner:fontanierh,label:correctness] complete-kart-authored-runtime-data
    Runtime data MUST use the actual cockpit/manifest source Items and complete
    declared character/adventure roster. The original source_identity APIs MUST
    select every playable grip and independent prepared-model receipt. Cockpit
    and grip bytes MUST be preserved; missing/stale/layout-mismatched profiles
    MUST fail before publication. No native work, registration, guessed grip,
    generated checkout scan or ambient character source MAY supply these outputs.
    """
    if context.params:raise ValueError('Kart data uses only its explicit source inputs')
    job=Path(__file__).resolve().parents[3]
    codec=_module(job/'platform/studio/atelier/build_v2/recipe_job.py','kart_root_codec')
    identity=_module(job/'games/yorimichi/tools/kart_grip_editor/source_identity.py','kart_authored_identity')
    scratch=context.output_dir/'.kart-inputs'
    if scratch.exists():raise ValueError('Kart data scratch must be fresh')
    scratch.mkdir(parents=True)
    def file(slot):
        path=context.input(slot)
        if path.is_symlink() or not path.is_file():raise ValueError('Kart source must be a declared regular file')
        return path
    def source_root(slot):
        root=context.input(slot)
        if root.is_symlink() or not root.is_dir():raise ValueError('Kart requires its complete frozen source Item')
        files=sorted(root.rglob('*'))
        archives=[p for p in files if p.is_file()]
        if (not archives or any(p.is_symlink() for p in files)
                or any(not p.name.endswith('.tree.tar') for p in archives)):
            raise ValueError('Kart source Item has foreign or missing ROOT members')
        if len(archives)!=(1 if slot=='cockpit' else 2):raise ValueError('Kart source Item ROOT census differs')
        values=[];kinds=[]
        for index,path in enumerate(archives):
            target=scratch/(slot+'-'+str(index))
            manifest=codec.unpack_root(path,target);kinds.append(manifest['kind'])
            if manifest['kind']=='file':values.append(target.read_bytes())
        if sorted(kinds)!=(['file'] if slot=='cockpit' else ['directory','file']):raise ValueError('Kart source ROOT kinds differ')
        if len(values)!=1:raise ValueError('Kart source Item must contain exactly its declared file ROOT')
        return values[0]
    try:
        cockpit_bytes=source_root('cockpit');manifest_bytes=source_root('manifest')
        cockpit=json.loads(cockpit_bytes);manifest=json.loads(manifest_bytes)
        parts={'SM_Kart_Body','SM_Kart_Seat','SM_Kart_Wheel','SM_Kart_SteeringWheel'}
        if (set(manifest)!=parts|{'layout'} or manifest['layout']!=cockpit or cockpit.get('schema')!=1
                or any(type(manifest[k].get('triangles')) is not int or manifest[k]['triangles']<=0 for k in parts)
                or sum(manifest[k]['triangles'] for k in parts)>6000):
            raise ValueError('Kart source manifest/cockpit or original total budget differs')
        chars=scratch/'game/assets/characters';chars.mkdir(parents=True)
        roles={'definition':{},'adventure':{},'grip':{},'model':{}}
        for slot,path in context.inputs.items():
            if slot in ('cockpit','manifest'):continue
            kind,sep,name=slot.partition('.')
            if not sep or kind not in roles or re.fullmatch('[a-z][a-z0-9-]*',name) is None:
                raise ValueError('Unexpected Kart character input role')
            roles[kind][name]=path
        if not roles['definition'] or set(roles['adventure'])!=set(roles['definition']):
            raise ValueError('Kart requires the complete explicit declaration roster')
        filenames={'definition':'character.toml','adventure':'adventure.toml','grip':'kart-grip.json','model':'kart-grip-model.json'}
        for kind,entries in roles.items():
            for name,path in entries.items():
                if path is None:
                    if kind!='adventure':raise ValueError('Missing required Kart authored character input')
                    continue
                folder=chars/name;folder.mkdir(exist_ok=True)
                shutil.copyfile(file(kind+'.'+name),folder/filenames[kind])
        identity.GAME=chars.parent.parent
        playable=identity.playable_ids()
        if not playable or set(roles['grip'])!=set(playable) or set(roles['model'])!=set(playable):
            raise ValueError('Kart grip/model roster differs from the original playable declarations')
        models=identity.prepared_models(chars)
        expected={'cockpit.json','prepared-models.json',*('grips/'+name+'.json' for name in playable)}
        if set(context.outputs)!=expected:raise ValueError('Kart data output roster differs from actual playable membership')
        grips={}
        for name in playable:
            path=identity.profile_path(name,chars);raw=path.read_bytes();pose=json.loads(raw)
            if pose.get('schema')!=1 or pose.get('character')!=name or pose.get('layout')!=manifest['layout']:
                raise ValueError('Stale or invalid original Kart grip: '+name)
            receipt=models['models'][name]
            if pose.get('model_sha256')!=receipt.get('model_sha256') or identity.digest(pose['bind_world'])!=receipt.get('bind_sha256'):
                raise ValueError('Kart authored grip does not match its independent prepared-model receipt: '+name)
            grips[name]=raw
        context.output('cockpit.json').write_bytes(cockpit_bytes)
        context.output('prepared-models.json').write_text(json.dumps(models,indent=2)+'\n')
        for name,raw in grips.items():context.output('grips/'+name+'.json').write_bytes(raw)
    finally:
        shutil.rmtree(scratch)
