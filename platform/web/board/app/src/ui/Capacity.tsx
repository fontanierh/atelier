// Reservations and observations stay separate: a quiet machine can still have retained ownership.
import {useEffect, useRef, useState} from 'react';
import type {State} from '../api/schema';
import {clock, since} from '../lib/format';

type Status = State['capacity'];
type Snapshot = NonNullable<Status['snapshot']>;
type Job = Snapshot['records'][number];
type Vector = Snapshot['total'];

const gib = (mib: number) => `${(mib / 1024).toFixed(1)} GiB`;
const cpu = (millis: number) => `${(millis / 1000).toFixed(1)} CPU`;
const dimensions: {key: keyof Vector; label: string; format: (n: number) => string}[] = [
  {key: 'memory_mib', label: 'Memory', format: gib},
  {key: 'cpu_millis', label: 'CPU budget', format: cpu},
  {key: 'temp_mib', label: 'Temporary disk', format: gib},
  {key: 'io_slots', label: 'I/O', format: (n) => `${n} slots`},
  {key: 'gpu_mib', label: 'GPU memory', format: gib},
];

function Reservation({job, now, fresh}: {job: Job; now: number; fresh: boolean}) {
  const measured = fresh && job.measured_at != null && now - job.measured_at >= 0 && now - job.measured_at < 10;
  const uncertain = job.state === 'uncertain';
  return (
    <article className={`capacity-job${uncertain ? ' uncertain' : ''}`}>
      <div className="capacity-job-head"><strong>{job.purpose || job.id}</strong>
        <span className={`capacity-tag${uncertain ? ' warning' : ''}`}>{job.state === 'waiting' ? 'awaiting retry' : job.state === 'queued' ? 'ready' : job.state}</span></div>
      <p className="capacity-meta">{[job.owner, job.checkout, job.phase].filter(Boolean).join(' · ') || 'Owner not reported'}
        {' · '}first ready {since(job.first_ready, now)}</p>
      <p>{gib(job.resources.memory_mib)} {job.charged ? 'reserved' : 'requested'} · {cpu(job.resources.cpu_millis)}
        {' · '}{!job.charged ? 'no current process observation' : job.measured_memory_mib == null ? 'memory observation unavailable'
          : `${gib(job.measured_memory_mib)} observed${measured ? '' : ' (stale)'}`}</p>
      <p className="capacity-meta">{gib(job.resources.temp_mib)} temporary disk · {job.resources.io_slots} I/O slots · {gib(job.resources.gpu_mib)} GPU {job.charged ? 'reserved' : 'requested'}</p>
      {job.locks.length > 0 && <p className="capacity-locks">Locks {job.charged ? 'held' : 'required'}: {job.locks.map((lock, i) => <code key={i}>{lock}</code>)}</p>}
      {job.wait_reason && <p className="capacity-reason">{job.wait_reason}</p>}
      {uncertain && <p className="capacity-reason">Reservation retained until ownership is resolved.</p>}
      {job.ancestry_unknown && <p className="capacity-reason">Process ancestry is uncertain.</p>}
    </article>
  );
}

/** @cc [owner:fontanierh,label:correctness] capacity-display-is-not-admission
 * Stale, missing or unavailable broker observations MUST NOT be displayed as free capacity.
 * Totals MUST come from the broker, including reservations outside a truncated visible list.
 * Observed process memory MUST remain distinct from reserved capacity and host memory.
 */
