import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useAtomValue, useSetAtom } from 'jotai';
import {
  Activity,
  ChevronDown,
  Folder,
  LayoutGrid,
  MessageSquarePlus,
  Plus,
} from 'lucide-react';
import { useActiveProject } from '@/lib/hooks/use-active-project';
import { useSessionList } from '@/lib/hooks/use-session-list';
import { apiClient } from '@/lib/api/client';
import { boardDialogAtom, projectSwitchVersionAtom, tasksAtom } from '@/lib/atoms/board';
import { sidebarCollapsedAtom, newSessionModalOpenAtom } from '@/lib/atoms/shell';
import { COLUMN_ORDER } from '@/lib/utils/constants';
import { SESSION_KIND_BADGE, sessionKind } from '@/lib/sessions/kind';
import type { WireProject, WireTask } from '@kagan/shared-api-client';
import { cn } from '@/lib/utils';

const STATUS_DOT: Record<string, string> = {
  BACKLOG: 'bg-[var(--kagan-rail-idle)] opacity-50',
  IN_PROGRESS: 'bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)] animate-pulse',
  REVIEW: 'bg-[var(--kagan-rail-review)]',
  DONE: 'bg-[var(--kagan-rail-running)] opacity-40',
};

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
        <ProjectsSection />
        <SidebarFoot />
      </div>
    </aside>
  );
}

function SidebarTop() {
  const setBoardDialog = useSetAtom(boardDialogAtom);
  const setNewSessionOpen = useSetAtom(newSessionModalOpenAtom);

  return (
    <div className="flex flex-col gap-px px-3 pt-3 pb-1.5">
      <SidebarLink
        kind="primary"
        icon={<Plus className="size-[15px]" />}
        kbd="N"
        onClick={() => setBoardDialog({ kind: 'create' })}
      >
        New task
      </SidebarLink>
      <SidebarLink
        icon={<MessageSquarePlus className="size-[15px]" />}
        onClick={() => setNewSessionOpen(true)}
      >
        New session
      </SidebarLink>
      <SidebarLink icon={<LayoutGrid className="size-[15px]" />} to="/board">
        Board
      </SidebarLink>
      <SidebarLink icon={<Activity className="size-[15px]" />} to="/chat">
        Activity
      </SidebarLink>
    </div>
  );
}

interface LinkProps {
  icon: React.ReactNode;
  kind?: 'primary';
  kbd?: string;
  to?: string;
  onClick?: () => void;
  children: React.ReactNode;
}

function SidebarLink({ icon, kind, kbd, to, onClick, children }: LinkProps) {
  const className = cn(
    'flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-[7px] text-left font-ui text-[13px] text-[var(--fg-2)] transition-colors',
    'hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
    kind === 'primary' && 'text-[var(--primary-soft)] [&_svg]:text-[var(--primary-soft)]',
  );
  const inner = (
    <>
      <span className="flex-shrink-0 text-[var(--muted-foreground)]">{icon}</span>
      <span className="flex-1 truncate">{children}</span>
      {kbd ? (
        <kbd className="ml-auto rounded border border-[var(--border)] px-1.5 py-px font-code text-[10px] text-[var(--fg-dim)]">{kbd}</kbd>
      ) : null}
    </>
  );
  if (to) {
    return (
      <Link to={to} className={className}>
        {inner}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {inner}
    </button>
  );
}

function SessionsSection() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessions } = useSessionList();
  const setNewSessionOpen = useSetAtom(newSessionModalOpenAtom);

  if (!sessions.length) return null;

  const activeId = location.pathname.startsWith('/chat/') ? location.pathname.slice('/chat/'.length) : null;

  return (
    <div>
      <div className="flex items-center px-4.5 pt-3.5 pb-1 font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--fg-dim)]">
        Sessions
        <span className="ml-auto font-medium tracking-[0.1em]">{sessions.length}</span>
        <button
          type="button"
          onClick={() => setNewSessionOpen(true)}
          className="ml-1.5 grid size-4.5 cursor-pointer place-items-center rounded bg-transparent text-[var(--fg-dim)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          aria-label="Add session"
        >
          <Plus className="size-3" />
        </button>
      </div>
      <ul role="list" className="px-2.5 pb-1">
        {sessions.slice(0, 8).map((s) => {
          const kind = sessionKind(s);
          if (kind !== 'orchestrator' && kind !== 'general') return null;
          const active = s.id === activeId;
          const orchestrator = kind === 'orchestrator';
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => navigate(`/chat/${s.id}`)}
                data-active={active ? 'true' : 'false'}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left font-ui text-[12.5px] text-[var(--muted-foreground)] transition-colors',
                  'hover:bg-[var(--surface-2)] hover:text-[var(--fg-2)]',
                  active && 'bg-[var(--surface-2)] text-[var(--foreground)] shadow-[inset_2px_0_0_var(--primary)]',
                )}
              >
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
                <span className="flex-1 truncate">{s.title || `Session ${s.id.slice(0, 6)}`}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <hr className="mx-4.5 border-t border-[var(--border)]" />
    </div>
  );
}

