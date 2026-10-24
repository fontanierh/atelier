"""Selected source-library identities for region build boundaries, without DCC imports."""
import json
from pathlib import Path
import tempfile
from atelier.atomic_files import managed_temporary_parent


def models(library, prefix):
    """The exact model membership and checksum values consumed by a region verifier."""
    files = json.loads(Path(library).read_text())['files']
    selected = {key: {'sha256': entry['sha256']} for key, entry in files.items()
                if key.startswith(prefix) and key.endswith('.glb')}
    if not selected:
        raise ValueError(f'{Path(library).name} lists no models under {prefix}')
    return selected


def publish(library, output, prefix):
    """@cc [owner:fontanierh,label:correctness] region-source-registry-boundary
    Publish every selected model key and consumed checksum, including additions/removals.
    Unrelated registry entries MUST NOT change these bytes. Production verification MUST read
    this declared snapshot, never silently fall back to the whole registry on a missing snapshot.
    Model and provenance bytes MUST remain separate inputs of the consuming action.
    Managed calls MUST use only their existing owned temporary scope on the same
    filesystem; unmanaged calls retain sibling temporaries and identical JSON bytes.
    """
    value = {'files': models(library, prefix)}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=managed_temporary_parent(output), prefix='.source-registry-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, sort_keys=True, separators=(',', ':'))
            stream.write('\n')
            stream.close()
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
