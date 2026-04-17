/**
 * Living kanban card vitals — dot + elapsed + truncated last log line.
 *
 * Sits under the task title. Silent (returns null) when the task is not
 * active so resting cards stay quiet. Respects prefers-reduced-motion.
 */

import { memo, useEffect, useRef } from 'react';
import { LiveRegion } from '@/components/a11y/live-region';
import { useReducedMotion } from '@/lib/a11y/use-reduced-motion';
import { useSessionStream } from '@/lib/hooks/use-session-stream';
import { cn } from '@/lib/utils';

interface CardPulseProps {
  /** Active session id; `null` puts the pulse into the queued/pending state. */
  sessionId: string | null | undefined;
  /** Task status from the board — drives whether we render and which state. */
  status: string;
  /** ISO timestamp the active session started at, if known. */
  startedAt?: string | null;
  /** Task title — included in the completion announcement. */
  taskTitle?: string;
  /** Opt-in liveness fallback when no active session is present. */
  isRunning?: boolean;
}

const ACTIVE_STATUS = 'IN_PROGRESS';
const PENDING_STATUSES = new Set(['BACKLOG']);
const ANNOUNCE_THROTTLE_MS = 60_000;

function formatElapsed(total: number): string {
  if (!Number.isFinite(total) || total < 0) return '0s';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function formatElapsedForSR(total: number): string {
  if (!Number.isFinite(total) || total < 0) return '0 seconds';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours} hours ${minutes} minutes`;
  if (minutes > 0) return `${minutes} minutes`;
  const seconds = total % 60;
  return `${seconds} seconds`;
}

function CardPulseImpl({
  sessionId,
  status,
  startedAt = null,
  taskTitle,
  isRunning,
}: CardPulseProps) {
  const upperStatus = status.toUpperCase();
  const isActive = upperStatus === ACTIVE_STATUS && (Boolean(sessionId) || Boolean(isRunning));
  const reducedMotion = useReducedMotion();
  const stream = useSessionStream(sessionId ?? null, {
    isActive,
    startedAt,
  });

  // Throttled elapsed-time announcement so screen readers don't fire every second.
  const lastAnnouncedAtRef = useRef(0);
  const completionAnnouncedRef = useRef(false);
  const prevActiveRef = useRef(isActive);

  useEffect(() => {
    if (!prevActiveRef.current) {
      completionAnnouncedRef.current = false;
    }
    prevActiveRef.current = isActive;
  }, [isActive]);

  if (!isActive) {
    if (PENDING_STATUSES.has(upperStatus)) {
      return (
        <div
          className="mt-0.5 flex items-center gap-1.5 text-[10px] leading-4 text-[color:var(--muted-foreground)]"
          data-testid="card-pulse-queued"
        >
          <span
            role="status"
            aria-label="Queued"
            className="size-1.5 rounded-full bg-[color:var(--kagan-rail-idle)]"
          />
          <span>Queued…</span>
        </div>
      );
    }
    // Resting state: completed / cancelled / review / done — stay silent.
    return null;
  }

  const elapsedLabel = formatElapsed(stream.elapsedSeconds);

  // Announce completion exactly once when the stream flips out of running.
  const terminalStatus = stream.status === 'completed' || stream.status === 'failed' || stream.status === 'cancelled';
  let message: string | null = null;
  if (terminalStatus && !completionAnnouncedRef.current) {
    const verb = stream.status === 'completed' ? 'completed' : stream.status === 'failed' ? 'failed' : 'cancelled';
    message = taskTitle ? `Task '${taskTitle}' ${verb}` : `Task ${verb}`;
    completionAnnouncedRef.current = true;
  } else {
    const now = Date.now();
    if (now - lastAnnouncedAtRef.current >= ANNOUNCE_THROTTLE_MS) {
      lastAnnouncedAtRef.current = now;
      message = `Running for ${formatElapsedForSR(stream.elapsedSeconds)}`;
    }
  }

  return (
    <div
      className="mt-0.5 flex items-center gap-1.5 text-[10px] leading-4 text-[color:var(--muted-foreground)]"
      data-testid="card-pulse-running"
    >
      <span
        role="status"
        aria-label="Running"
        className={cn(
          'size-1.5 shrink-0 rounded-full bg-[color:var(--kagan-rail-warning)]',
          !reducedMotion && 'animate-pulse',
        )}
      />
      <span className="font-code tabular-nums text-[color:var(--foreground)]">{elapsedLabel}</span>
      {stream.lastLog ? (
        <span className="line-clamp-1 min-w-0 truncate text-[color:var(--muted-foreground)]" title={stream.lastLog}>
          {stream.lastLog}
        </span>
      ) : null}
      <LiveRegion message={message} />
    </div>
  );
}

export const CardPulse = memo(CardPulseImpl);
CardPulse.displayName = 'CardPulse';
