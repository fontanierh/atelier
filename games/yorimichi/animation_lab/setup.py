"""Install the pinned experiment into ignored build output, then export the fox.

    uv run python games/yorimichi/animation_lab/setup.py
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
REVISION = '5d6aabedd947297b5ba6706d8e9113e68c0c3e4f'
MODEL = 'https://huggingface.co/Linzhan/UniMate/resolve/387a344c3031299bc25fcbef35d36bd186d5afe7/unimate_uniml3d_f60_v2/'
CHECKPOINT_SHA = 'cbcfb7a057e45f967d5964fecf6b3f83358096f1306f25831e1644a18a50eb34'


def command(*args):
    subprocess.run([str(a) for a in args], cwd=REPO, check=True)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=REPO / 'build/yorimichi/unimate')
    args = ap.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    upstream = root / 'upstream'
    if not upstream.exists():
        command('git', 'clone', 'https://github.com/Friedrich-M/UniMate.git', upstream)
    command('git', '-C', upstream, 'checkout', '--detach', REVISION)
    env = root / 'venv'
    if not env.exists():
        command('uv', 'venv', env, '--python', '3.11')
    python = env / 'bin/python'
    command('uv', 'pip', 'install', '--python', python, '-r', HERE / 'requirements.txt')
    command('uv', 'pip', 'install', '--python', python, '--no-build-isolation',
            'Motion @ git+https://github.com/inbar-2344/Motion.git@ac236251f90e5ca37c444c53ad383fc85de6d833')
    download(MODEL + 'checkpoints/checkpoint_step_100000.pt', root / 'model/checkpoint.pt', CHECKPOINT_SHA)
    download(MODEL + 'config.json', root / 'model/config.json')
    download(MODEL + 'dataset_stats.npy', root / 'model/dataset_stats.npy')
    # This small export only samples transforms and writes glTF, without rendering.
    from atelier.safety import guarded
    code = guarded.run([os.environ.get('BLENDER', 'blender'), '-b', '--threads', '2', '--python-exit-code', '1',
        '--python', str(HERE / 'export_rig.py'), '--', '--source',
        str(REPO / 'games/yorimichi/assets/characters/fox-hunter/FoxHunter-Anim-r05.blend'),
        '--output', str(root / 'assets')], root / 'export-health', timeout=90, lock=False,
        purpose='small glTF export without rendering')
    if code:
        raise SystemExit(code)
    command('npm', 'ci', '--prefix', HERE, '--no-audit', '--no-fund')
    command(HERE / 'node_modules/.bin/esbuild', HERE / 'app.js', '--bundle', '--format=esm',
            '--minify', f'--outfile={root / "web/app.js"}')
    print('Ready. Run the guarded server command in animation_lab/README.md.')


if __name__ == '__main__':
    main()
