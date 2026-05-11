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
import { AgentCliPopover } from '@/components/shell/popovers/agent-cli-popover';
import { ProjectSwitcherPopover } from '@/components/shell/popovers/project-switcher-popover';
import { MobileTabs } from '@/components/shell/mobile-tabs';
import { CreateProjectDialog } from '@/components/layout/create-project-dialog';
import { AddRepoDialog } from '@/components/layout/add-repo-dialog';
import { useEventStream } from '@/lib/hooks/use-event-stream';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { apiClient } from '@/lib/api/client';
import {
  fetchTasksAtom,
  projectSwitchVersionAtom,
  boardDialogAtom,
} from '@/lib/atoms/board';
import {
  spotlightOpenAtom,
  sidebarCollapsedAtom,
  createProjectDialogOpenAtom,
  addRepoDialogOpenAtom,
} from '@/lib/atoms/shell';
import { integrationImportOpenAtom } from '@/lib/atoms/ui';
import { useActiveProject } from '@/lib/hooks/use-active-project';
import { Spinner } from '@/components/ui/spinner';

function ShellLayout() {
  useEventStream();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const setSpotlightOpen = useSetAtom(spotlightOpenAtom);
  const setSidebarCollapsed = useSetAtom(sidebarCollapsedAtom);
  const setBoardDialog = useSetAtom(boardDialogAtom);
  const setProjectVersion = useSetAtom(projectSwitchVersionAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [integrationImportOpen, setIntegrationImportOpen] = useAtom(integrationImportOpenAtom);
  const [createProjectOpen, setCreateProjectOpen] = useAtom(createProjectDialogOpenAtom);
  const [addRepoOpen, setAddRepoOpen] = useAtom(addRepoDialogOpenAtom);
  const activeProject = useActiveProject();
  const [projectChecked, setProjectChecked] = useState(false);
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  // Auto-collapse sidebar on mobile breakpoint
  useEffect(() => {
    setSidebarCollapsed(isMobile);
  }, [isMobile, setSidebarCollapsed]);

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

      // ⌘⇧P opens spotlight (VS Code muscle-memory alias of ⌘K)
      if (meta && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        setSpotlightOpen(true);
        return;
      }
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
            className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--bg)] pb-14 md:pb-0"
          >
            <Outlet />
          </main>
        </div>
      </div>

      <MobileTabs />
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
      <AgentCliPopover />
      <ProjectSwitcherPopover />

      {/* Project management dialogs wired to shell atoms */}
      <CreateProjectDialog
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        onCreated={() => setCreateProjectOpen(false)}
      />
      <AddRepoDialog
        open={addRepoOpen}
        onOpenChange={setAddRepoOpen}
        projectId={activeProject?.id}
        onAdded={() => {
          setAddRepoOpen(false);
          setProjectVersion((v) => v + 1);
        }}
      />
    </>
  );
}

export const Component = ShellLayout;
