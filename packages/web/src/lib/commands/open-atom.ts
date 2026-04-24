import { atom } from 'jotai';

/**
 * Open state for the command palette (Cmd+K).
 * Toggled by `useGlobalShortcuts` and the header search button.
 */
export const commandPaletteSpineOpenAtom = atom(false);
