import { useCallback, useEffect, useRef, useState } from 'react';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { MessageSquareText, Plus, Trash2 } from 'lucide-react';
import type { WireChatSessionSummary } from '@/lib/api/types';
import { apiClient } from '@/lib/api/client';
import { tasksAtom } from '@/lib/atoms/board';
import {
  rightRailChatSessionIdAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  workspaceSessionIdAtom,
} from '@/lib/atoms/ui';
import { timeAgo } from '@/lib/utils/time';
import { cn } from '@/lib/utils';
import { OrchestratorChatPanel } from '@/components/session/orchestrator-chat-panel';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

function sortOrchestratorSessions(sessions: WireChatSessionSummary[]): WireChatSessionSummary[] {
  return [...sessions]
    .filter((session) => session.source.toLowerCase() !== 'task-session')
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function Component() {
  const [selectedSessionId, setSelectedSessionId] = useAtom(workspaceSessionIdAtom);
  const setRailMode = useSetAtom(rightRailModeAtom);
  const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
  const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
  const tasks = useAtomValue(tasksAtom);
  const [sessions, setSessions] = useState<WireChatSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const bootstrappedRef = useRef(false);

  const upsertSession = useCallback((session: WireChatSessionSummary) => {
    setSessions((prev) => {
      const next = prev.filter((item) => item.id !== session.id);
      return sortOrchestratorSessions([session, ...next]);
    });
  }, []);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [loaded, settings] = await Promise.all([
        apiClient.getChatSessions(),
        apiClient.getSettings().catch(() => ({} as Record<string, string>)),
      ]);
      const sorted = sortOrchestratorSessions(loaded);
      setSessions(sorted);

      const globalActiveSessionId = settings.chat_last_active_session?.trim();
      if (globalActiveSessionId && sorted.some((session) => session.id === globalActiveSessionId)) {
        setSelectedSessionId((current) => current ?? globalActiveSessionId);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, [setSelectedSessionId]);

  const createSession = useCallback(async () => {
    setCreating(true);
    setLoadError(null);
    try {
      const session = await apiClient.createChatSession({});
      upsertSession(session);
      setSelectedSessionId(session.id);
      return session.id;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create conversation';
      setLoadError(message);
      toast.error(message);
      return null;
    } finally {
      setCreating(false);
    }
  }, [setSelectedSessionId, upsertSession]);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await apiClient.deleteChatSession(sessionId);
        setSessions((prev) => {
          const remaining = prev.filter((session) => session.id !== sessionId);
          const sortedRemaining = sortOrchestratorSessions(remaining);
          if (selectedSessionId === sessionId) {
            setSelectedSessionId(sortedRemaining[0]?.id ?? null);
          }
          return sortedRemaining;
        });
        toast.success('Conversation deleted');
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to delete conversation');
      }
    },
    [selectedSessionId, setSelectedSessionId],
  );

  useEffect(() => {
    setRailMode('none');
    setRailTaskId(null);
    setRailChatSessionId(null);
  }, [setRailMode, setRailTaskId, setRailChatSessionId]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (loading) return;

    if (sessions.length === 0 && !bootstrappedRef.current) {
      bootstrappedRef.current = true;
      void createSession();
      return;
    }

    if (!selectedSessionId || !sessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(sessions[0]?.id ?? null);
    }
  }, [loading, sessions, selectedSessionId, setSelectedSessionId, createSession]);

  const totalTasks = tasks.length;
  const inProgressCount = tasks.filter((t) => t.status === 'IN_PROGRESS').length;
  const reviewCount = tasks.filter((t) => t.status === 'REVIEW').length;
  const doneCount = tasks.filter((t) => t.status === 'DONE').length;
  const backlogCount = tasks.filter((t) => t.status === 'BACKLOG').length;

  // When a session is active, show the full chat view
  if (selectedSessionId) {
    return (
      <div className="flex h-full min-h-0">
        {/* Desktop sidebar */}
        <aside className="hidden w-64 shrink-0 overflow-hidden lg:block">
          <div className="flex h-full flex-col bg-[color:var(--surface-0)]">
            <div className="flex items-center justify-between px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">Conversations</p>
              <Button
                variant="ghost"
                size="sm"
                className="size-7 p-0 text-[var(--muted-foreground)]"
                onClick={() => { void createSession(); }}
              >
                <Plus className="size-3.5" />
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
              {sessions.map((session) => (
                <SessionItem
                  key={session.id}
                  session={session}
                  active={selectedSessionId === session.id}
                  onSelect={() => setSelectedSessionId(session.id)}
                  onDelete={() => { void deleteSession(session.id); }}
                />
              ))}
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">
          {/* Mobile session picker */}
          <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] px-4 py-3 lg:hidden">
            <NativeSelect
              value={selectedSessionId ?? ''}
              onChange={(event) => setSelectedSessionId(event.target.value || null)}
              disabled={loading || sessions.length === 0}
            >
              {sessions.length > 0 ? (
                sessions.map((session) => (
                  <NativeSelectOption key={session.id} value={session.id}>
                    {session.label || 'Untitled conversation'}
                  </NativeSelectOption>
                ))
              ) : (
                <NativeSelectOption value="">
                  {loading ? 'Loading...' : 'No conversations'}
                </NativeSelectOption>
              )}
            </NativeSelect>
            <Button
              variant="ghost"
              size="sm"
              disabled={creating}
              onClick={() => { void createSession(); }}
            >
              New
            </Button>
          </div>

          <ErrorBoundary>
            <OrchestratorChatPanel
              key={selectedSessionId}
              sessionId={selectedSessionId}
              layout="chat-right"
              surface="workspace"
              onSetLayout={() => {}}
              onClose={() => setSelectedSessionId(null)}
              onSessionUpdated={upsertSession}
            />
          </ErrorBoundary>
        </main>
      </div>
    );
  }

  // No session selected — show the Claude-style centered home
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
                <button
                  key={session.id}
                  type="button"
                  onClick={() => setSelectedSessionId(session.id)}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-[color:var(--surface-1)]"
                >
                  <MessageSquareText className="size-4 shrink-0 text-[var(--muted-foreground)]" />
                  <span className="min-w-0 flex-1 truncate">{session.label || 'Untitled conversation'}</span>
                  <span className="shrink-0 text-xs text-[var(--muted-foreground)]">{timeAgo(session.updated_at)}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SessionItem({
  session,
  active,
  onSelect,
  onDelete,
}: {
  session: WireChatSessionSummary;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        'group flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
        active
          ? 'bg-[color:var(--surface-2)] text-[var(--foreground)]'
          : 'text-[var(--muted-foreground)] hover:bg-[color:var(--surface-1)] hover:text-[var(--foreground)]',
      )}
    >
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-start gap-2 text-left">
        <span
          className={cn(
            'mt-1.5 size-2 shrink-0 rounded-full',
            active ? 'bg-[var(--primary)]' : 'bg-[var(--muted-foreground)]',
          )}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium leading-snug">{session.label || 'Untitled conversation'}</p>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--muted-foreground)]">
            <span>{timeAgo(session.updated_at)}</span>
            {session.agent_backend ? (
              <span className="inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px]">
                {session.agent_backend}
              </span>
            ) : null}
          </div>
        </div>
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="mt-0.5 hidden rounded p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
        aria-label="Delete conversation"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
