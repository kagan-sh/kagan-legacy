import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { useActiveProject } from '@/lib/hooks/use-active-project';

const DONE_INITIAL_LIMIT = 5;

function rawChatSessionId(session: SessionItemResponse): string {
  return session.chat_session_id ?? session.id;
}

interface TaskGroup {
  taskId: string;
  title: string;
  taskStatus: string | null;
  sessions: SessionItemResponse[];
  updatedAt: string;
}

interface PartitionedSessions {
  loose: SessionItemResponse[];
  liveTasks: TaskGroup[];
  doneTasks: TaskGroup[];
}

function partitionSessions(
  sessions: SessionItemResponse[],
  query: string,
  activeProjectId: string | null,
): PartitionedSessions {
  const projectScoped = activeProjectId
    ? sessions.filter((s) => (s.project_id ?? null) === activeProjectId)
    : sessions;

  const filtered = query
    ? projectScoped.filter((s) => {
        const title = (s.title || '').toLowerCase();
        const backend = (s.type || '').toLowerCase();
        return title.includes(query) || backend.includes(query);
      })
    : projectScoped;

  const loose: SessionItemResponse[] = [];
  const taskMap = new Map<string, TaskGroup>();

  for (const s of filtered) {
    if (s.task_id) {
      const group = taskMap.get(s.task_id) ?? {
        taskId: s.task_id,
        title: s.title || `KAG-${s.task_id.slice(0, 7)}`,
        taskStatus: s.task_status ?? null,
        sessions: [],
        updatedAt: s.updated_at,
      };
      group.sessions.push(s);
      if (s.updated_at > group.updatedAt) group.updatedAt = s.updated_at;
      if (!group.taskStatus && s.task_status) group.taskStatus = s.task_status;
      taskMap.set(s.task_id, group);
    } else {
      loose.push(s);
    }
  }

  const allTasks = Array.from(taskMap.values()).sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );

  const liveTasks = allTasks.filter((g) => g.taskStatus !== 'DONE');
  const doneTasks = allTasks.filter((g) => g.taskStatus === 'DONE');

  return { loose, liveTasks, doneTasks };
}

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { sessions: allSessions, loading, refresh } = useSessionList();
  const activeProject = useActiveProject();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(id ?? null);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [doneShowAll, setDoneShowAll] = useState(false);
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

  const streamingSessionIds = useMemo(
    () => new Set(allSessions.filter((s) => s.capabilities.can_stop).map((s) => s.id)),
    [allSessions],
  );

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

  const partitions = useMemo(
    () => partitionSessions(allSessions, normalizedQuery, activeProject?.id ?? null),
    [allSessions, normalizedQuery, activeProject?.id],
  );

  // Auto-expand the task containing the active session.
  useEffect(() => {
    if (!activeId) return;
    const activeTask = [...partitions.liveTasks, ...partitions.doneTasks].find((g) =>
      g.sessions.some((s) => s.id === activeId || s.chat_session_id === activeId),
    );
    if (activeTask) {
      setExpandedTasks((prev) => {
        if (prev.has(activeTask.taskId)) return prev;
        const next = new Set(prev);
        next.add(activeTask.taskId);
        return next;
      });
    }
  }, [activeId, partitions]);

  const activeSession = useMemo(() => {
    if (!activeId) return null;
    return allSessions.find((s) => s.id === activeId || s.chat_session_id === activeId) ?? null;
  }, [allSessions, activeId]);

  const isArchived = activeSession?.task_status === 'DONE';

  const createSession = useCallback(
    async (type: 'orchestrator' | 'general') => {
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
    },
    [navigate, refresh],
  );

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

  const visibleDone = doneShowAll
    ? partitions.doneTasks
    : partitions.doneTasks.slice(0, DONE_INITIAL_LIMIT);
  const hiddenDoneCount = partitions.doneTasks.length - visibleDone.length;

  const hasAnything =
    partitions.loose.length > 0 ||
    partitions.liveTasks.length > 0 ||
    partitions.doneTasks.length > 0;

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
          ) : !hasAnything ? (
            <p className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
              {query ? 'No matching sessions' : 'No sessions yet'}
            </p>
          ) : (
            <div className="pt-2">
              {/* Loose sessions (orchestrator + general) */}
              {partitions.loose.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  isActive={isActiveSession(session)}
                  isStreaming={streamingSessionIds.has(session.id)}
                  badge={session.type === 'general' ? '○' : '◈'}
                  onOpen={() => openSession(session)}
                  onDelete={(e) => {
                    e.stopPropagation();
                    void deleteSession(session.id);
                  }}
                />
              ))}

              {/* Live task groups */}
              {partitions.liveTasks.map((group) => (
                <TaskGroupBlock
                  key={group.taskId}
                  group={group}
                  expanded={expandedTasks.has(group.taskId)}
                  onToggle={() => toggleTask(group.taskId)}
                  isActiveSession={isActiveSession}
                  streamingSessionIds={streamingSessionIds}
                  openSession={openSession}
                  deleteSession={deleteSession}
                />
              ))}

              {/* Done bucket */}
              {partitions.doneTasks.length > 0 && (
                <div className="mt-3 border-t border-[color:var(--border-subtle)] pt-3">
                  <p className="px-1 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                    Done <span className="font-code">({partitions.doneTasks.length})</span>
                  </p>
                  {visibleDone.map((group) => (
                    <TaskGroupBlock
                      key={group.taskId}
                      group={group}
                      expanded={expandedTasks.has(group.taskId)}
                      onToggle={() => toggleTask(group.taskId)}
                      isActiveSession={isActiveSession}
                      streamingSessionIds={streamingSessionIds}
                      openSession={openSession}
                      deleteSession={deleteSession}
                      muted
                    />
                  ))}
                  {hiddenDoneCount > 0 && (
                    <button
                      type="button"
                      onClick={() => setDoneShowAll(true)}
                      className="mt-1 w-full rounded px-1 py-1 text-left text-[11px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                    >
                      Show more ({hiddenDoneCount})
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
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
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <h2 className="truncate text-sm font-medium">
                  {activeSession.title || 'Untitled'}
                </h2>
                {isArchived && (
                  <span className="shrink-0 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
                    Archived · merged
                  </span>
                )}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <OrchestratorSessionBody chatSessionId={rawChatSessionId(activeSession)} />
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

interface TaskGroupBlockProps {
  group: TaskGroup;
  expanded: boolean;
  onToggle: () => void;
  isActiveSession: (s: SessionItemResponse) => boolean;
  streamingSessionIds: Set<string>;
  openSession: (s: SessionItemResponse) => void;
  deleteSession: (id: string) => Promise<void> | void;
  muted?: boolean;
}

function TaskGroupBlock({
  group,
  expanded,
  onToggle,
  isActiveSession,
  streamingSessionIds,
  openSession,
  deleteSession,
  muted,
}: TaskGroupBlockProps) {
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          'flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
          muted ? 'text-[var(--muted-foreground)]' : 'text-[var(--foreground)]',
          'hover:bg-[color:var(--surface-1)]',
        )}
      >
        <ChevronRight
          className={cn('size-3 shrink-0 transition-transform', expanded && 'rotate-90')}
        />
        <span className="min-w-0 flex-1 truncate">{group.title}</span>
        <span className="shrink-0 font-code text-[10px] text-[var(--muted-foreground)]">
          {group.sessions.length}
        </span>
      </button>
      {expanded && (
        <div className="ml-3 border-l border-[color:var(--border-subtle)] pl-1.5">
          {group.sessions.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              isActive={isActiveSession(session)}
              isStreaming={streamingSessionIds.has(session.id) && !muted}
              badge={session.role === 'reviewer' ? '◇' : '◆'}
              onOpen={() => openSession(session)}
              onDelete={(e) => {
                e.stopPropagation();
                void deleteSession(session.id);
              }}
              muted={muted}
            />
          ))}
        </div>
      )}
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
  muted?: boolean;
}

