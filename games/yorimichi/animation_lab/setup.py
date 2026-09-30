"""Install the pinned experiment into ignored build output, then export the fox.

    uv run python games/yorimichi/animation_lab/setup.py
"""
import argparse
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def command(*args):
    subprocess.run([str(a) for a in args], cwd=REPO, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path)
    ap.add_argument('--generator', choices=['unimate', 'kimodo'], default='unimate')
    args = ap.parse_args()
    root = (args.root or REPO / "build/yorimichi" / args.generator).resolve()
    if args.generator == "kimodo":
        from atelier.ai.kimodo.install import install
    else:
        from atelier.ai.unimate.install import install
    install(root, atelier_source=REPO)
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
    if args.generator == 'unimate':
        command('node', HERE / 'export_reference.mjs', root)
    command(HERE / 'node_modules/.bin/esbuild', HERE / 'app.js', '--bundle', '--format=esm',
            '--minify', f'--outfile={root / "web/app.js"}')
    print('Ready. Run the guarded server command in animation_lab/README.md.')


if __name__ == '__main__':
    main()
