"""Freeze original railway inputs on the host, then run its bounded Blender diagnostic."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
sys.path.insert(0, str(REPO / 'platform/studio'))
from atelier import engine
from atelier.harness.safety.guarded import run

ORIGINAL = '283329c07ea04bee34587022a3d43827468c66d7'
DONOR = '14b09c56e8b651e7ec7102f350a7cfbf05aa2fb0'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def identity(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('Source authority requires regular files')
    stat = path.stat()
    return dict(device=stat.st_dev, ctime_ns=stat.st_ctime_ns, size=stat.st_size, mtime_ns=stat.st_mtime_ns, inode=stat.st_ino,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--natural-handoff', type=Path)
    args = parser.parse_args(argv)
    donor = args.donor.resolve(); root = args.output.resolve(); root.mkdir(parents=True, exist_ok=True)
    if git(donor, 'rev-parse', 'HEAD').decode().strip() != DONOR or git(donor, 'status', '--short', '--untracked-files=no'):
        raise ValueError('Stopped railway donor source changed')
    records = {}; originals = root / 'original-source/train'; originals.mkdir(parents=True, exist_ok=True)
    def record(key, path): records[key] = dict(path=str(path), **identity(path))
    for item in ('track.py', 'track_build.py', 'station.py', 'station_site.py', 'overbridge.py', 'earthworks.py', 'route.py', 'corridor.py'):
        path = originals / item; path.write_bytes(git(REPO, 'show', ORIGINAL + ':games/yorimichi/world/train/' + item)); record('original.' + item, path)
    source = root / 'original-source/belmonte-source.py'
    source.write_bytes(git(REPO, 'show', ORIGINAL + ':games/yorimichi/world/regions/belmonte/source.py'))
    record('original.belmonte.source.py', source)
    fixture = root / 'fixture'; donor_records = {}
    inputs = {'input.route.json': 'belmonte-train/route/route.json', 'input.line.json': 'belmonte-train/route/line.json',
        **{'input.natural.' + key: 'belmonte/natural/' + key + '.glb' for key in ('SM_BM_NorthApron', 'SM_BM_NorthCountry')},
        **{'input.' + key: key for key in ('world.json', 'heightmap.npy', 'farhills.npy',
            'megapark/trail.json', 'craterpark/v2/geometry.npz')}}
    for key, relative in inputs.items():
        path = donor / 'build/yorimichi' / relative; before = identity(path)
        target = fixture / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        if identity(path) != before or identity(target)['sha256'] != before['sha256']: raise ValueError('Input changed while freezing')
        donor_records[str(path)] = before; record(key, target)
    natural_producer=None;natural_records={}
    if args.natural_handoff:
        handoff_path=args.natural_handoff.resolve();handoff_before=identity(handoff_path)
        handoff=json.loads(handoff_path.read_text());producer=Path(handoff['checkout'])
        if handoff['whole_exit']!=0 or git(producer,'rev-parse','HEAD').decode().strip()!=handoff['source_head'] or git(producer,'status','--short','--untracked-files=no'):
            raise ValueError('Normal natural-source producer is not stopped at its handoff')
        for owner in ('SM_BM_NorthApron','SM_BM_NorthCountry'):
            source=producer/'build/yorimichi/belmonte-natural-source-data'/(owner+'.surface')
            before=identity(source);expected=handoff['files'][str(source)]
            if (before['sha256']!=expected['sha256'] or before['size']!=expected['bytes'] or
                [before[key] for key in ('device','inode','size','mtime_ns','ctime_ns')]!=expected['stat']):
                raise ValueError('Normal natural-source product differs from stopped handoff')
            target=fixture/'belmonte-natural-source-data'/(owner+'.surface');target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
            if identity(source)!=before or identity(target)['sha256']!=before['sha256']: raise ValueError('Normal source changed during independent copy')
            natural_records[str(source)]=before;record('normal.natural.'+owner,target)
            task=handoff['tasks']['world.belmonte.north.natural.'+owner]
            certificate=Path(task['certificate']);certificate_before=identity(certificate)
            if certificate_before['sha256']!=task['sha256']: raise ValueError('Normal natural-source certificate changed')
            natural_records[str(certificate)]=certificate_before
        natural_records[str(handoff_path)]=handoff_before
        natural_producer=dict(head=handoff['source_head'],checkout=str(producer),handoff_sha256=handoff_before['sha256'],
            actions={owner:handoff['tasks']['world.belmonte.north.natural.'+owner]['action'] for owner in ('SM_BM_NorthApron','SM_BM_NorthCountry')})
    for path in (GAME / 'world/train').glob('*.py'): record('current.train.' + path.name, path)
    for path in (GAME / 'tools/train_track_source_control.py', GAME / 'world/region_mesh_parts.py',
                 GAME / 'world/mesh_pieces.py', GAME / 'tools/atomic_equivalence.py'):
        record('current.' + path.name, path)
    from atelier.build_inputs import local_imports
    for path in local_imports(GAME / 'tools/train_track_source_control.py',
                              (GAME / 'world', GAME / 'world/regions', REPO / 'platform/studio')):
        if path.is_file(): record('closure.' + path.relative_to(REPO).as_posix(), path)
    sys.path.insert(0, str(GAME / 'world'))
    import yori
    from craterpark.v2 import v4_config
    for path in v4_config.input_paths():
        path = Path(path)
        if path.is_file(): record('design.' + path.relative_to(REPO).as_posix(), path)
    # Every committed terrain/query input is bound independently of ignored donor outputs.
    manifest = GAME / 'assets/belmonte/source.json'; record('asset.belmonte.manifest', manifest)
    if manifest.read_bytes() != git(REPO, 'show', ORIGINAL + ':games/yorimichi/assets/belmonte/source.json'):
        raise ValueError('Original Belmonte committed source manifest changed; require an explicit source authority')
    for entry in json.loads(manifest.read_text())['meshes']:
        if entry['name'].startswith('SM_BM_BT_Terrain_'):
            record('asset.' + entry['name'], manifest.parent / entry['path'])
    line = GAME / 'assets/vehicles/belmonte-train/line.json'; record('asset.line', line)
    if line.read_bytes() != git(REPO, 'show', ORIGINAL + ':games/yorimichi/assets/vehicles/belmonte-train/line.json'):
        raise ValueError('Original committed railway line changed')
    authority = root / 'authority.json'
    authority.write_text(json.dumps(dict(schema=1, original=ORIGINAL, current_head=git(REPO, 'rev-parse', 'HEAD').decode().strip(),
        donor=DONOR, fixture=str(fixture), files=records, donor_inputs=donor_records, natural_source_producer=natural_producer), indent=2) + '\n')
    result = run([engine.blender(), '--factory-startup', '-b', '--threads', '3', '--python-exit-code', '1', '--python',
        str(GAME / 'tools/train_track_source_control.py'), '--', '--authority', str(authority), '--output', str(root / 'result.json')],
        root / 'source.guard', timeout=1200, purpose='immutable original railway selected source and actual GLB fields')
    # Git/source checks happen only after the enclosing native job has ended.
    if git(donor, 'rev-parse', 'HEAD').decode().strip() != DONOR or git(donor, 'status', '--short', '--untracked-files=no'):
        raise ValueError('Stopped donor source changed during control')
    if natural_producer and (git(Path(natural_producer['checkout']),'rev-parse','HEAD').decode().strip()!=natural_producer['head']
            or git(Path(natural_producer['checkout']),'status','--short','--untracked-files=no')):
        raise ValueError('Normal source producer changed during control')
    for path, before in {**donor_records,**natural_records}.items():
        if identity(Path(path)) != before: raise ValueError('Stopped donor input changed during control')
    for row in records.values():
        if identity(Path(row['path'])) != {key: row[key] for key in ('device', 'ctime_ns', 'size', 'mtime_ns', 'inode', 'sha256')}:
            raise ValueError('Frozen source/input identity changed during control')
    return result


if __name__ == '__main__': raise SystemExit(main())
