"""Exact source-registry cutoff callback observations, without invoking it."""
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import types
from atelier.build_v2.legacy_qualification import CallableObservation

SOURCE_AST = '8e0a464b917fc48cf12b1093a0e63913f1f2522328caa39c59c2c5a3df36c0df'
CONSTRUCTOR_AST = '92c87069485fc1e2c433dce939258521f2437827c9864c7950aefa848b9ad5f3'
ATOMIC_AST = '33c1d609f4391d80c3d267ed0b61a19304f58d51232f8cec8b7b43d69c4f3b78'


class UnsupportedBrinecoveSources(ValueError):
    """The callback or original closed source-registry role differs."""


@dataclass(frozen=True)
class BrinecoveSources:
    step: str
    raw_inputs: tuple[Path, ...]
    code_inputs: tuple[Path, ...]
    output_paths: tuple[Path, ...]
    produced_inputs: tuple[Path, ...]
    callback: CallableObservation
    publisher: CallableObservation
    models: CallableObservation


def _read(checkout,path):
    from atelier.build_v2.controller_client import _read_at, MAX_SOURCE_FILE_BYTES
    try:return _read_at(checkout,path.relative_to(checkout).as_posix(),MAX_SOURCE_FILE_BYTES)
    except (OSError,ValueError) as error:raise UnsupportedBrinecoveSources('source is linked, missing or outside checkout') from error


def _hash(node):
    return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()


def _output(path):
    from atelier.build_v2.controller_client import _open_root
    current=path
    while True:
        try:info=current.lstat()
        except FileNotFoundError:current=current.parent;continue
        except OSError as error:raise UnsupportedBrinecoveSources('output ancestry cannot be inspected') from error
        if not (stat.S_ISREG(info.st_mode) if current==path else stat.S_ISDIR(info.st_mode)):
            raise UnsupportedBrinecoveSources('output has linked or foreign ancestry')
        try:
            fd=_open_root(current if stat.S_ISDIR(info.st_mode) else current.parent);os.close(fd)
        except OSError as error:raise UnsupportedBrinecoveSources('output ancestry is not anchored') from error
        return


