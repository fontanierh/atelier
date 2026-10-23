"""Combined exact native park membership retirement after complete current validation."""
from pathlib import Path
from atelier import native_membership
from atelier.export_manifest import real_directory


def inventory(editor, root, prefix):
    destination = root + '/Meshes'
    return native_membership.inventory(editor, destination, 'SM_' + prefix + '_') | \
        native_membership.inventory(editor, destination, 'UC_' + prefix + '_')


def retire(editor, previous, report, root, prefix, content):
    """@cc [owner:fontanierh,label:correctness] park-current-before-combined-retirement
    Every current render/collision/seed MUST exist physically and have been validated
    and saved before retirement. A single reference preflight MUST cover all obsolete
    children and parents. Foreign references MUST refuse before any deletion. Task
    success MUST require physical old-package absence and exact current membership.
    """
    destination = root + '/Meshes'
    rows = [row for field in ('render', 'collision', 'seam') for row in report.get(field, [])]
    names = [row['name'] for row in rows]
    if not rows or len(set(names)) != len(names):
        raise ValueError('Incomplete or duplicate native park roster')
    current = set()
    for name in names:
        family = ('UC_' if name.startswith('UC_') else 'SM_') + prefix + '_'
        current.add(native_membership.package_path(destination, family, name))
    real_directory(content)
    def physical(package):
        return Path(content) / (package[len('/Game/'):] + '.uasset')
    for package in previous | current:
        path = physical(package)
        real_directory(path.parent)
        if path.is_symlink():
            raise ValueError('Linked owned native park package')
        if package in current and (not editor.does_asset_exist(package) or not path.is_file()):
            raise ValueError('Missing saved current park primary: ' + package)
    replacements = {package: sorted(current) for package in previous - current}
    retired = native_membership.retire_replaced(editor, replacements) if replacements else []
    for package in retired:
        path = physical(package)
        if any(path.with_suffix(suffix).exists() or path.with_suffix(suffix).is_symlink()
               for suffix in ('.uasset','.uexp','.ubulk','.uptnl')):
            raise ValueError('Superseded park package remains on disk: ' + package)
    if inventory(editor, root, prefix) != current:
        raise ValueError('Native park membership differs from complete current roster')
    return retired
