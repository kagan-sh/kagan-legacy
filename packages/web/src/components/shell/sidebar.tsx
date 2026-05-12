import { useEffect, useRef, useState, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import {
  ChevronDown,
  ChevronRight,
  Cpu,
  ExternalLink,
  Kanban,
  MessageSquarePlus,
  Play,
  Plus,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { useActiveProject } from '@/lib/hooks/use-active-project';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import {
  sidebarCollapsedAtom,
  newSessionModalOpenAtom,
  sessionsSectionOpenAtom,
  tasksSectionOpenAtom,
} from '@/lib/atoms/shell';
import { sessionPickerOpenAtom } from '@/lib/atoms/ui';
import { useShellPopover } from '@/components/shell/popover';
import { COLUMN_ORDER, STATUS_LABELS } from '@/lib/utils/constants';
import { SESSION_KIND_BADGE, sessionKind, taskSessionLane } from '@/lib/sessions/kind';
import { apiClient } from '@/lib/api/client';
import type { SessionItemResponse, TaskSessionResponse, WireTask } from '@kagan/shared-api-client';
import { cn } from '@/lib/utils';

const STATUS_DOT: Record<string, string> = {
  BACKLOG: 'bg-[var(--kagan-rail-idle)] opacity-50',
  IN_PROGRESS:
    'bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)] animate-pulse',
  REVIEW: 'bg-[var(--kagan-rail-review)]',
  DONE: 'bg-[var(--kagan-rail-running)] opacity-40',
};

// ---------------------------------------------------------------------------
// Small in-memory cache for task sessions — 30s TTL so re-renders don't thrash
// ---------------------------------------------------------------------------
interface CachedTaskSessions {
  sessions: TaskSessionResponse[];
  fetchedAt: number;
}
const taskSessionCache = new Map<string, CachedTaskSessions>();
const CACHE_TTL_MS = 30_000;

async function fetchTaskSessionsCached(taskId: string): Promise<TaskSessionResponse[]> {
  const cached = taskSessionCache.get(taskId);
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return cached.sessions;
  }
  const sessions = await apiClient.getTaskSessions(taskId);
  taskSessionCache.set(taskId, { sessions, fetchedAt: Date.now() });
  return sessions;
}

export function Sidebar() {
  const collapsed = useAtomValue(sidebarCollapsedAtom);
  return (
    <aside
      data-collapsed={collapsed ? 'true' : 'false'}
      className={cn(
        'overflow-hidden border-r border-[var(--border)] bg-[var(--surface-0)] transition-[width] duration-200 ease-out',
        collapsed ? 'w-0' : 'w-[252px]',
      )}
      aria-hidden={collapsed}
      aria-label="Workspace sidebar"
    >
      <div className="flex h-full w-[252px] flex-col">
        <SidebarTop />
        <SessionsSection />
        <TasksSection />
        <SidebarFoot />
      </div>
    </aside>
  );
}

function SidebarTop() {
  const setBoardDialog = useSetAtom(boardDialogAtom);
  const setNewSessionOpen = useSetAtom(newSessionModalOpenAtom);
  const agentsPopover = useShellPopover('agents', 'left');
  const agentsBtnRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="flex flex-col gap-px px-3 pt-3 pb-1.5">
      <SidebarButton
        kind="primary"
        icon={<Plus className="size-[15px]" />}
        kbd="N"
        onClick={() => setBoardDialog({ kind: 'create' })}
      >
        New task
      </SidebarButton>
      <SidebarButton
        icon={<MessageSquarePlus className="size-[15px]" />}
        onClick={() => setNewSessionOpen(true)}
      >
        New session
      </SidebarButton>
      <SidebarLink icon={<Kanban className="size-[15px]" />} to="/board">
        Board
      </SidebarLink>
      {/* Agents opens a popover instead of navigating; caret signals dropdown */}
      <button
        ref={agentsBtnRef}
        type="button"
        aria-label="Agents"
        aria-expanded={agentsPopover.isOpen}
        onClick={(e) => agentsPopover.openFromEvent(e)}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-[7px] text-left font-ui text-[13px] text-[var(--fg-2)] transition-colors',
          'hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
          agentsPopover.isOpen && 'bg-[var(--surface-2)] text-[var(--foreground)]',
        )}
      >
        <span className="flex-shrink-0 text-[var(--muted-foreground)]">
          <Cpu className="size-[15px]" />
        </span>
        <span className="flex-1 truncate">Agents</span>
        <ChevronDown
          data-testid="sidebar-agents-caret"
          className={cn(
            'ml-auto size-3.5 flex-shrink-0 text-[var(--fg-dim)] transition-transform duration-150',
            agentsPopover.isOpen && 'rotate-180',
          )}
          strokeWidth={1.75}
        />
      </button>
    </div>
  );
}

