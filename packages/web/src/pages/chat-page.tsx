import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { MessageSquareText, Plus, Search, Trash2, ChevronRight } from 'lucide-react';
import type { SessionItemResponse } from '@kagan/shared-api-client';
import { apiClient } from '@/lib/api/client';
import { timeAgo } from '@/lib/utils/time';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { OrchestratorSessionBody } from '@/components/session/OrchestratorSessionBody';
import { useSessionList } from '@/lib/hooks/use-session-list';

function rawChatSessionId(session: SessionItemResponse): string {
  return session.chat_session_id ?? session.id;
}

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { sessions: allSessions, loading, refresh } = useSessionList();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(id ?? null);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set(['default']));

  const normalizedQuery = query.toLowerCase().trim();

  useEffect(() => {
    if (id) setActiveId(id);
  }, [id]);

  const filteredSessions = useMemo(() => {
    if (!normalizedQuery) return allSessions;
    return allSessions.filter((s) => {
      const title = (s.title || '').toLowerCase();
      const backend = (s.type || '').toLowerCase();
      return title.includes(normalizedQuery) || backend.includes(normalizedQuery);
    });
  }, [allSessions, normalizedQuery]);

  const activeSession = useMemo(() => {
    if (!activeId) return null;
    return allSessions.find((s) => s.id === activeId || s.chat_session_id === activeId) ?? null;
  }, [allSessions, activeId]);

  const chatSessions = useMemo(() => {
    return filteredSessions.filter((s) => s.type !== 'task');
  }, [filteredSessions]);

  const taskSessions = useMemo(() => {
    return filteredSessions.filter((s) => s.type === 'task');
  }, [filteredSessions]);

  const createSession = useCallback(async () => {
    setCreating(true);
    try {
      const session = await apiClient.createSession({ type: 'orchestrator', title: 'New conversation' });
      setActiveId(session.id);
      navigate(`/chat/${session.id}`, { replace: true });
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create conversation');
    } finally {
      setCreating(false);
    }
  }, [navigate, refresh]);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await apiClient.closeSession(sessionId);
        if (activeId === sessionId) {
          setActiveId(null);
          navigate('/chat', { replace: true });
        }
        await refresh();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to close conversation');
      }
    },
    [activeId, navigate, refresh],
  );

  const toggleProject = useCallback((key: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const openSession = useCallback(
    (session: SessionItemResponse) => {
      const sessionId = session.chat_session_id ?? session.id;
      setActiveId(sessionId);
      navigate(`/chat/${sessionId}`, { replace: true });
    },
    [navigate],
  );

  return (
    <div className="flex h-full min-h-0">
      {/* Left sidebar */}
      <div className="flex w-60 shrink-0 flex-col border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
        <div className="space-y-3 border-b border-[color:var(--border-subtle)] p-3">
          <p className="text-sm font-semibold text-[var(--foreground)]">Chat sessions</p>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2"
            onClick={createSession}
            disabled={creating}
          >
            <Plus className="size-3.5" />
            New chat
          </Button>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter sessions..."
              className="h-8 pl-8 text-sm"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {/* Orchestrator & general sessions */}
          <div className="pt-3">
            <button
              type="button"
              onClick={() => toggleProject('default')}
              className="flex w-full items-center gap-1 px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <ChevronRight
                className={cn(
                  'size-3 shrink-0 transition-transform',
                  expandedProjects.has('default') && 'rotate-90',
                )}
              />
              Conversations
            </button>
            {expandedProjects.has('default') && (
              <div className="space-y-0.5">
                {loading && chatSessions.length === 0 ? (
                  <div className="space-y-1 px-1">
                    <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
                    <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
                  </div>
                ) : chatSessions.length > 0 ? (
                  chatSessions.map((session) => (
                    <div
                      key={session.id}
                      className="group flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors"
                    >
                      <button
                        type="button"
                        onClick={() => openSession(session)}
                        className={cn(
                          'flex min-w-0 flex-1 items-start gap-2 text-left',
                          (activeId === session.id || activeId === session.chat_session_id)
                            ? 'text-[var(--foreground)]'
                            : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                        )}
                      >
                        <span
                          className={cn(
                            'mt-1.5 size-2 shrink-0 rounded-full',
                            (activeId === session.id || activeId === session.chat_session_id)
                              ? 'bg-[var(--primary)]'
                              : 'bg-[var(--muted-foreground)]',
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium leading-snug">
                            {session.title || 'Untitled'}
                          </p>
                          <span className="text-[11px] text-[var(--muted-foreground)]">
                            {timeAgo(session.updated_at)}
                          </span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); void deleteSession(session.id); }}
                        className="mt-0.5 hidden rounded p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
                        aria-label="Delete session"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
                    {query ? 'No matching sessions' : 'No sessions yet'}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Task sessions */}
          {taskSessions.length > 0 && (
            <div className="pt-3">
              <button
                type="button"
                onClick={() => toggleProject('tasks')}
                className="flex w-full items-center gap-1 px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              >
                <ChevronRight
                  className={cn(
                    'size-3 shrink-0 transition-transform',
                    expandedProjects.has('tasks') && 'rotate-90',
                  )}
                />
                Task sessions
              </button>
              {expandedProjects.has('tasks') && (
                <div className="space-y-0.5">
                  {taskSessions.map((session) => (
                    <div
                      key={session.id}
                      className="group flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors"
                    >
                      <button
                        type="button"
                        onClick={() => openSession(session)}
                        className={cn(
                          'flex min-w-0 flex-1 items-start gap-2 text-left',
                          (activeId === session.id || activeId === session.chat_session_id)
                            ? 'text-[var(--foreground)]'
                            : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                        )}
                      >
                        <MessageSquareText className="mt-1 size-3.5 shrink-0 text-[var(--muted-foreground)]" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium leading-snug">
                            {session.title || 'Untitled task'}
                          </p>
                          <span className="text-[11px] text-[var(--muted-foreground)]">
                            {timeAgo(session.updated_at)}
                          </span>
                        </div>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {activeSession ? (
          <div className="flex flex-1 flex-col min-h-0">
            <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-sm font-medium">
                  {activeSession.title || 'Untitled'}
                </h2>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <OrchestratorSessionBody
                chatSessionId={rawChatSessionId(activeSession)}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted-foreground)]">
            <div className="space-y-4 text-center">
              <MessageSquareText className="mx-auto size-8 text-[var(--muted-foreground)]" />
              <p>Select a session or start a new chat</p>
              <Button variant="ghost" size="sm" onClick={createSession}>
                <Plus className="size-3.5 mr-2" />
                New chat
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
