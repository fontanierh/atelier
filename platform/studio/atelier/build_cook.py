"""Explicit UE 5.8 cook experiments and bounded observations; default cooking is unchanged."""
from dataclasses import replace
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid


class CookMode(str, Enum):
    DEFAULT = 'default'
    FULL = 'modern-full'
    INCREMENTAL = 'modern-incremental'


def apply(ctx, steps):
    """Apply the invocation's package-only mode on every fresh recipe load."""
    from .build import UnrealPackage
    mode = CookMode(getattr(ctx, 'cook_mode', CookMode.DEFAULT))
    if mode is CookMode.DEFAULT:
        from .build_checkpoints import configured
        if configured(ctx) is None:
            return steps
        # Checkpoint builds always use dependency-tracked cooking. The unconfigured platform
        # template keeps its historical command shape; no second production path is advertised.
        mode = CookMode.INCREMENTAL
    for step in steps:
        step.commands = [replace(command, cook_mode=mode) if isinstance(command, UnrealPackage) else command
                         for command in step.commands]
    return steps


def measurement_reason(value):
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 300
                              or any(ord(c) < 32 for c in value)):
        raise ValueError('Cook reason must be a short single line')
    return value


def forced(ctx, step, force):
    from .build import UnrealPackage
    if getattr(ctx, 'checkpoint_settings', None) is not None:
        return bool(force and step.name == getattr(ctx, 'checkpoint_force_task', None))
    return bool(force and (getattr(ctx, 'cook_mode', CookMode.DEFAULT) is CookMode.DEFAULT
                           or any(isinstance(command, UnrealPackage) for command in step.commands)))


def validate_force(ctx, force):
    if force and getattr(ctx, 'cook_mode', CookMode.DEFAULT) is not CookMode.DEFAULT:
        reason = getattr(ctx, 'cook_reason', None)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 300 or any(ord(c) < 32 for c in reason):
            raise SystemExit('Experimental forced cooking requires a short --cook-reason')


def validate_selection(ctx, selected, *, touch=False):
    from .build import UnrealPackage
    if getattr(ctx, 'cook_mode', CookMode.DEFAULT) is CookMode.DEFAULT:
        return
    packages = [step for step in selected if any(isinstance(command, UnrealPackage) for command in step.commands)]
    if touch or not packages:
        raise SystemExit('Experimental cook mode requires a selected package command and cannot be touched')
    if any(not step.heavy for step in packages):
        raise SystemExit('Experimental cooking requires the normal heavy compile guard lifecycle')


def options(mode, root):
    mode = CookMode(mode)
    if mode is CookMode.DEFAULT:
        return []
    version = json.loads((Path(root) / 'Engine/Build/Build.version').read_text())
    if (version.get('MajorVersion'), version.get('MinorVersion')) != (5, 8):
        raise ValueError('Experimental modern cooking is source-verified only for UE 5.8')
    flag = '-fullcook' if mode is CookMode.FULL else '-cookincremental'
    return [f'-AdditionalCookerOptions={flag} -Cook.DependencyTracking=1']


MAX_LINE = 16384
MAX_BYTES = 128 * 1024**2
POLL_BYTES = 256 * 1024
CATEGORY = re.compile(r'(?:^|\s|\])LogCook:\s*(?:(?:Display|Warning|Error):\s*)?(.*)$')
TIME = re.compile(r'(Build|Cook|Stage|Package|Archive|BuildCookRun) (?:command )?time: ([0-9]+(?:\.[0-9]+)?) s$')
STATS = re.compile(r'Packages Cooked: (\d+),(?: Packages Incrementally Skipped: (\d+),)? Packages Skipped by Platform: (\d+), Total Packages: (\d+)$')