export function Capacity({status, connected, bridge, serverTime}: {status?: Status; connected: boolean; bridge: boolean; serverTime?: number}) {
  const [, tick] = useState(0);
  const sampledAt = serverTime == null ? undefined : Math.max(serverTime, status?.checked_at ?? serverTime);
  const anchor = useRef({sampledAt, received: performance.now()});
  if (anchor.current.sampledAt !== sampledAt) anchor.current = {sampledAt, received: performance.now()};
  // Advance the board's clock between updates; the viewer's wall clock may be different.
  const now = (anchor.current.sampledAt ?? Date.now() / 1000) + (performance.now() - anchor.current.received) / 1000;
  useEffect(() => { const timer = setInterval(() => tick((n) => n + 1), 3000); return () => clearInterval(timer); }, []);
  const snapshot = status?.snapshot;
  const fresh = Boolean(connected && status?.fresh && snapshot && now - snapshot.observed_at >= 0 && now - snapshot.observed_at < 10);
  const legacy = status?.configuration === 'legacy';
  const full = snapshot?.mode === 'capacity' && snapshot.cutover;
  const title = legacy ? 'Legacy slots' : fresh ? full ? snapshot.recovering ? 'Capacity recovery' : 'Capacity admission'
    : 'Capacity bridge' : 'Capacity status unavailable';
  const active = snapshot?.records.filter((job) => job.charged || job.state === 'gated') || [];
  const waiting = snapshot?.records.filter((job) => job.state === 'queued' || job.state === 'waiting') || [];
  return (
    <section className={`card capacity-card${snapshot && !fresh ? ' capacity-stale' : ''}`} aria-labelledby="capacityHeading">
      <div className="capacity-heading"><h2 className="eyebrow" id="capacityHeading">Admission</h2>
        <span className={`capacity-tag${!legacy && !fresh ? ' warning' : ''}`}>{title}</span></div>
      {legacy ? <p>{bridge ? 'A capacity bridge holds all legacy lanes. Its broker is not visible to this board.'
        : 'Capacity admission is not configured for this board. Existing slot locks and guards apply.'}</p>
        : <p>{fresh ? full ? snapshot.recovering ? 'New grants are paused while compatibility or ownership is checked.'
          : 'The broker admits work within resource budgets and named locks. Legacy mutexes remain sealed.'
          : 'Broker reservations and all legacy lane locks are required. Extra concurrency is not enabled.'
          : status?.configuration === 'invalid' ? 'The board cannot read a valid capacity configuration.'
          : status?.availability === 'checking' || !status ? 'Checking the broker.'
          : 'No current broker observation. Capacity availability is unknown.'}</p>}
      {snapshot && <>
        {!fresh && <p className="capacity-warning">Last known state · observed {since(snapshot.observed_at, now)}. These figures are stale.</p>}
        {snapshot.recovering && <p className="capacity-warning">Recovery is holding new grants while compatibility and uncertain ownership are checked.</p>}
        <dl className="capacity-budget">
          {dimensions.map(({key, label, format}) => {
            const remaining = snapshot.total[key] - snapshot.reserve[key] - snapshot.charged_resources[key];
            return <div key={key}><dt>{label}</dt><dd><strong>{format(snapshot.charged_resources[key])}</strong> reserved
              <small>{format(Math.max(0, remaining))} unreserved · {format(snapshot.reserve[key])} held back · {format(snapshot.total[key])} total</small>
              {remaining < 0 && <small className="capacity-warning">Reservations exceed the configured budget</small>}</dd></div>;
          })}
        </dl>
        <p className="capacity-meta">GPU memory is part of unified memory. CPU is a scheduling budget, not a process limit. Per-job CPU, disk and GPU observations are unavailable.</p>
        <div className="capacity-section"><h3>{snapshot.charged_count} reservations · {snapshot.waiting_count} waiting</h3>
          {active.map((job) => <Reservation key={job.id} job={job} now={now} fresh={fresh} />)}
          {waiting.length > 0 && <h3>Queue</h3>}
          {waiting.map((job) => <Reservation key={job.id} job={job} now={now} fresh={fresh} />)}
          {snapshot.truncated && <p className="capacity-meta">Showing {snapshot.returned_records} of {snapshot.total_records} records. Totals include every reservation.</p>}
        </div>
        <p className="capacity-meta">Epoch {snapshot.epoch} · observed {clock(snapshot.observed_at)} · read-only status</p>
      </>}
    </section>
  );
}
