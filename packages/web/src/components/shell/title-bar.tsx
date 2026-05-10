import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { ChevronLeft, ChevronRight, Clock, Kanban, MessagesSquare, Moon, PanelLeft, Search, Sun } from 'lucide-react';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { resolvedThemeAtom, setThemeModeAtom } from '@/lib/atoms/theme';
import { sidebarCollapsedAtom, spotlightOpenAtom } from '@/lib/atoms/shell';
import { useShellPopover } from '@/components/shell/popover';
import { useActiveProject } from '@/lib/hooks/use-active-project';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';

const KAGAN_GLYPH = 'ᘚᘛ';

function isHotKey(prefix: 'cmd' | 'ctrl', e: KeyboardEvent): boolean {
  return prefix === 'cmd' ? e.metaKey : e.ctrlKey;
}

function shellTabFor(pathname: string): 'workspace' | 'kanban' {
  if (pathname.startsWith('/board') || pathname.startsWith('/task')) return 'kanban';
  return 'workspace';
}

export function TitleBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const sseConnected = useAtomValue(sseConnectedAtom);
  const setSpotlightOpen = useSetAtom(spotlightOpenAtom);
  const [sidebarCollapsed, setSidebarCollapsed] = useAtom(sidebarCollapsedAtom);
  const resolvedTheme = useAtomValue(resolvedThemeAtom);
  const setThemeMode = useSetAtom(setThemeModeAtom);
  const activeProject = useActiveProject();
  const [agentCount, setAgentCount] = useState<number | null>(null);
  const activityPopover = useShellPopover('activity', 'right');

  const tab = shellTabFor(location.pathname);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getChatAgents()
      .then((res) => {
        if (cancelled) return;
        setAgentCount(res.backends.length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleTheme = () => {
    setThemeMode(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <header
      role="banner"
      className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-[var(--border)] bg-[linear-gradient(180deg,var(--surface-2),var(--surface-1))] px-3.5"
      style={{ height: 44, position: 'relative', zIndex: 20 }}
    >
      <div className="flex items-center gap-2.5">
        <div className="flex gap-2 mr-1" aria-hidden="true">
          <span className="size-3 rounded-full bg-[#ff5f57] border border-black/40" />
          <span className="size-3 rounded-full bg-[#febc2e] border border-black/40" />
          <span className="size-3 rounded-full bg-[#28c840] border border-black/40" />
        </div>

        <TitleBarIconButton
          label="Toggle sidebar"
          shortcut="⌘\\"
          active={sidebarCollapsed}
          onClick={() => setSidebarCollapsed((v) => !v)}
        >
          <PanelLeft className="size-[15px]" />
        </TitleBarIconButton>

        <TitleBarIconButton label="Back" onClick={() => navigate(-1)}>
          <ChevronLeft className="size-[15px]" />
        </TitleBarIconButton>

        <TitleBarIconButton label="Forward" onClick={() => navigate(1)}>
          <ChevronRight className="size-[15px]" />
        </TitleBarIconButton>

        <div className="ml-1.5 flex items-center gap-2.5 font-code text-[12px] text-[var(--muted-foreground)]">
          <span
            className="font-semibold tracking-[-0.04em] text-[14px] text-[var(--primary)]"
            style={{ fontFeatureSettings: '"liga" 0' }}
          >
            {KAGAN_GLYPH}
          </span>
          <span className="text-[var(--fg-dim)] truncate max-w-[260px]" title={activeProject?.name ?? ''}>
            {activeProject ? `~/${activeProject.name}` : '—'}
          </span>
        </div>
      </div>

      <ShellTabs tab={tab} />

      <div className="flex items-center justify-end gap-2.5">
        <button
          type="button"
          onClick={() => setSpotlightOpen(true)}
          className="search-trigger inline-flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--panel-border-strong)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          aria-label="Search tasks and commands"
        >
          <Search className="size-[13px]" />
          <span>Search tasks…</span>
          <kbd className="ml-1 rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px font-code text-[9.5px] text-[var(--fg-dim)]">⌘K</kbd>
        </button>

        <span
          title={`Daemon ${sseConnected ? 'connected' : 'offline'}`}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-code text-[11px]',
            sseConnected
              ? 'border-[rgba(212,168,75,0.20)] bg-[rgba(212,168,75,0.08)] text-[var(--primary-soft)]'
              : 'border-[rgba(232,85,53,0.22)] bg-[rgba(232,85,53,0.08)] text-[#e85535]',
          )}
        >
          <span
            className={cn('size-1.5 rounded-full', sseConnected ? 'bg-[#3fb58e] shadow-[0_0_8px_#3fb58e]' : 'bg-[#e85535]')}
          />
          daemon{agentCount !== null ? ` · ${agentCount} agents` : ''}
        </span>

        <TitleBarIconButton
          label="Activity"
          active={activityPopover.isOpen}
          onClick={activityPopover.openFromEvent}
        >
          <Clock className="size-[15px]" />
        </TitleBarIconButton>

        <Link
          to="/settings"
          aria-label="Settings"
          className="rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
        >
          <SettingsGlyph />
        </Link>

        <TitleBarIconButton
          label={resolvedTheme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          shortcut="⌘⇧L"
          onClick={toggleTheme}
        >
          {resolvedTheme === 'dark' ? <Sun className="size-[15px]" /> : <Moon className="size-[15px]" />}
        </TitleBarIconButton>
      </div>
    </header>
  );
}

function ShellTabs({ tab }: { tab: 'workspace' | 'kanban' }) {
  return (
    <nav
      aria-label="Workspace tabs"
      className="relative inline-flex items-center rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-[3px]"
      data-tab={tab}
    >
      <span
        aria-hidden
        className="absolute top-[3px] bottom-[3px] w-[calc(50%_-_3px)] rounded-[5px] border border-[var(--panel-border)] bg-[var(--surface-3)] shadow-[0_1px_2px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.04)] transition-[left] duration-200 ease-out"
        style={{ left: tab === 'workspace' ? 3 : '50%' }}
      />
      <Link
        to="/chat"
        className={cn(
          'relative z-[2] inline-flex items-center gap-2 rounded-[5px] px-3.5 py-1 font-ui text-[12px] font-medium transition-colors',
          tab === 'workspace' ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)]',
        )}
        aria-current={tab === 'workspace' ? 'page' : undefined}
        title="Workspace · ⌘1"
      >
        <MessagesSquare className="size-[13px]" />
        Workspace
      </Link>
      <Link
        to="/board"
        className={cn(
          'relative z-[2] inline-flex items-center gap-2 rounded-[5px] px-3.5 py-1 font-ui text-[12px] font-medium transition-colors',
          tab === 'kanban' ? 'text-[var(--foreground)]' : 'text-[var(--muted-foreground)]',
        )}
        aria-current={tab === 'kanban' ? 'page' : undefined}
        title="Kanban · ⌘2"
      >
        <Kanban className="size-[13px]" />
        Kanban
      </Link>
    </nav>
  );
}

interface IconButtonProps {
  label: string;
  shortcut?: string;
  active?: boolean;
  onClick: React.MouseEventHandler<HTMLButtonElement>;
  children: React.ReactNode;
}

function TitleBarIconButton({ label, shortcut, active, onClick, children }: IconButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={shortcut ? `${label} (${shortcut})` : label}
      aria-label={label}
      aria-pressed={active}
      data-active={active ? 'true' : 'false'}
      className={cn(
        'grid size-7 cursor-pointer place-items-center rounded-md border-0 bg-transparent text-[var(--muted-foreground)] transition-colors',
        'hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
        active && 'bg-[rgba(212,168,75,0.10)] text-[var(--primary-soft)]',
      )}
    >
      {children}
    </button>
  );
}

function SettingsGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.75">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

// Re-export hot key resolver (kept private by default)
export const __test__ = { isHotKey };
