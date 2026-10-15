"""Private download worker; the parent owns the hard deadline and all publication."""
import asyncio
import json
from pathlib import Path
import sys

from . import artifact_remote as remote
from .artifact_bundle import BundleError


def main(request_file):
    result = None
    try:
        request = json.loads(Path(request_file).read_bytes())
        result = Path(request['result'])
        downloaded = asyncio.run(remote._transfer(
            request['base'], request['key'], Path(request['trust']), Path(request['directory']),
            request['timeout'], remote.Progress(lambda message: print(message, flush=True))))
        outcome, code = {'downloaded_bytes': downloaded}, 0
    except (remote.RemoteError, BundleError) as error:
        outcome, code = {'error': str(error), 'missing': isinstance(error, remote.RemoteMiss)}, 1
    except Exception:
        outcome, code = {'error': 'Artifact download failed'}, 1
    if result is not None:
        result.write_text(json.dumps(outcome))
    return code


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
