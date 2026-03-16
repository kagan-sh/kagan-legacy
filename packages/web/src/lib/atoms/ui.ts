import { atom } from 'jotai';

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

/** Command palette open state. */
export const commandPaletteOpenAtom = atom(false);

/** Session picker overlay open state. */
export const sessionPickerOpenAtom = atom(false);

export const helpOverlayOpenAtom = atom(false);

/** Plugin import dialog open state. */
export const pluginImportOpenAtom = atom(false);
/** Track whether any dialog/modal is open to pause background refetches. */
export const dialogOpenCountAtom = atom(0);

export const isAnyDialogOpenAtom = atom((get) => get(dialogOpenCountAtom) > 0);
