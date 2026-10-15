"""Changes between certified product inventories, using metadata already held by the builder."""
import json
import os
from pathlib import Path, PurePosixPath
import re

from . import build_products, paths

SHA256 = re.compile(r'[0-9a-f]{64}')


def root_labels(ctx, step):
    """Portable lexical labels, without inspecting paths. External roots remain incomparable."""
    bases = ((Path(os.path.abspath(ctx.out)), '<build>'), (Path(os.path.abspath(paths.REPO)), '<repo>'))
    result = {}
    for product in step.products:
        labels = []
        for root in product.roots():
            path = Path(os.path.abspath(root))
            label = next((prefix + '/' + path.relative_to(base).as_posix()
                          for base, prefix in bases if path.is_relative_to(base)), None)
            labels.append(label)
        result[product.name] = labels
    return result


def optional_roots(step):
    """Retain optional root roles separately, keeping old required-only labels compatible."""
    return {product.name: list(range(len(product.paths), len(product.roots())))
            for product in step.products if product.optional_paths}


def files(record, roots, optional=()):
    """Accept only a complete, internally consistent historical inventory; never read its files."""
    if (not isinstance(record, dict) or not isinstance(roots, list) or not roots
            or any(not isinstance(root, str) or not root.startswith(('<build>/', '<repo>/'))
                   or '..' in root.split('/') for root in roots) or len(set(roots)) != len(roots)):
        return None
    if (not isinstance(optional, (list, tuple)) or any(type(index) is not int or not 0 <= index < len(roots)
                                                     for index in optional) or len(set(optional)) != len(optional)):
        return None
    if optional and (optional[0] == 0 or list(optional) != list(range(optional[0], len(roots)))):
        return None  # Product declares required roots first, followed by every optional root.
    inventory = record.get('inventory')
    if (not isinstance(inventory, dict) or set(inventory) != {'schema', 'files'}
            or type(inventory['schema']) is not int or inventory['schema'] != 1 or not isinstance(inventory['files'], dict)):
        return None
    try:
        if build_products.identity(inventory) != record.get('digest'):
            return None
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None
    members = inventory['files']
    if any(f'{index}/.' not in members for index in range(len(roots))):
        return None
    indexes = {str(index) for index in range(len(roots))}
    for name, item in members.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            return None
        index, separator, relative = name.partition('/')
        path = PurePosixPath(relative)
        if (not separator or index not in indexes or not relative or relative != path.as_posix()
                or path.is_absolute() or '..' in path.parts):
            return None
        if relative != '.' and members.get(f'{index}/{path.parent.as_posix()}') != {'kind': 'directory'}:
            return None
        if item.get('kind') == 'absent':
            if relative != '.' or int(index) not in optional or item != {'kind': 'absent'}:
                return None
        elif item.get('kind') == 'directory':
            if item != {'kind': 'directory'}:
                return None
        elif item.get('kind') == 'file':
            if (set(item) != {'kind', 'size', 'sha256'} or type(item['size']) is not int or item['size'] < 0
                    or not isinstance(item['sha256'], str) or not SHA256.fullmatch(item['sha256'])):
                return None
        else:
            return None
    return members


