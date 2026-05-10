import { atom } from 'jotai';
import { boardDialogAtom } from '@/lib/atoms/board';
import type { SessionItemResponse } from '@kagan/shared-api-client';

/** Session picker overlay open state. */
export const sessionPickerOpenAtom = atom(false);

export const helpOverlayOpenAtom = atom(false);

/** Quick Actions command palette open state. */
export const commandPaletteOpenAtom = atom(false);

/** Integration import dialog open state. */
export const integrationImportOpenAtom = atom(false);

// ---------------------------------------------------------------------------
// Unified session overlay state
// ---------------------------------------------------------------------------

/** The session currently shown in the unified overlay. */
export const selectedSessionAtom = atom<SessionItemResponse | null>(null);

/** Whether the session overlay is visible. */
export const sessionOverlayOpenAtom = atom<boolean>(false);

/** Layout mode of the session overlay. */
export const sessionOverlayLayoutAtom = atom<'docked' | 'fullscreen'>('docked');

/** Derived atom: true if any modal dialog or session overlay should pause background work. */
export const isAnyDialogOpenAtom = atom((get) => {
  return (
    get(sessionPickerOpenAtom) ||
    get(helpOverlayOpenAtom) ||
    get(integrationImportOpenAtom) ||
    get(commandPaletteOpenAtom) ||
    get(sessionOverlayOpenAtom) ||
    get(boardDialogAtom).kind !== 'none'
  );
});
