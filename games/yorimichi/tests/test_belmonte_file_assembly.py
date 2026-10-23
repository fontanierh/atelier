"""File-only assembly preserves complete query aliases and refuses foreign outputs."""
import hashlib
import importlib
from pathlib import Path

import pytest

from atelier.atomic_files import atomic_json
from atelier.export_manifest import sha

GAME=Path(__file__).resolve().parents[1]


@pytest.fixture
def assembly(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return importlib.import_module('belmonte.assemble')


def inputs(tmp_path,assembly):
    from test_belmonte_ground_pieces import model
    raw=model();source=tmp_path/'source.glb';source.write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest();files={key:{} for key in assembly.FOLDERS};surfaces=[]
    for name in assembly.NORTH:
        files['ground/glb'][name+'.glb']=(source,digest)
        files['natural'][name+'.glb']=(source,digest)
        surfaces.append(dict(name=name,path='ground/glb/'+name+'.glb',sha256=digest,
            bounds_m=[[0.,0.,0.],[20.,20.,0.]],triangles=4))
    files['glb']['SM_BM_Witness.glb']=(source,digest)
    report=dict(meshes=[dict(name='SM_BM_Witness',path='glb/SM_BM_Witness.glb',sha256=digest)],materials={})
    return files,surfaces,report


def test_file_assembly_preserves_alias_bytes_unchanged_mtimes_and_native_report(tmp_path,assembly):
    files,surfaces,report=inputs(tmp_path,assembly);out=tmp_path/'out'
    assembly.publish(out,files,assembly.previous(out),dict(version=1),report,surfaces)
    assert (out/'glb/SM_BM_Witness.glb').read_bytes()==(tmp_path/'source.glb').read_bytes()
    before={p.relative_to(out).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in out.rglob('*.glb')}
    (out/'import-report.json').write_bytes(b'owned-by-native')
    assembly.publish(out,files,assembly.previous(out),dict(version=1),report,surfaces)
    assert before=={p.relative_to(out).as_posix():(p.read_bytes(),p.stat().st_mtime_ns) for p in out.rglob('*.glb')}
    assert (out/'import-report.json').read_bytes()==b'owned-by-native'
    assert not (out/assembly.JOURNAL).exists()


@pytest.mark.parametrize('fault',['foreign','link','directory','bad_source','broken_root_link','unrecorded_old'])
def test_all_destination_and_source_refusals_precede_any_owned_write(tmp_path,assembly,fault):
    files,surfaces,report=inputs(tmp_path,assembly);out=tmp_path/'out'
    assembly.publish(out,files,assembly.previous(out),dict(version=1),report,surfaces)
    before=(out/'build-report.json').read_bytes();outside=tmp_path/'external';outside.write_bytes(b'keep')
    if fault=='foreign':(out/'glb/Foreign.glb').write_bytes(b'keep')
    elif fault=='link':
        path=out/'natural'/surfaces[0]['name'];path=path.with_suffix('.glb');path.unlink();path.symlink_to(outside)
    elif fault=='directory':(out/'textures/Unknown').mkdir()
    elif fault=='bad_source':
        files['glb']['SM_BM_Witness.glb']=(tmp_path/'source.glb','0'*64)
    elif fault=='broken_root_link':
        link=tmp_path/'linked';link.symlink_to(tmp_path/'missing');out=link
    elif fault=='unrecorded_old':
        (out/'glb/Former.glb').write_bytes(b'keep')
    with pytest.raises((ValueError,FileNotFoundError)):
        assembly.publish(out,files,assembly.previous(out),dict(version=2),report,surfaces)
    assert outside.read_bytes()==b'keep' and (tmp_path/'out/build-report.json').read_bytes()==before


def test_retire_only_prior_complete_members_after_current_publication(tmp_path,assembly):
    files,surfaces,report=inputs(tmp_path,assembly);out=tmp_path/'out'
    old=dict(report,meshes=[*report['meshes'],dict(name='SM_BM_Former',path='glb/SM_BM_Former.glb',sha256=sha(tmp_path/'source.glb'))])
    files['glb']['SM_BM_Former.glb']=files['glb']['SM_BM_Witness.glb']
    assembly.publish(out,files,assembly.previous(out),dict(version=1),old,surfaces)
    del files['glb']['SM_BM_Former.glb']
    assembly.publish(out,files,assembly.previous(out),dict(version=2),report,surfaces)
    assert not (out/'glb/SM_BM_Former.glb').exists()
    assert (out/'glb/SM_BM_Witness.glb').exists()


def test_interrupted_assembly_retires_only_journal_owned_member(tmp_path,assembly):
    files,surfaces,report=inputs(tmp_path,assembly);out=tmp_path/'out'
    assembly.publish(out,files,assembly.previous(out),dict(version=1),report,surfaces)
    (out/'glb/SM_BM_Interrupted.glb').write_bytes(b'known incomplete')
    atomic_json(out/assembly.JOURNAL,dict(schema=1,owner='BelmonteAtomic',files={
        key:sorted(set(files[key])|({'SM_BM_Interrupted.glb'} if key=='glb' else set())) for key in assembly.FOLDERS}))
    assembly.publish(out,files,assembly.previous(out),dict(version=2),report,surfaces)
    assert not (out/'glb/SM_BM_Interrupted.glb').exists()