interface LinkProps {
  icon: React.ReactNode;
  to: string;
  children: React.ReactNode;
}

function SidebarLink({ icon, to, children }: LinkProps) {
  const className =
    'flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-[7px] text-left font-ui text-[13px] text-[var(--fg-2)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]';
  return (
    <Link to={to} className={className}>
      <span className="flex-shrink-0 text-[var(--muted-foreground)]">{icon}</span>
      <span className="flex-1 truncate">{children}</span>
    </Link>
  );
}

interface ButtonProps {
  icon: React.ReactNode;
  kind?: 'primary';
  kbd?: string;
  onClick: () => void;
  children: React.ReactNode;
}

function SidebarButton({ icon, kind, kbd, onClick, children }: ButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-[7px] text-left font-ui text-[13px] text-[var(--fg-2)] transition-colors',
        'hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
        kind === 'primary' && 'text-[var(--primary-soft)] [&_svg]:text-[var(--primary-soft)]',
      )}
    >
      <span className="flex-shrink-0 text-[var(--muted-foreground)]">{icon}</span>
      <span className="flex-1 truncate">{children}</span>
      {kbd ? (
        <kbd className="ml-auto rounded border border-[var(--border)] px-1.5 py-px font-code text-[10px] text-[var(--fg-dim)]">
          {kbd}
        </kbd>
      ) : null}
    </button>
  );
}

const SESSIONS_VISIBLE_CAP = 8;
/** Minimum session count before "View all sessions" is shown. */
const VIEW_ALL_SESSIONS_MIN = 5;

/** State for a single session row's inline delete confirmation. */
type DeleteState = 'idle' | 'confirm';

interface SessionRowProps {
  session: SessionItemResponse;
  active: boolean;
  onNavigate: (id: string) => void;
  onDeleted: () => void;
}

