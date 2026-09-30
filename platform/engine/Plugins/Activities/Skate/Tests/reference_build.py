"""Build temporary Rust probes against a Git snapshot of the frozen reference.

Only the probe and its Cargo target/dependency declarations are added. All original
Rust implementation files stay byte-identical. Call from a guarded compile job.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from session_parity import PLUGIN, REFERENCE_REVISION, digest


def build_probe(output, name, filename, target_dir, bevy=False, extra_sources=None):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=PLUGIN,text=True).strip())
    relative=(PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision=subprocess.check_output(['git','rev-parse',REFERENCE_REVISION],cwd=root,text=True).strip()
    archive=subprocess.check_output(['git','archive',f'{revision}:{relative}'],cwd=root)
    source=output/'reference-source'
    if extra_sources and source.exists():
        shutil.rmtree(source)  # Alias builds always start from a fresh generated snapshot.
    source.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source,filter='data')
    originals={p.relative_to(source).as_posix():digest(p) for p in sorted(source.rglob('*.rs'))
               if p.name!='migration_probe.rs'}
    # Add byte-identical module aliases when #[path] changes Rust's child lookup.
    # Existing original files are never replaced; original identity stays separate.
    aliases={}
    for destination,origin in (extra_sources or {}).items():
        destination_path=Path(destination);origin_path=Path(origin)
        if destination_path.is_absolute() or origin_path.is_absolute():
            raise ValueError('Probe module aliases must be relative to the staged root')
        target=(source/destination_path).resolve();original=(source/origin_path).resolve()
        if not target.is_relative_to(source.resolve()) or not original.is_relative_to(source.resolve()):
            raise ValueError('Probe module alias escapes the staged root')
        if target.exists() or target.is_symlink():
            raise ValueError('Probe module alias cannot overwrite an existing source')
        relative=original.relative_to(source.resolve()).as_posix()
        if relative not in originals or not original.is_file():
            raise ValueError('Probe module alias must copy an original implementation source')
        raw=original.read_bytes();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        if target.read_bytes()!=raw:
            raise AssertionError('Probe module alias differs from its original source')
        aliases[target.relative_to(source.resolve()).as_posix()]=dict(source=relative,sha256=digest(target))
    crate=source/'atelier-host'; cargo=crate/'Cargo.toml'
    # Reuse versions already pinned by the original worker's Cargo.lock.
    dependencies='skate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\n'
    if bevy: dependencies+='bevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n'
    cargo.write_text(cargo.read_text()+f'\n{dependencies}\n[[bin]]\nname="{name}"\npath="src/migration_probe.rs"\n')
    shutil.copyfile(filename,crate/'src/migration_probe.rs')
    subprocess.run(['cargo','+1.97.1','build','--release','--offline','--jobs','2','--manifest-path',str(cargo),
                    '--target-dir',str(target_dir.resolve()),'--bin',name],check=True)
    for relative,expected in originals.items():
        if digest(source/relative)!=expected: raise AssertionError(f'Reference implementation changed: {relative}')
    binary=target_dir.resolve()/'release'/name
    destination=output/name; shutil.copy2(binary,destination)
    report=dict(reference_revision=revision,source_archive_sha256=hashlib.sha256(archive).hexdigest(),
                original_source_sha256=originals,staged_module_aliases=aliases,probe_sha256=digest(filename),binary_sha256=digest(destination),
                cargo_lock_sha256=digest(crate/'Cargo.lock'),compiler=subprocess.check_output(['rustc','+1.97.1','-vV'],text=True).strip())
    (output/f'{name}-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return destination
