import { useEffect } from 'react';
import { X, Maximize2, PanelRight, MessageSquare, Bot, CircleDot } from 'lucide-react';
import { useSessionOverlay } from '@/lib/hooks/use-session-overlay';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { useSessionActions } from '@/lib/hooks/use-session-actions';
import { cn } from '@/lib/utils';
import { OrchestratorSessionBody } from './OrchestratorSessionBody';
import { TaskSessionBody } from './TaskSessionBody';
import { GeneralSessionBody } from './GeneralSessionBody';
import type { SessionItemResponse } from '@kagan/shared-api-client';

export function SessionOverlay() {
  const { selectedSession, isOpen, layout, close, setLayout, selectSession } =
    useSessionOverlay();
  const { sessions, loading } = useSessionList();
  const { canStop, canClose, stop, close: closeSession } = useSessionActions();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, close]);

  if (!isOpen) return null;

  const isDocked = layout === 'docked';

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex',
        isDocked && 'justify-end',
        !isDocked && 'items-center justify-center bg-black/50 p-4',
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Session overlay"
    >
      <div
        className={cn(
          'flex bg-[color:var(--surface-0)] shadow-[var(--ambient-shadow)]',
          isDocked &&
            'h-full w-full max-w-[28rem] border-l border-[color:var(--border-subtle)] lg:max-w-[32rem]',
          !isDocked &&
            'h-[90vh] w-full max-w-4xl overflow-hidden rounded-lg border border-[color:var(--border-subtle)]',
        )}
      >
        {/* Session list sidebar */}
        <div className="hidden w-60 shrink-0 flex-col border-r border-[color:var(--border-subtle)] md:flex">
          <div className="flex items-center justify-between px-3 py-2.5">
            <span className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
              Sessions
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {loading && sessions.length === 0 ? (
              <div className="px-3 py-2 text-xs text-[var(--muted-foreground)]">
                Loading...
              </div>
            ) : (
              sessions.map((session) => (
                <SessionListItem
                  key={session.id}
                  session={session}
                  active={session.id === selectedSession?.id}
                  onSelect={() => selectSession(session)}
                />
              ))
            )}
          </div>
        </div>

        {/* Main content */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Header */}
          {selectedSession ? (
            <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h2 className="truncate text-sm font-medium">{selectedSession.title}</h2>
                  <SessionTypeBadge type={selectedSession.type} />
                </div>
              </div>
              <div className="flex items-center gap-1">
                {canStop(selectedSession) && (
                  <button
                    type="button"
                    onClick={() => stop(selectedSession)}
                    className="rounded px-2 py-1 text-xs text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  >
                    Stop
                  </button>
                )}
                {canClose(selectedSession) && (
                  <button
                    type="button"
                    onClick={() => closeSession(selectedSession)}
                    className="rounded px-2 py-1 text-xs text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  >
                    Close
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setLayout(isDocked ? 'fullscreen' : 'docked')}
                  className="rounded p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  aria-label={isDocked ? 'Fullscreen' : 'Dock'}
                >
                  {isDocked ? (
                    <Maximize2 className="size-4" />
                  ) : (
                    <PanelRight className="size-4" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={close}
                  className="rounded p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  aria-label="Close overlay"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>
          ) : null}

          {/* Body */}
          <div className="min-h-0 flex-1 overflow-hidden">
            {!selectedSession ? (
              <div className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]">
                Select a session
              </div>
            ) : (
              <SessionBodyRouter session={selectedSession} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SessionListItem({
  session,
  active,
  onSelect,
}: {
  session: SessionItemResponse;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
        active
          ? 'bg-[color:var(--surface-2)] text-[var(--foreground)]'
          : 'text-[var(--muted-foreground)] hover:bg-[color:var(--surface-1)] hover:text-[var(--foreground)]',
      )}
    >
      <SessionTypeIcon type={session.type} />
      <span className="min-w-0 flex-1 truncate">{session.title}</span>
    </button>
  );
}

function SessionTypeIcon({ type }: { type: string }) {
  if (type === 'orchestrator') return <MessageSquare className="size-3.5 shrink-0" />;
  if (type === 'task') return <Bot className="size-3.5 shrink-0" />;
  return <CircleDot className="size-3.5 shrink-0" />;
}

function SessionTypeBadge({ type }: { type: string }) {
  const label = type.charAt(0).toUpperCase() + type.slice(1);
  return (
    <span className="shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
      {label}
    </span>
  );
}

function SessionBodyRouter({ session }: { session: SessionItemResponse }) {
  switch (session.type) {
    case 'orchestrator':
      return <OrchestratorSessionBody sessionId={session.id} />;
    case 'task':
      return <TaskSessionBody taskId={session.task_id ?? session.id} sessionId={session.id} />;
    default:
      return <GeneralSessionBody sessionId={session.id} />;
  }
}
