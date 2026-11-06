"""A stand-in for the `atelier claims` commands authority.py runs: task scopes and the publish-stage path check."""
import json


class FakeClaims:
    def __init__(self, scopes=(), covers=True):
        self.scopes, self.covers, self.checks = list(scopes), covers, []

    def __call__(self, command, **_):
        if command[4:6] == ['task', 'show']:
            claims = [{'state': 'active', 'items': [{'kind': 'scope', 'value': s} for s in self.scopes]}]
            return Result(0, json.dumps({'id': command[6], 'claims': claims}))
        if command[4] == 'check':
            self.checks.append(command)
            return Result(0 if self.covers else 1)
        raise AssertionError(f'unexpected command {command}')


class Result:
    def __init__(self, returncode, stdout=''):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ''
