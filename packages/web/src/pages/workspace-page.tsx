import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAtom, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import type { WireChatSessionSummary } from '@/lib/api/types';
import { apiClient } from '@/lib/api/client';
import {
  rightRailChatSessionIdAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  workspaceSessionIdAtom,
} from '@/lib/atoms/ui';
import { WorkspaceSidebar } from '@/components/workspace/workspace-sidebar';
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
  const [sessions, setSessions] = useState<WireChatSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const bootstrappedRef = useRef(false);

  const sortedSessions = useMemo(() => sortOrchestratorSessions(sessions), [sessions]);

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

    if (sortedSessions.length === 0 && !bootstrappedRef.current) {
      bootstrappedRef.current = true;
      void createSession();
      return;
    }

    if (!selectedSessionId || !sortedSessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(sortedSessions[0]?.id ?? null);
    }
  }, [loading, sortedSessions, selectedSessionId, setSelectedSessionId, createSession]);

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-80 shrink-0 overflow-hidden border-r border-[color:var(--border-subtle)] lg:block">
        <WorkspaceSidebar
          sessions={sortedSessions}
          loading={loading}
          selectedSessionId={selectedSessionId}
          onSelect={setSelectedSessionId}
          onCreateNew={() => {
            void createSession();
          }}
          onDelete={(sessionId) => {
            void deleteSession(sessionId);
          }}
        />
      </aside>

      <main className="min-w-0 flex-1 overflow-hidden">
        <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] px-4 py-3 lg:hidden">
          <NativeSelect
            value={selectedSessionId ?? ''}
            onChange={(event) => setSelectedSessionId(event.target.value || null)}
            disabled={loading || sortedSessions.length === 0}
          >
            {sortedSessions.length > 0 ? (
              sortedSessions.map((session) => (
                <NativeSelectOption key={session.id} value={session.id}>
                  {session.label || 'Untitled conversation'}
                </NativeSelectOption>
              ))
            ) : (
              <NativeSelectOption value="">
                {loading ? 'Loading conversations...' : 'No conversations'}
              </NativeSelectOption>
            )}
          </NativeSelect>
          <Button
            variant="ghost"
            size="sm"
            disabled={creating}
            onClick={() => {
              void createSession();
            }}
          >
            New
          </Button>
        </div>

        <ErrorBoundary>
          {selectedSessionId ? (
            <OrchestratorChatPanel
              key={selectedSessionId}
              sessionId={selectedSessionId}
              layout="chat-right"
              surface="workspace"
              onSetLayout={() => {}}
              onClose={() => setSelectedSessionId(null)}
              onSessionUpdated={upsertSession}
            />
          ) : (
            <div className="flex h-full items-center justify-center px-6">
              <div className="max-w-md text-center">
                <p className="text-lg font-semibold text-[var(--foreground)]">Start a workspace conversation</p>
                <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                  The orchestrator is the workspace in this view. Open an existing conversation or create a new one.
                </p>
                {loadError ? (
                  <p className="mt-3 text-sm text-[var(--destructive)]">{loadError}</p>
                ) : null}
                <div className="mt-5">
                  <Button
                    disabled={creating}
                    onClick={() => {
                      void createSession();
                    }}
                  >
                    New conversation
                  </Button>
                </div>
              </div>
            </div>
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
