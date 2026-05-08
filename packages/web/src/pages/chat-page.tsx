import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { MessageSquareText, Plus, Search, Trash2, ChevronRight, ChevronDown } from 'lucide-react';
import type { AgentBackendResponse, SessionItemResponse } from '@kagan/shared-api-client';
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

interface ProjectGroup {
  projectId: string;
  projectName: string;
  orchestratorSessions: SessionItemResponse[];
  generalSessions: SessionItemResponse[];
  taskGroups: Map<string, { title: string; sessions: SessionItemResponse[] }>;
}

function groupSessionsByProject(sessions: SessionItemResponse[]): ProjectGroup[] {
  const projects = new Map<string, ProjectGroup>();

  for (const s of sessions) {
    const pid = s.project_id || 'default';
    if (!projects.has(pid)) {
      projects.set(pid, {
        projectId: pid,
        projectName: pid === 'default' ? 'Default project' : pid,
        orchestratorSessions: [],
        generalSessions: [],
        taskGroups: new Map(),
      });
    }
    const group = projects.get(pid)!;

    if (s.type === 'orchestrator' && !s.role && !s.task_id) {
      group.orchestratorSessions.push(s);
    } else if (s.task_id) {
      // Worker/reviewer session nested under a task
      const tkey = s.task_id;
      if (!group.taskGroups.has(tkey)) {
        group.taskGroups.set(tkey, { title: `KAG-${tkey.slice(0, 7)}`, sessions: [] });
      }
      group.taskGroups.get(tkey)!.sessions.push(s);
    } else {
      group.generalSessions.push(s);
    }
  }

  return Array.from(projects.values());
}

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { sessions: allSessions, loading, refresh } = useSessionList();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(id ?? null);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (id) {
      // Auto-expand projects containing the active session
      const active = allSessions.find((s) => s.id === id || s.chat_session_id === id);
      if (active?.project_id) initial.add(active.project_id);
    }
    if (initial.size === 0) initial.add('default');
    return initial;
  });
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem('kagan-sidebar-width');
      if (saved) {
        const w = parseInt(saved, 10);
        if (w >= 180 && w <= 360) return w;
      }
    }
    return 240;
  });
  const [isResizing, setIsResizing] = useState(false);
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Streaming session IDs (from capabilities.can_stop)
  const streamingSessionIds = useMemo(() => {
    return new Set(
      allSessions.filter((s) => s.capabilities.can_stop).map((s) => s.id),
    );
  }, [allSessions]);

  // Agent backends
  const [agents, setAgents] = useState<AgentBackendResponse[]>([]);
  useEffect(() => {
    apiClient.getChatAgents().then((res) => setAgents(res.backends)).catch(() => {});
  }, []);

  // Activity events (last 5)
  const [activityEvents, setActivityEvents] = useState<{ id: string; text: string; ts: number }[]>([]);
  const [activityExpanded, setActivityExpanded] = useState(true);
  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent;
      const event = custom.detail?.event;
      if (event?.type === 'task_status_changed' && event.payload) {
        const text = `${event.payload.from_status} → ${event.payload.to_status} ${custom.detail?.task_id ? `KAG-${custom.detail.task_id.slice(0, 7)}` : ''}`;
        setActivityEvents((prev) => {
          const next = [{ id: event.id || String(Date.now()), text, ts: Date.now() }, ...prev];
          return next.slice(0, 5);
        });
      }
    };
    window.addEventListener('kagan:session-event', handler);
    return () => window.removeEventListener('kagan:session-event', handler);
  }, []);

  // Sidebar resizing
  useEffect(() => {
    if (!isResizing) return;
    const onMouseMove = (e: MouseEvent) => {
      const w = Math.max(180, Math.min(360, e.clientX));
      setSidebarWidth(w);
    };
    const onMouseUp = () => {
      setIsResizing(false);
      localStorage.setItem('kagan-sidebar-width', String(sidebarWidth));
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isResizing, sidebarWidth]);

  const normalizedQuery = query.toLowerCase().trim();

  useEffect(() => {
    if (id) setActiveId(id);
  }, [id]);

  const projectGroups = useMemo(() => {
    const filtered = normalizedQuery
      ? allSessions.filter((s) => {
          const title = (s.title || '').toLowerCase();
          const backend = (s.type || '').toLowerCase();
          return title.includes(normalizedQuery) || backend.includes(normalizedQuery);
        })
      : allSessions;
    return groupSessionsByProject(filtered);
  }, [allSessions, normalizedQuery]);

  const activeSession = useMemo(() => {
    if (!activeId) return null;
    return allSessions.find((s) => s.id === activeId || s.chat_session_id === activeId) ?? null;
  }, [allSessions, activeId]);

  const createSession = useCallback(async (type: 'orchestrator' | 'general') => {
    setCreating(true);
    try {
      const session = await apiClient.createSession({ type, title: 'New conversation' });
      setActiveId(session.id);
      navigate(`/chat/${session.id}`, { replace: true });
      setNewChatOpen(false);
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

  const toggleTask = useCallback((key: string) => {
    setExpandedTasks((prev) => {
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

  const isActiveSession = (session: SessionItemResponse) =>
    activeId === session.id || activeId === session.chat_session_id;

  return (
    <div className="flex h-full min-h-0">
      {/* Left sidebar */}
      <div
        ref={sidebarRef}
        className="relative flex shrink-0 flex-col border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]"
        style={{ width: sidebarWidth }}
      >
        <div className="space-y-3 border-b border-[color:var(--border-subtle)] p-3">
          <p className="text-sm font-semibold text-[var(--foreground)]">Chat sessions</p>

          {/* New chat dropdown */}
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-2"
              onClick={() => setNewChatOpen(!newChatOpen)}
              disabled={creating}
            >
              <Plus className="size-3.5" />
              New chat
            </Button>
            {newChatOpen && (
              <div
                className="absolute left-0 top-full z-20 mt-1 w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] shadow-lg"
                style={{ borderRadius: '4px' }}
              >
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[var(--foreground)] hover:bg-[color:var(--accent)]"
                  onClick={() => createSession('orchestrator')}
                >
                  <span className="text-[var(--primary)]">&#x25C8;</span>
                  Orchestrator
                </button>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[var(--foreground)] hover:bg-[color:var(--accent)]"
                  onClick={() => createSession('general')}
                >
                  <span className="text-[var(--muted-foreground)]">&#x25CB;</span>
                  General
                </button>
              </div>
            )}
          </div>

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
          {loading && allSessions.length === 0 ? (
            <div className="space-y-1 px-1 pt-3">
              <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
              <div className="h-12 animate-pulse rounded-md bg-[var(--muted)]" />
            </div>
          ) : projectGroups.length > 0 ? (
            projectGroups.map((pg) => {
              const totalInProject =
                pg.orchestratorSessions.length +
                pg.generalSessions.length +
                Array.from(pg.taskGroups.values()).reduce((acc, g) => acc + g.sessions.length, 0);
              const isExpanded = expandedProjects.has(pg.projectId);
              return (
                <div key={pg.projectId} className="pt-3">
                  <button
                    type="button"
                    onClick={() => toggleProject(pg.projectId)}
                    className="flex w-full items-center gap-1 px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  >
                    <ChevronRight
                      className={cn(
                        'size-3 shrink-0 transition-transform',
                        isExpanded && 'rotate-90',
                      )}
                    />
                    <span className="flex-1 text-left truncate">{pg.projectName}</span>
                    <span className="font-code text-[10px]">{totalInProject}</span>
                  </button>

                  {isExpanded && (
                    <div className="space-y-0.5">
                      {/* Orchestrator sessions */}
                      {pg.orchestratorSessions.length > 0 && (
                        <div className="mb-1">
                          {pg.orchestratorSessions.map((session) => (
                            <SessionRow
                              key={session.id}
                              session={session}
                              isActive={isActiveSession(session)}
                              isStreaming={streamingSessionIds.has(session.id)}
                              badge="&#x25C8;"
                              onOpen={() => openSession(session)}
                              onDelete={(e) => { e.stopPropagation(); void deleteSession(session.id); }}
                            />
                          ))}
                        </div>
                      )}

                      {/* General sessions */}
                      {pg.generalSessions.length > 0 && (
                        <div className="mb-1">
                          {pg.generalSessions.map((session) => (
                            <SessionRow
                              key={session.id}
                              session={session}
                              isActive={isActiveSession(session)}
                              isStreaming={streamingSessionIds.has(session.id)}
                              badge="&#x25CB;"
                              onOpen={() => openSession(session)}
                              onDelete={(e) => { e.stopPropagation(); void deleteSession(session.id); }}
                            />
                          ))}
                        </div>
                      )}

                      {/* Task groups with nested sessions */}
                      {Array.from(pg.taskGroups.entries()).map(([taskId, taskGroup]) => {
                        const taskExpanded = expandedTasks.has(taskId);
                        return (
                          <div key={taskId}>
                            <button
                              type="button"
                              onClick={() => toggleTask(taskId)}
                              className="flex w-full items-center gap-1 px-1 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                            >
                              {taskExpanded ? (
                                <ChevronDown className="size-3 shrink-0" />
                              ) : (
                                <ChevronRight className="size-3 shrink-0" />
                              )}
                              <span className="flex-1 text-left truncate font-code">{taskGroup.title}</span>
                              <span className="font-code text-[10px]">{taskGroup.sessions.length}</span>
                            </button>
                            {taskExpanded && (
                              <div className="ml-2 border-l border-[color:var(--border-subtle)] pl-2">
                                {taskGroup.sessions.map((session) => (
                                  <SessionRow
                                    key={session.id}
                                    session={session}
                                    isActive={isActiveSession(session)}
                                    isStreaming={streamingSessionIds.has(session.id)}
                                    badge={session.role === 'reviewer' ? '&#x21BA;' : '&#x2192;'}
                                    onOpen={() => openSession(session)}
                                    onDelete={(e) => { e.stopPropagation(); void deleteSession(session.id); }}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <p className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
              {query ? 'No matching sessions' : 'No sessions yet'}
            </p>
          )}

          {/* Activity section */}
          <div className="border-t border-[color:var(--border-subtle)] pt-3">
            <button
              type="button"
              onClick={() => setActivityExpanded(!activityExpanded)}
              className="flex w-full items-center gap-1 px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <ChevronRight
                className={cn(
                  'size-3 shrink-0 transition-transform',
                  activityExpanded && 'rotate-90',
                )}
              />
              Activity
            </button>
            {activityExpanded && (
              <div className="space-y-0.5 px-1">
                {activityEvents.length === 0 ? (
                  <p className="py-2 text-center text-[10px] text-[var(--muted-foreground)]">
                    No recent activity
                  </p>
                ) : (
                  activityEvents.map((ev) => (
                    <div key={ev.id} className="truncate px-1 py-1 text-[11px] text-[var(--muted-foreground)]">
                      {ev.text}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Agents section */}
          <div className="border-t border-[color:var(--border-subtle)] pb-3 pt-3">
            <p className="px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
              Agents
            </p>
            <div className="space-y-0.5 px-1">
              {agents.length === 0 ? (
                <p className="py-2 text-center text-[10px] text-[var(--muted-foreground)]">
                  Loading agents...
                </p>
              ) : (
                agents.map((agent) => (
                  <div key={agent.name} className="flex items-center gap-2 py-0.5">
                    <span
                      className={cn(
                        'size-2 shrink-0 rounded-full',
                        agent.available ? 'bg-[var(--kagan-rail-running)]' : 'bg-[var(--kagan-rail-error)]',
                      )}
                    />
                    <span className="truncate text-[11px] text-[var(--muted-foreground)]">
                      {agent.name}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Resize handle */}
        <div
          className="absolute right-0 top-0 h-full w-2 cursor-col-resize hover:bg-[var(--primary)]/20"
          style={{ zIndex: 5 }}
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizing(true);
          }}
        />
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
              <div className="flex items-center justify-center gap-2">
                <Button variant="ghost" size="sm" onClick={() => createSession('orchestrator')}>
                  <span className="mr-1.5">&#x25C8;</span>
                  Orchestrator
                </Button>
                <Button variant="ghost" size="sm" onClick={() => createSession('general')}>
                  <span className="mr-1.5">&#x25CB;</span>
                  General
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface SessionRowProps {
  session: SessionItemResponse;
  isActive: boolean;
  isStreaming: boolean;
  badge: string;
  onOpen: () => void;
  onDelete: (e: React.MouseEvent) => void;
}

function SessionRow({ session, isActive, isStreaming, badge, onOpen, onDelete }: SessionRowProps) {
  return (
    <div
      className={cn(
        'group flex items-start gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
        isActive && 'border-l-2 border-[var(--primary)] bg-[color:var(--accent)]',
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className={cn(
          'flex min-w-0 flex-1 items-start gap-2 text-left',
          isActive ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
        )}
      >
        <span className="mt-1 flex shrink-0 gap-1">
          <span className="text-[11px] leading-none">{badge}</span>
          {isStreaming && (
            <span
              className="size-2 mt-0.5 shrink-0 rounded-full bg-[var(--kagan-rail-running)] animate-pulse"
              style={{ animationDuration: '1s' }}
            />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <p className="truncate pr-2 font-medium leading-snug">
              {session.title || 'Untitled'}
            </p>
            <span className="shrink-0 text-[11px] text-[var(--muted-foreground)]">
              {timeAgo(session.updated_at)}
            </span>
          </div>
          {session.role && (
            <span className="text-[10px] text-[var(--muted-foreground)]">
              {session.role}
            </span>
          )}
        </div>
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="mt-0.5 hidden rounded p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
        aria-label="Delete session"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
