"""Terminal guarded stdout prefix snapshots; never wait for or signal shared services."""
import hashlib
import os
from pathlib import Path
import stat

from atelier.export_manifest import real_directory
from atomic_equivalence_io import artifact,require,MAX_ARTIFACT_BYTES


def snapshot(receipt_row,whole_row,source,destination,*,expected_exit):
    """Bind an independent prefix only after exact owned-caller terminal evidence.

    Shared-service appends after cleanup MAY extend stdout. The copied prefix
    MUST remain byte-identical across two source reads and a regular-file identity
    check; truncation, replacement, prefix mutation or special files MUST refuse.
    This does not promote a failed caller or wait for an unowned shared process.
    """
    import json
    receipt=json.loads(artifact(receipt_row));whole=json.loads(artifact(whole_row));late=receipt.get('late_reporters',{})
    require(type(whole.get('exit_code'))is int and whole['exit_code']==expected_exit
        and receipt.get('state')=='child_exited' and receipt.get('cleanup_complete')is True
        and receipt.get('processes')==[] and receipt.get('footprint_bytes')==0
        and not late.get('unresolved') and not late.get('unresolved_pids') and not late.get('scan_failed'),
        'Stdout snapshot requires exact terminal/empty owned caller')
    source=Path(source).absolute();destination=Path(destination).absolute();real_directory(source.parent);real_directory(destination.parent)
    before=source.lstat();require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=MAX_ARTIFACT_BYTES,'Invalid stdout source')
    require(not os.path.lexists(destination),'Fresh stdout snapshot required')
    with source.open('rb')as stream:payload=stream.read(before.st_size)
    require(len(payload)==before.st_size,'Stdout source truncated during snapshot')
    digest=hashlib.sha256(payload).hexdigest()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb')as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o400)
    with source.open('rb')as stream:again=stream.read(before.st_size)
    after=source.lstat()
    require((before.st_dev,before.st_ino,before.st_mode)==(after.st_dev,after.st_ino,after.st_mode)
        and after.st_size>=before.st_size and hashlib.sha256(again).hexdigest()==digest,'Stdout source identity/prefix changed')
    row=dict(path=str(destination),sha256=digest);require(artifact(row)==payload,'Independent stdout snapshot differs')
    identity=lambda st:[st.st_dev,st.st_ino,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
    return row,dict(source=str(source),source_before=identity(before),source_after=identity(after),prefix_bytes=len(payload),
        prefix_sha256=digest,terminal_receipt=receipt_row,whole=whole_row,expected_exit=expected_exit,
        append_after_cleanup_allowed=True,shared_services_waited_or_signalled=False)
