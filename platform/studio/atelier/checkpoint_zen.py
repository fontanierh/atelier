"""Export/import Zen through UE's snapshot tasks, inside the existing checkpoint guard.

Never copy Zen's live database. These tasks transfer cooked data; they do not cook or compile
the game. The default cooker can then evaluate its normal dependency records on the receiver.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

from . import build_products
from .build_cache import atomic_json
from .checkpoint_store import CheckpointError, identity, read_json

NAMESPACE = 'http://www.epicgames.com/BuildGraph'


def graph(ctx, operation, folder, descriptor):
    root = ET.Element('BuildGraph', xmlns=NAMESPACE)
    agent = ET.SubElement(root, 'Agent', Name='Checkpoint', Type='Mac')
    node = ET.SubElement(agent, 'Node', Name='Checkpoint')
    if operation == 'export':
        ET.SubElement(node, 'ZenExportSnapshot', Project=str(ctx.uproject), Platform='Mac',
                      DestinationStorageType='File', DestinationFileDir=str(folder),
                      DestinationFileName='cook', SnapshotDescriptorFile=str(descriptor))
    else:
        ET.SubElement(node, 'ZenImportSnapshot', Project=str(ctx.uproject), SnapshotDescriptorFile=str(descriptor))
    return ET.tostring(root, encoding='unicode')


def run(ctx, operation, folder, descriptor):
    """Called only by the owned checkpoint worker, under its aggregate tree guard."""
    folder.mkdir(parents=True, exist_ok=True)
    script = ctx.logs / ('checkpoint-zen-' + operation + '.xml')
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(graph(ctx, operation, folder, descriptor))
    if operation == 'import':
        # UE 5.8's ZenImportSnapshotTask concatenates unquoted engine/project paths.
        # Use its documented CLI operations with argv boundaries preserved instead.
        project = ctx.uproject.resolve()
        project_id = project.stem + '.' + hashlib.md5(str(project).encode(), usedforsecurity=False).hexdigest()[:8]
        binary = ctx.unreal_root / 'Engine/Binaries/Mac'
        host = ['--hosturl', 'localhost:8558']
        project_store = project.parent / 'Saved/Cooked/Mac/ue.projectstore'
        commands = [[str(binary / 'ZenLaunch'), str(project), '-SponsorProcessID=' + str(os.getpid())],
                    [str(binary / 'zen'), 'project-create', '--force-update', project_id,
                     str(ctx.unreal_root), str(ctx.unreal_root / 'Engine'), str(project.parent), str(project), *host],
                    [str(binary / 'zen'), 'oplog-create', '--force-update', project_id, 'Mac', *host],
                    [str(binary / 'zen'), 'oplog-import', project_id, 'Mac', str(project_store), '--clean',
                     *host, '--file', str(folder), '--name', 'cook']]
        atomic_json(project_store, dict(zenserver=dict(islocalhost=True, hostname='[::1]', hostport=8558,
                    projectid=project_id, oplogid='Mac', remotehostnames=[], operatingmode='Stream')))
    else:
        commands = [[str(ctx.unreal_root / 'Engine/Build/BatchFiles/RunUAT.sh'), 'BuildGraph',
                     '-Script=' + str(script), '-Target=Checkpoint', '-NoCompile', '-Unattended', '-utf8output']]
    for command in commands:
        run_command(ctx, operation, command)


def run_command(ctx, operation, command):
    log = ctx.logs / ('checkpoint-zen-' + operation + '.log')
    with log.open('ab') as output:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        deadline, spoken = time.monotonic() + 1800, time.monotonic()
        try:
            while child.poll() is None:
                if time.monotonic() >= deadline:
                    raise CheckpointError('Zen checkpoint transfer timed out; original cooked data retained')
                if time.monotonic() - spoken >= 25:
                    print(f'Zen checkpoint {operation}: waiting for UE snapshot task; '
                          f'{log.stat().st_size} log bytes, no game build or cook requested', flush=True)
                    spoken = time.monotonic()
                time.sleep(.25)
            if child.returncode:
                raise CheckpointError(f'Zen checkpoint {operation} failed; see {log}')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=3)


def export(ctx):
    if not getattr(ctx, 'uproject', None):
        return
    cooked = ctx.uproject.parent / 'Saved/Cooked'
    stores = list(cooked.glob('*/ue.projectstore'))
    if not stores:
        return
    if [p.parent.name for p in stores] != ['Mac']:
        raise CheckpointError('Checkpoint Zen export currently supports the Mac cook platform only')
    folder = ctx.out / '.state/checkpoint-zen'
    receipt = folder / 'export.json'
    # Capture the complete cook metadata, not the live Zen DB. Source imports without a cook
    # can keep this previous cooked baseline; the next cooker reevaluates dependencies.
    markers = [p for p in cooked.rglob('*') if p.is_file() and not p.is_symlink()]
    key = identity({str(p.relative_to(cooked)): build_products.file_digest(p) for p in sorted(markers)})
    if receipt.is_file() and read_json(receipt).get('cook_metadata') == key:
        return
    folder.mkdir(parents=True, exist_ok=True)
    descriptor = folder / 'descriptor.json'
    run(ctx, 'export', folder, descriptor)
    value = read_json(descriptor)
    snapshots = value.get('snapshots', [])
    if not snapshots or any(s.get('type') != 'file' or s.get('targetplatform') != 'Mac' for s in snapshots):
        raise CheckpointError('Zen export did not produce a complete file snapshot')
    atomic_json(receipt, dict(cook_metadata=key))
