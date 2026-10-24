"""Selected in-process callback code identities, never execution authority."""
from dataclasses import dataclass, field
from pathlib import Path
from .legacy_qualification import UnsupportedOrigin

_CALL_ORIGIN = object()


@dataclass(frozen=True)
class _CapturedCallRuntime:
    files: tuple[Path, ...]
    origin: object = field(repr=False, compare=False)


def bind_captured_call(step, *, checkout, issuer_files, code_inputs):
    """Fixed issuer attachment only; no invocation or write permission is constructed."""
    names = set(issuer_files)
    files = tuple(dict.fromkeys(map(Path, code_inputs)))
    if not files or any(path.suffix != '.py' or path.relative_to(checkout).as_posix() not in names for path in files):
        raise UnsupportedOrigin('callback code is outside its original captured issuer')
    step._captured_call_runtime = _CapturedCallRuntime(files, _CALL_ORIGIN)


def captured_call_inputs(step):
    runtime = getattr(step, '_captured_call_runtime', None)
    if runtime is None:
        return ()
    if type(runtime) is not _CapturedCallRuntime or runtime.origin is not _CALL_ORIGIN:
        raise UnsupportedOrigin('callback runtime is not a fixed issuer observation')
    return runtime.files
