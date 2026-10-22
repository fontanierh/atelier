"""Retire superseded generated native packages only after complete current validation."""
import re


def package_path(destination, prefix, name):
    if (not isinstance(destination, str) or not re.fullmatch(r'/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*', destination)
            or not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*_', prefix)
            or not isinstance(name, str) or not re.fullmatch(re.escape(prefix)+r'[A-Za-z0-9_]+', name)):
        raise ValueError('Invalid generated native package ownership')
    return destination+'/'+name


def inventory(editor, destination, prefix):
    """Only canonical generated names in one explicitly owned folder participate."""
    package_path(destination, prefix, prefix+'OwnershipProbe')
    found = set()
    for asset in editor.list_assets(destination, recursive=False, include_folder=False):
        if not isinstance(asset, str) or not asset.startswith(destination+'/'):
            raise ValueError('Native inventory escaped its owner folder')
        relative = asset[len(destination)+1:]
        name = relative.split('.')[0]
        if not name.startswith(prefix):
            continue
        package = package_path(destination, prefix, name)
        if asset not in (package, package+'.'+name):
            raise ValueError('Invalid generated native object path')
        if package in found:
            raise ValueError('Duplicate generated native package')
        found.add(package)
    return found


def retire(editor, previous, names, destination, prefix):
    """@cc [owner:fontanierh,label:correctness] retire-only-completed-native-membership
    The caller MUST validate and save EVERY current model before invoking retirement.
    Only inventoried generated packages in this exclusive owner folder MAY retire.
    Current packages and any package referenced from outside the retirement set MUST
    never be deleted. The full deletion plan MUST pass ownership, existence and external
    reference checks before any deletion; failures MUST prevent task completion.
    """
    if not isinstance(previous, set) or not isinstance(names, (list, tuple)) or not names:
        raise ValueError('Native retirement requires complete current membership')
    current = {package_path(destination, prefix, name) for name in names}
    if len(current) != len(names):
        raise ValueError('Duplicate current native package')
    for package in previous:
        if not isinstance(package, str) or package_path(destination, prefix, package.rsplit('/', 1)[-1]) != package:
            raise ValueError('Native retirement escaped its owner folder')
    if any(not editor.does_asset_exist(package) for package in current):
        raise ValueError('Current native membership is incomplete')
    obsolete = previous-current
    if any(not editor.does_asset_exist(package) for package in obsolete):
        raise ValueError('Prior native membership changed before retirement')
    return _retire(editor, obsolete)


def retire_replaced(editor, replacements):
    """@cc [owner:fontanierh,label:correctness] retire-completely-replaced-native-parents
    The caller MUST own and explicitly delegate each old generated parent to its
    complete validated and saved replacement packages. Every replacement MUST exist
    before any retirement. Self references, cycles, escapes and external references
    MUST refuse before deletion. Saved originals outside the declared generated
    ownership MUST NOT enter this map. A failed deletion MUST prevent publication.
    """
    pattern = r'/Game/(?:[A-Za-z0-9_]+/)+[A-Za-z0-9_][A-Za-z0-9_-]*'
    if not isinstance(replacements, dict) or not replacements:
        raise ValueError('Native replacement requires explicit parent ownership')
    all_current = set()
    for parent, children in replacements.items():
        if (not isinstance(parent, str) or not re.fullmatch(pattern, parent)
                or not isinstance(children, (list, tuple)) or not children
                or any(not isinstance(child, str) or not re.fullmatch(pattern, child) for child in children)
                or len(set(children)) != len(children)):
            raise ValueError('Invalid native replacement membership')
        all_current.update(children)
    if set(replacements) & all_current:
        raise ValueError('Native replacement contains a current parent or cycle')
    if any(not editor.does_asset_exist(child) for child in all_current):
        raise ValueError('Current native replacements are incomplete')
    obsolete = {parent for parent in replacements if editor.does_asset_exist(parent)}
    return _retire(editor, obsolete)


def _retire(editor, obsolete):
    # References between retiring packages are allowed: each is removed through
    # the editor API. A live current/foreign package must keep its dependencies.
    for package in sorted(obsolete):
        references = editor.find_package_referencers_for_asset(package, load_assets_to_confirm=True)
        if references is None or isinstance(references, (str, bytes, dict)):
            raise ValueError('Invalid native package reference inventory')
        try:
            references = list(references)  # UE exposes TArray as unreal.Array, not a Python list.
        except TypeError as error:
            raise ValueError('Invalid native package reference inventory') from error
        if any(not isinstance(reference, str) or reference not in obsolete for reference in references):
            raise ValueError('Superseded native package still has external references: '+package)
    retired = []
    # Primaries precede their conventional collision companions. Lexical order
    # puts a primary before Primary_Collision while leaving unrelated names stable.
    for package in sorted(obsolete):
        if not editor.delete_asset(package) or editor.does_asset_exist(package):
            raise ValueError('Could not retire superseded native package: '+package)
        retired.append(package)
    return retired
