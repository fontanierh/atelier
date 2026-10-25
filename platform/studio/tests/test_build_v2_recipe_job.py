"""Complete-root codec and producer-view boundary regressions."""
import io
import json
from pathlib import Path
import tarfile

import pytest

from atelier.build_v2 import recipe_job as job


def test_complete_root_roundtrip_file_directory_empty_and_absent(tmp_path):
    for kind in ('file', 'directory', 'empty', 'absent'):
        source = tmp_path / kind
        if kind == 'file':
            source.write_bytes(b'raw\0payload')
        elif kind in ('directory', 'empty'):
            source.mkdir()
            if kind == 'directory':
                (source / 'nested').mkdir()
                (source / 'nested/data').write_bytes(b'content')
                (source / 'nested/executable').write_bytes(b'executable')
                (source / 'nested/executable').chmod(0o755)
        archive = tmp_path / (kind + '.tar')
        manifest = job.pack_root(source, archive, required=kind != 'absent')
        duplicate = tmp_path / (kind + '.again.tar')
        job.pack_root(source, duplicate, required=kind != 'absent')
        assert archive.read_bytes() == duplicate.read_bytes()
        result = tmp_path / (kind + '.restored')
        assert job.unpack_root(archive, result) == manifest
        assert job.inventory(result) == job.inventory(source)


def test_missing_required_link_and_existing_destination_refuse(tmp_path):
    with pytest.raises(ValueError, match='required'):
        job.pack_root(tmp_path / 'missing', tmp_path / 'required.tar')
    target = tmp_path / 'target'
    target.write_text('data')
    alias = tmp_path / 'alias'
    alias.symlink_to(target)
    with pytest.raises(ValueError, match='link'):
        job.pack_root(alias, tmp_path / 'link.tar')
    archive = tmp_path / 'valid.tar'
    job.pack_root(target, archive)
    with pytest.raises(ValueError, match='exists'):
        job.unpack_root(archive, target)
    assert target.read_text() == 'data'


@pytest.mark.parametrize('name,kind', [('../escape', 'file'), ('root', 'symlink'), ('root', 'hardlink')])
def test_archive_unknown_paths_and_links_refuse_before_root_write(tmp_path, name, kind):
    archive = tmp_path / 'bad.tar'
    manifest = json.dumps({'version': 1, 'kind': 'file', 'entries': [['', 'file', 1, 0o644, '0' * 64]]}).encode()
    with tarfile.open(archive, 'w', format=tarfile.USTAR_FORMAT) as output:
        row = tarfile.TarInfo(job.MANIFEST)
        row.size = len(manifest)
        output.addfile(row, io.BytesIO(manifest))
        row = tarfile.TarInfo(name)
        row.size = 1
        row.mode = 0o644
        if kind != 'file':
            row.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
            row.linkname = '/outside'
        output.addfile(row, io.BytesIO(b'x') if kind == 'file' else None)
    destination = tmp_path / 'restored'
    with pytest.raises(ValueError):
        job.unpack_root(archive, destination)
    assert not destination.exists()


def test_view_uses_declared_mapping_and_refuses_output_input_overlap(tmp_path):
    (tmp_path / job.RUNTIME).mkdir(mode=0o700)
    (tmp_path / 'source.py').write_text('def run(): pass\n')
    (tmp_path / 'inputs').mkdir()
    (tmp_path / 'inputs/raw').write_text('input')
    request = {'code': ['source.py'], 'inputs': [{'path': 'inputs/raw'}],
               'params': {'recipe': {'paths': {'data/raw': 'inputs/raw'},
                                     'outputs': [{'path': 'build/result'}]}}}
    view, protected, writes = job.prepare_view(request, tmp_path)
    assert (view / 'data/raw').read_text() == 'input'
    assert str(view / 'source.py') in protected
    assert writes == [str(view / 'build/result')]
    assert (tmp_path / 'inputs/raw').read_text() == 'input'


def test_existing_parent_mkdir_is_noop_only_and_other_writes_remain_refused(tmp_path):
    from atelier.build_v2.python_job import PathGuard
    output = tmp_path / 'build' / 'product'
    output.parent.mkdir()
    guard = PathGuard(str(tmp_path), [], [], lambda report: None,
                      [str(output)], mkdir_existing=[str(output.parent)])
    calls = []
    def mkdir(path, **kwargs):
        calls.append(path)
        raise FileExistsError(path)
    wrapped = guard.wrap('mkdir', mkdir, 'write')
    with pytest.raises(FileExistsError):
        wrapped(str(output.parent))
    assert calls == [str(output.parent)]
    assert not guard.allowed('write', str(output.parent))
    assert not guard.allowed('write', str(output.parent / 'other'))
    assert guard.allowed('write', str(output))


