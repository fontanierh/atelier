"""Record a paid operation before submission and prevent accidental resubmission.

The operation writes its artifacts and returns public provenance fields. Failures are
uncertain until reconciled with the provider: this module never retries a paid call.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re


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


def set_aside(path):
    """Rename path to <stem>.rejected-N<suffix>, so a record or its output is kept rather than overwritten when a call
    is paid for again. Returns the new path."""
    path = Path(path); n = 1
    while path.with_name(f'{path.stem}.rejected-{n}{path.suffix}').exists(): n += 1
    return path.rename(path.with_name(f'{path.stem}.rejected-{n}{path.suffix}'))


def redact(text):
    """An error message safe to print and record: signed download URLs removed."""
    return re.sub(r'https://\S+', '<URL omitted>', str(text))


def try_once(path, metadata, operation):
    """`run_once` for a batch that goes on: (record, None) when the call is done, else (None, why). why says that the
    path was recorded before (set the record aside to pay again) or names this call's error, with any URL left out;
    it is for printing only, never recorded. A failed call stays recorded as uncertain."""
    try:
        return run_once(path, metadata, operation), None
    except FileExistsError as error:
        if error.filename != str(path):
            return None, f'{type(error).__name__}: {error}'
        return None, f'already recorded in {Path(path).name}; set it aside to pay for this call again'
    except Exception as error:  # noqa: BLE001 - run_once has recorded it
        return None, redact(f'{type(error).__name__}: {error}')[:600]
