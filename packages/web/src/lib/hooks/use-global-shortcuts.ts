import { useEffect } from 'react';
import { useSetAtom } from 'jotai';
import { commandPaletteOpenAtom } from '@/lib/atoms/ui';

/**
 * Wires every global shortcut that the command-palette spine owns. Currently
 * that's just Cmd/Ctrl+K (open or toggle the palette).
 *
 * Design notes:
 *   - We listen on `document` in the capture phase so the palette can open
 *     even when focus is inside an editor. Cmd/Ctrl is a modifier — users
 *     who hit it explicitly while typing mean to invoke the palette.
 *   - Plain `k` (no modifier) inside an editable target falls through to
 *     the underlying control. No interception.
 *   - preventDefault so browsers don't steal Cmd+K for their own actions
 *     (Firefox quick-find, Safari web search, etc.).
 *
 * Keep this small. Additional global shortcuts live beside this one, not
 * scattered across feature components.
 */
export function useGlobalShortcuts(): void {
  const setOpen = useSetAtom(commandPaletteOpenAtom);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const hasModifier = event.metaKey || event.ctrlKey;
      if (!hasModifier) return;
      if (event.shiftKey || event.altKey) return;

      const key = event.key.toLowerCase();
      if (key !== 'k') return;

      event.preventDefault();
      event.stopPropagation();
      setOpen((prev) => !prev);
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [setOpen]);
}
