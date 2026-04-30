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

export type RightRailDismissalContext = { kind: 'task' | 'session'; id: string };

export function rightRailDismissalKey(context: RightRailDismissalContext): string {
  return `${context.kind}:${context.id}`;
}

export const rightRailDismissalsAtom = atom<Record<string, true>>({});

export const dismissRightRailContextAtom = atom(
  null,
  (get, set, context?: RightRailDismissalContext | null) => {
    const target =
      context ??
      (get(rightRailTaskIdAtom)
        ? ({ kind: 'task', id: get(rightRailTaskIdAtom)! } satisfies RightRailDismissalContext)
        : get(rightRailChatSessionIdAtom)
          ? ({ kind: 'session', id: get(rightRailChatSessionIdAtom)! } satisfies RightRailDismissalContext)
          : null);
    if (!target) return;
    const key = rightRailDismissalKey(target);
    set(rightRailDismissalsAtom, (prev) => ({ ...prev, [key]: true }));
  },
);

export const clearRightRailDismissalAtom = atom(
  null,
  (_get, set, context: RightRailDismissalContext) => {
    const key = rightRailDismissalKey(context);
    set(rightRailDismissalsAtom, (prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  },
);

/** Session picker overlay open state. */
export const sessionPickerOpenAtom = atom(false);

export const helpOverlayOpenAtom = atom(false);

/** Command palette (Cmd+K) open state. */
export const commandPaletteOpenAtom = atom(false);

/** Integration import dialog open state. */
export const integrationImportOpenAtom = atom(false);

/** Currently selected orchestrator session in workspace view. */
export const workspaceSessionIdAtom = atom<string | null>(null);

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
