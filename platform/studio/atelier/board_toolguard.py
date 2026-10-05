"""Bound foreground Claude tool calls so steering can reach the next model turn.

Native background jobs retain their original command, timeout, and render guard.
This hook only changes future tool inputs; it never signals a running process.
"""
import json
import math
import sys


FOREGROUND_MS = 30_000
POLL_MS = 10_000


def decision(event):
    if not isinstance(event, dict) or event.get('hook_event_name') != 'PreToolUse':
        return None
    original = event.get('tool_input')
    if not isinstance(original, dict):
        return None
    tool = event.get('tool_name')
    if tool == 'Bash' and not original.get('run_in_background', False):
        limit = FOREGROUND_MS
    elif tool == 'TaskOutput' and original.get('block', True):
        limit = POLL_MS
    else:
        return None
    timeout = original.get('timeout')
    if (isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
            and math.isfinite(timeout) and 0 < timeout <= limit):
        return None
    updated = dict(original, timeout=limit)
    return {'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'updatedInput': updated,
        'additionalContext': (
            f'Atelier responsiveness guard bounded this {tool} call to {limit // 1000} seconds. '
            'Use Bash run_in_background for lengthy or uncertain jobs. Consume native completion '
            'notifications and check output in bounded calls; never poll in a foreground sleep loop. '
            'Reply to steering and board requests promptly and update the user at least every 60 seconds.'
        ),
    }}


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        print('Invalid Claude tool-hook input', file=sys.stderr)
        return 2
    result = decision(event)
    if result is not None:
        print(json.dumps(result))
    return 0
