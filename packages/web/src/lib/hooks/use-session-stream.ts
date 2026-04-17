/**
 * Per-card SSE subscription — scoped to a single session id.
 *
 * Reuses the global `kagan:session-event` CustomEvent bus dispatched from
 * `useEventStream` (see lib/hooks/use-event-stream.ts). No new network
 * connection is opened: this hook filters the existing stream.
 *
 * Active subscriptions: monitor via React DevTools Profiler; alert if > ~20
 * concurrent. A no-op (zero listeners, zero state) when `sessionId` is null
 * or when `isActive` is false — Andrew Ng's rule: only running cards pay.
 */

import { useEffect, useRef, useState } from 'react';
import { renderEvent } from '@/lib/api/event-rendering';
import type { WireEvent } from '@/lib/api/types';

export type StreamedStatus =
  | 'running'
  | 'queued'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface SessionStreamState {
  /** Seconds elapsed since the session started; 0 when idle. */
  elapsedSeconds: number;
  /** Most recent human-readable log line, truncated. null while silent. */
  lastLog: string | null;
  /** Most recent lifecycle signal observed over SSE. */
  status: StreamedStatus | null;
}

interface UseSessionStreamOptions {
  /** Skip subscription when false, regardless of sessionId. */
  isActive: boolean;
  /** ISO timestamp used as the origin for elapsed-time math. */
  startedAt?: string | null;
}

const EMPTY_STATE: SessionStreamState = {
  elapsedSeconds: 0,
  lastLog: null,
  status: null,
};

const MAX_LOG_CHARS = 60;

/** Extract a short, display-ready summary line from an SSE event. */
function summarizeEvent(event: WireEvent): { text: string; status: StreamedStatus | null } {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const renderable = renderEvent(event.type, payload, event.id, event.session_id ?? '');
  let text = '';
  let status: StreamedStatus | null = null;

  if (event.type === 'AGENT_COMPLETED') status = 'completed';
  else if (event.type === 'AGENT_FAILED') status = 'failed';
  else if (
    event.type === 'OUTPUT_CHUNK' ||
    event.type === 'TOOL_CALL_START' ||
    event.type === 'TOOL_CALL_UPDATE' ||
    event.type === 'AGENT_STATUS'
  ) {
    status = 'running';
  }

  if (renderable) {
    const bodyLine = renderable.body.split('\n').find((line) => line.trim().length > 0);
    text = bodyLine?.trim() ?? renderable.title;
  } else {
    text = event.type;
  }

  if (text.length > MAX_LOG_CHARS) {
    text = `${text.slice(0, MAX_LOG_CHARS - 1).trimEnd()}…`;
  }

  return { text, status };
}

function computeElapsed(startedAt: string | null | undefined): number {
  if (!startedAt) return 0;
  const start = Date.parse(startedAt);
  if (!Number.isFinite(start)) return 0;
  const delta = Math.floor((Date.now() - start) / 1000);
  return delta < 0 ? 0 : delta;
}

/**
 * Subscribe to live session activity for a single task's active session.
 *
 * - Opens **zero** listeners when `isActive` is false or `sessionId` is null.
 * - Coalesces incoming SSE events into a 1 Hz state update — the DOM never
 *   re-renders faster than once per second no matter how chatty the agent is.
 * - Automatically unsubscribes on unmount or when `sessionId` / `isActive`
 *   flips (e.g. the task transitions out of IN_PROGRESS).
 */
export function useSessionStream(
  sessionId: string | null | undefined,
  options: UseSessionStreamOptions,
): SessionStreamState {
  const { isActive, startedAt } = options;
  const [state, setState] = useState<SessionStreamState>(EMPTY_STATE);

  // Latest pending log line captured between ticks.
  const pendingLogRef = useRef<string | null>(null);
  const pendingStatusRef = useRef<StreamedStatus | null>(null);

  useEffect(() => {
    if (!isActive || !sessionId) {
      // Guido's rule: make the no-op explicit. No listener, no interval,
      // no lingering state.
      setState(EMPTY_STATE);
      pendingLogRef.current = null;
      pendingStatusRef.current = null;
      return;
    }

    // Seed elapsed immediately so the dot appears alive on mount.
    setState((prev) => ({
      ...prev,
      elapsedSeconds: computeElapsed(startedAt),
      status: prev.status ?? 'running',
    }));

    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as
        | { task_id?: string; event?: WireEvent }
        | undefined;
      const wireEvent = detail?.event;
      if (!wireEvent) return;
      if (wireEvent.session_id && wireEvent.session_id !== sessionId) return;

      const summary = summarizeEvent(wireEvent);
      if (summary.text) pendingLogRef.current = summary.text;
      if (summary.status) pendingStatusRef.current = summary.status;
    };

    window.addEventListener('kagan:session-event', handler);

    // 1 Hz tick: one render per second, no matter the event rate.
    const tick = window.setInterval(() => {
      const pendingLog = pendingLogRef.current;
      const pendingStatus = pendingStatusRef.current;
      pendingLogRef.current = null;
      pendingStatusRef.current = null;
      setState((prev) => {
        const nextElapsed = computeElapsed(startedAt);
        const nextLog = pendingLog ?? prev.lastLog;
        const nextStatus = pendingStatus ?? prev.status ?? 'running';
        if (
          prev.elapsedSeconds === nextElapsed &&
          prev.lastLog === nextLog &&
          prev.status === nextStatus
        ) {
          return prev;
        }
        return {
          elapsedSeconds: nextElapsed,
          lastLog: nextLog,
          status: nextStatus,
        };
      });
    }, 1000);

    return () => {
      window.removeEventListener('kagan:session-event', handler);
      window.clearInterval(tick);
      pendingLogRef.current = null;
      pendingStatusRef.current = null;
    };
  }, [sessionId, isActive, startedAt]);

  return state;
}
