"""Captured bootstrap for the existing audited Python worker, not a task scheduler.

The fixed issuer selects the single supported script and grants its original audit/input
scope. This loader supplies captured code at logical original filenames; the original
build_audit_worker still clears outputs, observes accesses and reports completion.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

# Load the existing capture implementation as pinned stdlib-only code before any
# package import. Its normal capture_controller checks the entire distribution.
BOOTSTRAP = '''import hashlib,os,sys,types
p,h,startup,spec=sys.argv[1:]
f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);raw=os.read(f,8*1024*1024+1);os.close(f)
if hashlib.sha256(raw).hexdigest()!=h: raise SystemExit('captured action bootstrap changed')
m=types.ModuleType('_atelier_pinned_controller_capture');m.__file__=p;sys.modules[m.__name__]=m
exec(compile(raw,p,'exec',dont_inherit=True),m.__dict__)
s=m._json(m._read_at(os.path.dirname(startup),os.path.basename(startup),2*1024*1024,owned=True))
if m.capture_controller(s['distribution']).digest!=s['source_digest']: raise SystemExit('captured action distribution changed')
sys.dont_write_bytecode=True
sys.path[:0]=[s['distribution']+'/platform/studio',s['distribution']+'/platform/harness']
from atelier.build_v2.legacy_action import main
main(s,spec)
'''


def worker_argv(manifest, specification, files):
    """The source-keyed actual worker flags/bootstrap; private paths are operational."""
    raw = dict(files)['platform/studio/atelier/build_v2/controller_client.py']
    client = Path(manifest['distribution']) / 'platform/studio/atelier/build_v2/controller_client.py'
    startup = Path(manifest['checkout']) / ('build/build-v2/legacy-host/' + manifest['nonce'] + '/startup.json')
    return [manifest['interpreter_role'], '-I', '-S', '-B', '-c', BOOTSTRAP,
            str(client), hashlib.sha256(raw).hexdigest(), str(startup), str(specification)]


def captured_execution_check(sources, *, checkout, platform_roots):
    """@cc [owner:fontanierh,label:correctness;safety] sticky-captured-action-origin
    Executing checkout Python modules MUST match the named captured compilation at
    their original filename before exec. A mismatch MUST remain sticky and fail the
    existing worker's final check even when the producer catches the initial refusal.
    Standard resolver-only queries and actual input/native-library IO MUST retain the
    original audit checks; installed context MUST NOT be misrepresented as captured
    project code. This hook is for the one-shot child, not general process authority.
    See test_build_v2_legacy_action.py and actual owned sticky-negative evidence.
    """
    from atelier.build_v2.legacy_qualification import _same_code, UnsupportedOrigin
    checkout = Path(checkout)
    installed = tuple(Path(root) for root in platform_roots)
    expected = {source.filename: source.compiled() for source in sources}
    def check(event, arguments):
        if event != 'exec':
            return
        code = arguments[0]
        path = Path(code.co_filename)
        if path.is_absolute() and path.is_relative_to(checkout):
            if any(path.is_relative_to(root) for root in installed):
                return  # Actual IO/native loads remain checked by the original audit.
            target = expected.get(code.co_filename)
            if target is None or not _same_code(code, target):
                check.failed = True
                raise UnsupportedOrigin('executing checkout code differs from the named capture')
    check.failed = False
    check.mark_failed = lambda: setattr(check, 'failed', True)
    def require_clean():
        if check.failed:
            raise UnsupportedOrigin('captured source-origin violation remains sticky')
    check.require_clean = require_clean
    return check


def main(manifest, specification):
    from atelier.build_v2.controller_client import _read_at, _json, _captured_source
    from atelier.build_v2.legacy_bootstrap import restore_python_context
    from atelier.build_v2.legacy_qualification import CapturedCode, captured_spec, captured_recipe_imports
    checkout = Path(manifest['checkout'])
    raw = _read_at(Path(specification).parent, Path(specification).name, 2 * 1024 * 1024, owned=True)
    spec = _json(raw)
    expected_env = spec.pop('legacy_environment')
    actual = dict(os.environ)
    if sys.platform == 'darwin':
        actual.pop('__CF_USER_TEXT_ENCODING', None)
        os.environ.pop('__CF_USER_TEXT_ENCODING', None)
    if actual.get('LC_CTYPE') in ('C.UTF-8', 'C.utf8', 'UTF-8') and 'LC_CTYPE' not in expected_env:
        actual.pop('LC_CTYPE')
    if actual != expected_env:
        raise ValueError('captured audit child environment differs from its original invocation')
    operational = manifest['operational_environment']
    original = {'PATH': operational['path']}
    original.update({name: operational[key] for key, name in (
        ('agent', 'ATELIER_AGENT'), ('cache', 'ATELIER_CACHE'), ('build_root', 'ATELIER_BUILD_ROOT'))
                     if operational[key] is not None})
    previous = dict(os.environ)
    os.environ.clear(); os.environ.update(original)
    try:
        restore_python_context(manifest)
    finally:
        os.environ.clear(); os.environ.update(previous)
    files = [(name, _read_at(manifest['issuer_root'], name, 8 * 1024 * 1024))
             for name in manifest['issuer_files']]
    if _captured_source(files).digest != manifest['issuer_digest']:
        raise ValueError('captured action issuer changed')
    nested_tool = spec.pop('legacy_nested_tool', None)
    selected = spec.pop('legacy_code_files')
    if (type(selected) is not list or not selected or len(selected) != len(set(selected))
            or not set(selected) <= dict(files).keys() or any(not name.endswith('.py') for name in selected)):
        raise ValueError('selected worker code roster is not the original finite descriptor')
    sources = [CapturedCode(str(checkout / name), data) for name, data in files if name in set(selected)]
    by_path = {source.filename: source for source in sources}
    source = by_path.get(spec['script'])
    if source is None or not Path(spec['script']).is_relative_to(checkout / 'games' / manifest['issuer_profile'].split('/')[1]):
        raise ValueError('unqualified captured Python action')
    # Keep the finite loader active before imports and throughout the observed action.
    # All code bytes are already in memory before the audit hook is installed.
    source_check = captured_execution_check(sources, checkout=checkout,
                     platform_roots=manifest['python_context']['platform_roots'])
    with captured_recipe_imports(sources, checkout=checkout,
                                 platform_roots=manifest['python_context']['platform_roots'], audited_imports=True,
                                 on_refusal=source_check.mark_failed):
        from atelier import build_audit_worker
        sys.addaudithook(source_check)
        import runpy
        original_run = runpy.run_path
        def captured_run(path, *, run_name=None):
            if path != source.filename or run_name != '__main__':
                raise ValueError('unqualified action script execution')
            module_spec = captured_spec('__main__', source)
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
            return vars(module)
        # The existing worker calls runpy exactly once. No ordinary recipe code
        # gets a live-source fallback, and the original implementation is restored.
        runpy.run_path = captured_run
        try:
            # Prepare only the owned audit scratch before the original observer
            # installs. Atomic JSON writes then remain inside that exact scope;
            # sibling temporary files never acquire product ownership.
            from atelier.atomic_files import managed_temporaries
            from contextlib import nullcontext
            def before(observer):
                if nested_tool is None:
                    return nullcontext()
                from atelier.build_v2.legacy_tool_action import node_execution
                return node_execution(nested_tool, scratch=spec['scratch'], sources=sources, observer=observer)
            with managed_temporaries(Path(spec['scratch']) / 'atomic-tmp'):
                build_audit_worker.execute(spec, after=source_check.require_clean, execution_scope=before)
        finally:
            runpy.run_path = original_run
