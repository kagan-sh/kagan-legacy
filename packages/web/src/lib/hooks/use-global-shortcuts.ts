import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useSetAtom } from 'jotai';
import {
  commandPaletteOpenAtom,
  helpOverlayOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { hasOpenOverlay, isEditableTarget } from '@/lib/utils/dom';
import { useSessionOverlay } from '@/lib/hooks/use-session-overlay';

function isPeriodKey(event: KeyboardEvent): boolean {
  return event.key === '.' || event.code === 'Period' || event.code === 'NumpadDecimal';
}

/**
 * Wires application-level shortcuts for command/search overlays, session overlay,
 * help, session switching, and workspace navigation.
 *
 * Design notes:
 *   - We listen on `document` in the capture phase so global actions can run
 *     even when focus is inside an editor. Cmd/Ctrl is a modifier — users
 *     who hit it explicitly while typing mean to invoke an app command.
 *   - Plain `k` (no modifier) inside an editable target falls through to
 *     the underlying control. No interception.
 *   - preventDefault so browsers don't steal the shortcut for their own actions
 *     (Firefox quick-find, Safari web search, etc.).
 *
 * Keep global shortcut ownership here so feature components expose actions
 * through atoms and callbacks instead of each attaching document listeners.
 */
export function useGlobalShortcuts(): void {
  const location = useLocation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const setCommandOpen = useSetAtom(commandPaletteOpenAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const overlay = useSessionOverlay();

  const workspaceRoute = location.pathname.startsWith('/workspace');
  const welcomeRoute = location.pathname.startsWith('/welcome');

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const hasModifier = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();

      if (hasModifier && event.shiftKey && !event.altKey && key === 'p') {
        event.preventDefault();
        event.stopPropagation();
        setSessionPickerOpen(false);
        setHelpOverlayOpen(false);
        setCommandOpen(true);
        return;
      }

      if (!welcomeRoute && hasModifier && !event.shiftKey && !event.altKey && key === 'k') {
        event.preventDefault();
        event.stopPropagation();
        setCommandOpen(false);
        setHelpOverlayOpen(false);
        setSessionPickerOpen(true);
        return;
      }

      if (
        !welcomeRoute &&
        hasModifier &&
        !event.shiftKey &&
        !event.altKey &&
        isPeriodKey(event)
      ) {
        event.preventDefault();
        event.stopPropagation();
        if (workspaceRoute) return;
        overlay.toggle();
        return;
      }

      if (
        !welcomeRoute &&
        hasModifier &&
        event.shiftKey &&
        !event.altKey &&
        key === 'f'
      ) {
        event.preventDefault();
        event.stopPropagation();
        if (overlay.isOpen && overlay.layout === 'fullscreen') {
          overlay.setLayout('docked');
        } else if (overlay.isOpen) {
          overlay.setLayout('fullscreen');
        } else {
          overlay.toggle();
          overlay.setLayout('fullscreen');
        }
        return;
      }

      if (
        !welcomeRoute &&
        hasModifier &&
        event.shiftKey &&
        !event.altKey &&
        key === 'k'
      ) {
        event.preventDefault();
        event.stopPropagation();
        setCommandOpen(false);
        setHelpOverlayOpen(false);
        setSessionPickerOpen(true);
        return;
      }

      if (
        !welcomeRoute &&
        !isEditableTarget(event.target) &&
        (event.key === '?' || event.key === 'F1')
      ) {
        event.preventDefault();
        event.stopPropagation();
        setCommandOpen(false);
        setSessionPickerOpen(false);
        setHelpOverlayOpen(true);
        return;
      }

      if (isMobile || hasOpenOverlay()) return;

      if (
        !welcomeRoute &&
        hasModifier &&
        event.shiftKey &&
        !event.altKey &&
        key === 'w'
      ) {
        event.preventDefault();
        event.stopPropagation();
        navigate(workspaceRoute ? '/board' : '/workspace');
      }
    }

    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
    };
  }, [
    isMobile,
    navigate,
    overlay,
    setCommandOpen,
    setHelpOverlayOpen,
    setSessionPickerOpen,
    welcomeRoute,
    workspaceRoute,
  ]);
}
