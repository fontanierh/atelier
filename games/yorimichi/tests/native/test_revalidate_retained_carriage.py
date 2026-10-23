"""Host-only retained-capture fault injection; no native work or real evidence access."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import revalidate_retained_carriage as run
import carriage_host_receipts as io


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    return io.write_new(path, value)


def test_only_material_policy_ast_may_change():
    old=b'COUNT=81\ndef material_text(x):\n return x\ndef compare(x):\n return x\n'
    new=old.replace(b'return x\ndef compare',b'return x.strip()\ndef compare')
    run.comparator_boundary(old,new)
    for changed in (new.replace(b'COUNT=81',b'COUNT=80'),new.replace(b'def compare(x):\n return x',b'def compare(x):\n return True'),
                    new+b'\nextra_gate=False\n',new.replace(b'def material_text',b'def other_policy')):
        with pytest.raises(ValueError): run.comparator_boundary(old,changed)


def test_old_rejection_must_be_reproduced_exactly():
    package='/Game/AtelierValidation/Carriage_0123456789ab'
    expected='Actual material/texture differs: '+package+'/Source/SM_BT_BaggageVan/LOD0/M_BT_Brass/text'
    def fail(*args): raise ValueError(expected)
    value=run.prior_rejection(SimpleNamespace(compare=fail),{},[],{}, {},package)
    assert not value['accepted'] and value['reproduced_from_retained_data']
    for compare in (lambda *args: {},lambda *args: (_ for _ in ()).throw(ValueError('missing geometry'))):
        with pytest.raises(ValueError): run.prior_rejection(SimpleNamespace(compare=compare),{},[],{}, {},package)


def fixture(tmp_path,monkeypatch,*,new_failure=False,late_change=False):
    root=tmp_path/'evidence';root.mkdir();receiver=tmp_path/'receiver';source=tmp_path/'old-source';public=tmp_path/'public-source'
    source.mkdir();receiver.mkdir();public.mkdir();current_host=root/'current-host-01';current_host.mkdir()
    output=root/'current-host-revalidation-01';events=[];retained=io.Retained();native={'module':'same-native'}
    host_pin=dict(path='retained-host-source',head=run.OLD_HOST_HEAD,sha256=run.OLD_HOST_SHA)
    package='/Game/AtelierValidation/Carriage_0123456789ab';specs={}
    driver=source/'games/yorimichi/tests/native/carriage_native_equivalence.py';driver.parent.mkdir(parents=True);driver.write_bytes(b'old native driver\n')
    for phase in ('original','current'):
        base=root/phase;base.mkdir()
        spec=dict(inputs={str(driver):io.digest(driver.read_bytes())},launch=dict(args=['private'],startup_log=str(base/'engine.log')),
                  package=package)
        put(base/'spec.json',spec);retained.load(base/'spec.json');specs[phase]=spec
        put(base/'cleanup.json',dict(remaining={},root='owned-fixture',allowed_packages=['owned']))
        put(base/'startup-ddc.json',dict(launch=spec['launch'],ddc='private'))
        (base/'engine.log').write_text('private startup\n')
    spec_sha=retained.rows[str(root/'current/spec.json')]['sha256']
    whole=dict(exit_code=0,phase='current',native=native,source_head=io.SOURCE_HEAD,receiving_head=io.RECEIVING_HEAD,
        spec_sha256=spec_sha,native_driver=dict(path=str(driver),sha256=io.digest(driver.read_bytes())),host_tool=host_pin,
        work_seconds=2400,queue_seconds=1200,launch=specs['current']['launch'],argv=['editor','private'])
    put(current_host/'whole-result.json',whole)
    marker='CARRIAGE ACTUAL67/81 VEHICLE FIXTURE COMPLETE current '+spec_sha
    snapshot=current_host/'current-stdout.log';snapshot.write_text(marker+'\nwhole0\n');snapshot.chmod(0o444)
    tree=root/'current/guard/memory-health-tree.json';put(tree,dict(state='child_exited'))
    sealed=root/'sealed.json';put(sealed,dict(sealed=True));retained.load(sealed)
    expected='Actual material/texture differs: '+package+'/Source/SM_BT_BaggageVan/LOD0/M_BT_Brass/text'
    def old_compare(*args): events.append('old-compare');raise ValueError(expected)
    proof=SimpleNamespace(__file__=str(driver),compare=old_compare,check_private_launch=lambda spec:spec['launch'],
                          startup_ddc=lambda launch,text:{'ddc':'private'})
    def artifact(row):
        data=Path(row['path']).read_bytes();assert io.digest(data)==row['sha256'];return data
    def guard_binding(value):
        events.append('guard')
        if value.get('original'):return
        assert marker.encode() in artifact(value['stdout']) and json.loads(artifact(value['whole_result']))['exit_code']==0
    original=dict(guard={'original':True})
    session=SimpleNamespace(root=root,receiver=receiver,source=source,output=output,retained=retained,native=native,
        specs=specs,proof=proof,generic=SimpleNamespace(artifact=artifact,guard_binding=guard_binding),tool_binding=lambda:host_pin,
        startup=lambda *args:events.append('startup'))
    def metadata(phase):
        events.append('metadata-'+phase)
        return ({phase:{str(k):{'phase':phase}for k in range(67)}},[phase],{phase:'all reflected material and PNG inputs'},
                {phase:'all door poses'})
    def finish():events.append('finish');retained.check()
    session.metadata=metadata;session.finish=finish
    fake=SimpleNamespace(Session=lambda *args:session,stable_read=io.stable_read,regular=io.regular,SOURCE_HEAD=io.SOURCE_HEAD,
        RECEIVING_HEAD=io.RECEIVING_HEAD,validate_sealed_original=lambda *args:original,
        empty_owned_tree=lambda *args:events.append('empty-root-tree'),physical_absence=lambda *args:events.append('absent'),
        write_new=io.write_new)
    monkeypatch.setattr(run,'load_host',lambda path:fake)
    monkeypatch.setattr(run.build,'__file__',str(receiver/'platform/studio/atelier/build.py'))
    monkeypatch.setattr(run,'clean_head',lambda path:run.NEW_COMPARATOR_HEAD if path==public else'private-host-head')
    comparator=public/'carriage.py';comparator.write_bytes(b'new reviewed public comparator\n')
    binding=dict(path=str(comparator),head=run.NEW_COMPARATOR_HEAD,sha256=io.digest(comparator.read_bytes()))
    observed=io.stable_read(comparator)[1]
    def new_compare(records,vehicles,materials,poses):
        events.append('new-compare')
        assert set(records)=={'original','current'} and all(len(records[p])==67 for p in records)
        assert vehicles==['current'] and set(materials)==set(poses)=={'original','current'}
        if new_failure:raise ValueError('real pixel or native geometry difference')
        if late_change:
            comparator.write_bytes(b'changed comparator\n')
        return dict(fixture_geometry_complete=True,census=dict(meshes=67,lods=81),complete=False,native_complete=False,
                    native_task_reuse=False,production_runtime_complete=False)
    monkeypatch.setattr(run,'load_comparator',lambda *args:(SimpleNamespace(compare=new_compare),binding,observed))
    return root,output,sealed,current_host,public,events


def test_revalidation_retains_both_captures_and_separates_new_comparator_lineage(tmp_path,monkeypatch):
    root,output,sealed,current_host,public,events=fixture(tmp_path,monkeypatch)
    old_files={str(p):p.read_bytes()for p in root.rglob('*')if p.is_file()}
    result=run.revalidate(root,output,sealed,current_host,'old-host-tool',public)
    assert all(Path(p).read_bytes()==data for p,data in old_files.items())
    assert result['fixture_geometry_complete'] and not result['complete'] and not result['native_complete']
    lineage=result['revalidation']
    assert lineage['no_new_native_execution'] and lineage['prior_host_pair_not_accepted']
    assert lineage['comparator']['head']==run.NEW_COMPARATOR_HEAD
    assert lineage['retained_host_tool']['head']==run.OLD_HOST_HEAD
    assert lineage['host_tool']['head']=='private-host-head' and lineage['old_comparison']['accepted'] is False
    assert events.index('old-compare')<events.index('new-compare')<events.index('finish')
    assert (output/'old-comparison-observation.json').exists() and (output/'paired-revalidation-result.json').exists()


@pytest.mark.parametrize('fault',['comparison','source-race'])
def test_revalidation_failure_never_publishes_paired_acceptance(tmp_path,monkeypatch,fault):
    root,output,sealed,current_host,public,_=fixture(tmp_path,monkeypatch,new_failure=fault=='comparison',late_change=fault=='source-race')
    before=(current_host/'whole-result.json').read_bytes()
    with pytest.raises(ValueError):run.revalidate(root,output,sealed,current_host,'old-host-tool',public)
    assert not(output/'paired-revalidation-result.json').exists()
    assert json.loads((output/'revalidation-failure.json').read_text())['accepted'] is False
    assert (current_host/'whole-result.json').read_bytes()==before
    assert (output/'old-comparison-observation.json').exists()
