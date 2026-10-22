"""Complete native pier package membership for normal incremental repair."""
import hashlib
import json
from pathlib import Path

from atelier.mesh_geometry import package_inventory


def present(out, content):
    """@cc [owner:fontanierh,label:correctness] complete-native-pier-package-presence
    A normal incremental hit MUST retain the complete currently published pier/board/material/texture
    package groups and matching runtime roster. Missing, changed or linked sidecars MUST rerun the
    native owner; report existence alone MUST NOT hide a missing piece. These byte checks MUST NOT
    replace current native import/material/collision proof when the owner actually executes.
    """
    try:
        root = Path(out) / 'skatepark'
        report = json.loads((root / 'import-report.json').read_text())
        runtime_path = root / 'runtime-park.json'
        runtime = json.loads(runtime_path.read_text())
        names = [row['name'] for row in runtime['meshes']]
        if not names or len(set(names)) != len(names) or set(report['park']) != set(names):
            return False
        if report['runtime_park_sha256'] != hashlib.sha256(runtime_path.read_bytes()).hexdigest():
            return False
        required = {'/Game/SkatePark/' + name for name in names}
        required.update('/Game/SkatePark/Board/' + name for name in ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel'))
        assets = report['assets']
        if (not isinstance(assets, list) or len(set(assets)) != len(assets) or not required <= set(assets)
                or any(not isinstance(asset, str) or not asset.startswith('/Game/SkatePark/') for asset in assets)):
            return False
        return report['files'] == package_inventory(content, assets)
    except (OSError, ValueError, TypeError, KeyError):
        return False
