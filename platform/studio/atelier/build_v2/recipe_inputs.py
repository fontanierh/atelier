"""Lower one extracted recipe row's consumed inputs into v2 unit inputs; never execute recipe code.

Generated paths bind to their producer's published items. Source directories are listed
completely from the checkout before keying (never a generated-output scan). Deferred
collectors keep their pure descriptor and see every owning producer root's frozen bytes.
References are conservative content edges. Installed engine roots are tool metadata.
"""
import os
from copy import deepcopy
from pathlib import Path, PurePosixPath


class Unsupported(ValueError):
    """An input cannot be represented without losing a consumed effect."""


TOOL_ROOTS = ('blender',)


def _path(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('.', '..') for part in value.split('/'))):
        raise Unsupported(f'noncanonical recipe path: {value!r}')
    return value


def _under(path, root):
    return path == root or path.startswith(root + '/')


def _source_members(checkout, path):
    """Complete regular-file membership of a checkout source path; links and specials refuse."""
    absolute = Path(checkout) / path
    try:
        info = absolute.lstat()
    except FileNotFoundError:
        return None
    if absolute.is_symlink():
        raise Unsupported(f'linked source input {path}')
    if not os.path.isdir(absolute):
        return [path]
    members = []
    for directory, names, files in os.walk(absolute, followlinks=False):
        names.sort()
        for name in names:
            if (Path(directory) / name).is_symlink():
                raise Unsupported(f'linked source directory {Path(directory, name).relative_to(checkout)}')
        for name in sorted(files):
            member = Path(directory) / name
            if member.is_symlink() or not member.is_file():
                raise Unsupported(f'linked or special source file {member.relative_to(checkout)}')
            members.append(member.relative_to(checkout).as_posix())
    return members


def _archive(rows_by_name, owner, item):
    producer = rows_by_name[owner]
    if item.startswith('product'):
        index = int(item.removeprefix('product'))
        product = producer['products'][index]
        owned = [*product['paths'], *product['optional_paths']]
        return owned, [f'products/{index}-{i}.tree.tar' for i in range(len(owned))]
    index = int(item.removeprefix('output'))
    root = producer['outputs'][index]
    suffix = 'mac.zip' if producer.get('native_output_encoding', {}).get(root) == 'mac-zip' else 'tree.tar'
    return [root], [f'outputs/{index}.{suffix}']


_ANCESTORS = {}


def _ancestors(name, rows_by_name, products):
    """Transitive prerequisites through needs, after, reads and references (memoised per graph)."""
    memo = _ANCESTORS.setdefault(id(rows_by_name), {})
    if name in memo:
        return memo[name]
    seen, todo = set(), [name]
    while todo:
        current = rows_by_name.get(todo.pop())
        if current is None:
            continue
        direct = [*current['needs'], *current['after'],
                  *(products[r['product']][0] for kind in ('reads', 'references')
                    for r in current[kind] if r['product'] in products)]
        for parent in direct:
            if parent not in seen and parent != name:
                seen.add(parent)
                todo.append(parent)
    memo[name] = seen
    return seen


