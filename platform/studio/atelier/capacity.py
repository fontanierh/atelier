"""Pure capacity planning for shadow evaluation. This module cannot admit or launch work.

All quantities are integers: MiB for memory/disk, thousandths of a core for CPU. On this unified-
memory model, memory_mib includes GPU allocations; gpu_mib is an additional subset ceiling. The caller
supplies a snapshot; a plan is advice, never a lease or a replacement for the live render lock.
"""
from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path


@dataclass(frozen=True)
class Resources:
    memory_mib: int = 0
    cpu_millis: int = 0
    temp_mib: int = 0
    io_slots: int = 0
    gpu_mib: int = 0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value < 0:
                raise ValueError(f'{name} must be a nonnegative integer')
        if self.gpu_mib > self.memory_mib:
            raise ValueError('Unified GPU memory must also be included in memory_mib')

    def __add__(self, other):
        return Resources(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})

    def excess(self, limit):
        return [f.name for f in fields(self) if getattr(self, f.name) > getattr(limit, f.name)]


@dataclass(frozen=True)
class Request:
    id: str
    resources: Resources
    locks: tuple[str, ...] = ()
    ready_at: int = 0
    seconds: int = 300
    bypasses: int = 0
    performance: bool = False

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError('A request needs a nonempty id')
        if any(type(v) is not int or v < 0 for v in (self.ready_at, self.seconds, self.bypasses)):
            raise ValueError('Queue times, duration and bypass count must be nonnegative integers')
        if type(self.performance) is not bool:
            raise ValueError('performance must be a boolean')
        if (not isinstance(self.locks, (tuple, list)) or
                any(not isinstance(lock, str) or not lock for lock in self.locks) or
                len(set(self.locks)) != len(self.locks)):
            raise ValueError('Named locks must be unique nonempty strings')


def conflicts(request, holders, total, reserve):
    """@cc [owner:fontanierh,label:safety] all-resources-or-none
    A request MUST fit every resource dimension and named lock simultaneously. A performance
    request MUST wait for all holders to drain; existing performance holders exclude all requests.
    """
    used = reserve
    locks = set()
    for holder in holders:
        used += holder.resources
        locks.update(holder.locks)
    reasons = [f'capacity:{name}' for name in (used + request.resources).excess(total)]
    reasons.extend(f'lock:{name}' for name in sorted(set(request.locks) & locks))
    if holders and (request.performance or any(holder.performance for holder in holders)):
        reasons.append('performance window must drain first')
    return reasons


def replace(holder_id, replacement, holders, total, reserve):
    """Test an immediate atomic phase change, including its full named-lock set.

    Failure leaves the existing grant intact. It does not queue an upgrade. To wait, the caller
    must release every resource and lock, or have reserved the full continuity envelope up front.
    """
    if sum(holder.id == holder_id for holder in holders) != 1 or replacement.id != holder_id:
        raise ValueError('A phase change must replace exactly its own grant')
    return conflicts(replacement, [h for h in holders if h.id != holder_id], total, reserve)


def plan(total, reserve, holders, waiting, *, now):
    """@cc [owner:fontanierh,label:safety] shadow-only-capacity
    This planner MUST remain side-effect free. Advice MUST NOT be accepted as admission. Queued
    requests MUST hold no resources or locks, and a long waiter's first-ready time MUST be preserved.
    """
    if type(now) is not int or now < 0:
        raise ValueError('now must be a nonnegative integer timestamp')
    ids = [r.id for r in [*holders, *waiting]]
    if len(set(ids)) != len(ids):
        raise ValueError('Request ids must be unique; a queued request cannot also hold a grant')
    if reserve.excess(total):
        raise ValueError('Host reserve exceeds total capacity')
    # Existing overcommit is valid input: show denials rather than inventing free capacity.
    held_locks = [lock for holder in holders for lock in holder.locks]
    if len(held_locks) != len(set(held_locks)):
        raise ValueError('The snapshot has conflicting live named locks')
    ready = sorted((r for r in waiting if r.ready_at <= now), key=lambda r: (r.ready_at, r.id))
    protected = next((r for r in ready if r.bypasses >= 2), None)
    # Up to two short jobs can pass the oldest long job. A protected waiter then gets priority,
    # including a drain window when it cannot fit yet. This is conservative shadow policy.
    ranked = sorted(ready, key=lambda r: (r.id != protected.id if protected else False,
                                         r.seconds > 300, r.ready_at, r.id))
    virtual = list(holders)
    decisions = {}
    protected_blocked = False
    for request in ranked:
        reasons = conflicts(request, virtual, total, reserve)
        if protected_blocked:
            reasons.append(f'drain for oldest protected waiter: {protected.id}')
        if request is protected and reasons:
            protected_blocked = True
        decisions[request.id] = {'id': request.id, 'recommendation': 'wait' if reasons else 'would-admit',
                                 'reasons': reasons, 'ready_at': request.ready_at,
                                 'resources': asdict(request.resources), 'locks': list(request.locks)}
        if not reasons:
            virtual.append(request)
    for request in waiting:
        if request.id not in decisions:
            decisions[request.id] = {'id': request.id, 'recommendation': 'wait',
                                     'reasons': ['not ready'], 'ready_at': request.ready_at}
    return {'schema': 1, 'mode': 'shadow', 'admission': False,
            'decisions': [decisions[r.id] for r in waiting]}


def read_request(value):
    return Request(**{**value, 'resources': Resources(**value['resources'])})


def main(path, *, as_json=False, echo=print):
    snapshot = json.loads(Path(path).read_text())
    if snapshot.get('schema') != 1:
        raise ValueError('Unsupported capacity snapshot schema')
    report = plan(Resources(**snapshot['total']), Resources(**snapshot['reserve']),
                  [read_request(v) for v in snapshot['holders']],
                  [read_request(v) for v in snapshot['waiting']], now=snapshot['now'])
    if as_json:
        echo(json.dumps(report, indent=2))
    else:
        echo('Shadow advice only: the existing render lock still decides admission.')
        for decision in report['decisions']:
            echo(f"{decision['id']}: {decision['recommendation']}" +
                 (' — ' + '; '.join(decision['reasons']) if decision['reasons'] else ''))
    return 0
