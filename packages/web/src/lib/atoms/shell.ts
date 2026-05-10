import { atom } from 'jotai';

export type ShellTab = 'workspace' | 'kanban';

export const shellTabAtom = atom<ShellTab>('workspace');

export const sidebarCollapsedAtom = atom(false);

export const spotlightOpenAtom = atom(false);

export type ShellPopover =
  | null
  | 'agents'
  | 'activity'
  | 'filter'
  | 'more'
  | 'advance'
  | 'agent-cli'
  | 'project-switcher';

/** Controls the Create Project dialog opened from the project-switcher popover. */
export const createProjectDialogOpenAtom = atom(false);

/** Controls the Add Repository dialog opened from the project-switcher popover. */
export const addRepoDialogOpenAtom = atom(false);

export interface PopoverAnchor {
  /** Horizontal anchor — `align: 'left'` uses this as `left`, `'right'` as `right` distance from viewport edge. */
  x: number;
  /** Preferred top — used when there is room below the trigger. */
  y: number;
  align: 'left' | 'right';
  /**
   * Optional fallback used when the panel does not fit below the trigger:
   * the panel pins its bottom edge to this value (so it opens upward).
   */
  triggerTop?: number;
}

interface ShellPopoverState {
  kind: ShellPopover;
  anchor: PopoverAnchor | null;
}

export const shellPopoverAtom = atom<ShellPopoverState>({ kind: null, anchor: null });

/**
 * Task id the `more` / `advance` popovers are bound to.
 *
 * Set by triggers (workspace head, task card) before opening the popover so
 * the shell-mounted popover instance can resolve task data from `tasksAtom`
 * without prop-drilling.
 */
export const popoverTaskIdAtom = atom<string | null>(null);

export const newSessionModalOpenAtom = atom(false);

export type BoardViewMode = 'board' | 'list';
/** Persists the Kanban view toggle (Board / List) across re-renders. */
export const boardViewModeAtom = atom<BoardViewMode>('board');

/**
 * Active Agent CLI — the local CLI program (claude-code, codex, gemini-cli,
 * goose, opencode, copilot, …) that drives the agent loop.
 *
 * `null` falls back to the server's default backend. The label "Agent CLI"
 * (not "Model") is canonical: in Kagan we pick the CLI program, not the LLM.
 */
export const currentAgentCliAtom = atom<string | null>(null);
