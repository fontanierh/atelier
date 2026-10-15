"""Explicit, short-lived input membership observations for legacy actions."""
from dataclasses import dataclass, field, replace
import inspect
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class DeferredInputs:
    """@cc [owner:fontanierh,label:correctness] explicit-deferred-collector
    Collectors MUST only observe membership, without importing tools or changing files. They MUST
    declare every implementation/helper file in support and every selection setting explicitly.
    Settings are positional arguments. This is a trusted declaration, not hostile-code isolation.
    """
    name: str
    collect: object = field(repr=False, compare=False)
    settings: tuple = ()
    support: tuple[Path, ...] = ()


def setting(value):
    """Only immutable explicit settings; paths retain their lexical spelling and flavour."""
    if isinstance(value, Path):
        return {'path': str(value)}
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is tuple:
        return [setting(item) for item in value]
    raise ValueError('Deferred input settings must be tuples, paths, strings, integers, booleans or None')


def validate(step):
    """Validate declarations without calling a collector or inspecting its members."""
    if type(step.deferred_inputs) not in (list, tuple):
        raise ValueError(f'{step.name}: deferred inputs must be an explicit list or tuple')
    if not step.deferred_inputs:
        return
    if (step.products or step.reads or step.references or step.queries or step.optional_inputs
            or step.cache or step.audit or step.batch or step.pool_roots or step.toolchain):
        raise ValueError(f'{step.name}: deferred inputs require a legacy action without cache, audit or batching')
    names = set()
    for provider in step.deferred_inputs:
        if (not isinstance(provider, DeferredInputs) or not isinstance(provider.name, str)
                or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', provider.name)
                or provider.name in names or not inspect.isfunction(provider.collect)
                or type(provider.settings) is not tuple or type(provider.support) is not tuple
                or not provider.support or not all(isinstance(p, Path) for p in provider.support)):
            raise ValueError(f'{step.name}: invalid or duplicate deferred input declaration')
        if Path(provider.collect.__code__.co_filename).resolve() not in {p.resolve() for p in provider.support}:
            raise ValueError(f'{step.name}: deferred collector implementation must be declared in support')
        setting(provider.settings)
        try:
            inspect.signature(provider.collect).bind(*provider.settings)
        except TypeError as error:
            raise ValueError(f'{step.name}: deferred collector settings do not match its arguments') from error
        names.add(provider.name)


@dataclass(frozen=True)
class InputObservation:
    """One immutable ordered input list; metadata contains criteria/code labels, never member identities."""
    paths: tuple[Path, ...]
    metadata: str | None = None
    members: tuple[Path, ...] = ()

    def excluding(self, predicate):
        return replace(self, paths=tuple(p for p in self.paths if not predicate(p)),
                       members=tuple(p for p in self.members if not predicate(p)))


def observe(step):
    """@cc [owner:fontanierh,label:correctness] selected-legacy-input-observation
    Unselected actions MUST NOT enumerate deferred membership. A selected fingerprint observation
    MUST freeze the ordered members and explicit criteria/code identity without mutating the recipe.
    A new observation MUST resolve membership afresh; source-only reuse MUST filter observed paths
    without retaining copied member identities in provider metadata.
    """
    validate(step)
    paths, metadata, selected = list(step.inputs), [], []
    if step.deferred_inputs:
        paths.append(Path(__file__))
    for provider in step.deferred_inputs:
        if not all(p.is_file() for p in provider.support):
            raise ValueError(f'{step.name}: deferred support files must exist')
        members = provider.collect(*provider.settings)
        if type(members) not in (list, tuple) or not all(isinstance(p, Path) for p in members):
            raise ValueError(f'{step.name}: deferred collector must return a list or tuple of paths')
        selected.extend(members)
        paths.extend(provider.support)
        paths.extend(members)
        metadata.append({'name': provider.name,
                         'collector': f'{provider.collect.__module__}:{provider.collect.__qualname__}',
                         'settings': setting(provider.settings),
                         'support': [str(p) for p in provider.support]})
    return InputObservation(tuple(paths), json.dumps(metadata, sort_keys=True, separators=(',', ':'))
                            if metadata else None, tuple(selected))