class Observation:
    def __init__(self, mode):
        self.mode = CookMode(mode)
        self.enabled = []
        self.decisions = []
        self.counts = []
        self.cooker_seconds = []
        self.timings = {name: [] for name in ('Build', 'Cook', 'Stage', 'Package', 'Archive', 'BuildCookRun')}
        self.completed = 0
        self.diagnostics = []

    def invalid(self, reason):
        if reason not in self.diagnostics:
            self.diagnostics.append(reason)

    def add(self, values, value):
        if len(values) < 2:
            values.append(value)
        if len(values) > 1:
            self.invalid('repeated or ambiguous cook observations')

    def line(self, text):
        text = text.strip()
        if len(text) > MAX_LINE:
            self.invalid('oversized log line')
            return
        if '********** COOK COMMAND COMPLETED **********' in text:
            self.completed += 1
        timing = TIME.search(text)
        if timing:
            value = float(timing[2])
            if math.isfinite(value):
                self.add(self.timings[timing[1]], value)
            else:
                self.invalid('invalid UAT duration')
        elif re.search(r'(Build|Cook|Stage|Package|Archive|BuildCookRun) (?:command )?time:', text):
            self.invalid('malformed UAT duration')
        match = CATEGORY.search(text)
        if not match:
            return
        message = match[1]
        if message.startswith('INCREMENTAL COOK DEPENDENCIES:'):
            if message == 'INCREMENTAL COOK DEPENDENCIES: Enabled. Incremental Cook Dependencies are enabled in Editor.ini:[CookSettings]:LegacyIterative=false.':
                self.add(self.enabled, True)
            else:
                self.add(self.enabled, False)
                self.invalid('modern dependency tracking disabled or unrecognized')
        elif message.startswith('FULL COOK:'):
            if '-Cook.DependencyTracking=0' in message or 'Dependencies are disabled' in message:
                reason = 'dependencies-disabled'
                self.invalid('modern dependency tracking disabled')
            elif message.startswith('FULL COOK: -forcerecook=true (or an equivalent) was specified.'):
                reason = 'explicit-full'
            elif re.match(r'FULL COOK: -cookincremental was specified, but .+ settings have changed and all previously cooked packages are invalidated\.', message):
                reason = 'settings-changed'
            elif message.startswith('FULL COOK: Incremental Cooks are disabled by default'):
                reason = 'default-full'
            else:
                reason = 'unrecognized-full'
                self.invalid('unrecognized full-cook decision')
            self.add(self.decisions, dict(mode='full', reason=reason))
        elif message.startswith('INCREMENTAL COOK:'):
            if message.startswith('INCREMENTAL COOK: Global settings are still valid. Keeping previously cooked packages for platform '):
                self.add(self.decisions, dict(mode='incremental', reason='settings-valid'))
            else:
                self.invalid('legacy or unrecognized incremental decision')
        elif message == 'Could not load PreviousAssetRegistry, which is unexpected when cooking incrementally. Abandoning incremental cook and executing a full cook.':
            if len(self.decisions) == 1 and self.decisions[0]['mode'] == 'incremental':
                self.decisions[0] = dict(mode='full', reason='missing-previous-registry')
            else:
                self.invalid('unexpected previous-registry fallback')
        elif 'its generated packages will not be removed from cook results. Run a full cook to remove them.' in message:
            self.invalid('retired generated packages require a full cook')
        elif message.startswith('Packages Cooked:'):
            match = STATS.fullmatch(message)
            if not match:
                self.invalid('malformed package statistics')
            else:
                values = [int(value) if value is not None else None for value in match.groups()]
                if any(value is not None and value > 2**63 - 1 for value in values):
                    self.invalid('package statistics exceed bound')
                elif (values[0] > values[3] or values[2] > values[3]
                      or values[1] is not None and values[0] + values[1] > values[3]):
                    self.invalid('inconsistent package statistics')
                else:
                    self.add(self.counts, dict(cooked=values[0], incrementally_skipped=values[1],
                                              skipped_by_platform=values[2], total=values[3]))
        elif message.startswith('Cook by the book total time in tick '):
            match = re.fullmatch(r'Cook by the book total time in tick ([0-9.]+)s total time ([0-9.]+)', message)
            if match:
                try:
                    value = float(match[2])
                    if not math.isfinite(value):
                        raise ValueError
                    self.add(self.cooker_seconds, value)
                except ValueError:
                    self.invalid('malformed cooker duration')
            else:
                self.invalid('malformed cooker duration')
        elif 'legacy iterative cook mode' in message.lower() or 'LegacyIterative incremental cooks do not robustly support' in message:
            self.invalid('legacy incremental fallback')
        if len(self.enabled) > 1 or len(self.decisions) > 1 or len(self.counts) > 1 or len(self.cooker_seconds) > 1:
            self.invalid('repeated or ambiguous cook observations')
        if any(len(values) > 1 for values in self.timings.values()):
            self.invalid('repeated or ambiguous UAT durations')

    def report(self, *, success):
        decision = self.decisions[0] if len(self.decisions) == 1 else None
        modern = len(self.enabled) == 1 and self.enabled[0]
        completed = self.completed == 1 and len(self.timings['Cook']) == 1
        valid = bool(success and modern and completed and decision and not self.diagnostics)
        if self.mode is CookMode.FULL and (not decision or decision['reason'] != 'explicit-full'):
            valid = False
        if self.mode is CookMode.INCREMENTAL and (not decision or decision['reason'] not in ('settings-valid', 'settings-changed', 'missing-previous-registry')):
            valid = False
        counts = self.counts[0] if len(self.counts) == 1 else dict(cooked=None, incrementally_skipped=None,
                                                                skipped_by_platform=None, total=None)
        if decision and decision['mode'] == 'full' and counts['incrementally_skipped'] not in (None, 0):
            self.invalid('full cook reported incremental skips')
            valid = False
        return dict(schema=1, requested=self.mode.value, validated=valid, command_succeeded=bool(success),
                    modern_dependencies=self.enabled[0] if len(self.enabled) == 1 else None,
                    zen_store=True if modern else None, decision=decision, counts=counts,
                    reuse_observed=(counts['incrementally_skipped'] > 0 if counts['incrementally_skipped'] is not None
                                    and decision and decision['mode'] == 'incremental' else None),
                    cook_completed=completed, cooker_seconds=self.cooker_seconds[0] if len(self.cooker_seconds) == 1 else None,
                    uat_seconds={name.lower(): values[0] if len(values) == 1 else None for name, values in self.timings.items()},
                    diagnostics=list(self.diagnostics))


