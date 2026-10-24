"""Bounded source-origin observations for reviewed legacy profiles, never epoch authority.

A frozen game-specific provider supplies the expected function/environment bindings.
These comparisons do not certify arbitrary Python effects, cleanup or a complete graph.
"""
from dataclasses import dataclass
import dis
import hashlib
import importlib.machinery
import importlib.util
import math
from pathlib import PurePath, PurePosixPath, PureWindowsPath, PosixPath, WindowsPath
import struct
import sys
import types

MAX_CODE_BYTES = 8 * 1024 * 1024
MAX_BINDINGS = 1024
MAX_DEPTH = 24
_PATH_TYPES = (PurePosixPath, PureWindowsPath, PosixPath, WindowsPath)


class UnsupportedOrigin(ValueError):
    """A named profile cannot establish this callable's actual captured origin."""


@dataclass(frozen=True)
class CapturedCode:
    filename: str
    content: bytes

    def __post_init__(self):
        if (type(self.filename) is not str or not self.filename or '\0' in self.filename
                or not PurePath(self.filename).is_absolute() or type(self.content) is not bytes
                or len(self.content) > MAX_CODE_BYTES):
            raise UnsupportedOrigin('invalid captured code identity')

    @property
    def digest(self):
        return hashlib.sha256(self.content).hexdigest()

    def compiled(self):
        # Compile only: no module body, import, decorator or default expression executes here.
        try:
            return compile(self.content, self.filename, 'exec', flags=0,
                           dont_inherit=True, optimize=sys.flags.optimize)
        except (SyntaxError, ValueError, RecursionError):
            # A refusal must not echo source lines/default values into a public diagnostic.
            raise UnsupportedOrigin('captured code cannot be compiled') from None


@dataclass(frozen=True)
class IdentityBinding:
    """Expected checked helper or trusted platform object, supplied by the fixed profile."""
    value: object


@dataclass(frozen=True)
class CallableObservation:
    filename: str
    qualname: str
    first_line: int
    source_digest: str
    binding_names: tuple[str, ...]


def _code_tree(code, depth=0):
    if depth > MAX_DEPTH:
        raise UnsupportedOrigin('captured code nesting exceeds limit')
    yield code
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from _code_tree(value, depth + 1)


def _same_code(actual, expected):
    # CodeType equality intentionally ignores some origin metadata in CPython.
    fields = ('co_filename', 'co_qualname', 'co_name', 'co_firstlineno', 'co_argcount',
              'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals', 'co_stacksize',
              'co_flags', 'co_code', 'co_names', 'co_varnames', 'co_freevars',
              'co_cellvars', 'co_linetable', 'co_exceptiontable')
    if actual != expected or any(getattr(actual, f) != getattr(expected, f) for f in fields):
        return False
    actual_children = [v for v in actual.co_consts if isinstance(v, types.CodeType)]
    expected_children = [v for v in expected.co_consts if isinstance(v, types.CodeType)]
    return (len(actual_children) == len(expected_children)
            and all(_same_code(a, e) for a, e in zip(actual_children, expected_children)))


def _same_value(actual, expected, budget, depth=0):
    budget[0] -= 1
    if budget[0] < 0 or depth > MAX_DEPTH:
        raise UnsupportedOrigin('callable binding exceeds limit')
    if isinstance(expected, IdentityBinding):
        return actual is expected.value
    if type(actual) is not type(expected):
        return False
    if expected is None or type(expected) in (bool, int, str, bytes):
        return actual == expected
    if type(expected) is float:
        return (math.isfinite(actual) and math.isfinite(expected)
                and struct.pack('!d', actual) == struct.pack('!d', expected))
    if type(expected) in _PATH_TYPES:
        return actual == expected
    if type(expected) in (list, tuple):
        return (len(actual) == len(expected)
                and all(_same_value(a, e, budget, depth + 1) for a, e in zip(actual, expected)))
    if type(expected) is dict:
        if any(type(k) is not str for k in actual) or any(type(k) is not str for k in expected):
            raise UnsupportedOrigin('callable binding keys must be strings')
        return (actual.keys() == expected.keys()
                and all(_same_value(actual[k], expected[k], budget, depth + 1) for k in expected))
    raise UnsupportedOrigin('unsupported callable binding type')


