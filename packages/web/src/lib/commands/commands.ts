/**
 * Built-in command palette actions.
 *
 * Registered once at app mount via `registerBuiltinCommands()`. Keep the list
 * flat and explicit — each command stands on its own. New commands that are
 * page-specific should register from the page itself at mount time.
 */
import {
  Bot,
  ChartBar,
  Check,
  CircleQuestionMark,
  Cog,
  Download,
  GitMerge,
  HelpCircle,
  LayoutDashboard,
  MessageSquareText,
  Home,
  PanelRight,
  Pencil,
  Play,
  Plus,
  Settings,
  Square,
  SunMoon,
  Trash2,
  Workflow,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { store } from '@/lib/atoms/store';
import { boardDialogAtom, tasksAtom } from '@/lib/atoms/board';
import { setThemeModeAtom, themeModeAtom } from '@/lib/atoms/theme';
import {
  helpOverlayOpenAtom,
  pluginImportOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import { registerCommand } from '@/lib/commands/registry';
import type { CommandAction } from '@/lib/commands/types';
import type { WireTask } from '@/lib/api/types';

function toggleTheme(): void {
  const current = store.get(themeModeAtom);
  const next = current === 'dark' ? 'light' : 'dark';
  store.set(setThemeModeAtom, next);
}

/**
 * Resolve the task id implied by the current URL.
 *
 * Kept path-based and framework-agnostic so the registry stays decoupled
 * from the router. Matches `/task/:id` and `/session/:id`.
 */
function currentTaskIdFromPath(): string | null {
  if (typeof window === 'undefined') return null;
  const path = window.location.pathname;
  const taskMatch = /^\/task\/([^/?]+)/.exec(path);
  if (taskMatch) return taskMatch[1] ?? null;
  const sessionMatch = /^\/session\/([^/?]+)/.exec(path);
  if (sessionMatch) return sessionMatch[1] ?? null;
  return null;
}

function currentTask(): WireTask | null {
  const id = currentTaskIdFromPath();
  if (!id) return null;
  return store.get(tasksAtom).find((task) => task.id === id) ?? null;
}

function hasCurrentTask(): boolean {
  return currentTask() !== null;
}

function currentTaskIsRunnable(): boolean {
  const task = currentTask();
  return Boolean(task && task.status !== 'DONE');
}

function currentTaskIsRunning(): boolean {
  return Boolean(currentTask()?.active_session);
}

function currentTaskIsInReview(): boolean {
  return currentTask()?.status === 'REVIEW';
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/**
 * All bundled commands. Exported for tests and for the (future) docs page.
 *
 * Order is not meaningful — the palette groups by `section` and fuzzy-matches
 * by title + keywords.
 */
export const BUILTIN_COMMANDS: CommandAction[] = [
  // ─── Navigate ────────────────────────────────────────────────────────────
  {
    id: 'nav-home',
    title: 'Go to Home',
    section: 'Navigate',
    keywords: ['home', 'start', 'overview'],
    icon: Home,
    handler: ({ navigate }) => navigate('/'),
  },
  {
    id: 'nav-board',
    title: 'Go to Board',
    section: 'Navigate',
    keywords: ['board', 'kanban', 'tasks'],
    icon: LayoutDashboard,
    handler: ({ navigate }) => navigate('/board'),
  },
  {
    id: 'nav-workspace',
    title: 'Go to Workspace',
    section: 'Navigate',
    keywords: ['workspace', 'sessions', 'agents'],
    icon: MessageSquareText,
    handler: ({ navigate }) => navigate('/workspace'),
  },
  {
    id: 'nav-analytics',
    title: 'Go to Analytics',
    section: 'Navigate',
    keywords: ['analytics', 'metrics', 'stats', 'charts'],
    icon: ChartBar,
    handler: ({ navigate }) => navigate('/analytics'),
  },
  {
    id: 'nav-settings',
    title: 'Go to Settings',
    section: 'Navigate',
    keywords: ['settings', 'preferences', 'config'],
    icon: Settings,
    handler: ({ navigate }) => navigate('/settings'),
  },
  {
    id: 'nav-session-switcher',
    title: 'Open Session Switcher',
    section: 'Navigate',
    keywords: ['session', 'switcher', 'picker', 'chat'],
    icon: PanelRight,
    shortcut: ['⌘', '⇧', 'K'],
    handler: () => store.set(sessionPickerOpenAtom, true),
  },
  {
    id: 'nav-task-open',
    title: 'Open current task',
    section: 'Navigate',
    keywords: ['task', 'open', 'detail'],
    icon: MessageSquareText,
    when: hasCurrentTask,
    handler: ({ navigate }) => {
      const id = currentTaskIdFromPath();
      if (id) navigate(`/task/${id}`);
    },
  },

  // ─── Create ──────────────────────────────────────────────────────────────
  {
    id: 'create-task',
    title: 'Create task',
    section: 'Create',
    keywords: ['new', 'task', 'add'],
    icon: Plus,
    handler: () => store.set(boardDialogAtom, { kind: 'create' }),
  },
  {
    id: 'create-edit-current-task',
    title: 'Edit current task',
    section: 'Create',
    keywords: ['edit', 'task', 'rename'],
    icon: Pencil,
    when: hasCurrentTask,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      store.set(boardDialogAtom, { kind: 'edit', taskId: task.id });
    },
  },
  {
    id: 'create-delete-current-task',
    title: 'Delete current task',
    section: 'Create',
    keywords: ['delete', 'remove', 'task'],
    icon: Trash2,
    when: hasCurrentTask,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      store.set(boardDialogAtom, { kind: 'delete', taskId: task.id });
    },
  },
  {
    id: 'create-github-import',
    title: 'Import from GitHub',
    section: 'Create',
    keywords: ['github', 'import', 'plugin', 'issues'],
    icon: Download,
    handler: () => store.set(pluginImportOpenAtom, true),
  },

  // ─── Run ─────────────────────────────────────────────────────────────────
  {
    id: 'run-start-current-task',
    title: 'Start current task',
    section: 'Run',
    keywords: ['start', 'run', 'agent', 'task'],
    icon: Play,
    when: currentTaskIsRunnable,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      apiClient.runTask(task.id).then(
        () => toast.success(`Starting ${task.title}`),
        (err) => toast.error(errorMessage(err, 'Failed to start task')),
      );
    },
  },
  {
    id: 'run-stop-current-task',
    title: 'Stop current task',
    section: 'Run',
    keywords: ['stop', 'cancel', 'agent', 'task'],
    icon: Square,
    when: currentTaskIsRunning,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      apiClient.cancelTask(task.id).then(
        () => toast.success(`Stopping ${task.title}`),
        (err) => toast.error(errorMessage(err, 'Failed to stop task')),
      );
    },
  },
  {
    id: 'run-review-approve',
    title: 'Approve review',
    section: 'Run',
    keywords: ['review', 'approve', 'accept'],
    icon: Check,
    when: currentTaskIsInReview,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      apiClient.reviewDecide(task.id, { action: 'approve' }).then(
        () => toast.success('Review approved'),
        (err) => toast.error(errorMessage(err, 'Failed to approve review')),
      );
    },
  },
  {
    id: 'run-review-reject',
    title: 'Reject review',
    section: 'Run',
    keywords: ['review', 'reject', 'decline'],
    icon: X,
    when: currentTaskIsInReview,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      apiClient.reviewDecide(task.id, { action: 'reject' }).then(
        () => toast.success('Review rejected'),
        (err) => toast.error(errorMessage(err, 'Failed to reject review')),
      );
    },
  },
  {
    id: 'run-review-merge',
    title: 'Merge review',
    section: 'Run',
    keywords: ['review', 'merge', 'ship'],
    icon: GitMerge,
    when: currentTaskIsInReview,
    handler: () => {
      const task = currentTask();
      if (!task) return;
      apiClient.reviewDecide(task.id, { action: 'merge' }).then(
        () => toast.success('Merging task changes'),
        (err) => toast.error(errorMessage(err, 'Failed to merge task')),
      );
    },
  },

  // ─── Settings (category deep-links) ──────────────────────────────────────
  // Uses hash fragments — the settings page may read these in a later pass.
  // For now they land on /settings, which is strictly better than nothing.
  {
    id: 'settings-workflow',
    title: 'Open Workflow settings',
    section: 'Settings',
    keywords: ['workflow', 'review', 'merge', 'planning'],
    icon: Workflow,
    handler: ({ navigate }) => navigate('/settings#workflow'),
  },
  {
    id: 'settings-agents',
    title: 'Open Agents settings',
    section: 'Settings',
    keywords: ['agents', 'backend', 'model'],
    icon: Bot,
    handler: ({ navigate }) => navigate('/settings#agents'),
  },
  {
    id: 'settings-advanced',
    title: 'Open Advanced settings',
    section: 'Settings',
    keywords: ['advanced', 'appearance', 'git', 'tooling'],
    icon: Cog,
    handler: ({ navigate }) => navigate('/settings#advanced'),
  },
  {
    id: 'toggle-theme',
    title: 'Toggle theme',
    section: 'Settings',
    keywords: ['theme', 'dark', 'light', 'appearance'],
    icon: SunMoon,
    handler: () => toggleTheme(),
  },

  // ─── Help ────────────────────────────────────────────────────────────────
  {
    id: 'help-shortcuts',
    title: 'Show keyboard shortcuts',
    section: 'Help',
    keywords: ['shortcuts', 'keys', 'bindings', 'help'],
    icon: HelpCircle,
    shortcut: ['?'],
    handler: () => store.set(helpOverlayOpenAtom, true),
  },
  {
    id: 'help-about',
    title: 'About Kagan',
    section: 'Help',
    keywords: ['about', 'version', 'docs', 'documentation'],
    icon: CircleQuestionMark,
    handler: () => store.set(helpOverlayOpenAtom, true),
  },
];

let registered = false;

/**
 * Register every built-in command. Safe to call more than once — subsequent
 * calls are no-ops. Call from the app root after atoms are ready.
 */
export function registerBuiltinCommands(): void {
  if (registered) return;
  registered = true;
  for (const action of BUILTIN_COMMANDS) {
    registerCommand(action);
  }
}

/** Test-only — allow re-registration across test cases. */
export function __resetBuiltinRegistrationForTests(): void {
  registered = false;
}
