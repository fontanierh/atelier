"""Shared numeric and recovery-counter contract for reaction receipt checks."""
import math


ERROR_COUNTERS = ('forced', 'invalid_payloads', 'invalid_origins', 'failed_apply', 'failed_restore',
                  'recoveries', 'rejected_resets', 'rejected_recoveries', 'lethal_superseded')
def finite(value):
    return type(value) in (int, float) and math.isfinite(value)
