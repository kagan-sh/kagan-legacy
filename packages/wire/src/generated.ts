/* eslint-disable */
/**
 * Auto-generated from kagan.wire JSON Schema.
 * DO NOT MODIFY BY HAND. Run `bash generate.sh` to regenerate.
 */

/**
 * Live session metadata associated with a task.
 */
export interface WireTaskActiveSession {
  id: string;
  status: string;
  mode: string;
  agent_backend: string;
  started_at: string;
}

export interface WireReviewVerdict {
  criterion_index: number;
  verdict: 'PASS' | 'FAIL';
  reason: string;
}

/**
 * Serialisable representation of a Kagan task.
 */
export interface WireTask {
  id: string;
  title: string;
  description?: string;
  /** Value of TaskStatus enum, e.g. 'BACKLOG'. */
  status: string;
  /** Name of Priority enum, e.g. 'HIGH'. */
  priority: string;
  /** Value of WorkMode enum, e.g. 'AUTO'. */
  execution_mode: string;
  base_branch?: string | null;
  acceptance_criteria?: string[];
  agent_backend?: string | null;
  launcher?: string | null;
  review_approved?: boolean;
  review_verdicts?: WireReviewVerdict[];
  updated_at?: string | null;
  last_event_at?: string | null;
  has_workspace?: boolean;
  review_running?: boolean;
  active_session?: WireTaskActiveSession | null;
}

/**
 * Serialisable representation of a Kagan project.
 */
export interface WireProject {
  id: string;
  name: string;
  active?: boolean;
}

/**
 * Serialisable representation of a Kagan session.
 */
export interface WireSession {
  id: string;
  task_id: string;
  status: string;
  mode: string;
  created_at: string;
}

/**
 * Serialisable representation of a Kagan event.
 */
export interface WireEvent {
  id: string;
  session_id: string;
  type: string;
  payload?: Record<string, unknown>;
  created_at: string;
}

/**
 * Generic wrapper for all wire responses.
 *
 * ``ok=True`` → ``data`` carries payload.
 * ``ok=False`` → ``error`` carries a human-readable message.
 */
export interface WireEnvelope {
  ok?: boolean;
  data?: unknown | null;
  error?: string | null;
}

/**
 * Base request envelope shared by all wire calls.
 */
export interface WireRequest {
  version?: string;
  trace_id?: string;
}

export type WireResponse = WireEnvelope;
