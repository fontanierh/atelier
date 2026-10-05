"""Regression for a successful job stranding steering in a foreground wait loop."""
import io
import json

import pytest

from atelier import board_toolguard as guard


def event(tool='Bash', **inputs):
    return {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'tool_input': inputs}


def test_completed_job_wait_cannot_block_for_fifteen_minutes():
    command = "until grep -q -E 'passed|Traceback|EXIT [1-9]' job.output; do sleep 5; done; cat job.output"
    request = event(command=command, timeout=900_000, description='Wait for check')
    result = guard.decision(request)['hookSpecificOutput']
    assert result['updatedInput'] == dict(request['tool_input'], timeout=30_000)
    assert request['tool_input']['timeout'] == 900_000
    assert 'run_in_background' in result['additionalContext']
    assert 'permissionDecision' not in result  # Existing permission/bypass rules still apply.


@pytest.mark.parametrize('timeout', [None, 900_000, 0, -1, float('inf'), True, '900000'])
def test_missing_or_invalid_timeout_is_bounded(timeout):
    request = event(command='cat job.output')
    if timeout is not None:
        request['tool_input']['timeout'] = timeout
    assert guard.decision(request)['hookSpecificOutput']['updatedInput']['timeout'] == 30_000


def test_native_background_compile_retains_its_guard_and_timeout():
    request = event(command='nice -n 10 uv run atelier build sandbox',
                    timeout=900_000, run_in_background=True)
    assert guard.decision(request) is None


@pytest.mark.parametrize('timeout', [1, 10_000, 30_000])
def test_already_bounded_foreground_commands_are_unchanged(timeout):
    assert guard.decision(event(command='cat job.output', timeout=timeout)) is None


def test_blocking_output_checks_return_control_without_cancelling_job():
    request = event('TaskOutput', task_id='existing-task', block=True, timeout=600_000)
    assert guard.decision(request)['hookSpecificOutput']['updatedInput'] == {
        'task_id': 'existing-task', 'block': True, 'timeout': 10_000,
    }
    assert guard.decision(event('TaskOutput', task_id='existing-task', block=False, timeout=600_000)) is None
    assert guard.decision(event('TaskOutput', task_id='existing-task'))['hookSpecificOutput']['updatedInput']['timeout'] == 10_000


def test_unrelated_tools_and_events_are_unchanged():
    assert guard.decision(event('Read', file_path='notes.md')) is None
    assert guard.decision(dict(event(command='sleep 60'), hook_event_name='PostToolUse')) is None
    assert guard.decision([]) is None
    assert guard.decision({'hook_event_name': 'PreToolUse', 'tool_input': None}) is None


def test_hook_cli_emits_valid_protocol_without_command_logging(monkeypatch, capsys):
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(event(command='private command', timeout=900_000))))
    assert guard.main() == 0
    output = capsys.readouterr()
    assert json.loads(output.out)['hookSpecificOutput']['updatedInput']['timeout'] == 30_000
    assert output.err == ''
    monkeypatch.setattr('sys.stdin', io.StringIO('not JSON'))
    assert guard.main() == 2
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'Invalid Claude tool-hook input\n'
