"""Owned upload worker; request and result live in the caller's private scratch directory."""
import json
from pathlib import Path
import sys

from .artifact_upload import UploadError, _execute


def main():
    request = json.loads(Path(sys.argv[1]).read_bytes())
    result = Path(request.pop('result'))
    try:
        receipt = _execute(request.pop('directory'), request.pop('trust'), request.pop('profile'), **request)
        result.write_text(json.dumps({'receipt': receipt}))
        return 0
    except UploadError as error:
        result.write_text(json.dumps({'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
