"""Explicit normal-build markers. They carry declarations, never v1 certificates."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import unicodedata

from .controller_client import MAX_CONTROL_BYTES, _relative


@dataclass(frozen=True)
class ControllerTarget:
    unit: str
    project: str
    declaration: dict
    staged_inputs: dict
    content_slots: dict
    allowed_install_roots: tuple

    def request(self, checkout):
        """Strict Rust control data; this Python layer computes no item identity."""
        value = {
            'version': 1, 'checkout': str(checkout), 'project': self.project,
            'allowed_install_roots': list(self.allowed_install_roots),
            'declaration': self.declaration, 'targets': [self.unit],
            'data_contract': {'content_slots': self.content_slots},
            'staged_inputs': self.staged_inputs,
        }
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > MAX_CONTROL_BYTES:
            raise ValueError('controller declaration exceeds control size bound')
        return json.loads(raw)

    def outputs(self, checkout):
        units = [unit for unit in self.declaration.get('units', ()) if unit.get('id') == self.unit]
        if len(units) != 1 or units[0].get('output_groups'):
            raise ValueError('controller marker requires one declared fixed target')
        result = []
        for item in units[0].get('outputs', ()):
            if item.get('destination') != 'checkout' or item.get('class') != 'JsonData':
                raise ValueError('initial controller marker requires checkout JsonData outputs')
            for member in item.get('files', ()):
                install = _relative(member.get('install_path'))
                result.append(Path(checkout) / install)
        if not result or len(set(result)) != len(result):
            raise ValueError('controller marker needs complete unique output ownership')
        return tuple(result)


def _claim(path):
    # Conservative metadata collision detection across the legacy boundary. Rust
    # still validates authoritative install policy; this is not APFS equivalence.
    return unicodedata.normalize('NFD', os.path.abspath(path)).casefold()


def validate_markers(steps, checkout):
    """@cc [owner:fontanierh,label:correctness] explicit-controller-step-ownership
    Controller steps MUST be explicit typed markers with complete matching output
    ownership and no v1 commands, key inputs, cache, checkpoints or tool dispatch.
    Their owned paths MUST NOT overlap another step's declared output roots. Empty
    commands alone MUST NOT imply controller ownership or a successful completion.
    See test_build_v2_controller_recipe.py. Rust validates the complete selected
    declaration before execution; v1 checkpoint/reader custody remains an activation gate.
    """
    steps = tuple(steps)
    if not any(getattr(step, 'controller', None) is not None for step in steps):
        return
    controller_names = {step.name for step in steps if getattr(step, 'controller', None) is not None}
    claims = []
    for step in steps:
        if set(step.needs) & controller_names:
            raise ValueError('v1 content needs cannot use controller input keys; an explicit content bridge is required')
        marker = getattr(step, 'controller', None)
        if marker is not None:
            if not isinstance(marker, ControllerTarget) or marker.unit != step.name:
                raise ValueError('invalid explicit controller step marker')
            forbidden = ('commands', 'inputs', 'deferred_inputs', 'optional_inputs', 'needs', 'products',
                         'reads', 'references', 'queries', 'pool_roots', 'cache', 'audit', 'toolchain',
                         'batch', 'heavy', 'cutoff', 'replan', 'checkpoint_outputs', 'checkpoint_restore',
                         'checkpoint_previous_needs', 'candidate_scope', 'verify', 'cook_recovery')
            if any(getattr(step, field, None) for field in forbidden):
                raise ValueError('controller step cannot use v1 execution/key/cache machinery')
            expected = marker.outputs(checkout)
            if {_claim(path) for path in step.outputs} != {_claim(path) for path in expected}:
                raise ValueError('controller step outputs differ from its complete declaration')
            marker.request(checkout)  # Also rejects non-data/unbounded serialization.
        roots = [*step.outputs, *getattr(step, 'checkpoint_outputs', ()), *getattr(step, 'pool_roots', ())]
        for product in getattr(step, 'products', ()):
            roots.extend(product.paths)
            roots.extend(product.optional_paths)
        for path in roots:
            claims.append((step.name, _claim(path), marker is not None))
    for owner, path, _ in (claim for claim in claims if claim[2]):
        for other, other_path, _ in claims:
            if owner != other and (
                    path == other_path or path.startswith(other_path + '/') or other_path.startswith(path + '/')):
                raise ValueError(f'controller output ownership overlaps: {owner} and {other}')
