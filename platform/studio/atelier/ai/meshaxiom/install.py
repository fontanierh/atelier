"""Install pinned upstream source, isolated inference dependencies and model payload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
from . import MODEL_ID, MODEL_REVISION, SOURCE_REVISION


def command(*args):
    subprocess.run([str(x) for x in args], check=True)


CHECKPOINTS = {
    'vertex': '4d60148fdddb65df502becbf9786131836a880fdba226180ce586a8ee10620fb',
    'topology': '7fb0c7cc2035616f811326d3e64c1393de39d8f652ab7aa122ab84a987d2a19f',
    'vae': '7d6833425af71e923756d2ebdb2863e704857bffb8b365ab0c2f5ec3bfb6f4bd',
}

def verify_source(root):
    """Refuse a different revision or edits to the pinned upstream tracked source."""
    source=Path(root)/'upstream'
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
    if head!=SOURCE_REVISION or dirty:
        raise ValueError('MeshAxiom upstream source must be clean at the pinned revision')


def verify_one(root, kind):
    path = Path(root)/f'models/weights/{kind}-ema.pt'
    print(f'Verifying {kind} checkpoint identity', flush=True)
    with path.open('rb') as handle:
        actual = hashlib.file_digest(handle, 'sha256').hexdigest()
    if actual != CHECKPOINTS[kind]:
        raise ValueError(f'Checkpoint hash mismatch: {kind}')
    return dict(file=f'weights/{kind}-ema.pt', sha256=actual, size=path.stat().st_size)

def verify(root):
    """@cc [owner:fontanierh,label:correctness] meshaxiom-checkpoint-identity
    Each consumed checkpoint MUST match the pinned release SHA256 before model construction.
    Missing or changed files MUST fail rather than selecting different weights.
    """
    root = Path(root)
    records = [verify_one(root, kind) for kind in CHECKPOINTS]
    (root/'verified.json').write_text(json.dumps(records, indent=2)+'\n')


def download(root):
    from huggingface_hub import snapshot_download
    root = Path(root)
    if shutil.disk_usage(root).free < 30*2**30:
        raise RuntimeError('Download needs 30 GiB free disk for the 19.66 GiB payload plus headroom')
    stop, start = threading.Event(), time.monotonic()
    def progress():
        while not stop.wait(25):
            size = sum(p.stat().st_size for p in (root/'models').rglob('*') if p.is_file())
            print(f'Downloading checkpoints: {size/2**30:.2f} GiB, {time.monotonic()-start:.0f}s elapsed', flush=True)
    threading.Thread(target=progress, daemon=True).start()
    try:
        snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=root/'models', max_workers=1,
                          allow_patterns=['weights/*', 'external/dinov3/*', '*.json', '*.md', 'SHA256SUMS'])
    finally:
        stop.set()
    verify(root)


def install(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    upstream = root/'upstream'
    if not upstream.exists():
        command('git', 'clone', 'https://github.com/AlayaLab/MeshAxiom.git', upstream)
    command('git', '-C', upstream, 'checkout', '--detach', SOURCE_REVISION)
    if not (root/'venv').exists():
        command('uv', 'venv', root/'venv', '--python', '3.12')
    python = root/'venv/bin/python'
    command('uv', 'pip', 'install', '--python', python, '-r', Path(__file__).with_name('requirements.lock.txt'))
    source = Path(__file__).resolve().parents[5]
    command('uv', 'pip', 'install', '--python', python, '--no-deps', '-e', source, '-e', upstream)
    command(python, '-m', 'atelier.ai.meshaxiom.install', '--root', root, '--download-only')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--download-only', action='store_true')
    p.add_argument('--verify-only', action='store_true')
    args = p.parse_args()
    if args.verify_only:
        verify(args.root)
    elif args.download_only:
        download(args.root)
    else:
        install(args.root)

if __name__ == '__main__':
    main()
