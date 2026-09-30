"""Install the pinned local model in a caller-selected build directory."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import urllib.request

REVISION = '5d6aabedd947297b5ba6706d8e9113e68c0c3e4f'
MODEL = 'https://huggingface.co/Linzhan/UniMate/resolve/387a344c3031299bc25fcbef35d36bd186d5afe7/unimate_uniml3d_f60_v2/'
CHECKPOINT_SHA = 'cbcfb7a057e45f967d5964fecf6b3f83358096f1306f25831e1644a18a50eb34'


def command(*args):
    subprocess.run([str(a) for a in args], check=True)


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


def install(root, atelier_source=None):
    """Return the isolated Python executable; do not export any character assets."""
    root = Path(root).resolve()
    atelier_source = Path(atelier_source or Path(__file__).resolve().parents[5])
    root.mkdir(parents=True, exist_ok=True)
    upstream = root / 'upstream'
    if not upstream.exists():
        command('git', 'clone', 'https://github.com/Friedrich-M/UniMate.git', upstream)
    command('git', '-C', upstream, 'checkout', '--detach', REVISION)
    env = root / 'venv'
    if not env.exists():
        command('uv', 'venv', env, '--python', '3.11')
    python = env / 'bin/python'
    command('uv', 'pip', 'install', '--python', python, '-r', Path(__file__).with_name('requirements.txt'))
    command('uv', 'pip', 'install', '--python', python, '--no-build-isolation',
            'Motion @ git+https://github.com/inbar-2344/Motion.git@ac236251f90e5ca37c444c53ad383fc85de6d833')
    download(MODEL + 'checkpoints/checkpoint_step_100000.pt', root / 'model/checkpoint.pt', CHECKPOINT_SHA)
    download(MODEL + 'config.json', root / 'model/config.json')
    download(MODEL + 'dataset_stats.npy', root / 'model/dataset_stats.npy')
    command('uv', 'pip', 'install', '--python', python, '--no-deps', '-e', atelier_source)
    return python


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    args = ap.parse_args()
    print(install(args.root))


if __name__ == '__main__':
    main()
