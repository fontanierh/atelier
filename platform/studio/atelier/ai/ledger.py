"""Record a paid operation before submission and prevent accidental resubmission.

The operation writes its artifacts and returns public provenance fields. Failures are
uncertain until reconciled with the provider: this module never retries a paid call.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re


def begin(path, metadata):
    """@cc [owner:fontanierh,label:correctness] exclusive-paid-submission
    A durable submitted record MUST exist before a paid operation starts. An existing record at
    this path, including an uncertain one, MUST prevent a second submission. Ephemeral CI runners
    MUST additionally use persistent receipts and a cross-run submission guard.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {**metadata, 'status': 'submitted', 'started_at': datetime.now(timezone.utc).isoformat()}
    # Exclusive creation also prevents two authoring processes from paying for the same revision.
    with path.open('x') as handle:
        handle.write(json.dumps(record, indent=2) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    return record


def finish(path, *, status, result=None):
    """Complete a split-phase operation such as a CI action; keep uncertain submissions visible."""
    if status not in ('done', 'submission_uncertain'):
        raise ValueError('Invalid paid-operation terminal status')
    path = Path(path)
    record = json.loads(path.read_text())
    if record.get('status') != 'submitted':
        raise ValueError('Only a submitted operation can be completed')
    record.update(result or {}, status=status, finished_at=datetime.now(timezone.utc).isoformat())
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as handle:
        handle.write(json.dumps(record, indent=2) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return record


def run_once(path, metadata, operation):
    begin(path, metadata)
    try:
        details = operation()
    except BaseException as error:
        # Provider messages can contain signed URLs or credentials. Keep only the error type.
        try:
            finish(path, status='submission_uncertain', result={'error_type': type(error).__name__})
        except BaseException as receipt_error:
            # The submitted receipt remains evidence even if the disk fails during finalization.
            error.add_note(f'Could not finalize paid-operation receipt: {type(receipt_error).__name__}')
        raise
    return finish(path, status='done', result=details)


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
