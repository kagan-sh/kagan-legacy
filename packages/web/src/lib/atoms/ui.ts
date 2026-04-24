import { atom } from 'jotai';
import { boardDialogAtom } from '@/lib/atoms/board';

/**
 * Right-rail panel mode.
 * - 'none': panel hidden
 * - 'chat-right': task chat docked to the right rail
 * - 'chat-bottom': task chat docked beneath the current workspace
 * - 'chat-fullscreen': task chat expanded into a fullscreen overlay
 */
export type RightRailMode = 'none' | 'chat-right' | 'chat-bottom' | 'chat-fullscreen';

export const rightRailModeAtom = atom<RightRailMode>('none');

/** Task ID for the right-rail chat panel. */
export const rightRailTaskIdAtom = atom<string | null>(null);

export const rightRailChatSessionIdAtom = atom<string | null>(null);

/** Session picker overlay open state. */
export const sessionPickerOpenAtom = atom(false);

export const helpOverlayOpenAtom = atom(false);

/** Plugin import dialog open state. */
export const pluginImportOpenAtom = atom(false);

/** Currently selected orchestrator session in workspace view. */
export const workspaceSessionIdAtom = atom<string | null>(null);

/** Derived atom: true if any dialog/overlay is open. */
export const isAnyDialogOpenAtom = atom((get) => {
  return (
    get(sessionPickerOpenAtom) ||
    get(helpOverlayOpenAtom) ||
    get(pluginImportOpenAtom) ||
    get(boardDialogAtom).kind !== 'none'
  );
});