function SessionRow({
  session,
  isActive,
  isStreaming,
  badge,
  onOpen,
  onDelete,
  muted,
}: SessionRowProps) {
  return (
    <div
      className={cn(
        'group relative flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors',
        isActive && 'bg-[color:var(--accent)]',
      )}
    >
      {isActive && (
        <span
          aria-hidden
          className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded bg-[var(--primary)]"
        />
      )}
      <button
        type="button"
        onClick={onOpen}
        className={cn(
          'flex min-w-0 flex-1 items-center gap-2 text-left',
          isActive
            ? 'text-[var(--foreground)]'
            : muted
              ? 'text-[var(--muted-foreground)]'
              : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
        )}
      >
        <span className="shrink-0 text-[11px] leading-none">{badge}</span>
        {isStreaming && (
          <span
            aria-hidden
            className="size-1.5 shrink-0 rounded-full bg-[var(--kagan-rail-running)]"
            style={{ animation: 'pulse 1.2s ease-in-out infinite' }}
          />
        )}
        <span className="min-w-0 flex-1 truncate leading-snug">
          {session.title || 'Untitled'}
        </span>
        <span className="shrink-0 text-[10px] text-[var(--muted-foreground)]">
          {timeAgo(session.updated_at)}
        </span>
      </button>
      <button
        type="button"
        onClick={onDelete}
        className="hidden rounded p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--destructive)] group-hover:block"
        aria-label="Delete session"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}