def test_nested_callback_binds_actual_freevars_without_evaluating_artificial_defaults(tmp_path):
    source = tmp_path / 'callback.py'
    source.write_text('def factory(path):\n    def action(value=3):\n        return path.name, value\n    return action\n')
    fn = job.bind({'source': 'callback.py', 'qualname': 'factory.<locals>.action', 'line': 2,
                   'captures': [{'path': 'data/expected'}], 'defaults': [7], 'kwdefaults': {}}, tmp_path)
    assert fn() == ('expected', 7)
    with pytest.raises(ValueError, match='closure'):
        job.bind({'source': 'callback.py', 'qualname': 'factory.<locals>.action', 'line': 2,
                  'captures': [], 'defaults': [], 'kwdefaults': {}}, tmp_path)


def test_derived_roster_requires_actual_resolved_member_list(tmp_path):
    descriptor = {'derived_items': {'root': 'build/exports', 'members': [
        {'piece': 'PieceA', 'root': 'build/exports/PieceA', 'slot': 'derived_0'}]}}
    result = job._value(descriptor, tmp_path)
    assert result[0][1] == 'PieceA'
    assert result[0][0].products[0].paths == (tmp_path / 'build/exports/PieceA',)
    with pytest.raises(ValueError, match='unresolved'):
        job._value({'derived_items': {'root': 'build/exports', 'templates': []}}, tmp_path)


def test_callback_decorator_line_and_qualified_current_code_are_bound(tmp_path):
    source = tmp_path / 'decorated.py'
    source.write_text('from functools import cache\n@cache\ndef validate(value=1):\n    return value + 2\n')
    fn = job.bind({'source': 'decorated.py', 'qualname': 'validate', 'line': 2,
                   'captures': [], 'defaults': [5], 'kwdefaults': {}}, tmp_path)
    assert fn() == 7
    with pytest.raises(ValueError, match='closure'):
        job.bind({'source': 'decorated.py', 'qualname': 'foreign', 'line': 2,
                  'captures': [], 'defaults': [5], 'kwdefaults': {}}, tmp_path)


def test_encoded_geometry_plan_decodes_every_selected_member_and_refuses_tampering(tmp_path):
    import hashlib
    from atelier import encoded_glb
    from test_gltf_partition import model
    root = tmp_path / 'plan'
    root.mkdir()
    packet = encoded_glb.encode(model(), key='Part')
    identity, _ = encoded_glb.decode(packet)
    (root / 'Part.mesh').write_bytes(packet)
    value = dict(schema=1, kind='encoded_glb', complete=True, triangle_limit=32768,
                 parent='Parent', source_triangles=identity['triangles'],
                 source_render_triangles=identity['triangles'], source_collision_triangles=0,
                 pieces=[dict(name='Part', payload='Part.mesh', sha256=hashlib.sha256(packet).hexdigest(),
                              triangles=identity['triangles'], role='render', bounds=identity['bounds'])])
    (root / 'plan.json').write_text(json.dumps(value))
    limits = dict(max_pieces=10, max_manifest_bytes=1024 * 1024,
                  max_member_bytes=1024 * 1024, max_total_bytes=2 * 1024 * 1024)
    assert job.verify_encoded_plan(root, parent='Parent', limits=limits) == value
    (root / 'Part.mesh').write_bytes(packet[:-1] + bytes([packet[-1] ^ 1]))
    with pytest.raises(ValueError):
        job.verify_encoded_plan(root, parent='Parent', limits=limits)


def test_complete_root_rejects_physical_hardlinks(tmp_path):
    import os
    source = tmp_path / 'source'
    source.write_text('data')
    os.link(source, tmp_path / 'alias')
    with pytest.raises(ValueError, match='hard link'):
        job.pack_root(source, tmp_path / 'out.tar')


def test_recipe_worker_announces_the_selected_runtime_before_initializing_protocol_identity():
    from atelier.build_v2.recipe_worker import RecipeWorker, BLENDER_VERSION, PYTHON_VERSION
    blender = RecipeWorker(io.BytesIO(), io.BytesIO(), True, blender='/installed/Blender')
    assert blender.version == BLENDER_VERSION
    python = RecipeWorker(io.BytesIO(), io.BytesIO(), True)
    assert python.version == PYTHON_VERSION
    fixture = RecipeWorker(io.BytesIO(), io.BytesIO(), False, blender='/installed/Blender')
    assert fixture.version == BLENDER_VERSION + '+unsandboxed-test'


