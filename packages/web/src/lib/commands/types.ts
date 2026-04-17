/**
 * Command palette action types.
 *
 * The registry is a module-level singleton — actions are registered once at
 * app mount. Each action has a stable `id` used as the map key and as the
 * analytics handle.
 *
 * Keep this small and explicit. No discriminated unions, no conditional
 * types. If a future field needs a union, add it as its own optional field.
 */
import type { LucideIcon } from 'lucide-react';

export type CommandSection =
  | 'Navigate'
  | 'Create'
  | 'Run'
  | 'Settings'
  | 'Help';

/**
 * Context passed to every command handler. Kept intentionally minimal —
 * the palette owns these, commands consume them. Add fields only when a
 * registered command needs one.
 */
export interface CommandContext {
  /** Router navigation — use this instead of window.location. */
  navigate: (path: string) => void;
  /** Optional user-facing message — toast if provided, else no-op. */
  toast?: (message: string) => void;
}

export interface CommandAction {
  /** Stable kebab-case id. Used as map key and telemetry handle. */
  id: string;
  /** Visible label rendered in the list. */
  title: string;
  /** Grouping section heading. */
  section: CommandSection;
  /** Extra tokens that feed the fuzzy matcher (e.g. "new", "task"). */
  keywords?: string[];
  /** Optional lucide icon shown at the row's leading edge. */
  icon?: LucideIcon;
  /** Display-only shortcut hint, e.g. ["⌘", "K"]. Does not register a keybind. */
  shortcut?: string[];
  /** Invoked when the user activates the command. */
  handler: (ctx: CommandContext) => void | Promise<void>;
  /** Optional guard — when it returns false the command is hidden. */
  when?: () => boolean;
}
