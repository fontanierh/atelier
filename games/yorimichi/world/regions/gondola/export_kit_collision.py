"""Export one explicit authored Gondola collision product, without render geometry."""
import argparse
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT), str(WORLD)]
import yori  # noqa: E402,F401
from atelier import export_manifest  # noqa: E402
import params as P  # noqa: E402
import solid  # noqa: E402
import checks  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    export_manifest.real_directory(args.input.parent)
    if args.input.is_symlink() or not args.input.is_file(): raise ValueError('Invalid Gondola collision source')
    value = json.loads(args.input.read_text())
    if (args.asset not in P.asset_names() or not args.asset.endswith('_Collision')
            or value.get('schema') != 1 or value.get('asset') != args.asset or not value.get('proxies')):
        raise ValueError('Foreign or incomplete selected Gondola collision')
    failures = checks.proxy_failures(value['proxies'])
    if failures: raise ValueError('Original Gondola collision gate failed: '+repr(failures))
    output = export_manifest.real_directory(args.output,create=True)
    if any(path.name not in (args.asset+'.fbx','export.json') or path.is_symlink() or not path.is_file() for path in output.iterdir()):
        raise ValueError('Foreign Gondola collision output')
    count = solid.export_collision(value['proxies'],output / (args.asset+'.fbx'),args.asset)
    export_manifest.publish_receipt(output,key=args.asset,primary=args.asset+'.fbx',triangles=12,
        bounds=[[-.05]*3,[.05]*3],metadata=dict(collision_hulls=count,source_sha256=export_manifest.sha(args.input)))
    print('GONDOLA SELECTED COLLISION COMPLETE',args.asset,count,flush=True)


if __name__ == '__main__': main()
