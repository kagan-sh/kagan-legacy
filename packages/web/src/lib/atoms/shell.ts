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

export const newSessionModalOpenAtom = atom(false);
