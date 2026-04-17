import { atom } from 'jotai';

/**
 * Open state for the new command-palette spine (Cmd+K).
 *
 * Intentionally separate from `commandPaletteOpenAtom` in `lib/atoms/ui` —
 * that atom still drives the legacy quick-actions dialog (Cmd+Shift+P).
 * During the migration window (see PR #115) both surfaces coexist; a
 * follow-up PR will consolidate them.
 */
export const commandPaletteSpineOpenAtom = atom(false);
