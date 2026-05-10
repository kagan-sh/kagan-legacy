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
  | 'permissions'
  | 'model'
  | 'locality'
  | 'branch'
  | 'access';

export interface PopoverAnchor {
  x: number;
  y: number;
  align: 'left' | 'right';
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

/** Composer context chips — shared between chat-input-bar and future popovers. */
export type ComposerAccess = 'full' | 'workspace' | 'readonly';
export type ComposerLocality = 'local' | 'remote';

export const composerAccessAtom = atom<ComposerAccess>('full');
export const composerLocalityAtom = atom<ComposerLocality>('local');
export const currentModelAtom = atom<string | null>(null);

/**
 * Branch selected by the user in the branch popover.
 * null means "use the active task's base_branch or fall back to 'main'".
 */
export const composerBranchAtom = atom<string | null>(null);
