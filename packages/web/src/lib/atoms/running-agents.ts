/**
 * Running agents atom — backed by GET /api/v1/agents/running.
 *
 * The atom is loaded eagerly on first use.  SSE updates are handled by
 * the main useEventStream hook; callers can also call refreshRunningAgentsAtom
 * to force a reload (e.g. after a project switch).
 */

import { atom } from 'jotai';
import type { ActiveAgentRowResponse } from '@kagan/shared-api-client';
import { apiClient } from '@/lib/api/client';

// ── Base state ───────────────────────────────────────────────────────────────

export interface RunningAgentsState {
  agents: ActiveAgentRowResponse[];
  loading: boolean;
  error: string | null;
}

const _runningAgentsBaseAtom = atom<RunningAgentsState>({
  agents: [],
  loading: false,
  error: null,
});

// ── Public read atom ─────────────────────────────────────────────────────────

export const runningAgentsAtom = atom((get) => get(_runningAgentsBaseAtom));

// ── Write atoms ──────────────────────────────────────────────────────────────

/** Set the loading state. */
export const setRunningAgentsLoadingAtom = atom(null, (_get, set, loading: boolean) => {
  set(_runningAgentsBaseAtom, (prev) => ({ ...prev, loading }));
});

/** Update with fresh agent list. */
export const setRunningAgentsAtom = atom(
  null,
  (_get, set, agents: ActiveAgentRowResponse[]) => {
    set(_runningAgentsBaseAtom, { agents, loading: false, error: null });
  },
);

/** Record an error from the last fetch. */
export const setRunningAgentsErrorAtom = atom(null, (_get, set, error: string) => {
  set(_runningAgentsBaseAtom, (prev) => ({ ...prev, loading: false, error }));
});

/**
 * Async write atom — triggers a fetch and updates state.
 * Call from effects or action handlers; never from render.
 */
export const refreshRunningAgentsAtom = atom(null, async (_get, set) => {
  set(_runningAgentsBaseAtom, (prev) => ({ ...prev, loading: true, error: null }));
  try {
    const response = await apiClient.getRunningAgents();
    set(_runningAgentsBaseAtom, { agents: response.agents, loading: false, error: null });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to fetch running agents';
    set(_runningAgentsBaseAtom, (prev) => ({ ...prev, loading: false, error: message }));
  }
});
