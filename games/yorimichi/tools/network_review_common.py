"""Read-only helpers for native private-network acceptance runners."""
import ipaddress
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from atelier.provenance import source_revision  # noqa: F401 - the review runners import it from here


def require_clean_source():
    from atelier import provenance
    return provenance.require_clean_source('Commit the reviewed source before recording native acceptance evidence')


def native_module_binary(ctx, name, filename, build_id, platform):
    """@cc [owner:fontanierh,label:correctness] native-module-provider-identity
    Each module MUST resolve to exactly one game or declared plugin binary.
    Plugin candidates MUST match the editor build ID and module filename;
    missing or ambiguous providers MUST refuse native acceptance.
    """
    from atelier.unreal_modules import plugins
    if Path(filename).name != filename:
        raise RuntimeError('Unexpected module path in native manifest')
    project = ctx.uproject.parent
    direct = project / 'Binaries' / platform / filename
    candidates = [direct] if direct.is_file() else []
    for descriptor, names, _ in plugins(ctx.uproject).values():
        if name not in names:
            continue
        folder = descriptor.parent / 'Binaries' / platform
        manifest = folder / 'UnrealEditor.modules'
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text())
        if data.get('BuildId') != build_id or data.get('Modules', {}).get(name) != filename:
            continue
        binary = folder / filename
        if binary.is_file():
            candidates.append(binary)
    candidates = sorted(set(path.resolve() for path in candidates))
    if len(candidates) != 1:
        raise RuntimeError('Native module has missing or ambiguous binary providers: ' + name)
    return candidates[0]


def current_native_build(ctx):
    """Tie the real loaded module files to a current successful compile recipe."""
    from atelier.build import fingerprint, load_recipe, order, outputs_present
    done = {}
    for step in order(load_recipe(ctx.game).steps(ctx), ['unreal.compile']):
        stamp = json.loads((ctx.stamps / (step.name + '.json')).read_text())
        current = fingerprint(step, done)
        if stamp.get('fingerprint') != current or not outputs_present(step):
            raise RuntimeError('Native acceptance requires a current build: ' + step.name)
        done[step.name] = current
    platform = 'Mac' if sys.platform == 'darwin' else 'Win64' if os.name == 'nt' else 'Linux'
    folder = ctx.uproject.parent / 'Binaries' / platform
    modules = json.loads((folder / 'UnrealEditor.modules').read_text())
    if 'Yorimichi' not in modules.get('Modules', {}):
        raise RuntimeError('The editor module manifest does not contain Yorimichi')

    def signature(path):
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        return dict(file=path.name, bytes=path.stat().st_size, sha256=digest)

    files = {}
    for name, filename in sorted(modules['Modules'].items()):
        files[name] = signature(native_module_binary(ctx, name, filename, modules['BuildId'], platform))
    return dict(compile_fingerprint=done['unreal.compile'], engine_build_id=modules['BuildId'],
                modules=files, executable=signature(ctx.unreal_app))


def tailnet_ipv4():
    candidates = [Path('/Applications/Tailscale.app/Contents/MacOS/Tailscale'),
                  Path('/opt/homebrew/bin/tailscale'), Path('/usr/local/bin/tailscale'),
                  Path('/usr/bin/tailscale')]
    if os.name == 'nt':
        candidates.insert(0, Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale/tailscale.exe')
    found = shutil.which('tailscale')
    if found:
        candidates.append(Path(found))
    executable = next((p for p in candidates if p.is_file()), None)
    if executable is None:
        raise RuntimeError('The private-bind proof requires the installed Tailscale CLI')
    # Fixed argv and a private child environment; never start the GUI or change the service.
    result = subprocess.run([str(executable), 'ip', '-4'], env=dict(os.environ, TAILSCALE_BE_CLI='1'),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2, check=False)
    if result.returncode != 0 or len(result.stdout) > 4096 or len(result.stderr) > 4096:
        raise RuntimeError('Tailscale did not return a usable private IPv4 address')
    try:
        address = ipaddress.IPv4Address(result.stdout.decode('ascii').strip())
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError('Tailscale returned an invalid IPv4 address') from exc
    if address not in ipaddress.IPv4Network('100.64.0.0/10'):
        raise RuntimeError('The verified address is outside the Tailscale IPv4 range')
    return str(address)