function SessionRow({ session, active, onNavigate, onDeleted }: SessionRowProps) {
  const kind = sessionKind(session);
  const [deleteState, setDeleteState] = useState<DeleteState>('idle');
  const revertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const orchestrator = kind === 'orchestrator';
  // Use can_stop as the running proxy — same heuristic as shell-layout
  const isRunning = session.capabilities?.can_stop === true;

  const clearRevertTimer = () => {
    if (revertTimerRef.current !== null) {
      clearTimeout(revertTimerRef.current);
      revertTimerRef.current = null;
    }
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteState('confirm');
    revertTimerRef.current = setTimeout(() => {
      setDeleteState('idle');
    }, 2000);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    clearRevertTimer();
    setDeleteState('idle');
  };

  const handleConfirmDelete = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      clearRevertTimer();
      setDeleteState('idle');
      const targetId = session.chat_session_id ?? session.id;
      try {
        await apiClient.closeSession(targetId);
        onDeleted();
      } catch {
        toast.error('Failed to delete session');
      }
    },
    [session, onDeleted],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => clearRevertTimer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (kind !== 'orchestrator' && kind !== 'general') return null;

  return (
    <li>
      <div
        className={cn(
          'group relative flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left font-ui text-[12.5px] text-[var(--muted-foreground)] transition-colors',
          'hover:bg-[var(--surface-2)] hover:text-[var(--fg-2)]',
          active &&
            'bg-[var(--surface-3)] text-[var(--foreground)] shadow-[inset_2px_0_0_var(--primary)]',
        )}
        data-active={active ? 'true' : 'false'}
      >
        {/* Main navigate button */}
        <button
          type="button"
          onClick={() => onNavigate(session.id)}
          className="flex min-w-0 flex-1 items-center gap-2 bg-transparent border-0 p-0 text-inherit"
          aria-label={session.title || `Session ${session.id.slice(0, 6)}`}
        >
          {/* Status dot */}
          <span
            className={cn(
              'flex-shrink-0 size-1.5 rounded-full',
              isRunning
                ? 'bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)] animate-pulse'
                : 'bg-[var(--kagan-rail-idle)] opacity-40',
            )}
          />
          <span
            className={cn(
              'flex-shrink-0 rounded px-1.5 py-px font-code text-[9px] uppercase tracking-[0.08em]',
              orchestrator
                ? 'bg-[rgba(212,168,75,0.14)] text-[var(--primary-soft)]'
                : 'bg-[var(--surface-2)] text-[var(--fg-dim)]',
            )}
          >
            {SESSION_KIND_BADGE[kind]}
          </span>
          <span className="flex-1 truncate">{session.title || `Session ${session.id.slice(0, 6)}`}</span>
        </button>

        {/* Delete controls — revealed on hover/focus-within */}
        {deleteState === 'idle' ? (
          <button
            type="button"
            aria-label="Delete session"
            onClick={handleDeleteClick}
            className={cn(
              'flex-shrink-0 rounded p-0.5 text-[var(--fg-dim)] transition-colors',
              'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
              'hover:text-[var(--destructive,#e85535)]',
            )}
          >
            <Trash2 className="size-3.5" strokeWidth={1.75} />
          </button>
        ) : (
          <span className="flex flex-shrink-0 items-center gap-1">
            <button
              type="button"
              aria-label="Confirm delete"
              onClick={(e) => void handleConfirmDelete(e)}
              className="rounded px-1.5 py-px font-code text-[9px] text-[var(--destructive,#e85535)] hover:bg-[rgba(232,85,53,0.12)] transition-colors"
            >
              Delete?
            </button>
            <button
              type="button"
              aria-label="Cancel delete"
              onClick={handleCancelDelete}
              className="rounded px-1.5 py-px font-code text-[9px] text-[var(--fg-dim)] hover:text-[var(--foreground)] transition-colors"
            >
              Cancel
            </button>
          </span>
        )}
      </div>
    </li>
  );
}

