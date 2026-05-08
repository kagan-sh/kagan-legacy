import { useCallback, useEffect, useState } from 'react';
import { useAtomValue } from 'jotai';
import { toast } from 'sonner';
import { MessageSquareText, Plus, Trash2 } from 'lucide-react';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import { apiClient } from '@/lib/api/client';
import { tasksAtom } from '@/lib/atoms/board';
import { timeAgo } from '@/lib/utils/time';
import { useSessionOverlay } from '@/lib/hooks/use-session-overlay';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { Button } from '@/components/ui/button';

function isChatSession(session: SessionItemResponse): boolean {
  return session.type !== 'task';
}

export function Component() {
  const overlay = useSessionOverlay();
  const { sessions: allSessions, loading, refresh } = useSessionList();
  const tasks = useAtomValue(tasksAtom);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const sessions = allSessions.filter(isChatSession);

  const createSession = useCallback(async () => {
    setCreating(true);
    setLoadError(null);
    try {
      const session = await apiClient.createSession({ type: 'orchestrator', title: 'New conversation' });
      overlay.open(session);
      await refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create conversation';
      setLoadError(message);
      toast.error(message);
    } finally {
      setCreating(false);
    }
  }, [overlay, refresh]);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await apiClient.closeSession(sessionId);
        toast.success('Conversation closed');
        await refresh();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to close conversation');
      }
    },
    [refresh],
  );

  useEffect(() => {
    if (sessions.length === 0 && !loading && !creating) {
      void createSession();
    }
  }, [loading, sessions.length, creating, createSession]);

  const totalTasks = tasks.length;
  const inProgressCount = tasks.filter((t) => t.status === 'IN_PROGRESS').length;
  const reviewCount = tasks.filter((t) => t.status === 'REVIEW').length;
  const doneCount = tasks.filter((t) => t.status === 'DONE').length;
  const backlogCount = tasks.filter((t) => t.status === 'BACKLOG').length;

  return (
    <div className="flex h-full min-h-0 flex-col items-center justify-center px-6">
      <div className="w-full max-w-lg space-y-8">
        {/* Hero greeting */}
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">What's next?</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Pick up where you left off or start something new.
          </p>
        </div>

        {/* Mini stats card */}
        {totalTasks > 0 ? (
          <div className="mx-auto flex max-w-sm items-center justify-center gap-6 py-2 text-center font-code text-xs text-[var(--muted-foreground)]">
            {inProgressCount > 0 ? (
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-[var(--kagan-rail-running)]" />
                {inProgressCount} active
              </span>
            ) : null}
            {reviewCount > 0 ? (
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-[var(--kagan-rail-review)]" />
                {reviewCount} review
              </span>
            ) : null}
            {doneCount > 0 ? (
              <span className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-[var(--kagan-success)]" />
                {doneCount} done
              </span>
            ) : null}
            {backlogCount > 0 ? (
              <span>{backlogCount} backlog</span>
            ) : null}
          </div>
        ) : null}

        {/* Primary CTA */}
        <div className="flex justify-center">
          <Button
            onClick={() => { void createSession(); }}
            disabled={creating}
            className="cta-glow px-6"
          >
            <Plus className="size-4" />
            New conversation
          </Button>
        </div>

        {loadError ? (
          <p className="text-center text-sm text-[var(--destructive)]">{loadError}</p>
        ) : null}

        {/* Recent sessions */}
        {sessions.length > 0 ? (
          <div className="space-y-3 pt-4">
            <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
              Recent
            </p>
            <div className="space-y-1">
              {sessions.slice(0, 6).map((session) => (
                <div
                  key={session.id}
                  className="group flex items-center gap-2"
                >
                  <button
                    type="button"
                    onClick={() => overlay.open(session)}
                    className="flex flex-1 items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-[color:var(--surface-1)]"
                  >
                    <MessageSquareText className="size-4 shrink-0 text-[var(--muted-foreground)]" />
                    <span className="min-w-0 flex-1 truncate">{session.title || 'Untitled conversation'}</span>
                    <span className="shrink-0 text-xs text-[var(--muted-foreground)]">{timeAgo(session.updated_at)}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => { void deleteSession(session.id); }}
                    className="hidden rounded p-1.5 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
                    aria-label="Close conversation"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
