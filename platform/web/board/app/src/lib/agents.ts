// What the board says about an agent: free for work, waiting on you, quiet.
import type {Agent, State} from '../api/schema';
import {idleLine, QUIET} from './format';

/** Waiting on the operator: the agent has an open operator task. */
export const isWaiting = (a: Agent | undefined, state: State | null, dismissed: ReadonlySet<number>) =>
  Boolean(a) && (state?.tasks || []).some((t) => t.agent === a!.agent && !dismissed.has(t.id));

export const quietFor = (a: Agent | undefined, now: number) =>
  a?.session === 'idle' && a.session_since ? Math.max(0, now - a.session_since) : 0;

/** Free for work: listening, not waiting on the operator, and either with no current task (its status line empty or
 *  exactly "idle") or with its own session quiet for QUIET seconds, whatever the line says. A busy session never is. */
export function isFree(a: Agent | undefined, state: State | null, dismissed: ReadonlySet<number>): boolean {
  if (!a || a.stop || !a.listening || a.delivery_error || isWaiting(a, state, dismissed) || a.session === 'busy') return false;
  // Render work in flight (a Holding or Waiting line, or a live lock) waits with the session idle, so quiet is not free.
  return idleLine(a) || (!a.engaged && quietFor(a, state?.time ?? Date.now() / 1000) >= QUIET);
}
