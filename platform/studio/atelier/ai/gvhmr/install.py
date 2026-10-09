"""Install GVHMR for macOS inference in a caller-selected build directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

REVISION = 'ee960bb6e2ea2d381aa97f08e9b71ef320b624b1'
# pytorch3d has no macOS wheel. GVHMR only needs its pure-Python rotation transforms, which are put on the
# path from a pinned source checkout; its compiled operators are never built.
PYTORCH3D_REVISION = '75ebeeaea0908c5527e7b1e305fbc7681382db47'  # v0.7.8
# Upstream publishes these on Google Drive, which cannot be fetched unattended. This revision-pinned mirror is
# verified against the checksums below.
MIRROR = 'https://huggingface.co/camenduru/GVHMR/resolve/21b32d5389e2e59c0737d4c4095bbc0b8c23f66b/'
CHECKPOINTS = {
    'gvhmr/gvhmr_siga24_release.ckpt': '4fae7da2de388d5da3514cb27a2d003f364dacb280e9cf88972b710e589c6b91',
    'hmr2/epoch=10-step=25000.ckpt': '2dcf79638109781d1ae5f5c44fee5f55bc83291c210653feead9b7f04fa6f20e',
    'vitpose/vitpose-h-multi-coco.pth': '50e33f4077ef2a6bcfd7110c58742b24c5859b7798fb0eedd6d2215e0a8980bc',
    'yolo/yolov8x.pt': 'c4d5a3f000d771762f03fc8b57ebd0aae324aeaefdd6e68492a9c4470f2d1e8b',
}
# The SMPL-X body model needs a licence registration at https://smpl-x.is.tue.mpg.de, so it is never downloaded.
BODY_MODEL = 'body_models/smplx/SMPLX_NEUTRAL.npz'


def command(*args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def download(url, target, sha=None):
    if target.exists() and (sha is None or digest(target) == sha):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + '.part')
    print(f'Downloading {target.name}', flush=True)
    with urllib.request.urlopen(url, timeout=60) as source, part.open('wb') as dest:
        while block := source.read(1024 * 1024):
            dest.write(block)
    if sha and digest(part) != sha:
        raise RuntimeError(f'Checksum mismatch for {target.name}; file not installed')
    part.replace(target)


def download_checkpoints(root):
    checkpoints = Path(root).resolve() / 'checkpoints'
    for name, sha in CHECKPOINTS.items():
        download(MIRROR + name, checkpoints / name, sha)
    (checkpoints / 'downloads.json').write_text(json.dumps({'mirror': MIRROR, 'sha256': CHECKPOINTS}, indent=2) + '\n')


def install_body_model(root, smplx):
    """Copy a registered SMPLX_NEUTRAL.npz into the build root and return its digest."""
    smplx = Path(smplx)
    if smplx.is_dir():
        smplx = next((p for p in (smplx / 'SMPLX_NEUTRAL.npz', smplx / 'smplx/SMPLX_NEUTRAL.npz') if p.exists()),
                     smplx / 'SMPLX_NEUTRAL.npz')
    if not smplx.is_file():
        raise FileNotFoundError(f'{smplx} not found; download SMPL-X from https://smpl-x.is.tue.mpg.de')
    target = Path(root).resolve() / 'checkpoints' / BODY_MODEL
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(smplx, target)
    return digest(target)


def checkout(url, path, revision):
    if not path.exists():
        command('git', 'clone', '--quiet', url, path)
    command('git', '-C', path, 'checkout', '--quiet', '--detach', revision)


def install(root, smplx=None, atelier_source=None):
    """Return the isolated Python executable."""
    root = Path(root).resolve()
    atelier_source = Path(atelier_source or Path(__file__).resolve().parents[5])
    root.mkdir(parents=True, exist_ok=True)
    upstream = root / 'upstream'
    checkout('https://github.com/zju3dv/GVHMR.git', upstream, REVISION)
    # The macOS patch replaces fixed CUDA placement with a selectable device. Reapply it on a clean tree so a
    # rerun after an upstream revision change is never applied twice.
    command('git', '-C', upstream, 'reset', '--quiet', '--hard', REVISION)
    command('git', '-C', upstream, 'apply', Path(__file__).with_name('macos.patch'))
    checkout('https://github.com/facebookresearch/pytorch3d.git', root / 'pytorch3d', PYTORCH3D_REVISION)
    env = root / 'venv'
    if not env.exists():
        command('uv', 'venv', env, '--python', '3.11')
    python = env / 'bin/python'
    command('uv', 'pip', 'install', '--python', python, '-r', Path(__file__).with_name('requirements.txt'))
    site = subprocess.run([python, '-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])'],
                          check=True, capture_output=True, text=True).stdout.strip()
    Path(site, 'pytorch3d_transforms.pth').write_text(f'{root / "pytorch3d"}\n')
    command('uv', 'pip', 'install', '--python', python, '--no-deps', '-e', upstream)
    command('uv', 'pip', 'install', '--python', python, '--no-deps', '-e', atelier_source)
    download_checkpoints(root)
    # Upstream resolves weights relative to its own tree.
    inputs = upstream / 'inputs'
    inputs.mkdir(exist_ok=True)
    link = inputs / 'checkpoints'
    if not link.is_symlink():
        link.symlink_to(root / 'checkpoints', target_is_directory=True)
    if smplx:
        install_body_model(root, smplx)
    if not (root / 'checkpoints' / BODY_MODEL).exists():
        print(f'Body model missing: rerun with --smplx <path to SMPLX_NEUTRAL.npz> '
              '(registration at https://smpl-x.is.tue.mpg.de)', flush=True)
    return python


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--smplx', type=Path, help='SMPLX_NEUTRAL.npz from a registered SMPL-X download')
    ap.add_argument('--weights-only', action='store_true')
    args = ap.parse_args()
    if args.weights_only:
        download_checkpoints(args.root)
    else:
        print(install(args.root, args.smplx))


if __name__ == '__main__':
    main()
