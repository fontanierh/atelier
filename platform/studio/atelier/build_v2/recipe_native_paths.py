"""Map only declared finished Native input members into an owned stock-cook view."""
from copy import deepcopy
from pathlib import Path
import re
import stat

SIDECARS = ('.uasset', '.umap', '.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')


def bind(job, job_dir):
    """@cc [owner:fontanierh,label:correctness;safety] declared-native-cook-paths
    Native paths MUST derive only from named declared job inputs and fully resolved
    derived-member input slots. Every mapped member MUST be a regular, unlinked
    canonical content/Game package file inside that staged input. Unknown slots,
    unresolved membership, duplicate destinations and outside paths MUST refuse.
    This projection MUST NOT inspect ambient Content or alter identity ingredients.
    """
    result = deepcopy(job)
    recipe = result['params']['recipe']
    binding = recipe.get('native_inputs')
    if binding is None:
        return result
    if (not isinstance(binding, dict) or set(binding) != {'slots', 'derived'}
            or not isinstance(binding['slots'], list) or not isinstance(binding['derived'], list)):
        raise ValueError('Native recipe inputs require explicit slots and resolved derived members')
    slots = list(binding['slots'])
    for token in binding['derived']:
        if (not isinstance(token, dict) or set(token) != {'derived_items'}
                or not isinstance(token['derived_items'], dict)
                or set(token['derived_items']) != {'root', 'members'}
                or not isinstance(token['derived_items']['members'], list)):
            raise ValueError('Native recipe member identities have not resolved')
        for row in token['derived_items']['members']:
            if not isinstance(row, dict) or not isinstance(row.get('slot'), str):
                raise ValueError('Native recipe member lacks its staged input slot')
            slots.append(row['slot'])
    if any(not isinstance(slot, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', slot) for slot in slots):
        raise ValueError('Native recipe input slot is invalid')
    incoming = {row['name']: row['path'] for row in job['inputs']}
    if len(incoming) != len(job['inputs']):
        raise ValueError('Native recipe has duplicate input slots')
    base = Path(job_dir)
    project = result['params']['project']
    if (not isinstance(project, str) or not project.endswith('.uproject')
            or project.startswith('/') or any(part in ('', '.', '..') for part in project.split('/'))):
        raise ValueError('Native recipe requires a canonical project descriptor')
    destination_root = str(Path(project).parent / 'Content')
    paths = recipe['paths']
    for slot in dict.fromkeys(slots):
        if slot not in incoming:
            raise ValueError('Native recipe names an undeclared input slot: ' + slot)
        relative = incoming[slot]
        if (not isinstance(relative, str) or relative.startswith('/')
                or any(part in ('', '.', '..') for part in relative.split('/'))):
            raise ValueError('Native recipe input is not a canonical staged path')
        source = base / relative
        content = source / 'content/Game'
        if source.resolve() != source or content.resolve() != content or not content.is_dir():
            raise ValueError('Native recipe input lacks its anchored content/Game tree')
        count = 0
        for path in sorted(content.rglob('*')):
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            name = path.relative_to(content).as_posix()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or path.resolve() != path
                    or not re.fullmatch(r'[A-Za-z0-9_/-]+(?:\.uasset|\.umap|\.uexp|\.ubulk|\.uptnl|\.m\.ubulk|\.upayload)', name)
                    or not name.endswith(SIDECARS)):
                raise ValueError('Native recipe input contains a foreign or aliased package member')
            destination = destination_root + '/' + name
            staged = relative + '/content/Game/' + name
            if destination in paths and paths[destination] != staged:
                raise ValueError('Native recipe input destinations collide: ' + destination)
            paths[destination] = staged
            count += 1
        if not count:
            raise ValueError('Native recipe input contains no package files')
    return result
