/**
 * chat-page.tsx
 *
 * Conversation surface — ws-head + chat thread + composer.
 * Session selection is owned by the shell sidebar; this page is purely
 * the conversation surface for the selected session.
 */

import { useMemo } from 'react';
import { useParams, Link } from 'react-router';
import { useAtomValue } from 'jotai';
import { ExternalLink, MoreHorizontal, MessageSquareText } from 'lucide-react';
import { tasksAtom } from '@/lib/atoms/board';
import { popoverTaskIdAtom, shellPopoverAtom } from '@/lib/atoms/shell';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { sessionKind, SESSION_KIND_BADGE } from '@/lib/sessions/kind';
import { OrchestratorSessionBody } from '@/components/session/OrchestratorSessionBody';
import { useSetAtom } from 'jotai';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import type { WireTask } from '@kagan/shared-api-client';
import { cn } from '@/lib/utils';

// ── Status helpers ────────────────────────────────────────────────────────────

type CanonicalStatus = 'Backlog' | 'In Progress' | 'Review' | 'Done';

function canonicalStatus(raw: string | null | undefined): CanonicalStatus {
  switch (raw) {
    case 'IN_PROGRESS': return 'In Progress';
    case 'REVIEW': return 'Review';
    case 'DONE': return 'Done';
    default: return 'Backlog';
  }
}

const STATUS_PILL: Record<CanonicalStatus, { label: string; data: string; className: string }> = {
  'Backlog': {
    label: 'Backlog',
    data: 'BACKLOG',
    className: 'text-[var(--fg-muted)] bg-[var(--surface-2)] border-[var(--border)]',
  },
  'In Progress': {
    label: 'In Progress',
    data: 'IN_PROGRESS',
    className: 'text-[var(--kagan-rail-running)] bg-[rgba(63,181,142,0.10)] border-[rgba(63,181,142,0.22)]',
  },
  'Review': {
    label: 'Review',
    data: 'REVIEW',
    className: 'text-[var(--kagan-rail-review)] bg-[rgba(194,124,78,0.10)] border-[rgba(194,124,78,0.22)]',
  },
  'Done': {
    label: 'Done',
    data: 'DONE',
    className: 'text-[var(--kagan-rail-running)] opacity-70 bg-[rgba(63,181,142,0.10)] border-[rgba(63,181,142,0.22)]',
  },
};

// ── WsHead ────────────────────────────────────────────────────────────────────

interface WsHeadProps {
  session: SessionItemResponse;
  task: WireTask | null;
}

function WsHead({ session, task }: WsHeadProps) {
  const setPopover = useSetAtom(shellPopoverAtom);
  const setPopoverTaskId = useSetAtom(popoverTaskIdAtom);
  const kind = sessionKind(session);

  const title = task?.title ?? session.title ?? 'Untitled';
  const rawStatus = task?.status ?? session.task_status ?? null;
  const status = canonicalStatus(rawStatus);
  const pill = STATUS_PILL[status];
  const isRunning = status === 'In Progress';

  const agentBadge = kind ? SESSION_KIND_BADGE[kind] : null;

  const taskShortId = task?.id ? task.id.slice(0, 7).toUpperCase() : null;

  const openMoreMenu = (e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopoverTaskId(task?.id ?? null);
    setPopover({ kind: 'more', anchor: { x: rect.right, y: rect.bottom, align: 'right' } });
  };

  return (
    <div
      className="flex items-center gap-3 border-b border-[var(--border)] px-6"
      style={{ height: '50px' }}
      data-testid="ws-head"
    >
      {/* Task ID chip */}
      {taskShortId ? (
        <span className="shrink-0 font-code text-[11px] tracking-[0.06em] text-[var(--fg-dim)]">
          {taskShortId}
        </span>
      ) : null}

      {/* Title */}
      <h1
        className="truncate text-[14px] font-medium text-[var(--fg)] tracking-[-0.01em]"
        data-testid="ws-head-title"
      >
        {title}
      </h1>

      {/* Agent chip */}
      {agentBadge ? (
        <span className="shrink-0 rounded border border-[var(--border)] bg-[var(--surface-2)] px-2 py-0.5 font-code text-[11px] text-[var(--fg-muted)]">
          {agentBadge}
        </span>
      ) : null}

      <div className="ml-auto flex items-center gap-2">
        {/* Status mode pill */}
        <button
          type="button"
          data-mode={pill.data}
          data-testid="ws-head-status-pill"
          className={cn(
            'inline-flex items-center gap-1.5 rounded border px-2.5 py-[3px] font-code text-[10px] font-semibold uppercase tracking-[0.18px] transition-[filter] hover:brightness-115',
            pill.className,
          )}
        >
          <span
            className={cn(
              'inline-block size-[5px] rounded-full bg-current shadow-[0_0_6px_currentColor]',
              isRunning && 'animate-pulse',
            )}
          />
          {pill.label}
        </button>

        {/* Open task link — only for task-bound sessions */}
        {task ? (
          <Link
            to={`/task/${task.id}`}
            aria-label="Open task"
            data-testid="ws-head-open-task"
            className="grid size-7 place-items-center rounded text-[var(--fg-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
          >
            <ExternalLink className="size-3.5" strokeWidth={1.75} />
          </Link>
        ) : null}

        {/* More menu */}
        <button
          type="button"
          onClick={openMoreMenu}
          aria-label="More options"
          data-testid="ws-head-more-btn"
          className="grid size-7 place-items-center rounded text-[var(--fg-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
        >
          <MoreHorizontal className="size-4" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function Component() {
  const { id } = useParams<{ id: string }>();
  const { sessions } = useSessionList();
  const tasks = useAtomValue(tasksAtom);

  const activeSession = useMemo(() => {
    if (!id) return null;
    return sessions.find((s) => s.id === id || s.chat_session_id === id) ?? null;
  }, [sessions, id]);

  const activeTask = useMemo<WireTask | null>(() => {
    if (!activeSession?.task_id) return null;
    return tasks.find((t) => t.id === activeSession.task_id) ?? null;
  }, [tasks, activeSession]);

  const chatSessionId = activeSession
    ? (activeSession.chat_session_id ?? activeSession.id)
    : null;

  if (!activeSession || !chatSessionId) {
    return (
      <div
        className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]"
        data-testid="chat-page-empty"
      >
        <div className="flex flex-col items-center gap-4 text-center">
          <MessageSquareText className="size-8 text-[var(--muted-foreground)]" />
          <p>Select a session from the sidebar</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="chat-page">
      <WsHead session={activeSession} task={activeTask} />
      <div className="min-h-0 flex-1 overflow-hidden">
        <OrchestratorSessionBody chatSessionId={chatSessionId} />
      </div>
    </div>
  );
}
