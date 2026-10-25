"""Pure v2 target declarations and request assembly; Rust owns validation and build decisions."""
from dataclasses import dataclass
import json
from pathlib import Path

from .controller_client import MAX_CONTROL_BYTES, _relative


@dataclass(frozen=True)
class ControllerTarget:
    unit: str
    project: str
    declaration: dict
    staged_inputs: dict
    content_slots: dict
    allowed_install_roots: tuple
    templates: tuple = ()
    selection_targets: tuple = ()

    def request(self, checkout):
        """Strict Rust control data; this Python layer computes no item identity."""
        value = {
            'version': 1, 'checkout': str(checkout), 'project': self.project,
            'allowed_install_roots': list(self.allowed_install_roots),
            'declaration': self.declaration, 'targets': list(self.selection_targets or (self.unit,)),
            'data_contract': {'content_slots': self.content_slots},
            'staged_inputs': self.staged_inputs,
        }
        if self.templates:
            value['templates'] = list(self.templates)
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > MAX_CONTROL_BYTES:
            raise ValueError(f'controller declaration is {len(raw)} bytes, limit {MAX_CONTROL_BYTES} bytes')
        return json.loads(raw)

    def outputs(self, checkout):
        units = [unit for unit in self.declaration.get('units', ()) if unit.get('id') == self.unit]
        if len(units) != 1 or units[0].get('output_groups'):
            raise ValueError('controller marker requires one declared fixed target')
        result = []
        for item in units[0].get('outputs', ()):
            if item.get('destination') != 'checkout':
                raise ValueError('target output requires an explicit checkout destination')
            for member in item.get('files', ()):
                install = _relative(member.get('install_path'))
                result.append(Path(checkout) / install)
        if not result or len(set(result)) != len(result):
            raise ValueError('controller marker needs complete unique output ownership')
        return tuple(result)

@dataclass(frozen=True)
class ControllerSelection:
    """One explicit selection over a complete pure declaration, with no Python action key."""
    members: tuple[ControllerTarget, ...]
    targets: tuple[str, ...]

    @property
    def name(self):
        return ', '.join(self.targets)

    def request(self, checkout):
        """@cc [owner:fontanierh,label:correctness] direct-v2-selection-request
        Preserve all declared units and original target/control data. Conflicting unit,
        staged-slot, project or contract declarations MUST refuse. Explicit selectors
        MUST remain selectors, never source keys, receipts or guessed cache outcomes.
        """
        if not self.members or not self.targets or len(set(self.targets)) != len(self.targets):
            raise ValueError('v2 requires a nonempty unique target selection')
        units, staged, slots, roots, templates = {}, {}, {}, set(), {}
        base = None
        seen = set()
        for member in self.members:
            if not isinstance(member, ControllerTarget):
                raise ValueError('invalid v2 target declaration')
            shared = (member.project, id(member.declaration), id(member.staged_inputs),
                      id(member.content_slots), member.allowed_install_roots, id(member.templates))
            if shared in seen:
                continue  # One shared graph may expose thousands of selectable roots.
            seen.add(shared)
            request = member.request(checkout)
            header = {key: value for key, value in request['declaration'].items() if key != 'units'}
            identity = (request['version'], request['checkout'], request['project'], header)
            if base is None:
                base = identity
            elif identity != base:
                raise ValueError('conflicting v2 project/declaration headers')
            roots.update(request['allowed_install_roots'])
            for template in request.get('templates', ()):
                key = (template['producer'], template['group'])
                if key in templates and templates[key] != template:
                    raise ValueError('conflicting v2 child template')
                templates[key] = template
            for unit in request['declaration']['units']:
                name = unit['id']
                if name in units and units[name] != unit:
                    raise ValueError('conflicting v2 unit: ' + name)
                units[name] = unit
            for name, value in request['staged_inputs'].items():
                if name in staged and staged[name] != value:
                    raise ValueError('conflicting v2 staged inputs: ' + name)
                staged[name] = value
            for name, value in request['data_contract']['content_slots'].items():
                if name in slots and slots[name] != value:
                    raise ValueError('conflicting v2 content contract: ' + name)
                slots[name] = value
        aliases = {member.unit: member.selection_targets for member in self.members
                   if member.selection_targets}
        selected = tuple(dict.fromkeys(unit for name in self.targets for unit in aliases.get(name, (name,))))
        if any(name not in units for name in selected):
            raise ValueError('selected v2 target is not declared')
        version, source, project, header = base
        result = {'version': version, 'checkout': source, 'project': project,
                'allowed_install_roots': sorted(roots),
                'declaration': {**header, 'units': list(units.values())},
                'targets': list(selected), 'data_contract': {'content_slots': slots},
                'staged_inputs': staged}
        if templates:
            result['templates'] = list(templates.values())
        return result
