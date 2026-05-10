import { useEffect, useRef, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { useAtom, useSetAtom } from 'jotai';
import { SkipLink } from '@/components/a11y/skip-link';
import { TitleBar } from '@/components/shell/title-bar';
import { Sidebar } from '@/components/shell/sidebar';
import { Spotlight } from '@/components/shell/spotlight';
import { NewSessionDialog } from '@/components/shell/new-session-dialog';
import { HelpOverlay } from '@/components/layout/help-overlay';
import { SessionPicker } from '@/components/session/session-picker';
import { IntegrationImportDialog } from '@/components/board/integration-import-dialog';
import { AgentsPopover } from '@/components/shell/popovers/agents-popover';
import { ActivityPopover } from '@/components/shell/popovers/activity-popover';
import { FilterPopover } from '@/components/shell/popovers/filter-popover';
import {
  ConnectedMorePopover,
  ConnectedAdvancePopover,
} from '@/components/shell/popovers/connected';
import { PermissionsPopover } from '@/components/shell/popovers/permissions-popover';
import { ModelPopover } from '@/components/shell/popovers/model-popover';
import { LocalityPopover } from '@/components/shell/popovers/locality-popover';
import { BranchPopover } from '@/components/shell/popovers/branch-popover';
import { useEventStream } from '@/lib/hooks/use-event-stream';
import { apiClient } from '@/lib/api/client';
import {
  fetchTasksAtom,
  projectSwitchVersionAtom,
  boardDialogAtom,
} from '@/lib/atoms/board';
import {
  spotlightOpenAtom,
  sidebarCollapsedAtom,
} from '@/lib/atoms/shell';
import { integrationImportOpenAtom } from '@/lib/atoms/ui';
import { Spinner } from '@/components/ui/spinner';

function ShellLayout() {
  useEventStream();
  const navigate = useNavigate();
  const setSpotlightOpen = useSetAtom(spotlightOpenAtom);
  const setSidebarCollapsed = useSetAtom(sidebarCollapsedAtom);
  const setBoardDialog = useSetAtom(boardDialogAtom);
  const setProjectVersion = useSetAtom(projectSwitchVersionAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [integrationImportOpen, setIntegrationImportOpen] = useAtom(integrationImportOpenAtom);
  const [projectChecked, setProjectChecked] = useState(false);
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProjects()
      .then((projects) => {
        if (cancelled) return;
        const active = projects.find((p) => p.active);
        if (active) {
          setProjectChecked(true);
          setProjectVersion((v) => v + 1);
          fetchTasks();
        } else {
          navigateRef.current('/welcome', { replace: true });
        }
      })
      .catch(() => {
        if (!cancelled) navigateRef.current('/welcome', { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [fetchTasks, setProjectVersion]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName || '').toLowerCase();
      const inField = tag === 'input' || tag === 'textarea' || tag === 'select';

      const meta = e.metaKey || e.ctrlKey;

      // ⌘K opens spotlight always
      if (meta && e.key === 'k') {
        e.preventDefault();
        setSpotlightOpen(true);
        return;
      }
      // ⌘\ toggles sidebar
      if (meta && e.key === '\\') {
        e.preventDefault();
        setSidebarCollapsed((v) => !v);
        return;
      }
      // ⌘1 / ⌘2 switch tabs
      if (meta && e.key === '1') {
        e.preventDefault();
        navigateRef.current('/chat');
        return;
      }
      if (meta && e.key === '2') {
        e.preventDefault();
        navigateRef.current('/board');
        return;
      }
      if (inField) return;
      // N opens new task modal
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        setBoardDialog({ kind: 'create' });
        return;
      }
      // / opens spotlight
      if (e.key === '/') {
        e.preventDefault();
        setSpotlightOpen(true);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [setSpotlightOpen, setSidebarCollapsed, setBoardDialog]);

  if (!projectChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--surface-0)]">
        <Spinner className="size-8 text-[var(--muted-foreground)]" />
      </div>
    );
  }

  return (
    <>
      <SkipLink>Skip to content</SkipLink>
      <div className="kg-shell-scanline grid h-screen grid-rows-[44px_1fr] overflow-hidden bg-[var(--bg)]">
        <TitleBar />
        <div className="flex min-h-0 min-w-0">
          <Sidebar />
          <main
            id="main-content"
            className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg)]"
          >
            <Outlet />
          </main>
        </div>
      </div>

      <Spotlight />
      <NewSessionDialog />
      <SessionPicker />
      <HelpOverlay />
      <IntegrationImportDialog
        open={integrationImportOpen}
        onOpenChange={setIntegrationImportOpen}
      />
      {/* Shell popovers — rendered at fixed position outside the grid */}
      <AgentsPopover />
      <ActivityPopover />
      <FilterPopover />
      <ConnectedMorePopover />
      <ConnectedAdvancePopover />
      <PermissionsPopover />
      <ModelPopover />
      <LocalityPopover />
      <BranchPopover />
    </>
  );
}

export const Component = ShellLayout;
