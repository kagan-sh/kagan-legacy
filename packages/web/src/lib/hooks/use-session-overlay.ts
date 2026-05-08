/**
 * useSessionOverlay — manages open/close/layout of the unified session overlay.
 *
 * Bridges the new overlay atoms (selectedSessionAtom, sessionOverlayOpenAtom,
 * sessionOverlayLayoutAtom) with a single ergonomic hook for components.
 */

import { useCallback } from 'react';
import { useAtom } from 'jotai';
import {
  selectedSessionAtom,
  sessionOverlayOpenAtom,
  sessionOverlayLayoutAtom,
} from '@/lib/atoms/ui';
import type { SessionItemResponse } from '@kagan/shared-api-client';

export interface UseSessionOverlayResult {
  /** Currently selected session (null when none). */
  selectedSession: SessionItemResponse | null;
  /** Whether the overlay is open. */
  isOpen: boolean;
  /** Current layout mode. */
  layout: 'docked' | 'fullscreen';
  /** Open the overlay for a specific session (optionally setting layout). */
  open: (session: SessionItemResponse, layout?: 'docked' | 'fullscreen') => void;
  /** Close the overlay (keeps selected session in state). */
  close: () => void;
  /** Toggle overlay visibility. */
  toggle: () => void;
  /** Change layout without closing. */
  setLayout: (layout: 'docked' | 'fullscreen') => void;
  /** Select a different session without changing open state. */
  selectSession: (session: SessionItemResponse | null) => void;
}

export function useSessionOverlay(): UseSessionOverlayResult {
  const [selectedSession, setSelectedSession] = useAtom(selectedSessionAtom);
  const [isOpen, setIsOpen] = useAtom(sessionOverlayOpenAtom);
  const [layout, setLayout] = useAtom(sessionOverlayLayoutAtom);

  const open = useCallback(
    (session: SessionItemResponse, nextLayout?: 'docked' | 'fullscreen') => {
      setSelectedSession(session);
      setIsOpen(true);
      if (nextLayout) setLayout(nextLayout);
    },
    [setSelectedSession, setIsOpen, setLayout],
  );

  const close = useCallback(() => {
    setIsOpen(false);
  }, [setIsOpen]);

  const toggle = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, [setIsOpen]);

  const selectSession = useCallback(
    (session: SessionItemResponse | null) => {
      setSelectedSession(session);
    },
    [setSelectedSession],
  );

  return {
    selectedSession,
    isOpen,
    layout,
    open,
    close,
    toggle,
    setLayout,
    selectSession,
  };
}
