"""Cleanup only the frozen failed native-06 Track namespace; never certify its outputs.

Admitted host preparation archives exact payloads before native admission. Native work is invoked only
by the parent's existing guarded UnrealScript flow, at a fully stopped receiver boundary.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

GAME=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(GAME/'world'),str(GAME/'tools'),str(Path(__file__).parent)]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atomic_equivalence_io import artifact,require  # noqa: E402
from track_native_equivalence import bound_inputs,receiving_startup,retire_owned,sha,startup_ddc  # noqa: E402

FAILED_SOURCE='f55b1847d385b3a07c3ea5f3a675dc218b78ce4a'
FAILED_SPEC='036507844a62136bc0cddfb7d27874947b3c540422546b8896b934b222775c03'
FAILED_MANIFEST='81740b8f83b8ddc100a967ad86f9bd7d3f064c9613a28ba3b07263bec3c16d20'
FAILED_PACKAGE='/Game/AtelierValidation/Track_ccaf965a2655'


def terminal_empty(value):
    late=value.get('late_reporters',{})
    require(value.get('state')=='child_exited' and value.get('cleanup_complete')is True
        and value.get('processes')==[] and value.get('footprint_bytes')==0
        and not late.get('unresolved')and not late.get('unresolved_pids')and not late.get('scan_failed'),
        'Failed caller is not positively terminal/empty')


def member(relative):
    path=Path(relative)
    require(isinstance(relative,str)and relative and not path.is_absolute()and path.as_posix()==relative
        and path.parts and '\\'not in relative and not any(p in('.','..','')for p in path.parts),'Unsafe frozen member')
    return path


def packages(manifest):
    result=set()
    for relative,row in manifest['files'].items():
        path=member(relative);require(path.suffix=='.uasset','Unexpected non-primary frozen payload')
        require(set(row)=={'identity','sha256'} and re.fullmatch('[0-9a-f]{64}',row['sha256'])
            and isinstance(row['identity'],list)and len(row['identity'])==5
            and all(type(v)is int and v>=0 for v in row['identity'])and row['identity'][2]>0,'Invalid frozen identity')
        result.add(manifest['package']+'/'+path.with_suffix('').as_posix())
    require(len(result)==len(manifest['files']),'Aliased frozen package names')
    for directory in manifest['directories']:member(directory)
    require(len(set(manifest['directories']))==len(manifest['directories']),'Aliased frozen directories')
    return result


def validate_custody(spec,manifest,terminal,startup,engine_log):
    require(spec['source_head']==manifest['source_head']==FAILED_SOURCE and manifest['spec_sha256']==FAILED_SPEC
        and spec['package']==manifest['package']==FAILED_PACKAGE and spec['phase']=='original'
        and manifest['whole_exit']==143 and manifest['output_certified']is False,'Wrong failed fixture authority')
    root=Path(spec['content'])/spec['package'].removeprefix('/Game/')
    require(root==Path(manifest['root']) and spec['receiving_head']==manifest['receiving_head'],
        'Failed namespace/receiver escaped original bound scope')
    require(len(packages(manifest))==317 and len(manifest['directories'])==105
        and sum(row['identity'][2]for row in manifest['files'].values())==49362728,'Incomplete frozen317 payload census')
    parents=set()
    for relative in manifest['files']:
        parent=Path(relative).parent
        while parent!=Path('.'):
            parents.add(parent.as_posix());parent=parent.parent
    require(set(manifest['directories'])==parents,'Frozen directories exceed exact known package parent chains')
    terminal_empty(terminal);require(terminal==manifest['terminal'],'Original guard differs from frozen terminal')
    observed=startup_ddc(spec['launch'],engine_log)
    require(startup['launch']==spec['launch']and all(startup[key]==value for key,value in observed.items()),
        'Original startup envelope/source custody differs')
    return root


def pin(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def read_file(path,expected):
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode)and before.st_nlink==1 and before.st_uid==os.getuid()
        and pin(before)==expected['identity'],'Frozen file changed/link/special/foreign identity')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb')as stream:
        require(pin(os.fstat(stream.fileno()))==expected['identity'],'File changed while opening')
        data=stream.read()
        require(pin(os.fstat(stream.fileno()))==expected['identity'],'File changed while reading')
    require(pin(path.lstat())==expected['identity'] and hashlib.sha256(data).hexdigest()==expected['sha256'],
        'Frozen package bytes/identity differ')
    return data


def scan(folder,manifest,*,remaining=False):
    """@cc [owner:fontanierh,label:safety] frozen-failed-fixture-membership
    Destructive cleanup MUST use only the frozen failed namespace/member identities.
    New, changed, missing-before-retirement, linked or special entries MUST refuse.
    Remaining files after supported native deletion MUST still match original bytes.
    """
    root=real_directory(folder);found={};directories=[]
    if not root.exists():
        require(remaining,'Frozen namespace disappeared before archive/retirement');return found
    def walk(path):
        for entry in sorted(os.scandir(path),key=lambda row:row.name):
            item=Path(entry.path);relative=item.relative_to(root).as_posix();info=entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                require(relative in manifest['directories'],'New directory in frozen namespace')
                directories.append(relative);walk(item)
            else:
                require(relative in manifest['files'],'New file/link/special entry in frozen namespace')
                read_file(item,manifest['files'][relative]);found[relative]=manifest['files'][relative]['sha256']
    walk(root)
    if not remaining:
        require(set(found)==set(manifest['files'])and set(directories)==set(manifest['directories']),
            'Incomplete frozen file/directory census')
    return found


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def archive_payloads(folder,manifest,destination):
    scan(folder,manifest)  # Complete preflight before first independent archive write.
    destination=real_directory(destination);require(not os.path.lexists(destination),'Fresh independent archive required')
    destination.mkdir()
    for relative in sorted(manifest['directories'],key=lambda p:len(Path(p).parts)):(destination/relative).mkdir()
    rows={}
    for relative,expected in sorted(manifest['files'].items()):
        data=read_file(Path(folder)/relative,expected);target=destination/relative
        with target.open('xb')as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        rows[relative]=dict(identity=pin(target.lstat()),sha256=expected['sha256'])
    archive=dict(package=manifest['package'],files=rows,directories=manifest['directories'])
    scan(destination,archive);scan(folder,manifest)
    for path in sorted([destination,*(destination/p for p in manifest['directories'])],key=lambda p:len(p.parts),reverse=True):
        sync_directory(path)
    sync_directory(destination.parent)
    return archive


def registry_census(U,manifest):
    registry=U.AssetRegistryHelpers.get_asset_registry();registry.wait_for_completion()
    require(not registry.is_loading_assets(),'Asset registry initial scan incomplete')
    expected=packages(manifest);wanted={p+'.'+p.rsplit('/',1)[-1]for p in expected}
    actual=[str(value)for value in U.EditorAssetLibrary.list_assets(manifest['package'],recursive=True,include_folder=False)]
    require(len(actual)==len(wanted)and set(actual)==wanted,'Registry packages differ from frozen primary census')
    return expected


def preflight_refs(U,allowed):
    for path in sorted(allowed):
        refs=U.EditorAssetLibrary.find_package_referencers_for_asset(path,load_assets_to_confirm=True)
        require(refs is not None and set(refs)<=allowed,'External/unknown referencer blocks failed fixture cleanup')


def retire_checked(U,manifest,archive,archive_root):
    folder=Path(manifest['root']);scan(folder,manifest);scan(archive_root,archive)
    allowed=registry_census(U,manifest);preflight_refs(U,allowed)
    real=U.get_editor_subsystem(U.EditorAssetSubsystem)
    require(real is not None,'Supported editor asset subsystem missing')
    def delete(objects):
        # Loading cannot broaden authority or silently change the retained bytes.
        require({obj.get_path_name()for obj in objects}=={p+'.'+p.rsplit('/',1)[-1]for p in allowed},
            'Loaded object identity escaped frozen packages')
        scan(folder,manifest);scan(archive_root,archive)
        require(registry_census(U,manifest)==allowed,'Registry changed during loaded preflight')
        preflight_refs(U,allowed)
        return real.delete_loaded_assets(objects)
    class Editor:
        def __getattr__(self,name):return getattr(U.EditorAssetLibrary,name)
        def load_asset(self,path):
            obj=U.EditorAssetLibrary.load_asset(path)
            require(obj is not None and obj.get_path_name()==path+'.'+path.rsplit('/',1)[-1],
                'Missing/redirected recorded asset refuses before deletion')
            return obj
    proxy=types.SimpleNamespace(EditorAssetLibrary=Editor(),EditorAssetSubsystem=U.EditorAssetSubsystem,SystemLibrary=U.SystemLibrary,
        get_editor_subsystem=lambda cls:types.SimpleNamespace(delete_loaded_assets=delete)if cls is U.EditorAssetSubsystem else U.get_editor_subsystem(cls))
    retire_owned(proxy,allowed,allowed)
    require(not U.EditorAssetLibrary.list_assets(manifest['package'],recursive=True,include_folder=False),
        'Registry asset remained after supported batch retirement')
    scan(archive_root,archive)
    return dict(root=str(folder),allowed_packages=sorted(allowed),remaining=scan(folder,manifest,remaining=True))


def native(spec_path,digest):
    import unreal as U
    spec=json.loads(artifact(dict(path=str(spec_path),sha256=digest)));bound_inputs(spec)
    startup=receiving_startup(spec,U);output=Path(spec['output']);atomic_json(output/'startup-ddc.json',startup)
    require(spec['manifest']['sha256']==FAILED_MANIFEST and spec['failed_spec']['sha256']==FAILED_SPEC,
        'Wrong immutable failed-spec/ownership bindings')
    manifest=json.loads(artifact(spec['manifest']));archive=json.loads(artifact(spec['archive_manifest']))
    old=json.loads(artifact(spec['failed_spec']))
    validate_custody(old,manifest,json.loads(artifact(spec['old_guard'])),json.loads(artifact(spec['old_startup'])),
        artifact(spec['old_engine_log']).decode(errors='replace'))
    require(spec['old_driver']['sha256']=='c4c6ff04b656bc2bdd41699cb288415ab5cacddcabd77cc0088a31ba574e22b4',
        'Wrong archived immutable namespace-producing driver')
    artifact(spec['old_driver'])
    require(spec['content']==old['content'],'Cleanup Content escaped original source scope')
    require(Path(U.Paths.project_content_dir()).resolve()==Path(spec['content']).resolve(),'Wrong receiving Content')
    require(manifest['package']==spec['package']==FAILED_PACKAGE,'Wrong cleanup namespace')
    result=retire_checked(U,manifest,archive,Path(spec['archive_root']))
    bound_inputs(spec);atomic_json(output/'cleanup.json',result)
    atomic_json(output/'result.json',dict(cleanup_only=True,output_certified=False,archive_preserved=True,
        failed_spec_sha256=FAILED_SPEC,frozen_manifest_sha256=FAILED_MANIFEST,retired_packages=len(result['allowed_packages'])))
    print('TRACK FAILED317 FIXTURE CLEANUP COMPLETE '+digest,flush=True)


if __name__=='__main__':
    native(Path(os.environ['ATELIER_TRACK_CLEANUP_SPEC']),os.environ['ATELIER_TRACK_CLEANUP_SHA256'])
