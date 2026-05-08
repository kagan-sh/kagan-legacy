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

/** Currently selected orchestrator session in workspace view. */
export const workspaceSessionIdAtom = atom<string | null>(null);

// ---------------------------------------------------------------------------
// Unified session overlay state (Agent D — replaces right-rail in Wave 4)
// ---------------------------------------------------------------------------

/** The session currently shown in the unified overlay. */
export const selectedSessionAtom = atom<SessionItemResponse | null>(null);

/** Whether the session overlay is visible. */
export const sessionOverlayOpenAtom = atom<boolean>(false);

/** Layout mode of the session overlay. */
export const sessionOverlayLayoutAtom = atom<'docked' | 'fullscreen'>('docked');

/** Derived atom: capabilities of the currently selected session (null if none). */
export const selectedSessionCapabilitiesAtom = atom((get) => {
  return get(selectedSessionAtom)?.capabilities ?? null;
});

/** Derived atom: true if any dialog/overlay is open. */
export const isAnyDialogOpenAtom = atom((get) => {
  return (
    get(sessionPickerOpenAtom) ||
    get(helpOverlayOpenAtom) ||
    get(integrationImportOpenAtom) ||
    get(commandPaletteOpenAtom) ||
    get(boardDialogAtom).kind !== 'none'
  );
});