function ProjectsSection() {
  const activeProject = useActiveProject();
  const tasks = useAtomValue(tasksAtom);
  const projectVersion = useAtomValue(projectSwitchVersionAtom);
  const [projects, setProjects] = useState<WireProject[]>([]);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProjects()
      .then((res) => {
        if (cancelled) return;
        setProjects(res);
        const initial: Record<string, boolean> = {};
        res.forEach((p) => {
          initial[p.id] = p.id === activeProject?.id;
        });
        setOpen(initial);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id, projectVersion]);

  const orderedTasks = useMemo(
    () =>
      COLUMN_ORDER.flatMap((status) => tasks.filter((t) => t.status === status)),
    [tasks],
  );

  return (
    <div className="flex-1 overflow-y-auto px-2.5 pb-2.5" role="navigation" aria-label="Projects">
      <div className="flex items-center px-4 pt-3.5 pb-1.5 font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--fg-dim)]">
        Projects <span className="ml-auto font-medium tracking-[0.1em]">{projects.length}</span>
      </div>
      {projects.map((p) => {
        const isActive = p.id === activeProject?.id;
        const projectTasks = isActive ? orderedTasks : [];
        const isOpen = open[p.id] ?? isActive;
        return (
          <div key={p.id} data-open={isOpen ? 'true' : 'false'} className="mt-1.5">
            <button
              type="button"
              onClick={() => setOpen((m) => ({ ...m, [p.id]: !m[p.id] }))}
              className="flex w-full select-none items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left font-ui text-[12.5px] font-medium text-[var(--fg-2)] hover:bg-[var(--surface-2)]"
            >
              <Folder className="size-[14px] text-[var(--muted-foreground)]" />
              {p.name}
              <span className="ml-1 font-code text-[10px] text-[var(--fg-dim)]">{projectTasks.length}</span>
              <ChevronDown
                className={cn('ml-auto size-2.5 text-[var(--fg-dim)] transition-transform', !isOpen && '-rotate-90')}
              />
            </button>
            {isOpen && isActive ? (
              projectTasks.length === 0 ? (
                <div className="px-5.5 pb-1.5 pt-1 italic text-[12px] text-[var(--fg-dim)]">No tasks</div>
              ) : (
                <ul role="list" className="flex flex-col gap-px py-0.5 pl-5.5 pr-1">
                  {projectTasks.map((t) => (
                    <SidebarTaskRow key={t.id} task={t} />
                  ))}
                </ul>
              )
            ) : isOpen && !isActive ? (
              <div className="px-5.5 pb-1.5 pt-1 italic text-[12px] text-[var(--fg-dim)]">Switch project to view tasks</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function SidebarTaskRow({ task }: { task: WireTask }) {
  const navigate = useNavigate();
  return (
    <li>
      <button
        type="button"
        onClick={() => navigate(`/task/${task.id}`)}
        className="flex w-full select-none items-center gap-2 rounded px-2.5 py-1.5 text-left font-ui text-[12.5px] text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--fg-2)]"
      >
        <span className={cn('size-1.5 flex-shrink-0 rounded-full', STATUS_DOT[task.status] ?? 'bg-[var(--fg-dim)]')} />
        <span className="flex-1 truncate">{task.title}</span>
      </button>
    </li>
  );
}

function SidebarFoot() {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getHealth()
      .then((res) => {
        if (cancelled) return;
        setVersion(res.version);
      })
      .catch(() => {});
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
        <span>{version ? `v${version}` : '…'}</span>
      </a>
    </div>
  );
}

function SettingsGlyphSm() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