def lower_inputs(row, *, rows, roots, products, checkout):
    """@cc [owner:fontanierh,label:correctness] recipe-inputs-complete-identity
    Return {inputs, staged, paths, slots, code, tools, deferred} for one row. Every consumed
    byte MUST have an identity: generated roots as producer items, source files and complete
    source-directory members as file inputs, deferred collectors with ALL owning producer
    roots, references as content edges. Unknown external data MUST refuse by name.
    """
    name = row['id']
    rows_by_name = rows if isinstance(rows, dict) else {r['id']: r for r in rows}
    inputs, staged, paths, slots, incoming = [], {}, {}, {}, {}
    code = set(map(_path, (c for c in row['code'] if not c.startswith('<'))))
    tools = sorted(c for c in row['code'] if c.startswith('<'))

    def upstream(owner, item, paths_read):
        if owner == name:
            raise Unsupported(f'{name}: action reads its own unpublished output')
        if (owner, item) not in incoming:
            slot = f'item{len(incoming)}'
            inputs.append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': owner, 'item': item}})
            staged[slot] = f'inputs/{slot}'
            slots[slot] = False
            incoming[(owner, item)] = slot
        slot = incoming[(owner, item)]
        owned, archives = _archive(rows_by_name, owner, item)
        for path in paths_read:
            matches = [i for i, root in enumerate(owned) if _under(path, root) or _under(root, path)]
            if not matches:
                raise Unsupported(f'{name}: input {path} has no product-root binding in {owner}')
            for index in matches:
                paths[_path(owned[index])] = f'{staged[slot]}/{archives[index]}'

    def generated_owners(path):
        """Producer items owning path, or owning roots beneath a declared directory."""
        owners = [(root, owner, item) for root, owner, item in roots if _under(path, root)]
        if owners:
            longest = max(len(root) for root, _, _ in owners)
            owners = {entry for entry in owners if len(entry[0]) == longest}
            if len(owners) != 1:
                raise Unsupported(f'{name}: ambiguous generated input {path}')
            return list(owners)
        return [(root, owner, item) for root, owner, item in roots if _under(root, path) and owner != name]

    def source(path, optional):
        members = _source_members(checkout, path)
        if members is None:
            if not optional:
                raise Unsupported(f'{name}: missing source input {path}')
            members = [path]  # an absent optional source keeps its explicit absence identity
        for member in members:
            if member in code or member in paths:
                continue
            slot = f'file{len(staged)}'
            inputs.append({'role': 'content', 'name': slot,
                           'source': {'kind': 'file', 'path': member, 'optional': bool(optional)},
                           'whole': 'The original producer consumes this complete declared source.'})
            staged[slot] = f'inputs/{slot}'
            slots[slot] = False
            paths[member] = staged[slot]

    def consumed(path, optional=False):
        path = _path(path)
        if path in code:
            return
        owners = generated_owners(path)
        if owners:
            for root, owner, item in owners:
                upstream(owner, item, [root if _under(root, path) else path])
            # A declared directory may mix source files with generated sub-roots.
            if any(_under(root, path) and root != path for root, _, _ in owners):
                for member in _source_members(checkout, path) or []:
                    if not any(_under(member, root) for root, _, _ in owners):
                        source(member, False)
            return
        source(path, optional)

    for kind in ('reads', 'references'):  # references: conservative content edges, never byte-free proof
        for read in row[kind]:
            if read['product'] not in products:
                raise Unsupported(f'{name}: unknown product {read["product"]}')
            owner, item, owned = products[read['product']]
            if owner != read['producer'] or list(owned) != list(read['paths']):
                raise Unsupported(f'{name}: product {read["product"]} differs from its owning declaration')
            upstream(owner, item, owned)
    for dependency in (*row['needs'], *row['after']):
        if dependency not in rows_by_name:
            raise Unsupported(f'{name}: unknown prerequisite {dependency}')
        for root, owner, item in roots:
            if owner == dependency:
                upstream(owner, item, [root])
    for entry in row['inputs']:
        root = entry.get('root', 'checkout')
        if root in TOOL_ROOTS:
            tools.append(f'<{root}>/{entry["path"]}')
            continue
        if root != 'checkout':
            raise Unsupported(f'{name}: external {root} data {entry["path"]} needs a declared external source unit')
        consumed(entry['path'], entry['optional'])
    deferred = []
    ancestors = _ancestors(name, rows_by_name, products) if row['deferred'] else set()
    for provider in row['deferred']:
        code.update(map(_path, provider['support']))
        if provider['collect'] is not None:
            code.add(_path(provider['collect']['source']))
        # Membership is data-dependent (collectors read upstream manifests), so the static bound is every
        # ANCESTOR producer root under a selected folder: never this step's own or a downstream output.
        generated_roots, source_roots = [], []
        def settings_paths(value):
            if isinstance(value, dict) and 'path' in value:
                if value.get('root', 'checkout') != 'checkout':
                    raise Unsupported(f'{name}: deferred {provider["name"]} reads external {value["root"]} data '
                                      f'{value["path"]}; it needs a declared external source unit')
                path = value['path']
                bound = [(root, producer, item) for root, producer, item in roots
                         if producer in ancestors and (path == '.' or _under(root, path) or _under(path, root))]
                for root, producer, item in bound:
                    upstream(producer, item, [root])
                    generated_roots.append(root)
                if path == '.':
                    source_roots.append(path)  # the whole checkout: the runtime keys observed members
                elif not any(_under(path, root) or _under(root, path) for root, _, _ in roots):
                    consumed(path)  # a source folder: every member is keyed now, no runtime observation needed
            elif isinstance(value, list):
                for item in value:
                    settings_paths(item)
        settings_paths(provider['settings'])
        descriptor = deepcopy(provider)
        descriptor['bound_generated_roots'] = sorted(set(generated_roots))
        descriptor['observed_source_roots'] = sorted(set(source_roots))
        deferred.append(descriptor)
    return {'inputs': inputs, 'staged': staged, 'paths': paths, 'slots': slots,
            'code': sorted(code), 'tools': sorted(set(tools)), 'deferred': deferred}
