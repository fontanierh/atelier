"""Record a paid operation before submission and prevent accidental resubmission.

The operation writes its artifacts and returns public provenance fields. Failures are
uncertain until reconciled with the provider: this module never retries a paid call.
"""
from datetime import datetime, timezone
import json
from pathlib import Path


def run_once(path, metadata, operation):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = lambda: datetime.now(timezone.utc).isoformat()
    record = {**metadata, 'status': 'submitted', 'started_at': now()}
    # Exclusive creation also prevents two authoring processes from paying for the same revision.
    with path.open('x') as handle:
        handle.write(json.dumps(record, indent=2) + '\n')
        handle.flush()
    try:
        result = operation()
        record.update(result, status='done')
        return record
    except BaseException as error:
        # Provider messages can contain signed URLs or credentials. Keep only the error type.
        record.update(status='submission_uncertain', error_type=type(error).__name__)
        raise
    finally:
        record['finished_at'] = now()
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(path)
