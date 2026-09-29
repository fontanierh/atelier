"""Read back every imported corrective at 60 Hz and the runtime-compressed poses."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
from pathlib import Path
import json
import unreal as U
ROOT = yori.OUT
OUT=ROOT/'cairo'
config=json.loads((OUT/'export.json').read_text())
E=U.EditorAssetLibrary
P=U.AnimPoseExtensions
mesh=E.load_asset('/Game/Cairo/SK_Cairo')
options=U.AnimPoseEvaluationOptions()
options.evaluation_type=U.AnimDataEvalType.COMPRESSED
options.optional_skeletal_mesh=mesh
definition=E.load_asset('/Game/Cairo/DA_Cairo')
roles={r['role'] for r in config['roles']}
actions={str(k) for k in definition.get_editor_property('actions')}
# SwordRun is an alias of SwordSprint added by import_cairo_armed.py, which runs after this check.
assert roles-{'SwordRun'}<=actions<=roles,(sorted(roles-actions),sorted(actions-roles))
assert definition.get_editor_property('use_authored_movement')
run=E.load_asset('/Game/Cairo/A_Run')
assert abs(run.get_editor_property('rate_scale')-.8)<1e-6
reference=P.get_reference_pose(mesh.skeleton)
rest={b:[getattr(P.get_bone_pose(reference,b,U.AnimPoseSpaces.WORLD).translation,a) for a in ["x","y","z"]] for b in ['root','pelvis','head','foot_L','foot_R','toe_L','toe_R']}
morphs=[m.get_name() for m in mesh.get_editor_property('morph_targets')]
errors=[];max_error=0;rows={}
for slot in mesh.materials:
    name=str(slot.get_editor_property('imported_material_slot_name'))
    mat=slot.material_interface
    assert mat and mat.get_path_name()=='/Game/Cairo/'+name+'.'+name,('Unsaved material binding',name,mat)
    assert mat.get_editor_property('used_with_skeletal_mesh')
    assert mat.get_editor_property('used_with_morph_targets')
    assert mat.get_editor_property('two_sided')==config['materials'][name]['two_sided']

for name,cfg in config['clips'].items():
    clip=E.load_asset('/Game/Cairo/A_'+name)
    assert clip, name
    worst=0;checked=0;worst_sample=None
    for frame in range(cfg['frames']):
        pose=P.get_anim_pose_at_time(clip,frame/60,options)
        assert P.is_valid(pose)
        for key,values in cfg['expected_morph_curves'].items():
            # Importers can prefix a mesh identifier. Require exactly one match.
            matches=[m for m in morphs if m==key or m.endswith('_'+key)]
            assert len(matches)==1,(key,matches)
            actual=P.get_curve_weight(pose,matches[0])
            err=abs(actual-values[frame]);checked+=1
            if err>worst:
                worst=err;worst_sample={'frame':frame,'curve':key,'expected':values[frame],'actual':actual}
    if worst>.002:errors.append(name+': corrective error '+str(worst))
    max_error=max(max_error,worst)
    rows[name]={'frames':cfg['frames'],'checked_curve_samples':checked,'max_curve_error':worst,'worst_sample':worst_sample}
report={'passed':not errors,'errors':errors,'rest_bones_cm':rest,'morph_targets':morphs,'clips':rows,'max_curve_error':max_error}
(OUT/'unreal_validation.json').write_text(json.dumps(report,indent=2)+'\n')
U.log('CAIRO VALIDATION '+json.dumps(report))
assert not errors,errors
