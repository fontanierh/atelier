"""One-shot Blender/editor Python bootstrap. Standard library only; never launches a host.

The parent supplies a private inherited report pipe and approved, hashed installation roots.
An audit covers Python-level action work, not the host's native I/O or native callbacks.
"""
import json
import os
from pathlib import Path
import sys
import sysconfig
from types import ModuleType


def load(name, path):
    # Embedded hosts may ignore PYTHONPYCACHEPREFIX at startup. Never execute ambient support
    # bytecode before execute() has configured the observer's private bytecode location.
    path = Path(path)
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def runtime_roots(approved):
    """Only recognized Python library directories inside the hashed host installation."""
    approved = [Path(p).resolve() for p in approved]
    roots = {Path(sysconfig.get_path(name)).resolve()
             for name in ('stdlib', 'platstdlib', 'purelib', 'platlib')}
    if not roots or any(not any(p.is_relative_to(base) for base in approved) for p in roots):
        raise RuntimeError('Native Python runtime is outside its fingerprinted installation')
    return sorted(map(str, roots))


def main():
    """@cc [owner:fontanierh,label:correctness] fresh-native-audit-process
    A native host MUST observe at most one audited action. Its irreversible hook MUST remain armed
    after completion, and the parent MUST reject trailing records before certifying the action.
    Arbitrary sys.path entries MUST NOT receive a tool-runtime exemption.
    """
    previous = getattr(sys, '_atelier_native_audit_started', False)
    if previous:
        if hasattr(previous, 'record'):
            previous.record('native lifecycle', reason='native host attempted a second audited action')
        raise RuntimeError('Native input audits require a fresh process for every action')
    sys._atelier_native_audit_started = True
    spec = json.loads(Path(os.environ['ATELIER_AUDIT_SPEC']).read_text())
    if spec['host'] not in ('Blender', 'UnrealScript'):
        raise ValueError('Unsupported native audit host')
    spec['runtime'] = runtime_roots(spec['installation'])
    spec['labels'].extend((p, 'runtime') for p in spec['runtime'])
    worker = load('atelier_native_audit_worker', Path(__file__).with_name('build_audit_worker.py'))
    after = None
    if spec['host'] == 'UnrealScript' and spec['module_guard']:
        guard = load('atelier_native_module_guard', Path(__file__).with_name('unreal_script_guard.py'))
        left_out = json.loads(os.environ['ATELIER_LEFT_OUT'])
        # Preserve descriptor isolation and the existing before/after native library checks.
        after = lambda: guard.check(spec['script'], left_out, guard.stop)
        after()
    worker.execute(spec, blender=spec['host'] == 'Blender', after=after)


if __name__ == '__main__':
    main()