def test_original_blender_argument_separator_is_preserved_by_generic_command_composition(tmp_path, monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    view = tmp_path / job.RUNTIME / 'view'
    view.mkdir(parents=True)
    script = view / 'original.py'
    script.write_text("import json, sys\nfrom pathlib import Path\nPath(__file__).with_name('argv.json').write_text(json.dumps(sys.argv[sys.argv.index('--')+1:]))\n")
    monkeypatch.setitem(sys.modules, 'bpy', ModuleType('bpy'))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.chdir(view)
    context = SimpleNamespace(output_dir=tmp_path / 'output', params={'recipe': {
        'commands': [{'kind': 'blender', 'script': 'original.py', 'args': ['actual-role'], 'env': [], 'threads': 3}],
        'paths': {}, 'outputs': [], 'verify': None}})
    job.run(context)
    assert json.loads((view / 'argv.json').read_text()) == ['actual-role']


@pytest.mark.parametrize('raised', [False, True])
def test_recipe_atomic_scope_reuses_bootstrap_held_scratch_and_resets_on_every_exit(tmp_path, monkeypatch, raised):
    import os
    from types import SimpleNamespace
    from atelier import atomic_files
    view = tmp_path / job.RUNTIME / 'view'
    helper = view / 'platform/studio/atelier/atomic_files.py'
    helper.parent.mkdir(parents=True)
    helper.write_bytes(Path(atomic_files.__file__).read_bytes())
    scratch = tmp_path / job.RUNTIME / 'tmp'
    scratch.mkdir()
    descriptor = os.open(scratch, os.O_RDONLY | os.O_DIRECTORY)
    info = os.fstat(descriptor)
    script = view / 'body.py'
    script.write_text("from pathlib import Path\nfrom atelier.atomic_files import atomic_json\natomic_json(Path(__file__).with_name('result.json'), {'value': 1})\n" + ("raise RuntimeError('original error')\n" if raised else ''))
    monkeypatch.chdir(view)
    real_open = os.open
    def without_root_anchor(path, flags, *args, **kwargs):
        assert os.fspath(path) != '/', 'scope must not reopen the filesystem root under PathGuard'
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', without_root_anchor)
    from atelier.build_v2.python_job import JobContext
    context = JobContext({}, [], {'recipe': {'paths': {}, 'commands': [{'kind':'python','script':'body.py','args':[],'env':[],'threads':3}],
                           'outputs':[], 'verify':None}}, 0)
    assert context._atomic_temporary is None
    context.output_dir = tmp_path / 'output'
    context._atomic_temporary = (scratch, descriptor, info.st_dev, info.st_ino)
    try:
        if raised:
            with pytest.raises(RuntimeError, match='original error'):
                job.run(context)
        else:
            job.run(context)
        assert atomic_files._MANAGED_TEMPORARY.get() is None
        assert json.loads((view / 'result.json').read_text()) == {'value': 1}
        assert list(scratch.iterdir()) == []
    finally:
        os.close(descriptor)


def test_real_recipe_configuration_allows_only_existing_output_parent_mkdir(tmp_path):
    import subprocess
    import sys
    from atelier.build_v2.recipe_worker import RecipeWorker
    root=tmp_path.resolve()
    (root/job.RUNTIME).mkdir()
    (root/'source.py').write_text('def run(context): pass\n')
    (root/'output').mkdir()
    request={'script':'source.py','code':['source.py'],'inputs':[],
             'outputs':[{'path':'products/one.tree.tar'}],
             'params':{'recipe':{'paths':{},'outputs':[{'path':'build/data/queries/one.json'}]}}}
    worker=RecipeWorker(io.BytesIO(),io.BytesIO(),True)
    worker.prepare_job(request,str(root))
    config=worker.configuration(request,str(root),99)
    parent=root/job.RUNTIME/'view/build/data/queries'
    assert str(parent)in config['mkdir_existing']
    program='''
import json,sys
from pathlib import Path
from atelier.build_v2.python_job import PathGuard
from atelier.export_manifest import real_directory
config=json.load(sys.stdin)
parent=Path(config['working_directory'])/'build/data/queries'
guard=PathGuard(str(parent.parents[5]),config['read_subpaths'],config['read_literals'],lambda _:None,
                config['write_subpaths'],config['working_directory'],config['mkdir_existing'])
guard.install()
real_directory(parent,create=True)
parent.mkdir(parents=True,exist_ok=True)
(parent/'one.json').write_text('declared')
assert not guard.allowed('write',str(parent))
assert not guard.allowed('write',str(parent/'unrelated'))
'''
    # The guard's job root is explicit; no guessed parent depth belongs in the fixture.
    program=program.replace("str(parent.parents[5])",repr(str(root)))
    result=subprocess.run([sys.executable,'-c',program],input=json.dumps(config),text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    assert (parent/'one.json').read_text()=='declared'
