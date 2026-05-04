import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useAtomValue, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { WireChatSessionSummary } from '@kagan/shared-api-client';
import {
  clearRightRailDismissalAtom,
  commandPaletteOpenAtom,
  dismissRightRailContextAtom,
  helpOverlayOpenAtom,
  rightRailChatSessionIdAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  sessionPickerOpenAtom,
  type RightRailMode,
} from '@/lib/atoms/ui';
import { useIsMobile } from '@/lib/hooks/use-mobile';
import { hasOpenOverlay, isEditableTarget } from '@/lib/utils/dom';

type DockedChatRailMode = Extract<RightRailMode, 'chat-right' | 'chat-bottom'>;

function cycleDockMode(mode: DockedChatRailMode): DockedChatRailMode | 'none' {
  if (mode === 'chat-right') return 'chat-bottom';
  return 'none';
}

/**
 * Wires application-level shortcuts for command/search overlays, chat rail
 * docking, help, session switching, and workspace navigation.
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
 * Keep global shortcut ownership here so feature components expose actions
 * through atoms and callbacks instead of each attaching document listeners.
 */
export function useGlobalShortcuts(): void {
  const location = useLocation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const railMode = useAtomValue(rightRailModeAtom);
  const railTaskId = useAtomValue(rightRailTaskIdAtom);
  const railChatSessionId = useAtomValue(rightRailChatSessionIdAtom);
  const setCommandOpen = useSetAtom(commandPaletteOpenAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const setRailMode = useSetAtom(rightRailModeAtom);
  const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
  const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
  const dismissRightRailContext = useSetAtom(dismissRightRailContextAtom);
  const clearRightRailDismissal = useSetAtom(clearRightRailDismissalAtom);
  const lastDockModeRef = useRef<DockedChatRailMode>('chat-right');

  const currentTaskId = useMemo(() => {
    const taskMatch = /^\/task\/([^/?]+)/.exec(location.pathname);
    if (taskMatch) return taskMatch[1];
    const sessionMatch = /^\/session\/([^/?]+)/.exec(location.pathname);
    if (sessionMatch) return sessionMatch[1];
    return null;
  }, [location.pathname]);
  const workspaceRoute = location.pathname.startsWith('/workspace');
  const welcomeRoute = location.pathname.startsWith('/welcome');

  const closeChatRail = useCallback(() => {
    dismissRightRailContext();
    setRailMode('none');
  }, [dismissRightRailContext, setRailMode]);

  const openChatRail = useCallback(
    (mode: DockedChatRailMode = 'chat-right') => {
      const nextTaskId = currentTaskId ?? railTaskId;
      if (!nextTaskId) return false;
      clearRightRailDismissal({ kind: 'task', id: nextTaskId });
      setRailTaskId(nextTaskId);
      setRailChatSessionId(null);
      setRailMode(mode);
      return true;
    },
    [
      clearRightRailDismissal,
      currentTaskId,
      railTaskId,
      setRailChatSessionId,
      setRailMode,
      setRailTaskId,
    ],
  );

  const setChatRailLayout = useCallback(
    (mode: Extract<RightRailMode, 'chat-right' | 'chat-bottom' | 'chat-fullscreen'>) => {
      if (mode === 'chat-right' || mode === 'chat-bottom') {
        lastDockModeRef.current = mode;
      }
      setRailMode(mode);
    },
    [setRailMode],
  );

  const createOrGetSession = useCallback(async (sessions: WireChatSessionSummary[]): Promise<string | null> => {
    try {
      const orchestratorSessions = sessions
        .filter((s) => ['orchestrator', 'web'].includes(s.source.toLowerCase()))
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

      const sessionId =
        orchestratorSessions.length > 0
          ? orchestratorSessions[0]!.id
          : (await apiClient.createChatSession({})).id;

      return sessionId;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create session';
      toast.error(message);
      return null;
    }
  }, []);

  useEffect(() => {
    if (railMode === 'chat-right' || railMode === 'chat-bottom') {
      lastDockModeRef.current = railMode;
    }
  }, [railMode]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const hasModifier = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      const railOpen = railMode !== 'none' && Boolean(railTaskId || railChatSessionId);

      if (hasModifier && event.shiftKey && !event.altKey && key === 'p') {
        event.preventDefault();
        event.stopPropagation();
        setSessionPickerOpen(false);
        setHelpOverlayOpen(false);
        setCommandOpen(true);
        return;
      }

      if (hasModifier && !event.shiftKey && !event.altKey && key === 'k') {
        event.preventDefault();
        event.stopPropagation();
        setCommandOpen((prev) => !prev);
        return;
      }

      if (
        !welcomeRoute &&
        hasModifier &&
        !event.shiftKey &&
        !event.altKey &&
        key === 'i'
      ) {
        event.preventDefault();
        event.stopPropagation();
        if (workspaceRoute) return;
        const hasTask = Boolean(currentTaskId ?? railTaskId);
        if (railOpen && (railMode === 'chat-right' || railMode === 'chat-bottom')) {
          const next = cycleDockMode(railMode);
          if (next === 'none') {
            closeChatRail();
          } else {
            setChatRailLayout(next);
          }
        } else if (railOpen) {
          closeChatRail();
        } else if (hasTask) {
          openChatRail('chat-right');
        } else {
          void (async () => {
            try {
              const sessions = await apiClient.getChatSessions();
              const sessionId = await createOrGetSession(sessions);
              if (sessionId) {
                clearRightRailDismissal({ kind: 'session', id: sessionId });
                setRailTaskId(null);
                setRailChatSessionId(sessionId);
                setRailMode('chat-right');
              }
            } catch {
              setSessionPickerOpen(true);
            }
          })();
        }
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
        if (railOpen && railMode === 'chat-fullscreen') {
          setChatRailLayout(lastDockModeRef.current);
        } else if (railOpen) {
          setChatRailLayout('chat-fullscreen');
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
    clearRightRailDismissal,
    closeChatRail,
    createOrGetSession,
    currentTaskId,
    isMobile,
    navigate,
    openChatRail,
    railChatSessionId,
    railMode,
    railTaskId,
    setChatRailLayout,
    setCommandOpen,
    setHelpOverlayOpen,
    setRailChatSessionId,
    setRailMode,
    setRailTaskId,
    setSessionPickerOpen,
    welcomeRoute,
    workspaceRoute,
  ]);
}
