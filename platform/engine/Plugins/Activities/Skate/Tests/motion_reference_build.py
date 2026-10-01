"""Build full pinned MotionHost probes in its original Rust module layout.

Only call under the parent-owned render/memory guard. Original files and staged
production module copies are verified before and after compiling the harness.
"""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from session_parity import PLUGIN, REFERENCE_REVISION, digest


def build_probes(output, target_dir, name, native_sources):
    native, cpp = PLUGIN/'Source/AtelierSkate/Private/Native', output/f'{name}-cpp'
    subprocess.run(['clang++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti',
        '-Wall', '-Wextra', '-Werror', '-I', str(native), *(str(native/f'{n}.cpp') for n in native_sources),
        str(PLUGIN/f'Tests/Native/{name}_probe.cpp'), '-o', str(cpp)], check=True)
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=PLUGIN, text=True).strip())
    relative = (PLUGIN/'ThirdParty/skate-runtime').relative_to(root).as_posix()
    revision = subprocess.check_output(['git', 'rev-parse', REFERENCE_REVISION], cwd=root, text=True).strip()
    archive = subprocess.check_output(['git', 'archive', f'{revision}:{relative}'], cwd=root)
    source = output/'reference-source'
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter='data')
    originals = {p.relative_to(source).as_posix(): digest(p) for p in sorted(source.rglob('*.rs')) if p.name != 'migration_probe.rs'}
    crate, host_source = source/'atelier-host', source/'crates/skate-host/src'
    staged = {}
    for original in sorted(host_source.rglob('*.rs')):
        relative = original.relative_to(host_source)
        if relative.as_posix() in ('lib.rs', 'main.rs'):
            continue
        destination = crate/'src'/relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
        expected = digest(original)
        assert digest(destination) == expected
        staged[relative.as_posix()] = expected
    cargo = crate/'Cargo.toml'
    cargo.write_text(cargo.read_text()+'\nskate-core={path="../crates/skate-core"}\nskate-data={path="../crates/skate-data"}\nskate-net={path="../crates/skate-net"}\nhalf="2.7.1"\nbevy={version="0.19",default-features=false,features=["std","multi_threaded","bevy_log"]}\n'
        +f'\n[[bin]]\nname="{name}-reference"\npath="src/migration_probe.rs"\n')
    probe = PLUGIN/f'Tests/Reference/{name}_probe.rs'
    shutil.copyfile(probe, crate/'src/migration_probe.rs')
    subprocess.run(['cargo', '+1.97.1', 'build', '--release', '--offline', '--jobs', '2', '--manifest-path', str(cargo), '--target-dir', str(target_dir.resolve()), '--bin', f'{name}-reference'], check=True)
    for relative, expected in originals.items():
        assert digest(source/relative) == expected
    for relative, expected in staged.items():
        assert digest(crate/'src'/relative) == expected
    rust = output/f'{name}-reference'
    shutil.copy2(target_dir.resolve()/f'release/{name}-reference', rust)
    (output/'reference-provenance.json').write_text(json.dumps(dict(reference_revision=revision, source_archive_sha256=hashlib.sha256(archive).hexdigest(),
        original_source_sha256=originals, staged_host_modules_sha256=staged, probe_sha256=digest(probe), binary_sha256=digest(rust),
        cargo_lock_sha256=digest(crate/'Cargo.lock'), compiler=subprocess.check_output(['rustc', '+1.97.1', '-vV'], text=True).strip()), indent=2)+'\n')
    return cpp, rust