def qualify_brinecove_sources(step,*,checkout:Path,output_root:Path)->BrinecoveSources:
    """@cc [owner:fontanierh,label:correctness;safety] source-registry-callback-observation
    Only the original Brinecove source-registry cutoff MAY qualify. Exact Step/Call
    controls, callback closure/globals and independently compiled publisher/models/
    managed-temp helper MUST agree with the fixed reviewed AST and source bindings.
    Qualification MUST NOT invoke callbacks/helpers, read generated outputs, create
    cold paths, claim source models or grant execution, repair or settlement.
    """
    from atelier import build,atomic_files
    from atelier.build_v2.controller_client import _open_root
    from atelier.build_v2.legacy_qualification import CapturedCode,IdentityBinding,UnsupportedOrigin,verify_callable
    checkout,output_root=Path(checkout),Path(output_root)
    if (type(step) is not build.Step or step.name!='world.brinecove.sources'
            or not checkout.is_absolute() or not output_root.is_absolute()
            or '..' in checkout.parts or '..' in output_root.parts
            or checkout==Path(checkout.anchor) or output_root==Path(output_root.anchor)):
        raise UnsupportedBrinecoveSources('foreign Step/anchors')
    try:fd=_open_root(checkout);os.close(fd)
    except OSError as error:raise UnsupportedBrinecoveSources('checkout is not anchored') from error
    game=checkout/'games/yorimichi';owner=game/'build.py';helper=game/'world/source_registry.py'
    library=game/'assets/source-library.json';atomic=checkout/'platform/studio/atelier/atomic_files.py'
    output=output_root/'digests/brinecove-source-library.json';_output(output)
    defaults={'deferred_inputs':[],'needs':[],'after':[],'heavy':False,'pool_roots':[],
        'explicit':False,'verify':None,'cutoff':True,'references':[],'cache':False,'audit':False,
        'optional_inputs':[],'queries':[],'toolchain':False,'batch':None,'cook_recovery':None,
        'checkpoint_previous_needs':None,'checkpoint_restore':None,'checkpoint_outputs':(),
        'candidate_scope':None,'replan':False,'controller':None,'products':[],'reads':[]}
    dynamic={'name','commands','inputs','outputs','about'}
    if (set(vars(step))-dynamic!=set(defaults)
            or any(type(vars(step)[n]) is not type(v) or vars(step)[n]!=v for n,v in defaults.items())
            or type(step.inputs) is not list or step.inputs!=[helper,library]
            or any(type(p) is not type(helper) for p in step.inputs)
            or type(step.outputs) is not list or step.outputs!=[output]
            or any(type(p) is not type(output) for p in step.outputs)
            or type(step.commands) is not list or len(step.commands)!=1):
        raise UnsupportedBrinecoveSources('original cutoff controls/input/output roles differ')
    call=step.commands[0]
    if (type(call) is not build.Call or set(vars(call))!={'name','fn'}
            or type(call.name) is not str or call.name!='Brinecove source-library selection'
            or type(call.fn) is not types.FunctionType):
        raise UnsupportedBrinecoveSources('original callback differs')
    # Anchor the raw manifest role without reading model/checksum data during qualification.
    try:
        fd=_open_root(library.parent)
        try:info=os.stat(library.name,dir_fd=fd,follow_symlinks=False)
        finally:os.close(fd)
        if not stat.S_ISREG(info.st_mode):raise ValueError('not a regular raw manifest')
    except (OSError,ValueError) as error:raise UnsupportedBrinecoveSources('raw manifest is not anchored') from error
    owner_code=CapturedCode(str(owner),_read(checkout,owner));source_code=CapturedCode(str(helper),_read(checkout,helper))
    atomic_code=CapturedCode(str(atomic),_read(checkout,atomic))
    try:
        constructors=[n for n in ast.parse(owner_code.content).body if isinstance(n,ast.FunctionDef) and n.name=='brinecove_source_step']
        if (len(constructors)!=1 or _hash(constructors[0])!=CONSTRUCTOR_AST
                or _hash(ast.parse(source_code.content))!=SOURCE_AST or _hash(ast.parse(atomic_code.content))!=ATOMIC_AST):
            raise UnsupportedBrinecoveSources('original source structure differs')
    except SyntaxError as error:raise UnsupportedBrinecoveSources('invalid original source syntax') from error
    module=call.fn.__globals__.get('source_registry')
    if type(module) is not types.ModuleType or vars(module).get('__file__')!=str(helper):
        raise UnsupportedBrinecoveSources('original source-registry provider differs')
    publisher,models=getattr(module,'publish',None),getattr(module,'models',None)
    if (type(publisher) is not types.FunctionType or type(models) is not types.FunctionType
            or publisher.__globals__ is not vars(module) or models.__globals__ is not vars(module)):
        raise UnsupportedBrinecoveSources('original source-registry helpers differ')
    def verify(fn,captured,**kw):
        if type(fn) is not types.FunctionType:raise UnsupportedBrinecoveSources('nonfunction helper')
        try:return verify_callable(fn,captured,namespace=fn.__globals__,**kw)
        except UnsupportedOrigin as error:raise UnsupportedBrinecoveSources('callable code/default/global bindings differ') from error
    verify(atomic_files.managed_temporary_parent,atomic_code,qualname='managed_temporary_parent',
        globals_={'_MANAGED_TEMPORARY':IdentityBinding(atomic_files._MANAGED_TEMPORARY),
                  'os':IdentityBinding(os),'stat':IdentityBinding(stat)},
        builtins_={'ValueError':IdentityBinding(ValueError)})
    observed_models=verify(models,source_code,qualname='models',
        globals_={'json':IdentityBinding(json),'Path':IdentityBinding(Path)},
        builtins_={'ValueError':IdentityBinding(ValueError)})
    observed_publisher=verify(publisher,source_code,qualname='publish',
        globals_={'models':IdentityBinding(models),'Path':IdentityBinding(Path),
                  'tempfile':IdentityBinding(tempfile),'json':IdentityBinding(json),
                  'managed_temporary_parent':IdentityBinding(atomic_files.managed_temporary_parent)},builtins_={})
    callback=verify(call.fn,owner_code,qualname='brinecove_source_step.<locals>.<lambda>',
        closures={'output':output},globals_={'source_registry':IdentityBinding(module),'ASSETS':game/'assets'},builtins_={})
    return BrinecoveSources(step.name,(helper,library),(owner,helper,atomic),(output,),(),callback,observed_publisher,observed_models)
