"""Read-only helpers for native private-network acceptance runners."""
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess


def source_revision():
    root = Path(__file__).resolve().parents[3]
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, timeout=5).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True, timeout=5)
    return dict(head_sha=head, dirty=bool(status.strip()))


def require_clean_source():
    revision = source_revision()
    if revision['dirty']:
        raise RuntimeError('Commit the reviewed source before recording native acceptance evidence')
    return revision


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
