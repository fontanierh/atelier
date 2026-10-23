"""Freeze exact old source/selected constructor before a bounded processless Blender probe."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from atelier import build,paths
from atelier.atomic_files import atomic_json
from atelier.build_inputs import local_imports
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

GAME=Path(__file__).resolve().parents[2];REPO=GAME.parents[1]
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--textures',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=real_directory(args.output.absolute())
    if os.path.lexists(root):raise ValueError('Fresh SkyDome probe root required')
    def git(*args):return subprocess.check_output(['git',*args],cwd=REPO)
    if git('status','--porcelain'):raise ValueError('Freeze source before native probe')
    head=git('rev-parse','HEAD').decode().strip();root.mkdir();archive=root/'archive';archive.mkdir()
    for name in ('build_assets.py','asset_mesh.py','material_specs.py'):
        raw=git('show',BASELINE+':games/yorimichi/world/'+name)
        (archive/name).write_bytes(raw)
        if (GAME/'world'/name).read_bytes()!=raw:raise ValueError('Original primitive closure differs: '+name)
    ms=importlib.util.spec_from_file_location('host_selected_props',GAME/'world/prop_sources.py');module=importlib.util.module_from_spec(ms);ms.loader.exec_module(module)
    selected=root/'selected.json';atomic_json(selected,module.project((archive/'build_assets.py').read_text())['SkyDome'])
    fixture=Path(__file__).with_name('skydome_normal_probe.py')
    files=set(local_imports(GAME/'world/plan_world_prop.py',(GAME/'world',paths.STUDIO)))
    files.update((Path(__file__),fixture,selected,*archive.iterdir()))
    files.update(args.textures.resolve()/row['texture'] for row in module.MATERIALS.values() if row.get('texture'))
    def identities():return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
    before=identities();spec=root/'spec.json';atomic_json(spec,dict(output=str(root/'products'),textures=str(args.textures.resolve()),
        original=str(archive/'build_assets.py'),selected=str(selected),inputs=before))
    ctx=build.Context('yorimichi');command=build.Blender(fixture,('--spec',str(spec),'--sha256',hashlib.sha256(spec.read_bytes()).hexdigest()),threads=3,factory_startup=True)
    code=guarded.run(command.argv(ctx),root/'guard',timeout=180,kind='job',purpose='SkyDome original BMesh normal/cache determinism diagnosis',env=ctx.env(),progress=15.,track_tree=True)
    atomic_json(root/'whole-result.json',dict(exit_code=code,source_head=head,baseline=BASELINE))
    if code:raise SystemExit(code)
    assert identities()==before and git('rev-parse','HEAD').decode().strip()==head and not git('status','--porcelain')
    guard=json.loads((root/'guard/memory-health-tree.json').read_text())
    assert guard['state']=='child_exited' and guard['cleanup_complete'] and not guard['processes'] and not guard.get('late_reporters',{}).get('unresolved')
    assert 'SKYDOME NORMAL PROBE COMPLETE' in (root/'guard/stdout.log').read_text()
    print('GUARDED SKYDOME NORMAL PROBE PASS',flush=True)


if __name__=='__main__':main()