function SessionsSection() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions, refresh } = useSessionList();
  const setNewSessionOpen = useSetAtom(newSessionModalOpenAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const [searchQuery, setSearchQuery] = useState('');
  const [isOpen, setIsOpen] = useAtom(sessionsSectionOpenAtom);

  if (!sessions.length) return null;

  const activeId = location.pathname.startsWith('/chat/')
    ? location.pathname.slice('/chat/'.length)
    : null;

  const showSearch = sessions.length > SESSIONS_VISIBLE_CAP;

  const filteredSessions = (() => {
    if (showSearch && searchQuery.trim()) {
      const term = searchQuery.toLowerCase();
      return sessions.filter(
        (s) =>
          (s.title ?? '').toLowerCase().includes(term) ||
          s.id.toLowerCase().includes(term),
      );
    }
    return sessions.slice(0, SESSIONS_VISIBLE_CAP);
  })();

  return (
    <div>
      {/* Collapsible eyebrow */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        className="flex w-full items-center px-4.5 pt-3.5 pb-1 font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--fg-dim)] hover:text-[var(--fg-2)] transition-colors"
      >
        <ChevronRight
          className={cn(
            'mr-1 size-3 flex-shrink-0 transition-transform duration-150',
            isOpen && 'rotate-90',
          )}
          strokeWidth={1.75}
        />
        Sessions
        <span className="ml-auto font-medium tracking-[0.1em]">{sessions.length}</span>
        <span
          role="none"
          onClick={(e) => {
            e.stopPropagation();
            setNewSessionOpen(true);
          }}
          className="ml-1.5 grid size-4.5 cursor-pointer place-items-center rounded bg-transparent text-[var(--fg-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          aria-label="Add session"
        >
          <Plus className="size-3" />
        </span>
      </button>

      {isOpen && (
        <>
          {showSearch && (
            <div className="px-2.5 pb-1">
              <input
                type="search"
                aria-label="Search sessions"
                placeholder="Filter sessions"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={cn(
                  'w-full rounded border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-1',
                  'font-code text-[11px] text-[var(--foreground)] placeholder:text-[var(--fg-dim)]',
                  'outline-none focus-visible:border-[var(--primary)] focus-visible:ring-1 focus-visible:ring-[var(--primary)]',
                )}
              />
            </div>
          )}

          <ul role="list" className="px-2.5 pb-1">
            {filteredSessions.map((s) => (
              <SessionRow
                key={s.id}
                session={s}
                active={s.id === activeId}
                onNavigate={(id) => navigate(`/chat/${id}`)}
                onDeleted={() => void refresh()}
              />
            ))}
          </ul>

          {sessions.length >= VIEW_ALL_SESSIONS_MIN && (
            <div className="px-2.5 pb-1.5">
              <button
                type="button"
                onClick={() => setSessionPickerOpen(true)}
                className={cn(
                  'flex w-full items-center gap-1 rounded px-2.5 py-1 font-code text-[11px]',
                  'text-[var(--fg-dim)] transition-colors hover:text-[var(--foreground)]',
                )}
              >
                View all sessions
                <ChevronRight className="size-3" strokeWidth={1.75} />
              </button>
            </div>
          )}
        </>
      )}

      <hr className="mx-4.5 border-t border-[var(--border-subtle)]" />
    </div>
  );
}

/**
 * Tasks section — grouped by status (Backlog → In Progress → Review → Done).
 * Each task row expands to show worker / reviewer sub-sessions fetched lazily.
 */
function TasksSection() {
  const tasks = useAtomValue(tasksAtom);
  const activeProject = useActiveProject();
  const [isOpen, setIsOpen] = useAtom(tasksSectionOpenAtom);
  // Per-task expansion state — no atom needed, local to this component
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // Cached sub-sessions per task — populated on expand
  const [taskSessions, setTaskSessions] = useState<Record<string, TaskSessionResponse[]>>({});

  const grouped = COLUMN_ORDER.map((status) => ({
    status,
    label: STATUS_LABELS[status],
    tasks: tasks.filter((t) => t.status === status),
  })).filter((g) => g.tasks.length > 0);

  const toggleExpand = useCallback(
    async (taskId: string) => {
      const next = !expanded[taskId];
      setExpanded((prev) => ({ ...prev, [taskId]: next }));
      if (next && !taskSessions[taskId]) {
        try {
          const sessions = await fetchTaskSessionsCached(taskId);
          setTaskSessions((prev) => ({ ...prev, [taskId]: sessions }));
        } catch {
          // Silently ignore — the chevron just won't expand content
        }
      }
    },
    [expanded, taskSessions],
  );

  return (
    <div className="flex-1 overflow-y-auto px-2.5 pb-2.5" role="navigation" aria-label="Tasks">
      {/* Collapsible eyebrow */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        className="flex w-full items-center px-4 pt-3.5 pb-1.5 font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--fg-dim)] hover:text-[var(--fg-2)] transition-colors"
      >
        <ChevronRight
          className={cn(
            'mr-1 size-3 flex-shrink-0 transition-transform duration-150',
            isOpen && 'rotate-90',
          )}
          strokeWidth={1.75}
        />
        Tasks
        <span className="ml-auto font-medium tracking-[0.1em]">{tasks.length}</span>
      </button>

      {isOpen && (
        <>
          {!activeProject || tasks.length === 0 ? (
            <p className="px-4 py-1.5 italic text-[12px] text-[var(--fg-dim)]">
              No tasks · press <kbd className="rounded border border-[var(--border)] px-1.5 py-px font-code text-[10px] text-[var(--fg-dim)]">N</kbd>
            </p>
          ) : (
            grouped.map(({ status, label, tasks: statusTasks }) => (
              <div key={status} className="mt-1">
                <div className="px-4 py-0.5 font-code text-[9.5px] font-semibold uppercase tracking-[0.2em] text-[var(--fg-dim)] opacity-60">
                  {label}
                </div>
                <ul role="list" className="flex flex-col gap-px pb-0.5">
                  {statusTasks.map((t) => (
                    <SidebarTaskRow
                      key={t.id}
                      task={t}
                      isExpanded={!!expanded[t.id]}
                      subSessions={taskSessions[t.id] ?? null}
                      onToggleExpand={toggleExpand}
                    />
                  ))}
                </ul>
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}

interface TaskRowProps {
  task: WireTask;
  isExpanded: boolean;
  subSessions: TaskSessionResponse[] | null;
  onToggleExpand: (taskId: string) => void;
}

function SidebarTaskRow({ task, isExpanded, subSessions, onToggleExpand }: TaskRowProps) {
  const navigate = useNavigate();

  // Worker / reviewer sessions filtered through the narrower
  const laneSessions = (subSessions ?? []).filter(
    (s) => taskSessionLane(s) === 'worker' || taskSessionLane(s) === 'reviewer',
  );
  // Show the caret if we have confirmed sessions OR haven't loaded yet (null = unloaded)
  // We show it optimistically; on load if no lane sessions it becomes noop
  const hasLaneSessions = laneSessions.length > 0;
  const showCaret = hasLaneSessions || subSessions === null;

  const handleRowClick = () => navigate(`/task/${task.id}`);

  const handleRunClick = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await apiClient.runTask(task.id);
        toast.success('Task started');
      } catch {
        toast.error('Failed to start task');
      }
    },
    [task.id],
  );

  const handleOpenClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigate(`/task/${task.id}`);
  };

  const handleCaretClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleExpand(task.id);
  };

  return (
    <li>
      <div className="group relative">
        <button
          type="button"
          onClick={handleRowClick}
          aria-label={task.title}
          className="flex w-full select-none items-center gap-2 rounded px-2.5 py-1.5 text-left font-ui text-[12.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--fg-2)]"
        >
          <span
            className={cn(
              'size-1.5 flex-shrink-0 rounded-full',
              STATUS_DOT[task.status] ?? 'bg-[var(--fg-dim)]',
            )}
          />
          <span className="flex-1 truncate">{task.title}</span>

          {/* Hover action: Run (backlog) or Open (other) */}
          <span
            className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity"
            onClick={(e) => e.stopPropagation()}
          >
            {task.status === 'BACKLOG' ? (
              <button
                type="button"
                aria-label="Run"
                onClick={handleRunClick}
                className="rounded p-0.5 text-[var(--fg-dim)] hover:text-[var(--kagan-rail-running)] transition-colors"
              >
                <Play className="size-3" strokeWidth={1.75} />
              </button>
            ) : (
              <button
                type="button"
                aria-label="Open"
                onClick={handleOpenClick}
                className="rounded p-0.5 text-[var(--fg-dim)] hover:text-[var(--foreground)] transition-colors"
              >
                <ExternalLink className="size-3" strokeWidth={1.75} />
              </button>
            )}
          </span>

          {/* Expansion caret — right edge, shown when sessions exist or not yet loaded */}
          {showCaret && (
            <button
              type="button"
              aria-label={isExpanded ? 'Collapse sessions' : 'Expand sessions'}
              onClick={handleCaretClick}
              className="ml-0.5 flex-shrink-0 rounded p-0.5 text-[var(--fg-dim)] hover:text-[var(--foreground)] transition-colors"
            >
              <ChevronDown
                className={cn(
                  'size-3 transition-transform duration-150',
                  isExpanded ? 'rotate-0' : '-rotate-90',
                )}
                strokeWidth={1.75}
              />
            </button>
          )}
        </button>

        {/* Sub-session rows — indented child list */}
        {isExpanded && hasLaneSessions && (
          <ul role="list" className="pl-[18px] pb-0.5">
            {laneSessions.map((s) => (
              <TaskSubSessionRow key={s.id} session={s} taskId={task.id} />
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

interface TaskSubSessionRowProps {
  session: TaskSessionResponse;
  taskId: string;
}

function TaskSubSessionRow({ session, taskId }: TaskSubSessionRowProps) {
  const navigate = useNavigate();
  const lane = taskSessionLane(session);
  const isRunning = session.status === 'running';

  const shortId = session.id.slice(0, 6);
  const label = shortId ? `Session ${shortId}` : session.id;

  const handleClick = () => {
    navigate(`/task/${taskId}?lane=${lane ?? 'worker'}`);
  };

  return (
    <li>
      <button
        type="button"
        onClick={handleClick}
        aria-label={`${lane === 'worker' ? 'Worker' : 'Reviewer'} session ${shortId}`}
        className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left font-ui text-[12px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--fg-2)]"
      >
        {/* Lane badge W / R */}
        <span
          className={cn(
            'flex-shrink-0 rounded px-1 py-px font-code text-[9px] uppercase',
            lane === 'worker'
              ? 'bg-[rgba(212,168,75,0.18)] text-[var(--primary-soft)]'
              : 'bg-[rgba(194,124,78,0.18)] text-[var(--kagan-rail-review)]',
          )}
        >
          {lane === 'worker' ? 'W' : 'R'}
        </span>
        <span className="flex-1 truncate">{label}</span>
        {/* Status dot */}
        <span
          className={cn(
            'flex-shrink-0 size-1.5 rounded-full',
            isRunning
              ? 'bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)] animate-pulse'
              : 'bg-[var(--kagan-rail-idle)] opacity-40',
          )}
        />
      </button>
    </li>
  );
}

function SidebarFoot() {
  const versionRef = useRef<string | null>(null);
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (versionRef.current !== null) return;
    let cancelled = false;
    import('@/lib/api/client').then(({ apiClient }) => {
      apiClient
        .getHealth()
        .then((res) => {
          if (cancelled || !containerRef.current) return;
          versionRef.current = res.version;
          containerRef.current.textContent = `v${res.version}`;
        })
        .catch(() => {});
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex items-center gap-2 border-t border-[var(--border)] px-3 py-2.5">
      <Link
        to="/settings"
        className="flex flex-1 items-center gap-2.5 rounded-md px-2.5 py-1.5 font-ui text-[13px] text-[var(--fg-2)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
      >
        <SettingsGlyphSm />
        Settings
      </Link>
      <a
        href="https://pypi.org/project/kagan/"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-[var(--border)] bg-transparent px-2 py-1 font-code text-[11px] text-[var(--fg-dim)] transition-colors hover:border-[var(--panel-border-strong)] hover:text-[var(--foreground)]"
        title="Kagan on PyPI"
      >
        <span className="font-semibold text-[var(--primary-soft)]">ᘚᘛ</span>
        <span ref={containerRef}>…</span>
      </a>
    </div>
  );
}

function SettingsGlyphSm() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