def verify_callable(function, captured, *, qualname, namespace, defaults=None,
                    keyword_defaults=None, closures=None, globals_=None, builtins_=None):
    """@cc [owner:fontanierh,label:correctness;safety] legacy-captured-callable-observation
    A supported callable observation MUST match actual code recursively to captured compilation
    at its original logical filename AND the fixed profile's explicit defaults, closures,
    semantic globals and helpers. Filenames, repr, current file hashes and __wrapped__ alone
    MUST NOT prove loaded code. Unknown native/wrapped/mutable bindings MUST refuse; returning
    this metadata MUST NOT construct epoch, write, cleanup or arbitrary-Call authority.
    See test_build_v2_legacy_qualification.py.
    """
    if (type(function) is not types.FunctionType or not isinstance(captured, CapturedCode)
            or type(qualname) is not str or type(namespace) is not dict
            or function.__globals__ is not namespace):
        raise UnsupportedOrigin('callable is not the expected source function')
    expected = [c for c in _code_tree(captured.compiled()) if c.co_qualname == qualname]
    if len(expected) != 1 or not _same_code(function.__code__, expected[0]):
        raise UnsupportedOrigin('loaded callable differs from captured code')
    closures = {} if closures is None else closures
    globals_ = {} if globals_ is None else globals_
    builtins_ = {} if builtins_ is None else builtins_
    if any(type(v) is not dict for v in (closures, globals_, builtins_)):
        raise UnsupportedOrigin('callable bindings need explicit profile records')
    if (any(type(k) is not str for v in (closures, globals_, builtins_) for k in v)
            or len(closures) + len(globals_) + len(builtins_) > MAX_BINDINGS):
        raise UnsupportedOrigin('invalid callable binding names')
    budget = [MAX_BINDINGS]
    if (not _same_value(function.__defaults__, defaults, budget)
            or not _same_value(function.__kwdefaults__, keyword_defaults, budget)):
        raise UnsupportedOrigin('callable defaults differ')
    if set(function.__code__.co_freevars) != set(closures):
        raise UnsupportedOrigin('callable closure names differ')
    try:
        actual_cells = dict(zip(function.__code__.co_freevars,
                                (cell.cell_contents for cell in function.__closure__ or ())))
    except ValueError:
        raise UnsupportedOrigin('callable has an empty closure') from None
    if any(not _same_value(actual_cells[k], v, budget) for k, v in closures.items()):
        raise UnsupportedOrigin('callable closure differs')
    global_names = {instruction.argval for code in _code_tree(function.__code__)
                    for instruction in dis.get_instructions(code)
                    if instruction.opname in ('LOAD_GLOBAL', 'LOAD_NAME')}
    if set(globals_) & set(builtins_) or global_names != set(globals_) | set(builtins_):
        raise UnsupportedOrigin('callable global/builtin binding coverage differs')
    if any(k not in namespace or not _same_value(namespace[k], v, budget) for k, v in globals_.items()):
        raise UnsupportedOrigin('callable global differs')
    if any(k in namespace or k not in function.__builtins__
           or not _same_value(function.__builtins__[k], v, budget) for k, v in builtins_.items()):
        raise UnsupportedOrigin('callable builtin differs')
    return CallableObservation(captured.filename, qualname, function.__code__.co_firstlineno,
                               captured.digest, tuple(sorted((*closures, *globals_, *builtins_))))


class CapturedLoader(importlib.machinery.SourceFileLoader):
    """Only a named captured source; does not load/write a pycache or relocate __file__."""
    def __init__(self, name, captured):
        if not isinstance(captured, CapturedCode):
            raise UnsupportedOrigin('loader requires captured source')
        super().__init__(name, captured.filename)
        self.captured = captured

    def get_code(self, fullname):
        if fullname != self.name:
            raise UnsupportedOrigin('captured module name differs')
        return self.captured.compiled()


def captured_spec(name, captured):
    """Make one profile-named pre-execution loader, preserving logical GAME/spec paths.

    This function is not an import hook or a generic module qualifier. The reviewed provider
    must select every allowed source; unknown nested imports still need their own gate.
    """
    if type(name) is not str or not name or not isinstance(captured, CapturedCode):
        raise UnsupportedOrigin('invalid named captured module')
    return importlib.util.spec_from_file_location(name, captured.filename,
                                                 loader=CapturedLoader(name, captured))
