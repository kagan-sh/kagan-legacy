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
  CircleQuestionMark,
  Cog,
  LayoutDashboard,
  MessageSquareText,
  Home,
  Plus,
  Settings,
  SunMoon,
  Workflow,
} from 'lucide-react';
import { store } from '@/lib/atoms/store';
import { boardDialogAtom } from '@/lib/atoms/board';
import { setThemeModeAtom, themeModeAtom } from '@/lib/atoms/theme';
import { registerCommand } from '@/lib/commands/registry';
import type { CommandAction } from '@/lib/commands/types';

function toggleTheme(): void {
  const current = store.get(themeModeAtom);
  const next = current === 'dark' ? 'light' : 'dark';
  store.set(setThemeModeAtom, next);
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

  // ─── Create ──────────────────────────────────────────────────────────────
  {
    id: 'create-task',
    title: 'Create task',
    section: 'Create',
    keywords: ['new', 'task', 'add'],
    icon: Plus,
    handler: () => store.set(boardDialogAtom, { kind: 'create' }),
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
    icon: CircleQuestionMark,
    shortcut: ['?'],
    handler: ({ toast }) => toast?.('Keyboard shortcuts panel not yet available.'),
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