def compare(previous, products, roots, *, restored=False, optional=None):
    """@cc [owner:fontanierh,label:correctness] certified-output-differences
    Changes MUST compare certified inventories, not filesystem writes or damage repaired by a restore.
    Missing/malformed baselines and changed root ordering MUST remain unknown. This diagnostic MUST
    NOT read product bytes or participate in fingerprints, product identities or cache manifests.
    """
    before, old_roots = previous.get('products'), previous.get('product_roots')
    old_optional = previous.get('product_optional_roots', {})
    optional = {} if optional is None else optional
    baseline = (isinstance(before, dict) and isinstance(old_roots, dict) and set(before) == set(old_roots)
                and isinstance(old_optional, dict) and isinstance(optional, dict)
                and isinstance(previous.get('fingerprint'), str) and SHA256.fullmatch(previous['fingerprint'])
                and not previous.get('touched'))
    names = sorted(set(products) | (set(before) if baseline else set()))
    result = []
    for name in names:
        old = files(before[name], old_roots.get(name), old_optional.get(name, ())) if baseline and name in before else {}
        new = files(products[name], roots.get(name), optional.get(name, ())) if name in products else {}
        reason = None
        if not baseline:
            reason = 'no comparable baseline'
        elif old is None or new is None:
            reason = 'malformed inventory or unsupported output roots'
        elif name in before and name in products and old_roots[name] != roots[name]:
            reason = 'output roots moved or reordered'
        elif name in before and name in products and old_optional.get(name, []) != optional.get(name, []):
            reason = 'output root optionality changed'
        declaration = ('unknown' if not baseline else 'added' if name not in before else
                       'retired' if name not in products else 'unchanged' if old_roots[name] == roots[name]
                       and old_optional.get(name, []) == optional.get(name, []) else 'changed')
        item = {'product': name, 'status': 'unknown' if reason else 'compared',
                'declaration': declaration, 'before_roots': old_roots.get(name) if baseline else None, 'roots': roots.get(name)}
        if reason:
            item['reason'] = reason
        else:
            def labels(members, declarations):
                return [declarations[int(index)] + ('' if relative == '.' else '/' + relative)
                        for index, relative in (member.split('/', 1) for member in sorted(members))]
            # An absent optional root is an inventory marker, not a retained output member.
            old_present = {key: value for key, value in old.items() if value['kind'] != 'absent'}
            new_present = {key: value for key, value in new.items() if value['kind'] != 'absent'}
            common = old_present.keys() & new_present.keys()
            item.update(added=labels(new_present.keys() - old_present.keys(), roots.get(name)),
                        retired=labels(old_present.keys() - new_present.keys(), old_roots.get(name)),
                        changed=labels((key for key in common if old_present[key] != new_present[key]), roots.get(name)),
                        unchanged=sum(old_present[key] == new_present[key] for key in common))
        result.append(item)
    return {'schema': 1, 'baseline': 'known' if baseline else 'unknown',
            'action': 'cache restore' if restored else 'execution', 'products': result}


def inspect(ctx, steps, wanted=()):
    """Historical receipts only; declarations select the steps, with no input/output verification."""
    from .build import order
    from .build_plan import read_stamp
    result = []
    for step in order(steps, list(wanted)):
        stamp = read_stamp(ctx.stamps / f'{step.name}.json')
        receipt = stamp.get('output_changes')
        reason = None
        if (ctx.stamps / f'{step.name}.restore.json').exists():
            reason = 'interrupted restoration'
        elif stamp.get('touched'):
            reason = 'touched outputs have no certified change receipt'
        elif not isinstance(receipt, dict) or receipt.get('schema') != 1 or not isinstance(receipt.get('products'), list):
            reason = 'not recorded'
        result.append({'step': step.name, 'time': stamp.get('time'),
                       'copied': bool(stamp.get('reused_from') or stamp.get('pooled_from')),
                       'changes': None if reason else receipt, 'reason': reason})
    return {'schema': 1, 'game': ctx.game, 'historical': True, 'steps': result}


def show(game, wanted=(), *, as_json=False, echo=print):
    from . import build
    ctx = build.Context(game, create=False)
    report = inspect(ctx, build.load_recipe(game).steps(ctx), wanted)
    if as_json:
        echo(json.dumps(report, indent=2))
        return 0
    echo('Historical certified-output differences; current files and filesystem writes are not checked.')
    for item in report['steps']:
        receipt = item['changes']
        if receipt is None:
            echo(f"{item['step']:34s} {item['reason']}")
            continue
        copied = ' (copied receipt)' if item['copied'] else ''
        echo(f"{item['step']:34s} {receipt.get('action', 'unknown action')}{copied}; baseline {receipt.get('baseline', 'unknown')}")
        for product in receipt['products']:
            if not isinstance(product, dict):
                continue
            if product.get('status') != 'compared':
                echo(f"  {product.get('product')}: unknown ({product.get('reason', 'invalid receipt')})")
                continue
            declaration = product.get('declaration', 'unknown')
            echo(f"  {product.get('product')}: declaration {declaration}; {product.get('unchanged')} unchanged members")
            for kind in ('added', 'changed', 'retired'):
                members = product.get(kind, [])
                if isinstance(members, list):
                    for member in members:
                        echo(f'    {kind}: {member}')
    return 0
