import type { SessionItemResponse } from '@kagan/shared-api-client';

/**
 * Closed union of session kinds the UI knows how to render.
 *
 * The wire field `SessionItemResponse.type` is typed as `string` because it's
 * generated from a free-form server enum. Any time UI code branches on it,
 * narrow through {@link sessionKind} so the branch is exhaustive at the type
 * level and unknown values surface as `null` rather than silently falling
 * through one of the branches.
 */
export type SessionKind = 'orchestrator' | 'general' | 'task';

const KNOWN: ReadonlySet<SessionKind> = new Set(['orchestrator', 'general', 'task']);

export function sessionKind(session: Pick<SessionItemResponse, 'type'>): SessionKind | null {
  return (KNOWN as Set<string>).has(session.type) ? (session.type as SessionKind) : null;
}

export const SESSION_KIND_LABEL: Record<SessionKind, string> = {
  orchestrator: 'Orchestrator',
  general: 'General',
  task: 'Task',
};

/** Short uppercase badge label used in lists / chips. */
export const SESSION_KIND_BADGE: Record<SessionKind, string> = {
  orchestrator: 'ORCH',
  general: 'GEN',
  task: 'TASK',
};