class Observer:
    """@cc [owner:fontanierh,label:correctness] experimental-modern-cook-evidence
    An experimental cook MUST require positive modern dependency tracking and one completed,
    unambiguous cook before certification. Legacy/disabled tracking, changed/truncated log identity,
    unsupported decisions and malformed evidence MUST refuse. Valid full invalidation MUST remain
    full, never be reported as observed reuse. Missing counters/timings MUST remain unknown.
    """
    def __init__(self, folder, mode, *, on_line=None):
        self.path = Path(folder) / 'stdout.log'
        self.report_path = Path(folder) / 'cook-observation.json'
        self.observation = Observation(mode)
        self.strict = CookMode(mode) is not CookMode.DEFAULT
        self.fd = None
        self.pin = None
        self.offset = 0
        self.buffer = b''
        self.pid = None
        self.reason = None
        self.invocation = uuid.uuid4().hex
        self.digest = hashlib.sha256()
        self.on_line = on_line

    def poll(self, pid):
        if self.pid is None:
            self.pid = pid
        elif self.pid != pid:
            raise RuntimeError('Cook observer child identity changed')
        try:
            self.read()
        except (OSError, ValueError) as error:
            self.observation.invalid('cook log is unavailable or changed')
            self.buffer = b''
            if self.strict:
                raise RuntimeError('Experimental cook log observation failed') from error
        if self.strict and self.observation.diagnostics:
            raise RuntimeError('Experimental cook refused: ' + '; '.join(self.observation.diagnostics))

    def read(self):
        if self.fd is None:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        actual = self.path.lstat()
        pin = (info.st_dev, info.st_ino)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or pin != (actual.st_dev, actual.st_ino) or self.pin not in (None, pin)
                or not self.offset <= info.st_size <= MAX_BYTES):
            raise ValueError('Cook log identity or bounds changed')
        self.pin = pin
        data = os.read(self.fd, min(POLL_BYTES, info.st_size - self.offset))
        self.offset += len(data)
        self.digest.update(data)
        self.buffer += data
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            decoded = line.decode('utf-8', errors='strict')
            self.observation.line(decoded)
            if self.on_line is not None:
                self.on_line(decoded)
        if len(self.buffer) > MAX_LINE:
            raise ValueError('Cook log line exceeds bound')
        return bool(data)

    def finish(self, *, success):
        try:
            if self.pid is not None:
                while self.read():
                    pass
                if self.buffer:
                    self.observation.invalid('truncated final log line')
                # One final bounded verification catches in-place rewrites between polls.
                before = os.fstat(self.fd)
                verified = hashlib.sha256()
                for offset in range(0, self.offset, 1024**2):
                    verified.update(os.pread(self.fd, min(1024**2, self.offset - offset), offset))
                after = os.fstat(self.fd)
                visible = self.path.lstat()
                if ((visible.st_dev, visible.st_ino) != self.pin or after.st_nlink != 1
                        or verified.digest() != self.digest.digest() or before.st_size != self.offset
                        or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                           (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                    self.observation.invalid('cook log changed during or after observation')
            else:
                self.observation.invalid('no admitted child observation')
        except (OSError, ValueError):
            self.observation.invalid('cook log is unavailable or changed')
        finally:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
        report = self.observation.report(success=success)
        report.update(reason=self.reason, invocation_id=self.invocation, child_pid=self.pid,
                      log_sha256=self.digest.hexdigest(), observed_bytes=self.offset)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.cook-observation-', dir=self.report_path.parent)
            with os.fdopen(fd, 'w') as stream:
                stream.write(json.dumps(report, indent=2) + '\n')
            os.replace(temporary, self.report_path)
        except OSError:
            if self.strict and success:
                raise RuntimeError('Experimental cook observation could not be retained') from None
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
        if self.strict and success and not report['validated']:
            raise RuntimeError('Experimental cook lacks complete supported modern evidence; no certification')
        return report
